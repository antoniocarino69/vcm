# Workflow di sviluppo — VCM

Regole valide per ogni contributo a questo repository (PoC e oltre).

## Principi

1. **`main` è sempre verde**: builda e i test passano sempre. Nessun commit
   diretto su `main` se non per merge e fix banali concordati.
2. **TDD dove ha senso**: i parser e la logica di ingest/dedup sono puri e
   coperti da test senza DB — ogni bug corretto merita un test di regressione
   scritto PRIMA del fix.
3. **Commit piccoli e atomici**: un commit = una motivazione. Messaggi in
   stile Conventional Commits.

## Branch

| Tipo        | Forma                       | Quando                                  |
|-------------|-----------------------------|-----------------------------------------|
| feature     | `feature/<nome-breve>`      | nuova funzionalità                      |
| fix         | `fix/<issue-id>-<nome>`     | correzione di un bug (da issue)         |
| refactor    | `refactor/<nome>`           | ristrutturazione senza cambio di comportamento |
| test        | `test/<nome>`               | solo suite/fixture                      |
| chore       | `chore/<nome>`              | build, CI, dipendenze, infra            |

## Flusso

### Feature
1. `git checkout -b feature/<nome>` da `main` aggiornato.
2. Sviluppo incrementale: scrivi/estendi i test, poi il codice.
3. Esegui la suite: `.venv/bin/python -m pytest backend/tests -q`
   (deve essere verde PRIMA del merge; per modifiche al DB/API: verificare anche
   lo stack reale `docker compose up -d --build` + flusso end-to-end).
4. Merge in `main` (fast-forward o --no-ff a scelta, niente force-push).

### Bug / problema
1. Si apre una **issue** (vedi sotto) con: sintomo, riproduzione, ambiente.
2. Branch `fix/<issue-id>-<nome>`; si scrive prima il test che riproduce il bug.
3. Fix + test verde → merge in `main` con messaggio `fix(#<id>): ...`
   che chiude la issue ("Closes #<id>").

## Issue (fino al remote)

Finché non colleghiamo un tracker remoto (GitHub), le issue vivono in
`issues/` come file markdown: `issues/NNNN-titolo-breve.md` con sezioni
**Contesto**, **Riproduzione**, **Comportamento atteso**, **Stato**
(aperta/in corso/chiusa + PR/commit di chiusura). I numeri NNNN sono
progressivi e diventeranno i riferimenti `#<id>` nei commit.

## Messaggi di commit

```
feat(parsers): supporto export CSV di Nessus
fix(ingest): #0003 auto-close non considerava lo scanner (regressione)
test(dedup): copre riapertura di un finding mitigato
chore(build): immagini docker con librerie WeasyPrint
docs: sezione workflow di sviluppo
```

Formato: `<tipo>(<ambito>): <descrizione>` — tipo tra
feat/fix/test/refactor/chore/docs; descrizione in imperativo, inglese o
italiano coerente col resto del progetto.

## Revisione (da remoto in poi)

Con il remote attivo: niente merge su `main` senza PR, revisione richiesta,
CI verde (pytest + lint). Le regole sopra restano valide anche in locale.
