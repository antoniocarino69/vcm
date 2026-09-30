# 0011 — Gestione clienti e ambienti dal portale

## Contesto
POST/list disponibili, GUI passiva; PATCH tenant e archiviazione non esposti.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
P1a crea e seleziona cliente/ambiente con persistenza al refresh; P1b modifica e archivia conservando storico. Dipendenze #0003/#0004/#0008/#0009.

## Stato
- aperta
