# 0007 — Correttezza host vuoti e compliance

## Contesto
seen_by_asset non registra host senza finding; SCC usa un unico host per tutti i TestResult; risultati pass vengono creati active e contati come rischio.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
Fix separati con regressioni: host presente vuoto vs assente; XCCDF multi-target; policy risultato compliance/lifecycle e metriche. Nessuna modifica implicita degli enum.

## Stato
- aperta
