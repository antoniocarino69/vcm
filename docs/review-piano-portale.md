# VCM — Review rapida e piano del portale operativo

Data: 30 settembre 2026. Base revisionata: `74f4b47`.
Richiesta: gestione clienti, ambienti, upload VA, triage e campagne dal portale;
nessuna autenticazione per il momento; HTTP pubblico su `0.0.0.0`.

## Valutazione

Il PoC ha una base utile: schema PostgreSQL dedicato, normalizzazione condivisa,
parser senza DB/rete, ingest separato dalla persistenza, worker Celery e report.
Conviene estenderlo, mantenendo clienti → ambienti → asset → finding.
Il lavoro principale è rendere utilizzabili questi contratti nel portale e
correggere i punti in cui isolamento e lifecycle non rispettano AGENTS.md.
Le campagne richiedono invece un modello nuovo: oggi non esistono nel DB.

La review è mirata a API, schema/ORM, ingest, parser e dashboard; non è un audit
completo né un benchmark su report di centinaia di MB.

## Cosa esiste davvero

| Area | Backend attuale | Portale attuale | Lavoro necessario |
|---|---|---|---|
| Clienti | POST/list/detail; status active/archived nel DB | Selettore | Creazione, modifica, archiviazione e contesto persistente |
| Ambienti | POST/list/PATCH, match_key e tag | Elenco passivo | Creazione, modifica, selezione coerente e validazione |
| Asset | POST/list/PATCH/move con storico | Solo top host | Inventario, dettaglio, filtri, modifica e spostamento |
| Import scanner | Upload 202, lista, dettaglio, worker | Ultimi import del primo ambiente del primo cliente | Upload, avanzamento, errori e aggiornamento risultati |
| Finding | Filtri, dettaglio, status e commenti | Solo aggregati | Elenco operativo, dettaglio, triage, cronologia |
| Report | Executive/Technical HTML/PDF/CSV | Link | Scope coerente e risultati verificabili |
| Campagne | Nessuna tabella/route | Assenti | Schema, migrazione, servizi, API e GUI |

Gli stati richiesti sono già supportati: Aperta = `active`, Mitigata/chiusa =
`mitigated`, Rischio accettato = `risk_accepted`, Falso positivo =
`false_positive`. Conservare questi enum; la GUI usa etichette italiane.
Risk accepted non significa vulnerabilità risolta: i report devono distinguerli.

## Risultati della review, in ordine di priorità

Le voci seguenti sono osservazioni statiche salvo dove è indicata una prova.
P1 = correttezza/isolamento da risolvere prima dei nuovi flussi; P2 = robustezza
e qualità dei dati; P3 = scalabilità e metriche.

