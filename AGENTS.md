# AGENTS.md — guida per qualsiasi agente/assistente che lavora su questo repo

Questo file è la fonte di verità per chiunque (agente AI di qualsiasi marca,
script, o sviluppatore umano) intervenga su VCM. Leggi questo file PRIMA di
toccare codice. In caso di conflitto con altri documenti, vince questo; se
invece è questo a essere in conflitto con il codice reale, aprine una issue.

---

## 1. Cos'è VCM

**Vulnerability & Compliance Management** self-hosted, multi-tenant, per
infrastruttura sistemistica, Active Directory e conformità STIG/SCAP.

- Dominio: vulnerabilità (Qualys VMDR, Tenable Nessus) e compliance
  (DISA SCC/XCCDF, PingCastle, Purple Knight).
- Utente di riferimento: team sistemistico/AD, non il mondo web in generale.
- Modello: **asset-centric lineare** (ispirazione DefectDojo per i parser,
  Faraday per la UX operativa). Niente gerarchie Engagement/Test.
- Stato attuale: **PoC funzionante e verificato end-to-end**. Auth/RBAC NON
  implementati deliberatamente (tabella `memberships` già pronta per la SSO).

## 2. Pietre miliari architetturali (non negoziabiali)

Questi sono i pilastri del progetto. Una modifica che li infrange è sbagliata
anche se "funziona".

1. **Multi-tenant rigoroso**: ogni record figlio porta `tenant_id`; nessuna
   query può mescolare clienti. Gerarchia: tenants → environments → assets →
   findings. Filtri sempre espliciti negli endpoint.
2. **Asset-centric, non scan-centric**: i finding appartengono agli asset; gli
   spostamenti tra ambienti (`asset_moves`) non devono MAI perdere storico
   scansioni/commenti (findings e scan_imports conservano l'`environment_id`
   dello snapshot).
3. **Parser puri e streaming**: `app/parsers/` non accede a DB né rete. Ogni
   parser è un *generatore* (`iterparse` + `clear()`) con memoria costante —
   i file scanner arrivano a centinaia di MB. Stdlib only dentro i parser
   (deploy air-gapped). Il contratto è `BaseParser` in `parsers/base.py`:
   `sniff(head)` + `parse(path) -> Iterator[ParsedHost]`.
4. **Normalizzazione unica**: ogni scanner produce `NormalizedFinding`
   (vulnerabilità O compliance). Severity normalizzata a
   critical/high/medium/low/info + `severity_raw` originale mai perso.
   STIG → CAT I/II/III. Payload grezzo sempre preservato in `raw` (JSONB).
5. **Deduplica e lifecycle deterministici** (`app/services/ingest.py`, codice
   puro e testato senza DB): hash `sha256(asset|scanner:rule_id|port)`, unico
   per ambiente; rilevazioni ripetute = update (last_seen, occurrence_count),
   mai duplicati; auto-close per (asset, scanner) solo su flag dell'import;
   riapertura automatica dei mitigati che ricompongono; ogni transizione di
   stato è tracciata in `finding_status_history`.
6. **Parsing asincrono**: upload → `scan_imports` (202) → task Celery
   `vcm.parse_import` → ingest a batch. L'API non deve mai bloccare su un XML
   gigante.
7. **PostgreSQL come si deve**: enum nativi creati da `db/schema.sql` (che è
   la fonte di verità del DB, i modelli SQLAlchemy devono restare 1:1 con
   quello), JSONB per payload grezzi e tag (indice GIN), `inet` per gli IP,
   vincoli CHECK per la coerenza dei finding (compliance ⇒ `result`,
   risk accepted ⇒ nota, aperto ⇒ `closed_at` NULL).
8. **Niente auth improvvisata**: finché non la decidiamo esplicitamente, NON
   introdurre middleware di autenticazione fai-da-te o credenziali hardcodate.
   L'aggancio futuro è `memberships.external_subject` + ruoli
   admin/analyst/viewer.

