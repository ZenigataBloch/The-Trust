# The-Trust

Bot personali per Telegram e Discord che scaricano video e immagini da un link e li ripubblicano, più **Branch**, l'applicazione desktop (Tkinter) che li accende e li spegne e gestisce gli invii.

| File | Cosa fa |
|---|---|
| `telegram_bot.py` | Bot Telegram: incolli un link (in chat, con tag o inline) e pubblica i file nella stessa chat |
| `discord_bot.py` | Bot Discord installato sul tuo account: comando `/url link:<url>` (e `/invia`, se `org_bot.py` è presente) |
| `org_bot.py` | **Branch**: interfaccia grafica, gestione chat/canali/avatar e invii; contiene anche il led che accende e spegne i bot |
| `bot_manager.py` | Avvia, ritrova, ferma e **aggiorna da GitHub** i due bot |
| `branch_tema.py` | Aspetto grafico di Branch (colori, avatar, liste) |
| `bot_log.py` | Log su file con rotazione quando i bot girano senza console (`pythonw`) |
| `aggiorna_cookies.py` | Aggiorna `cookies.txt` da un export del browser (TikTok, Instagram, Reddit, X) |
| `applica_fix_nhentai.py` | Patch una tantum a `telegram_bot.py` per l'errore di certificato SSL |
| `bots.env.example` | Modello del file di configurazione `bots.env` |

## Requisiti

- Python 3.10 o superiore
- `ffmpeg` nel `PATH`
- Librerie:

```
pip install -U yt-dlp gallery-dl python-telegram-bot discord.py Pillow
```

(`Pillow` serve a Branch per immagini e avatar tondi; `python-telegram-bot` serve anche al bot Discord, che riusa funzioni di `telegram_bot.py`.)

## Installazione su una macchina nuova

```
git clone https://github.com/ZenigataBloch/The-Trust.git
cd The-Trust
copy bots.env.example bots.env        (Linux/Termux: cp bots.env.example bots.env)
```

Poi:

1. Apri `bots.env` e compila i valori (vedi sotto).
2. Se servono i cookie (TikTok, Instagram, Reddit, X), crea `cookies.txt` con `aggiorna_cookies.py` e indicane il percorso in `COOKIES_FILE`.
3. Avvia Branch: `python org_bot.py` (oppure `pythonw org_bot.py` su Windows, senza finestra di console).

All'apertura Branch controlla GitHub, aggiorna il codice se serve, poi accende i bot che non girano già. Chiudendo Branch i bot **restano accesi**; si spengono solo cliccando il led.

## Configurazione: `bots.env`

Il file sta accanto agli script, **non è nel repository** (contiene token) e va creato a mano su ogni macchina. Righe `NOME=valore`, `#` per i commenti.

| Variabile | Obbligatoria | Significato |
|---|---|---|
| `BOT_TOKEN` | sì | token del bot Telegram (@BotFather) |
| `OWNER_ID` | sì | il tuo ID utente Telegram |
| `DISCORD_TOKEN` | sì | token del bot Discord |
| `DISCORD_OWNER_ID` | sì | il tuo ID utente Discord (solo tu puoi usare i comandi) |
| `COOKIES_FILE` | no, ma serve per TikTok/Instagram/Reddit | **percorso assoluto** di `cookies.txt` |
| `COOKIES_BROWSER` | no | browser da cui leggere i cookie, es. `firefox,chrome` |
| `CHANNEL_ID` | no (consigliata) | ID dei tuoi canali Telegram, separati da virgola |
| `AUTO_CHANNEL_ID` | no | canali Telegram in cui il bot funziona senza tag |
| `SSL_SENZA_VERIFICA` | no | host per cui riprovare senza verifica SSL (default `nhentai.net`, vuoto = mai) |
| `DISCORD_INVII_DIR` | no | cartella dei dati di Branch (default `invii/` accanto agli script) |
| `INLINE_TAG`, `DISCORD_MAX_MB`, `IG_*`, `INVII_*` | no | regolazioni varie, descritte nei commenti in testa ai singoli file |

Attenzione ai valori: `bots.env` espande `%VAR%` e `$VAR`, quindi un `$` o un `%` dentro un valore verrebbe interpretato.

### Come vengono lette le variabili

`bot_manager.py` le raccoglie in quest'ordine (l'ultima vince):

1. l'ambiente con cui è stato lanciato Branch;
2. le righe `set NOME=valore` del file `launch.bat` accanto agli script, **solo per ciò che manca ancora**;
3. `bots.env`, che ha sempre l'ultima parola.

> I file `.bat` e `.vbs` non sono nel repository (vedi `.gitignore`). Su una macchina clonata `launch.bat` non esiste, quindi **tutto ciò che prima stava nel `.bat` deve essere in `bots.env`**.

## Aggiornamenti automatici

La cartella dei bot è un clone di questo repository. Branch esegue `git fetch` + `merge --ff-only` all'apertura e ogni 30 minuti. Se arrivano modifiche:

- `telegram_bot.py` / `discord_bot.py` → riavvia solo quel bot;
- `org_bot.py` / `bot_log.py` → riavvia entrambi i bot;
- `org_bot.py`, `bot_manager.py`, `branch_tema.py` → Branch stesso va riavviato a mano (il log lo segnala).

Per pubblicare una modifica:

```
git add .
git commit -m "descrizione"
git push
```

Se sulla macchina dei bot hai modifiche locali ai file tracciati, il merge si blocca e il log lo segnala: modifica sul PC di sviluppo e sulla macchina dei bot fai solo pull.

## Cookie

```
python aggiorna_cookies.py --clipboard      # dagli appunti (Termux:API)
python aggiorna_cookies.py percorso/file    # da un file esportato
```

Sostituisce solo i cookie dei siti presenti nell'export, lascia intatti gli altri e salva il vecchio file come `cookies.txt.bak`. I bot rileggono il file a ogni download: non serve riavviarli.

## Cosa NON è nel repository

Vedi `.gitignore`: `bots.env`, `cookies.txt*`, la cartella `invii/` (chat, avatar, backup, canali), i file `.bat`/`.vbs`, i log, `bots_pid.json`, `instagram_uso.json`.

**Non pubblicare mai token o cookie.** Se succede, rigenerali subito (BotFather, Discord Developer Portal) ed esci dalle sessioni dei siti interessati.
