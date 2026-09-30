# 0011 — Gestione clienti e ambienti dal portale

## Contesto
POST/list disponibili, GUI passiva; PATCH tenant e archiviazione non esposti.

## Riproduzione / verifica
Riferimenti e scenari dettagliati in `docs/review-piano-portale.md`.
Scrivere regressioni prima dei fix; per API/DB/worker verificare lo stack reale.

## Comportamento atteso
P1a crea e seleziona cliente/ambiente con persistenza al refresh; P1b modifica e archivia conservando storico. Dipendenze #0003/#0004/#0008/#0009.

## Stato
- aperta per l'archiviazione (comportamento definito, UI non esposta); P1a e P1b modifica completati
- branch: feature/0011-client-environment-portal (P1a) e
  feature/0011-p1b-client-environment-editing (P1b)
- P1a: `clients.html`, creazione/selezione cliente e ambiente, tipo e match_key;
  browser reale con persistenza al refresh, layout mobile e dati test rimossi.
- P1b: modifica cliente (nome, chiave, descrizione) e ambiente (nome, tipo,
  match_key) con PATCH realmente parziali (solo i campi cambiati), feedback
  inline su 409 duplicati e 422 valori invalidi, "No changes to save." su
  invio senza modifiche. Guard su risposte tardive: un PATCH o una creazione
  completati dopo il cambio cliente non toccano mai il cliente selezionato.
- Comportamento archiviazione (definito prima di esporlo): l'archiviazione
  imposta `status='archived'` senza cancellare nulla — import, findings,
  commenti, spostamenti e report restano leggibili; un client archiviato non
  riceve nuovi import/ambienti/asset e compare solo con un filtro esplicito;
  la riattivazione ripristina le operazioni. Nessuna eliminazione a cascata
  dell'anagrafica viene mai proposta dall'interfaccia.
- Browser regression: empty state, duplicate checks, server errors, safe text,
  client switching and stale responses. No authentication added.
- Evidenze P1b: regressione `frontend/tests/clients-edit.browser.cjs`
  (rossa prima dell'implementazione) + 4 suite esistenti verdi; flusso reale
  UI↔API su stack :8080 (creazione, modifica cliente e ambiente verificate via
  API), layout mobile a 390px; dati temporanei rimossi.
