# 0003 — Isolare dashboard e report per cliente

## Contesto
api/dashboards.py:86 e :98 omettono tenant/environment per top_hosts e ad_health. Il report Executive riusa dashboard.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
Applicare scope prima di aggregazione/limit. Regressione PostgreSQL con due clienti e più di 20 snapshot; verifica report e stack reale.

## Stato
- aperta
