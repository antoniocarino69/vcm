# 0011 — Gestione clienti e ambienti dal portale

## Contesto
POST/list disponibili, GUI passiva; PATCH tenant e archiviazione non esposti.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
P1a crea e seleziona cliente/ambiente con persistenza al refresh; P1b modifica e archivia conservando storico. Dipendenze #0003/#0004/#0008/#0009.

## Stato
- aperta per P1b (modifica e archiviazione); P1a completato
- branch: feature/0011-client-environment-portal
- P1a: `clients.html`, creazione/selezione cliente e ambiente, tipo e match_key;
  browser reale con persistenza al refresh, layout mobile e dati test rimossi.
- Browser regression: empty state, duplicate checks, server errors, safe text,
  client switching and stale responses. No authentication added.
