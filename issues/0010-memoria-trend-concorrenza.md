# 0010 — Misurare memoria e correggere metriche storiche

## Contesto
Ingest batch per host con hash accumulati per tutto import; liste parser non costanti; trend raggruppa stato attuale per last_seen; indici asset univoci annunciati ma assenti.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
Prima correggere concorrenza in #0006; benchmark RSS e query in M4, streaming misurato, trend da eventi con definizione esplicita. Ogni intervento in issue/PR separata.

## Stato
- aperta
