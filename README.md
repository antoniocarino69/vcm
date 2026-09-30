# VCM — Vulnerability & Compliance Management

Piattaforma web modulare, multi-tenant e self-hosted di gestione vulnerabilità e
conformità (STIG/SCAP) per infrastruttura sistemistica e Active Directory.

Ispirazioni architetturali:
- **DefectDojo** (`dojo/tools/`): la logica di estrazione dei parser Qualys/Nessus,
  ma senza la gerarchia Engagement/Test — qui il modello è lineare e **asset-centric**.
- **Faraday Security**: interfaccia operativa snella orientata alla visibilità
  immediata degli host e dei workspace/ambienti.

Parser supportati: **Qualys VMDR** (XML SCAN / ASSET_DATA_REPORT), **Tenable
Nessus** (`.nessus` XML + CSV), **DISA SCC** (XCCDF results / ARF), **PingCastle**
(XML + HTML), **Purple Knight** (CSV + HTML).

Autenticazione: **non implementata** (fase 1, come richiesto). Il binding per la
futura SSO/RBAC è già modellato in `memberships` (ruoli admin/analyst/viewer).

---

## 1. Architettura dei container

```
                    ┌──────────────────────────────────────────────┐
                    │  docker-compose.yml                          │
                    │                                              │
 browser ──────────►│  frontend (nginx:8080→80)                    │
                    │    ├─ SPA statica (frontend/index.html)      │
                    │    └─ proxy /api/* ─────────────┐            │
                    │                                 ▼            │
                    │                        api (FastAPI:8000)    │
                    │                          │ upload report     │
                    │                          ▼                   │
                    │                    redis (broker Celery)     │
                    │                          │ task parse_import │
                    │                          ▼                   │
                    │              worker (Celery, parsing XML)    │
                    │                          │                   │
                    │                          ▼                   │
                    │              postgres:16 (JSONB, inet, enum) │
                    └──────────────────────────────────────────────┘
```

| Servizio  | Immagine             | Ruolo                                                        |
|-----------|----------------------|--------------------------------------------------------------|
| frontend  | nginx:1.27-alpine    | SPA + reverse proxy `/api` (body fino a 2 GB)                |
| api       | python:3.12-slim     | FastAPI: CRUD, upload, dashboard, report                     |
| worker    | python:3.12-slim     | Celery: parsing asincrono in streaming dei report giganti    |
| postgres  | postgres:16-alpine   | Dati (JSONB per payload grezzi, `inet` per IP, enum nativi)  |
| redis     | redis:7-alpine       | Broker/result backend Celery                                 |

Volumi: `pgdata` (database), `uploads` (file scanner originali), `reports`.
Upload dei report in `POST /api/environments/{id}/imports`: il file viene su
disco, il record `scan_imports` nasce `pending`, e il worker Celery esegue il
parsing senza bloccare l'API (`task_acks_late`, `prefetch=1`: un file gigante
per worker alla volta).

## 2. Modello dati (db/schema.sql)

Multi-tenant gerarchico con modello lineare asset-centric:

```
tenants (Clienti)
 └── environments (Ambienti: Produzione, DMZ, Active Directory, ...; tag JSONB;
     match_key = ip | fqdn | netbios per la riconciliazione asset)
      └── assets (host: ip inet, fqdn, netbios, os, tag JSONB, criticality)
           └── findings (vulnerabilità + compliance in tabella unica,
                kind = vulnerability | compliance)
```

Tabelle chiave:
- **tenants / environments** — isolamento per cliente; `environments.tags`
  (JSONB + GIN) per tag arbitrari (`tier:critical`, `location:milano`...);
  `match_key` definisce la chiave di matching degli asset.
- **assets / asset_moves** — gli asset possono essere spostati tra ambienti:
  `asset_moves` registra ogni transizione e lo storico è preservato perché
  `findings` e `scan_imports` conservano l'`environment_id` dello *snapshot*
  all'epoca dell'importazione (commenti e scansioni restano coerenti).
- **scan_imports** — ogni upload: scanner, sha256 (anti-duplicato per tenant),
  flag `auto_close`, statistiche JSONB dell'ingest, stato del task.
- **findings** — tabella unica per vulnerabilità e compliance:
  `rule_id` (QID / PluginID / Rule idref / RiskId / Indicator), `severity`
  normalizzata + `severity_raw` originale, `stig_category` (CAT I/II/III),
  CVE (`text[]`), CVSS, porta/protocollo, `benchmark`/`profile`/`result`
  (SCC), `affected_objects` (PingCastle/Purple Knight), `scanner_output`,
  `raw` JSONB con il payload grezzo dello scanner.
  Lifecycle: `status` (active | mitigated | false_positive | risk_accepted),
  `first_seen`/`last_seen`/`occurrence_count`, `closed_at`/`closed_by_import_id`,
  `risk_accepted_until` + nota obbligatoria. Vincoli CHECK per coerenza
  (compliance ⇒ `result` NOT NULL; risk accepted ⇒ nota; aperto ⇒ `closed_at` NULL).
  **Deduplica**: indice unico `(environment_id, dedup_hash)`.
- **finding_status_history / finding_comments** — audit delle transizioni di
  stato e commenti per-host (preservati sugli spostamenti).
- **ad_health_snapshots** — storico AD Health Score (global score PingCastle /
  punteggio postura Purple Knight + score per categoria) per le gauge.
- **report_jobs / memberships** — coda report e RBAC tenant-scoped (admin,
  analyst, viewer) con `external_subject` pronto per la SSO futura.

