# 0008 — Rendering sicuro e contesto uniforme del portale

## Contesto
index.html interpola nomi/filename/titoli in HTML; cambio cliente lascia import del primo ambiente iniziale.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
DOM/textContent per dati esterni, uno scope condiviso, report disabilitati senza cliente. Test browser con payload HTML innocuo e due clienti.

## Stato
- aperta
