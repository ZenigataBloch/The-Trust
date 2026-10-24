Ti preparo un prompt/file di handover pensato per Claude, con workflow **una feature alla volta**, niente test, niente spiegazioni extra, modifica solo file necessari e attesa di `PROSEGUI`.

```md
# NEXT_AGENT.md
# BRANCH - Feature Development Handover

## Progetto

Nome: BRANCH

Concept:
Branch è un Personal Intelligence Hub ispirato alla Trust di 100 Bullets.

L'app raccoglie informazioni da fonti diverse tramite moduli specializzati ("Branches"), le organizza, le collega e permette agli utenti di creare missioni di monitoraggio continuo.

Non è un semplice aggregatore:
- raccoglie dati;
- analizza informazioni;
- crea report;
- mantiene memoria;
- permette agenti specializzati.

---

# Regole operative per Claude

## Workflow obbligatorio

Implementare UNA SOLA FEATURE PER VOLTA.

Dopo ogni feature:

1. Modificare solo i file necessari.
2. Non creare sistemi inutili o sovradimensionati.
3. Non fare refactoring generale.
4. Non aggiungere test.
5. Non eseguire test.
6. Non fare verifiche manuali.
7. Non proporre feature successive.
8. Creare/aggiornare NEXT_AGENT.md con stato corrente.

Terminare sempre con:

```
fatto: [nome feature]
file: [lista file modificati]
```

Attendere poi:

```
PROSEGUI
```

prima di continuare.

---

# Filosofia tecnica

Preferire:

- architettura modulare;
- plugin indipendenti;
- configurazioni semplici;
- codice leggibile;
- sistemi estendibili.

Ogni nuova sorgente deve essere un modulo separato.

---

# Terminologia

## Branches

I moduli principali vengono chiamati Branches.

Esempi:

GRAVES
- ricerca web
- booru
- intelligence generale

VASCO
- Discord

MEDICI
- Telegram

SHEPHERD
- GitHub

ROMA
- RSS/news

VERNER
- YouTube

DEITRICH
- documenti/PDF

---

# ROADMAP FEATURES

## FASE 1 - Core Application

### Feature 1
Creazione struttura base Branch.

Obiettivo:
Creare architettura iniziale:

- core
- branches
- agents
- missions
- reports
- storage

---

### Feature 2
Sistema Branch Manager.

Obiettivo:
Gestire moduli installati.

Funzioni:

- registrazione Branch;
- attivazione/disattivazione;
- configurazione base.

---

### Feature 3
Sistema configurazione.

Obiettivo:

Creare gestione:

- settings;
- API keys;
- preferenze utente;
- configurazioni Branch.

---

# FASE 2 - Intelligence Engine

### Feature 4
Sistema Agent Base.

Creare struttura per agenti.

Ogni agente deve avere:

- nome;
- ruolo;
- input;
- output;
- memoria.

---

### Feature 5
Sistema Missioni.

Creare concetto:

Mission = obiettivo permanente.

Esempio:

"Monitora tutto riguardo Godot".

Una missione contiene:

- sorgenti;
- regole;
- frequenza;
- output.

---

### Feature 6
Sistema Report.

Creare generazione report:

- giornalieri;
- settimanali;
- su richiesta.

---

### Feature 7
Sistema memoria.

Permettere salvataggio:

- eventi;
- risultati;
- collegamenti;
- cronologia.

---

# FASE 3 - Branch Sources

## GRAVES

### Feature 8
Branch GRAVES base.

Ricerca web.

Funzioni:

- query;
- raccolta risultati;
- salvataggio.

---

### Feature 9
GRAVES Intelligence.

Aggiungere:

- riassunti;
- classificazione;
- rilevanza.

---

## VASCO

### Feature 10
Branch Discord base.

Funzioni:

- connessione;
- lettura canali;
- raccolta messaggi.

---

### Feature 11
Discord Intelligence.

Aggiungere:

- riassunti;
- ricerca eventi importanti;
- monitoraggio parole chiave.

---

## MEDICI

### Feature 12
Branch Telegram base.

Funzioni:

- monitoraggio;
- ricezione;
- invio notifiche.

---

### Feature 13
Telegram Intelligence.

Aggiungere:

- filtri;
- alert;
- report.

---

## SHEPHERD

### Feature 14
Branch GitHub.

Monitoraggio:

- repository;
- commit;
- release;
- issue.

---

# FASE 4 - User Experience

### Feature 15
Dashboard principale.

Visualizzare:

- Branch attivi;
- Missioni;
- Report;
- Alert.

---

### Feature 16
Sistema Watchlist.

Creare elementi monitorabili:

Esempio:

- Godot;
- Wild West;
- PSPRecomp;
- Claude.

---

### Feature 17
Timeline Intelligence.

Visualizzare:

- eventi;
- cambiamenti;
- cronologia.

---

### Feature 18
Centro notifiche.

Gestire:

- priorità;
- urgenza;
- notifiche esterne.

---

# FASE 5 - Advanced AI

### Feature 19
Multi Agent Analysis.

Integrare modello MAGI:

Tre agenti analizzano:

- fatti;
- conseguenze;
- criticità.

---

### Feature 20
Decision Reports.

Generare:

- situazione;
- analisi;
- possibili azioni.

---

# FASE 6 - Expansion

### Feature 21
Branch YouTube.

### Feature 22
Branch RSS.

### Feature 23
Branch PDF/Documents.

### Feature 24
Branch Local Files.

### Feature 25
Branch Browser History.

---

# Stato corrente

Feature completate:
Nessuna.

Feature corrente:
Nessuna.

Prossima feature:
Feature 1 - Creazione struttura base Branch.

Attendere comando:

PROSEGUI
```