Viste analitiche: `v_open_findings`, `v_severity_distribution`,
`v_top_vulnerable_hosts`, `v_top_widespread_rules`, `v_daily_lifecycle`.

## 3. Parser: contratto e streaming

`app/parsers/base.py` definisce `BaseParser` con contratto minimo:

- `sniff(head)` — riconosce il formato dai primi 8 KB (il dispatch non dipende
  dall'estensione: `scanner=auto` nelle importazioni);
- `parse(path)` — **generatore** di `ParsedHost` a memoria costante: i parser
  usano `ElementTree.iterparse` su eventi `end` e fanno `clear()` dei nodi già
  emessi, quindi file XML da centinaia di MB girano in pochi MB di RAM;
- l'output è `NormalizedFinding` (vulnerabilità o voce di compliance).

### Qualys VMDR (`qualys.py`)

Gestisce entrambi gli export XML:
- **SCAN**: `HOST → SERVICES → SERVICE → VULNS → VULN` (QID, SEVERITY 1-5,
  VULN_TITLE, CVE_ID_LIST, CVSS3_BASE, DIAGNOSIS, SOLUTION, RESULTS, porta e
  protocollo dal SERVICE);
- **ASSET_DATA_REPORT**: `HOST → VULN_INFO_LIST → VULN_INFO` (QID, TYPE,
  SEVERITY, PORT, PROTOCOL, VULN con dettagli).

Pipeline asincrona: `POST .../imports` → record `scan_imports` → task Celery
`vcm.parse_import` → `QualysParser.parse()` (streaming) → `ingest_stream()`
con scrittura a DB in batch (`INGEST_BATCH_SIZE`, default 500 host per flush).

### Gli altri parser

- **Nessus**: `.nessus` XML (un `ReportHost` bufferizzato alla volta) e CSV
  (Plugin ID, Risk Factor, CVE, CVSS, Plugin Output, Remediation).
- **SCC/XCCDF + ARF**: `rule-result` → Rule ID (`SV-xxxxx`), severity XCCDF →
  CAT I/II/III, result → pass/fail/not_reviewed/not_applicable/error,
  benchmark + profile, CCI ident, finding details.
- **PingCastle**: risk rules XML/HTML con categoria (Privileged Accounts,
  Trust, Domain Trust, Anomalies, Delegation...), risk score, technical
  details, remediation; `GlobalScore` → `ad_health_snapshots`.
- **Purple Knight**: CSV/HTML indicatori IOE/IOC con categoria (Account
  Hygiene, Infrastructure, Kerberos, AD Delegation), severity, score e lista
  `affected_objects`.

## 4. Deduplica e lifecycle (`app/services/ingest.py`)

- **Hash identificativo**: `sha256(asset_id | scanner:rule_id | port)` —
  la spec prevede `asset + rule_id + port`; il prefisso `scanner:` qualifica il
  namespace del rule_id (QID Qualys vs PluginID Nessus) per evitare collisioni
  cross-scanner. Vincolo unico su `(environment_id, dedup_hash)`.
- **Rilevazione ripetuta**: nessun duplicato — si aggiornano `last_seen`,
  `occurrence_count++`, i campi descrittivi più ricchi e i CVE (merge).
- **Auto-closing** (flag per singola importazione): i finding aperti *dello
  stesso scanner* su *quel specifico asset* non presenti nel nuovo report
  vengono chiusi come `Mitigated` con `closed_by_import_id` e nota. Un host
  assente dal report non viene toccato.
- **Riapertura**: un finding mitigato che ricompare torna `Active` con
  transizione registrata nello storico.
- **Stati manuali**: `False Positive`, `Risk Accepted` (data scadenza + nota
  obbligatoria), `Mitigated` manuale — ogni transizione in
  `finding_status_history`.

## 5. Dashboard e report

- `GET /api/dashboard` — overview cliente cross-ambiente: totali, distribuzione
  severità, distribuzione CAT I/II/III, trend aperti/chiusi, Top 10 regole più
  diffuse, Top 10 host più vulnerabili, gauge AD Health Score, punteggio di
  postura 0-100.
- `GET /api/reports/executive?tenant_id=...` — Executive Report HTML/PDF:
  solo sintesi, postura, distribuzione rischio, progressi di remediation.
- `GET /api/reports/technical?tenant_id=...` — Technical Report HTML/PDF/CSV:
  dettaglio per host con CVE, regola STIG, output scanner e remediation.

## 6. Avvio

```bash
docker compose up -d --build          # stack completo su :8080
# sviluppo locale (porte DB su loopback):
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

Test (parser + motore di ingest, nessun DB richiesto):

```bash
uv venv .venv && uv pip install --python .venv/bin/python pytest
.venv/bin/python -m pytest backend/tests -q
```

Configurazione via env: `DATABASE_URL`, `REDIS_URL`, `STORAGE_DIR`,
`INGEST_BATCH_SIZE`, `MAX_UPLOAD_MB`, `DEFAULT_MATCH_KEY`, `HTTP_PORT`.

## 7. Roadmap

1. Autenticazione/RBAC effettivo (SSO/OIDC mappato su `memberships`).
2. Upload multi-file e API di ingest da collector (Qualys API pull).
3. Report PDF server-side (WeasyPrint già cablato, opzionale).
4. Notifiche/regole (SLA remediation, scadenza risk acceptance).
5. Materializzazione delle viste trend per istanze con milioni di finding.
