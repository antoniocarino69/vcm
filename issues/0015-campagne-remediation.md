# 0015 — Campagne asset-centric di remediation

## Contesto
Nessuna tabella o route campagne: proposta in docs/review-piano-portale.md.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
P4a schema+migrazione+servizi+API+GUI minima: selezione finding, owner, scadenza e progresso. P4b operatività separata. Nessuna gerarchia Engagement/Test, associazioni stesso tenant, nessuna chiusura finding implicita.

## Stato
- aperta