## 3. Pietre miliari di prodotto (roadmap concordata)

Completate:
- M0 PoC: schema, 5 parser, ingest con dedup/auto-close, API, worker,
  dashboard, report Executive/Technical (HTML/PDF/CSV), stack docker, repo.

Da fare, in quest'ordine:
- M1: autenticazione/RBAC effettivo (SSO/OIDC → `memberships`).
- M2: ingest programmatico (pull API Qualys, upload multi-file, collector).
- M3: notifiche e SLA (scadenza risk acceptance, alert su trend critico).
- M4: performance su grandi istanze (viste trend materializzate, indici mirati).

Apri una issue per ogni milestone prima di iniziarla; i passi avanti si
mergiano in piccoli incrementi, non in un "M3 completo" monolitico.

### Current product direction (2026-09-30)

The user explicitly deferred authentication. Complete the operational portal
increments in `docs/portal-next-steps.md` before starting SSO/RBAC; do not treat
the older M1 ordering as authorization to introduce authentication now.
That document is the active, checkable plan for sidebar navigation, scoped
asset/finding views, optional scan dates/tags, OS/tag filters, VA campaigns and
remediation campaigns. Check items only after real verification and publication.
An individual vulnerability decision applies to one asset-associated finding,
never globally to a CVE/rule across all servers. Campaigns remain optional
associations and must not introduce a mandatory Engagement/Test hierarchy.

## 4. Come si lavora qui (workflow obbligatorio)

Il dettaglio è in `CONTRIBUTING.md`. Il minimo sindacale:

1. **`main` è sempre verde.** Mai commit diretti su `main` (fatte salve
   concordanze esplicite). Ogni intervento parte da una branch:
   `feature/<nome>`, `fix/<issue-id>-<nome>`, `test/<nome>`, `refactor/<nome>`,
   `chore/<nome>`, `docs/<nome>`.
2. **Prima il test, poi il codice.** Ogni bug risolto richiede un test di
   regressione scritto prima del fix. La suite deve essere verde prima del
   merge: `.venv/bin/python -m pytest backend/tests -q`
3. **I problemi diventano issue**: file `issues/NNNN-titolo.md` (template in
   `issues/README.md`) prima di mettere mano; il fix chiude la issue dal
   commit (`fix(#NNNN): ...` + `Closes #NNNN`).
4. **Commit Conventional Commits**: `<tipo>(<ambito>): <descrizione>`
   (feat/fix/test/refactor/chore/docs). Atomici, motivazione singola.
   Corpo del commit in italiano, tono tecnico, niente narrativa.
5. **Verifica reale, non dichiarata**: per modifiche a parser/ingest basta la
   suite; per modifiche a API/DB/worker verificare anche lo stack vero
   (`docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build`)
   e un flusso end-to-end (upload → import completed → findings → dashboard).
   Non dichiarare mai "funziona" senza aver visto girare il codice.
6. **Commit and push completed work**: after every successfully completed feature
   and at the end of each work session, update its issue/checklist, run the
   required checks, commit the complete increment and push the active branch to
   `https://github.com/antoniocarino69/vcm.git`. Verify that the remote branch
   contains the commit. Do not leave completed work only on one computer.
   If a push fails, report the precise blocker and retain the local commit;
   never claim publication succeeded. Do not force-push, replace remote history,
   or bypass the main/PR workflow to make the push succeed.
   If Git CLI credentials are unavailable but an authorized GitHub connection
   can publish the work, use its supported write tools, record any rewritten
   commit hashes/provenance, and synchronize the local working branch with the
   published branch. Never expose access tokens in files, commands or logs.

## 5. Verifiche rapide

```bash
# suite (20+ test, nessun DB richiesto)
cd /root/vcm && .venv/bin/python -m pytest backend/tests -q

# stack completo (API su :8080 tramite nginx)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
curl -s http://127.0.0.1:8080/api/health

# fixture reali per test manuali: backend/tests/fixtures/
```