| Priorità / issue | Evidenza | Effetto e verifica richiesta |
|---|---|---|
| P1 / #0003 | `backend/app/api/dashboards.py:86` e `:98`: top_hosts e ad_health non applicano tenant/environment | La dashboard filtrata e il report Executive che la riusa possono contenere dati di altri clienti. Test PostgreSQL con due tenant e due ambienti, anche oltre 20 snapshot AD. |
| P1 / #0004 | `api/findings.py:58`: tenant opzionale; detail/status/comments recuperano per solo ID. Analogamente route asset/import per ID | Manca un contratto di scope obbligatorio. Rendere esplicito tenant e validare ambiente/asset nelle letture e mutazioni. Nessuna auth necessaria per applicare questo vincolo. |
| P1 / #0004 | `db/schema.sql:81`, `:187`, `:199`: moves/history/comments senza tenant_id; FK tenant/ambiente/asset indipendenti | Divergenza dal pilastro «ogni record figlio porta tenant_id»; il DB non impedisce tutti gli abbinamenti cross-tenant. Migrazione con backfill e vincoli composti, mantenendo gli snapshot ambiente dei finding. |
| P1 / #0002 | `services/ingest.py:132`, prima del fix: riapertura di qualunque stato non active | Il reimport annulla decisioni manuali. Corretto in questa branch: riaprire solo mitigated, preservare FP/RA e aggiornare evidenze. Quattro regressioni verificate prima e dopo il fix. |
| P1 / #0005 | `services/assets.py:49`: fallback FQDN etichettato come ip; `dbrepo.py:72` lo confronta con inet | Prova pura: host con solo `ad.example.local` e match_key ip produce `AssetIdentity('ip', 'ad.example.local')`. Il lookup PostgreSQL può fallire invece di usare fqdn. Test prima del fix e import AD reale con solo FQDN. |
| P2 / #0006 | `api/imports.py:74`: `await file.read()` prima del controllo dimensione | L'upload carica tutto in RAM; con limite nginx 2 GB il rischio di esaurimento memoria è concreto. Scrittura a chunk, limite e hash incrementali, pulizia su errori/disconnessione. |
| P2 / #0006 | `api/imports.py:85`: alias validi, ma risoluzione canonica solo nel ramo auto | `scanner=nessus` e `qualys` raggiungono l'enum con alias non canonici e possono diventare un falso 409 per il catch generico del commit. Canonicalizzare e distinguere conflitti reali dagli altri errori. |
| P2 / #0006 | `api/imports.py:117`: commit prima di `.delay()`; `workers/tasks.py:14` e `:26` | Broker indisponibile può lasciare import pending senza task; max_retries non attiva da solo retry. Manca una guardia contro riesecuzioni/import concorrenti. Definire dispatch recuperabile e ingest idempotente per singolo import, testando interruzioni e concorrenza. |
| P2 / #0007 | `services/ingest.py:242`: seen_by_asset nasce solo nel ciclo finding | Un host presente con zero finding non genera coppia asset/scanner: auto-close non chiude i vecchi finding. Un host assente deve invece restare invariato. Serve identificare lo scanner anche per host vuoti. |
| P2 / #0007 | `parsers/scc.py:53` e `:108`: un unico ParsedHost per tutto il file | Più TestResult/target nello stesso XCCDF possono confluire nel primo host. Fixture multi-target e separazione per risultato, conservando benchmark/profilo. |
| P2 / #0007 | `services/ingest.py:171` crea tutti i risultati active; dashboard conta tutti gli active | Anche compliance pass/not_applicable contribuisce al rischio aperto. Definire la relazione fra esito compliance e lifecycle senza eliminare le evidenze; un pass non deve riaprire un fail mitigato. |
| P2 / #0008 | `frontend/index.html:113`, `:140`, `:201`: dati esterni interpolati in HTML | Nomi cliente, filename e titoli scanner possono diventare markup/script persistente nel portale. Usare textContent/DOM per i dati; test browser con payload HTML innocuo. |
| P2 / #0008 | `frontend/index.html:124` e `:215`: import caricati dal primo cliente, onchange aggiorna solo dashboard/link | Cambiare cliente lascia import e ambienti incoerenti; la vista Tutti genera link report con tenant vuoto. Uno scope condiviso deve guidare tutte le sezioni. |
| P2 / #0009 | `api/tenants.py:97`, `:140`: PATCH usa schema di creazione e model_dump completo | Richiede campi obbligatori e può azzerare tag/identità omessi. Schemi di patch separati, exclude_unset, validazione enum/UUID/IP e gestione 404/409/422. |
| P2 / #0009 | `models.py`: assenza dei CHECK e di diversi indici/vincoli presenti in schema.sql; `dbrepo.py:20` create_all | ORM non è 1:1 per vincoli. Non usare create_all come migrazione; test schema effettivo e strategia versionata per volumi già esistenti. Cambiare schema.sql non aggiorna un volume Docker popolato. |
| P3 / #0010 | `services/ingest.py:217` e `:226`: batch conta host, seen_by_asset conserva hash dell'intero import | Il generatore non garantisce memoria costante: liste per host, accumulo globale, una transazione lunga. Definire budget di memoria e misurare RSS prima di riprogettare i batch. |
| P3 / #0010 | `parsers/qualys.py:114`: context.root non disponibile durante il consumo; SCC/PK accumulano liste/tabelle | clear non basta a dimostrare memoria costante e rimozione dei nodi; test sintetici grandi e stream per host/risultato senza dipendenze extra. |
| P3 / #0010 | `api/dashboards.py:70`: raggruppamento last_seen, senza finestra 30 giorni | È una distribuzione dello stato attuale per ultima rilevazione, non il trend storico delle aperture/chiusure. Basare i flussi sugli eventi e distinguere stock da nuove transizioni giornaliere. |

Altro limite da trattare nel disegno degli import: `UNIQUE(tenant_id,
content_sha256)` impedisce il medesimo file in due ambienti dello stesso cliente
e il retry tramite nuovo upload di un file fallito. Non rimuovere il vincolo
senza definire prima l'identità dell'import e una migrazione.
Anche la riconciliazione asset manca di un vincolo univoco effettivo: il commento
in schema.sql sugli indici creati da services/assets non corrisponde al servizio.
Due worker possono creare duplicati. Trattarlo insieme ai test di concorrenza.

## Confronto con i progetti di riferimento

