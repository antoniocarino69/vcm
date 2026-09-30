# 0005 — Fallback AD confronta FQDN con inet

## Contesto
services/assets.py:49 restituisce match_key ip anche se il valore viene da host.fqdn. dbrepo confronta il valore con Asset.ip.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
Test prima del fix: ParsedHost(fqdn="ad.example.local"), match_key ip deve usare fqdn; verifica import PostgreSQL reale.

## Stato
- aperta