Ambiente: Python 3.12 (venv in `.venv/`, `uv` disponibile), PostgreSQL 16 e
Redis 7 via Docker. La macchina è headless: ogni servizio web costruito qui
deve restare **raggiungibile dall'esterno** (bind 0.0.0.0 / porta pubblica).

## 6. Convenzioni di codice

- Python: type hints ovunque, nuove docstring in inglese con concetto tecnico in
  inglese (finding, dedup, sniff...), funzioni pure quando la logica è
  testabile senza DB (è il motivo per cui `services/` non ha SQLAlchemy).
- Naming: `snake_case` ovunque; le tabelle rispecchiano `db/schema.sql`;
  gli enum stringa sono lowercase tranne `CAT_I/II/III`.
- Niente dipendenze inutili: dentro `app/parsers/` solo stdlib; altrove solo
  ciò che è già in `requirements.txt`.
- Un file = una responsabilità; se supera ~400 righe, chiediti se va spezzato.
- Commenti: spiegano il PERCHÉ, non il COSA. Niente commenti che riassumono
  la riga successiva.
- Refactoring e fix di refusi vanno in commit/PR separati da feature e fix
  (niente "fix + pulizia" mescolati).
- Product UI, new documentation, comments and docstrings use English. The
  conversation with the user may remain Italian; existing data values and
  scanner evidence are preserved in their original language.

### Reference repositories and interface design

Consult the actual Faraday (`https://github.com/infobyte/faraday`) and
DefectDojo (`https://github.com/DefectDojo/django-DefectDojo`) repositories and
official documentation when implementing navigation, filters, finding details,
campaign workflows or scanner compatibility. Inspect relevant code/screenshots,
record the source revision and distinguish OSS from commercial behavior.
Do not rely solely on a generic dashboard or remembered descriptions.
Reuse/adapt suitable code or interaction patterns with provenance and the
applicable license recorded, while preserving VCM's architecture and deployment
constraints. Verify scanner formats against official versioned schemas/examples
and sanitized real exports; do not present an assumed CSV layout as a verified
vendor export.

The portal must have shared sidebar sections, stable client/environment context,
practical asset/finding tables, and a consistent visual language designed for
system administrators. Avoid repeating generic card grids and oversized KPI
panels across every page. Design and verify actual list/detail/filter workflows,
including mobile/keyboard behavior, before declaring the interface refactor done.

## 7. Cosa NON fare

- Non inventare API, tabelle o campi che non esistono: leggi `db/schema.sql`
  e `app/api/` prima di scrivere codice che li usa.
- Non aggirare la deduplica inserendo finding direttamente: si passa sempre
  da `app/services/ingest.py`.
- Non loggare o committare segreti (in futuro: credenziali scanner, token).
  I report scanner caricati sono dati cliente: finiscono solo nei volumi
  Docker, mai nel repo.
- Non correggere un bug "silenziosamente" nel codice di un altro strato
  durante una feature: apri una issue e procedi per iscritto.
- Non cambiare il significato di `dedup_hash`, degli stati dei finding o
  degli enum: sono contratti dati (verranno migrazioni quando servirà).
- Non dichiarare finito ciò che non è stato eseguito/verificato.

## 8. Mappa del repository

```
db/schema.sql            fonte di verità del database (11 tabelle, 5 viste)
backend/app/parsers/     BaseParser + 5 parser streaming (stdlib only)
backend/app/services/    ingest (dedup/auto-close/lifecycle), assets, report
backend/app/api/         route FastAPI (tenants, imports, findings, dashboard, reports)
backend/app/workers/     Celery: vcm.parse_import
backend/app/models.py    ORM SQLAlchemy 2.0 (enum nativi, 1:1 con schema.sql)
backend/tests/           suite + fixture reali dei 5 scanner
frontend/index.html      dashboard operativa (Chart.js)
deploy/nginx.conf        reverse proxy (body 2GB per i report)
issues/                  issue tracker locale (fino al remote git)
CONTRIBUTING.md          workflow dettagliato
README.md                architettura e avvio
```
