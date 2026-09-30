# 0014 — Finding e triage dal portale

## Contesto
API status/comment/history disponibili, GUI assente.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
P3b elenco/dettaglio e quattro stati, note/scadenza/commenti/history. P3c bulk in incremento separato, ogni ID scoped, esiti espliciti. Dipende da #0002/#0004/#0008 e upload.

## Stato
- aperta per P3c (bulk actions separate); P3b completato
- branch: feature/0014-finding-workflow (impilata su feature/0011-p1b-client-environment-editing)
- P3b consegnato: `/vulnerabilities.html` (lista operativa filtrata/paginata:
  ambiente, asset, OS, rule/CVE, severity, status, tags, scanner, porta,
  first/last seen) e `/finding.html` (contesto asset, severity originale e
  normalizzata, CVSS/CVE, evidenze scanner, provenienza import, commenti,
  cronologia). Decisioni individuali su Open/Mitigated/False positive/Risk
  accepted con motivo (obbligatorio per l'accettazione) e scadenza opzionale.
- Unità di decisione verificata: ogni POST colpisce un solo finding ID;
  accettare la regola X sul server A lascia la stessa regola sul server B
  invariata (regressione PostgreSQL + verifica live UI↔API), e una porta non
  cambia l'altra (regressione su stessa regola, stessa asset, due porte).
- Evidenze: regressioni backend scritte prima e osservate fallire (3 failed),
  poi 48 passed con PostgreSQL; suite browser `findings.browser.cjs` +
  altre 5 suite verdi; flusso live su stack reale (upload Qualys → import
  completed → lista → dettaglio → accettazione via UI → sibling invariato),
  dati temporanei rimossi.
- Resta aperto: P3c bulk actions (ID espliciti, check tenant per ID, batch
  limitati, esiti visibili) e la copertura osservazioni complete (#0020).

## Updated product scope (2026-09-30)
See `docs/portal-next-steps.md`, section C. Assets and individual vulnerabilities; E. Filters — #0014, #0021.
The current request includes a shared sidebar, per-asset finding decisions,
OS/tag filtering and optional pre-upload dates/tags; proposals require scoped
API/schema increments before being presented as implemented behavior.