DefectDojo è utile per i flussi di triage, reimport, deduplica, note e risk
acceptance con motivazione/scadenza. La sua documentazione distingue Open Source
e Pro: non assumere che ogni workflow mostrato sia disponibile nel codice OSS.
Riprendere i concetti operativi senza introdurre Engagement/Test.
Fonti: [finding e deduplica](https://docs.defectdojo.com/asset_modelling/engagements_tests/pro__findings/),
[risk acceptance OSS](https://docs.defectdojo.com/triage_findings/findings_workflows/os__risk_acceptance/),
[repository](https://github.com/DefectDojo/django-DefectDojo).

Faraday è utile come riferimento per il contesto di lavoro selezionato,
dashboard operativa e raggruppamento delle vulnerabilità. In VCM il contesto
resta cliente/ambiente; un raggruppamento per regola o soluzione è una vista
di lavoro sopra i finding, senza modificare dedup_hash.
Fonti: [dashboard e workspace](https://docs.faradaysec.com/Dashboard-v4/),
[grouping](https://docs.faradaysec.com/Grouping/),
[repository](https://github.com/infobyte/faraday).

Per ora il confronto riguarda funzionalità e architettura, non una revisione
integrale dei due codebase. Prima di copiare un modulo concreto registrare
origine, commit e licenza del file. Questo incremento usa codice VCM.

## Architettura del portale proposta

Conservare FastAPI, Celery, PostgreSQL e nginx. Iniziare con frontend statico
modulare, separando script e stili dall'HTML; non serve introdurre un framework
o una nuova toolchain per form, tabelle e polling.
Rendere locale Chart.js per l'uso air-gapped, oggi dipende da CDN.

Navigazione: Clienti, Ambienti, Asset, Finding, Importazioni, Campagne, Report.
Cliente sempre visibile; ambiente facoltativo per le viste cross-ambiente del
medesimo cliente. La vista complessiva è una scelta esplicita e non permette
mutazioni senza aver selezionato un cliente.

Ogni pagina ha stati vuoto/caricamento/errore, validazione, conferma del risultato
persistito e filtri coerenti. Le risposte tardive di un vecchio scope non devono
sovrascrivere il nuovo contesto. Nessuna credenziale o autenticazione introdotta;
changed_by/author restano dichiarazioni dell'operatore, non identità verificate.

## Piano di esecuzione in incrementi completi

La richiesta attuale rinvia esplicitamente M1 auth/RBAC. I passi P0–P5 portano
il PoC al portale operativo; M2/M3/M4 restano milestone successive, con issue
dedicata prima di iniziarle. Non iniziare collector/API pull o notifiche in
questa fase. Ogni riga seguente va spezzata in PR atomiche se necessario, ma
un flusso viene dichiarato pronto solo quando è verificabile dalla GUI.

| Passo | Consegna | Dipendenze | Criterio di completamento |
|---|---|---|---|
| P0a | Correzione lifecycle #0002 | Nessuna | FP/RA preservati, mitigated riaperto, suite verde; completato in questa branch |
| P0b | Scope dashboard/report #0003 e scope API #0004 | Nessuna | Due clienti, nessun dato o aggiornamento fuori scope; API/DB testati nello stack |
| P0c | Fallback AD #0005, import #0006, compliance/host vuoti #0007 | P0a | I cinque scanner completano ingest reale; alias, errore broker, host vuoto e multi-target coperti |
| P0d | Rendering sicuro e contesto #0008; contratti PATCH/schema #0009 | P0b | Dati scanner resi come testo, scope uniforme, patch parziali conservano gli altri campi |
| P1a | Portale creazione clienti e ambienti #0011 | P0b/P0d | Dal browser: crea cliente, crea ambiente, ricarica e ritrova entrambi; errori gestiti |
| P1b | Modifica clienti/ambienti e archiviazione cliente #0011 | P1a/#0009 | PATCH tenant da aggiungere; archivio conserva storico ed esclude nuove operazioni secondo policy esplicita |
| P2 | Upload VA e monitoraggio import #0012 | P1a/P0c | Form cliente/ambiente/scanner/file, auto-close off iniziale, polling fino a completed/failed, risultati e dashboard aggiornati |
| P3a | Inventario e dettaglio asset #0013 | P1a/P0b | Filtri, paginazione, finding/storico per asset; spostamento stesso tenant conserva snapshot e commenti |
| P3b | Elenco/dettaglio finding e triage #0014 | P2/P0a/P0d | Aperta/Mitigata/FP/RA, nota e data, commenti e cronologia persistiti; refresh conferma i cambi |
| P3c | Azioni multiple #0014 | P3b | Validazione tenant per ogni ID, limiti al batch, riepilogo esiti; nessun aggiornamento silenziosamente saltato |
| P4a | Campagne: schema, API e portale minimo #0015 | P3b/#0004/#0009 | Crea campagna, collega finding selezionati, responsabile testuale/scadenza, elenco e dettaglio con progresso reale |
| P4b | Campagne: operatività #0015 | P4a | Filtri per regola/asset/team, note, chiusura con consuntivo; reimport aggiorna progresso senza perdere associazioni |
| P5 | Report e dashboard operativa #0016 | P3b/P4a | Report correttamente scoped con rischio aperto/accettato/mitigato separato, sintesi campagne; trend con definizione verificata |
| M1 | SSO/OIDC e memberships | Esplicita futura decisione | Rinviato su richiesta, nessun lavoro auth ora |
| M2 | Upload multiplo, collector e pull scanner | Dopo rivalutazione roadmap/M1 | Credenziali esterne e ingest programmatico in issue separate |
| M3 | SLA, scadenza RA e notifiche | Dopo M2 secondo roadmap | Job periodico idempotente, transizioni tracciate, policy scadenze testata |
| M4 | Ottimizzazione grandi istanze #0010 | Dopo M3 secondo roadmap | Misure RSS/query, indici mirati, paginazione e trend materializzati se giustificati |

SLA e scadenza automatica RA sono futuri; P3 mostra e memorizza la data ma non
promette la riapertura automatica a scadenza. Prima di ciascun incremento
aggiornare l'issue relativa con scope, test e dipendenze ancora aperte.

## Campagne: proposta dati da implementare in P4

Questi oggetti **non esistono oggi**. Una campagna è una raccolta di finding
persistenti dello stesso cliente, anche su più ambienti, con obiettivo operativo
(es. patch Windows server ottobre, hardening DC, remediation STIG CAT I).
Non è un contenitore di scansioni e non diventa proprietaria dei finding.

Proposta minima:

- `remediation_campaigns`: id, tenant_id, name, description, owner testuale,
  due_date, stato draft/active/completed/cancelled, created_at/updated_at.
- `remediation_campaign_findings`: tenant_id, campaign_id, finding_id,
  added_at; vincolo univoco campaign/finding e FK composte coerenti col tenant.
- Storico campagna con tenant_id per variazioni e associazioni; il lifecycle
  del finding continua a essere registrato in finding_status_history.

Schema.sql, migrazione incrementale per volumi esistenti e modelli devono
avanzare insieme. Gli stati campagna sono separati dagli enum finding.
API proposta scoped su tenant: crea/lista/dettaglio/PATCH campagne,
aggiunta/rimozione esplicita dei finding e consuntivo. Sono nuove route da
progettare in P4, non endpoint disponibili.

La prima versione mantiene associazioni esplicite: i filtri aiutano a scegliere
i finding, ma non ampliano automaticamente la campagna ad ogni nuovo import.
Un finding può partecipare a più campagne; non deve essere duplicato.
Se ricompare, il reimport riapre il mitigato e il progresso riflette il finding
attuale, conservando lo storico della campagna già completata.

Consuntivo: totale, aperti, mitigati, FP, rischi accettati, scaduti come target
di campagna. Percentuale tecnica = mitigati/totale; evidenziare separatamente
FP/RA. Chiusura ammessa con aperti solo con motivazione di consuntivo, senza
modificare automaticamente lo stato dei finding. Nessun «chiudi campagna ⇒
chiudi vulnerabilità» implicito.

## Protocollo di verifica e ripresa

Prima di un fix scrivere il test di regressione e osservarlo fallire; poi
correggere e lanciare `.venv/bin/python -m pytest backend/tests -q`.
Per API/DB/worker: build stack con entrambi i compose e flusso reale upload →
completed → finding → dashboard; usare fixture del repo in un tenant di prova.
Testare isolamento con un secondo tenant e verificare esplicitamente i 4xx.
Non caricare report cliente nel repository.

Per ogni flusso GUI verificare dal browser creazione/refresh/errori e cambio
scope. Controllare la porta pubblicata `0.0.0.0:8080`; database e Redis restano
su loopback. Health locale non dimostra raggiungibilità da un dispositivo remoto:
il controllo finale dall'esterno usa `http://<IP-server>:8080`.

Prima di interrompere: nessun form incompleto visibile, suite verde, issue
aggiornata con commit e test reali, nota su cosa è effettivamente deployato.
Il prossimo incremento consigliato è #0003, seguito dal contratto di scope
#0004; poi P1a. Non avviare tutte le pagine o l'intero modello campagne insieme.

## Verifiche eseguite in questa sessione

- Suite iniziale: **20 passed**.
- Quattro regressioni FP/RA × auto_close on/off: **4 failed** prima del fix.
- Suite dopo il fix #0002: **24 passed**; test esistente di riapertura mitigati verde.
- Riproduzione pura del fallback FQDN errato; non corretto, aperto #0005.
- Docker compose ps: API, worker, frontend attivi; PostgreSQL/Redis healthy.
- Frontend pubblicato su **0.0.0.0:8080** e IPv6; `/api/health` = `{"status":"ok"}`.
- Nessuna modifica a autenticazione, GUI, API, DB o configurazione di rete.
- Fix #0002 verificato nella suite locale; immagini Docker esistenti non
  ricostruite in questa sessione. Nessuna nuova funzionalità GUI dichiarata pronta.
