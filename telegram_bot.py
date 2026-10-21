"""
Bot Telegram personale: pubblica i file nella STESSA chat da cui riceve il link.

Uso:
  - Chat privata col bot (solo tu): incolli il link, il bot ti manda i file.
  - Gruppo o canale, modalità INLINE: scrivi  @nomedelbot <link>  e tocca il
    risultato "Scarica e pubblica" che compare sopra la tastiera. Il bot
    pubblica i file e cancella il messaggio col link.
  - Gruppo o canale, modalità TAG: scrivi  <link> @nomedelbot  (il tag NON
    deve stare all'inizio). Stesso risultato.

Nella console vedi in tempo reale cosa sta scaricando e inviando.

Dipendenze:  pip install -U yt-dlp gallery-dl python-telegram-bot
Serve anche ffmpeg nel PATH (per unire audio e video di Reddit).
La modalità inline va attivata su @BotFather: /setinline

Variabili d'ambiente:
  BOT_TOKEN   token di @BotFather
  OWNER_ID    il tuo ID Telegram (chat private, gruppi, inline e avvisi)
  CHANNEL_ID  (consigliato) ID numerico dei tuoi canali, separati da virgola
              (es. -1001234567890). Se manca, il bot risponde ai tag in
              QUALSIASI canale in cui è amministratore.
  AUTO_CHANNEL_ID  (opzionale) canali in cui il bot funziona senza tag: ogni
              post con un link viene scaricato e il post originale cancellato.

DA FUORI, in qualsiasi chat o gruppo dove il bot NON è presente (modalità inline, solo OWNER_ID):
  @nomedelbot /url <link>              poi tocca «Scarica qui»
  @nomedelbot /ricerca <cosa cercare>  poi tocca «Cerca qui» (1 immagine)
Un messaggio inline contiene un solo file. Serve /setinline e /setinlinefeedback = Enabled su @BotFather.

Comandi classici (solo se il bot è nella chat; solo OWNER_ID):
  /url <link>      scarica e pubblica nella chat (o rispondi a un messaggio con un link e scrivi /url)
  /ricerca <cosa cercare> [-n 1-10]
  /booru <tag> [-n 1-5] [-s r34|gb|db|e621|rg] [-r]
Un admin che scrive "in modo anonimo" arriva al bot come GroupAnonymousBot e viene ignorato.

/ricerca usa il modulo Graves (graves.py): serve la chiave di un provider (GRAVES_SERPER_KEY,
GRAVES_SERPAPI_KEY o GOOGLE_API_KEY+GOOGLE_CX in bots.env). GRAVES_ORIGINALE=1 manda le immagini come
file (prima un album, poi uno per uno se l'album fallisce), senza la ricompressione che Telegram applica
alle foto. /booru mostra prima l'anteprima, poi il file. Chiavi e variabili: vedi l'inizio di graves.py.

Protezione Instagram (opzionale; 0 = disattivato). Troppe richieste ravvicinate fanno scattare
«attività sospetta» sull'account dei cookie: il bot le conta (tutti i moduli, anche dopo un riavvio),
ti avvisa, aspetta tra un download e l'altro e si ferma al raggiungimento di un tetto.
  IG_AVVISO_ORA / IG_AVVISO_GIORNO   avviso a N download in 1 h / 24 h (default 12 / 60)
  IG_MAX_ORA / IG_MAX_GIORNO         blocco a N download in 1 h / 24 h (default 25 / 100)
  IG_PAUSA_SEC                       pausa minima tra due download (default 5)
  IG_COOLDOWN_MIN                    pausa se Instagram segnala limiti o attività sospetta (default 30)
  IG_STATO_FILE                      contatore (default: instagram_uso.json accanto allo script)
Sono stime prudenti, non limiti ufficiali di Instagram: regolale in base a ciò che vedi.

Cache dei download: dopo un invio riuscito il bot ricorda i file_id di Telegram del link. Se rimandi lo
stesso link (anche con parametri di tracciamento diversi, es. ?igsh=...) li rimanda senza riscaricare né
ricaricare: niente yt-dlp/gallery-dl, niente conteggio Instagram. /riscarica <link> ignora la cache.
  TG_CACHE_GIORNI   validità di una voce (default 30; 0 = cache disattivata)
  TG_CACHE_FILE     dove la salva (default: download_cache.json accanto allo script)
Vale per chat, gruppi, canali, /url e inline. I file_id valgono solo per lo stesso bot (cambi token = cache ignorata).

Aggiornamento automatico di yt-dlp e gallery-dl (desktop e Android): all'avvio e poi ogni N ore il bot
esegue "pip install -U yt-dlp gallery-dl" in background e ricarica yt-dlp senza riavviarsi. Aspetta la
fine del download in corso. Se pip risponde "externally-managed" (Termux) riprova con
--break-system-packages. /aggiorna lo forza subito.
  AUTOUPDATE_ORE          ogni quante ore (default 24; 0 = disattivato)
  AUTOUPDATE_STATO_FILE   dove ricorda l'ultimo controllo (default: autoupdate.json accanto allo script)

Nei gruppi e nei canali il bot deve essere amministratore con i permessi
"Pubblica messaggi" ed "Elimina messaggi".
"""
import asyncio
import atexit
import contextvars
import datetime
import functools
import hashlib
import html
import importlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import struct
import time
import urllib.error
import urllib.request
import uuid
import traceback
import zlib
from importlib import metadata
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yt_dlp
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InlineQueryResultCachedMpeg4Gif,
    InlineQueryResultCachedPhoto,
    InlineQueryResultCachedVideo,
    InputMediaAnimation,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    InputTextMessageContent,
    Update,
)
from telegram.constants import ChatType
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    ChosenInlineResultHandler,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from bot_log import attiva_log_su_file

# Senza console (pythonw) stdout/stderr sono None: li giro su un file .log con rotazione.
attiva_log_su_file()

# httpx (usato da python-telegram-bot) a livello INFO scrive nel log gli URL delle richieste,
# che per la Bot API contengono il token: lo tengo a WARNING anche se qualcuno attiva i log
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# evita errori di codifica nella console di Windows
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER = int(os.environ.get("OWNER_ID") or 0)
CHANNELS = {
    int(x)
    for x in os.environ.get("CHANNEL_ID", "").replace(" ", "").split(",")
    if x
}

# Canali dove il bot lavora in AUTOMATICO, senza bisogno del tag @bot: ogni post con
# un link viene scaricato e ripubblicato, e il post originale viene cancellato.
# Si cambiano con la variabile AUTO_CHANNEL_ID (ID separati da virgola).
# Questi canali sono accettati anche se non compaiono in CHANNEL_ID.
AUTO_CHANNELS = {
    int(x)
    for x in os.environ.get("AUTO_CHANNEL_ID", "-1001856872810,-1001184345416")
    .replace(" ", "")
    .split(",")
    if x
}

# 1 = nel testo inviato dall'inline mode accoda anche "@bot" (vecchio comportamento).
# Di default è 0: il bot riconosce da solo i messaggi inviati "via @bot".
INLINE_TAG = os.environ.get("INLINE_TAG") == "1"

# 1 = l'inline propone anche «Scarica e pubblica» / «ricerca …» come testo: funziona SOLO nelle chat dove
# il bot è presente. Di default 0: si propone solo «Scarica qui», che funziona dappertutto.
INLINE_PUBBLICA = os.environ.get("INLINE_PUBBLICA") == "1"

# Un messaggio inline contiene UN SOLO file (limite di Telegram: niente album). Se il post ne ha più d'uno
# l'elenco propone in cima anche «📚 Album», che manda tutti i file come galleria: funziona SOLO nelle chat
# dove il bot è presente (li pubblica lui, dalla cache). 0 = non proporlo.
INLINE_ALBUM = os.environ.get("INLINE_ALBUM", "1") != "0"
# Se l'account personale (Telethon) è collegato, «📚 Album» funziona in QUALSIASI chat: il bot manda l'album
# a te in privato e il tuo account lo INOLTRA nella chat di destinazione. Su Telegram compare quindi come
# «Inoltrato da <nome del bot>»: si vede che l'ha pubblicato il bot, non tu. Il messaggio inline col link
# (riconoscibile dal segno ALBUM_MARK) viene cancellato. Senza account personale resta il vecchio
# comportamento (l'album parte solo nelle chat dove c'è il bot).
ALBUM_MARK = "📚 "

# Inline con anteprima: appena incolli il link il bot scarica; se finisce entro INLINE_ATTESA secondi
# l'elenco mostra già il file vero (miniatura compresa) e toccandolo parte direttamente, senza segnaposto.
INLINE_SEGNAPOSTO = os.environ.get("INLINE_SEGNAPOSTO") == "1"   # 1 = mostra «SCARICA QUI» mentre prepara
INLINE_ATTESA = float(os.environ.get("INLINE_ATTESA", "2"))

# cookie per i siti che richiedono il login (Instagram, TikTok, X...). Si provano in ordine:
#   COOKIES_BROWSER  uno o più browser separati da virgola, es. "firefox,chrome"
#                    se manca, uso i browser installati (firefox, chrome, edge, brave); "none" li esclude
#   COOKIES_FILE     file Netscape (es. C:\bot\cookies.txt), provato per ultimo
COOKIES_FILE = os.environ.get("COOKIES_FILE")        # es. C:\bot\cookies.txt (formato Netscape)
COOKIES_BROWSER = os.environ.get("COOKIES_BROWSER")  # es. firefox
if not COOKIES_FILE:    # nessuna variabile impostata: se accanto allo script c'è un cookies.txt lo uso
    _cookies_accanto = Path(__file__).resolve().with_name("cookies.txt")
    if _cookies_accanto.is_file():
        COOKIES_FILE = str(_cookies_accanto)

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ANIM_EXT = {".gif"}
ALL_EXT = VIDEO_EXT | IMAGE_EXT | ANIM_EXT

MAX_PHOTO = 10 * 1024 * 1024   # limite Telegram per le foto
MAX_FILE = 50 * 1024 * 1024    # limite upload dei bot (API standard)
URL_RE = re.compile(r"https?://[^\s<>\"']+")


# Su Windows i bot girano senza console (pythonw): senza questo flag ogni chiamata a
# ffmpeg/ffprobe/gallery-dl apre per un attimo una finestra nera (con ffmpeg
# installato da Chocolatey compare la schermata "Chocolatey").
_NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def run_nowin(*args, **kw):
    return subprocess.run(*args, **{**_NO_WINDOW, **kw})


def popen_nowin(*args, **kw):
    return subprocess.Popen(*args, **{**_NO_WINDOW, **kw})


def _python_console() -> str:
    """python.exe (con console) al posto di pythonw.exe: gallery-dl scrive su una pipe."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and exe.with_name("python.exe").exists():
        return str(exe.with_name("python.exe"))
    return sys.executable


# ---------- log in console ----------
def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def mb(n: float) -> str:
    return f"{n / 1_000_000:.1f} MB"


# ---------- aggiornamento automatico di yt-dlp e gallery-dl ----------
# I siti cambiano di continuo: un estrattore vecchio è la causa più comune dei download che falliscono.
try:
    AUTOUPDATE_ORE = float(os.environ.get("AUTOUPDATE_ORE", "24"))   # 0 = disattivato
except ValueError:
    AUTOUPDATE_ORE = 24.0
AUTOUPDATE_STATO = Path(os.environ.get("AUTOUPDATE_STATO_FILE")
                        or Path(__file__).resolve().with_name("autoupdate.json"))
PACCHETTI_DL = ("yt-dlp", "gallery-dl")

# Chi scarica tiene questo lock (yt-dlp e gallery-dl); l'aggiornamento lo prende per tutta la durata di
# pip e della ricarica, così non cambia i file sotto un download in corso.
_LOCK_DL = threading.RLock()


def _sotto_lock(fn):
    @functools.wraps(fn)
    def avvolta(*a, **k):
        with _LOCK_DL:
            return fn(*a, **k)
    return avvolta


def _versioni() -> dict:
    importlib.invalidate_caches()
    out = {}
    for pacchetto in PACCHETTI_DL:
        try:
            out[pacchetto] = metadata.version(pacchetto)
        except metadata.PackageNotFoundError:
            out[pacchetto] = None
    return out


def _pip_aggiorna():
    cmd = [_python_console(), "-m", "pip", "install", "-U", "--disable-pip-version-check", "--no-input",
           *PACCHETTI_DL]
    kw = dict(capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    r = run_nowin(cmd, **kw)
    if r.returncode and "externally-managed" in (r.stdout + r.stderr).lower():   # Termux / Python di sistema
        r = run_nowin(cmd + ["--break-system-packages"], **kw)
    return r


def _ricarica_yt_dlp():
    """Rimpiazza yt_dlp nel processo con la versione appena installata (l'unico uso è download_ytdlp)."""
    global yt_dlp
    vecchio = yt_dlp
    for nome in [n for n in sys.modules if n == "yt_dlp" or n.startswith("yt_dlp.")]:
        del sys.modules[nome]
    try:
        importlib.invalidate_caches()
        yt_dlp = importlib.import_module("yt_dlp")
    except Exception:
        yt_dlp = vecchio
        raise


def _au_ultimo() -> float:
    try:
        return float(json.loads(AUTOUPDATE_STATO.read_text(encoding="utf-8")).get("ultimo", 0))
    except Exception:
        return 0.0


def _au_scrivi():
    try:
        AUTOUPDATE_STATO.write_text(json.dumps({"ultimo": time.time()}), encoding="utf-8")
    except OSError as e:
        log(f"Aggiornamento: non riesco a salvare lo stato ({e})")


def aggiorna_downloader() -> tuple[bool, str]:
    """pip install -U di yt-dlp e gallery-dl, poi ricarica yt-dlp senza riavviare il bot.
    Aspetta la fine del download in corso. Ritorna (riuscito, riassunto)."""
    with _LOCK_DL:
        prima = _versioni()
        log("Aggiornamento: pip install -U yt-dlp gallery-dl…")
        try:
            r = _pip_aggiorna()
        except Exception as e:
            log(f"Aggiornamento non riuscito: {e}")
            return False, f"pip non è partito: {e}"
        if r.returncode:
            coda = " | ".join((r.stderr or r.stdout).strip().splitlines()[-3:])
            log(f"Aggiornamento non riuscito (pip codice {r.returncode}): {coda}")
            return False, f"pip ha fallito: {coda[:300]}"
        dopo = _versioni()
        cambiati = [f"{p} {prima[p]} → {dopo[p]}" for p in PACCHETTI_DL if prima[p] != dopo[p]]
        in_uso = getattr(getattr(yt_dlp, "version", None), "__version__", None)
        if dopo["yt-dlp"] and in_uso != dopo["yt-dlp"]:   # anche se l'aveva già aggiornato qualcun altro
            try:
                _ricarica_yt_dlp()
            except Exception as e:
                log(f"Ricarica di yt-dlp non riuscita ({e}): serve riavviare il bot")
                cambiati.append("ricarica di yt-dlp fallita, riavvia il bot")
    _au_scrivi()
    esito = ("aggiornato: " + ", ".join(cambiati)) if cambiati else "già aggiornati"
    log(f"Aggiornamento: {esito}")
    return True, esito


def _ciclo_aggiornamento():
    time.sleep(20)   # lascio finire l'avvio
    while True:
        attesa = _au_ultimo() + AUTOUPDATE_ORE * 3600 - time.time()
        if attesa > 0:
            time.sleep(min(attesa, 6 * 3600))
            continue
        ok, _ = aggiorna_downloader()
        if not ok:
            time.sleep(1800)   # niente rete o pip bloccato: riprovo tra mezz'ora


def log_versioni():
    """Scrive nel log le versioni di yt-dlp e gallery-dl: i siti cambiano di continuo e un
    estrattore vecchio è la causa più comune dei download che falliscono."""
    for pacchetto in ("yt-dlp", "gallery-dl"):
        try:
            v = metadata.version(pacchetto)
        except metadata.PackageNotFoundError:
            log(f"{pacchetto}: NON installato")
            continue
        extra = ""
        m = re.match(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", v) if pacchetto == "yt-dlp" else None
        if m:   # le versioni di yt-dlp sono date: avviso se è vecchia
            try:
                giorni = (datetime.date.today() - datetime.date(*map(int, m.groups()))).days
            except ValueError:
                giorni = 0
            if giorni > 60:
                extra = (f"  <-- vecchia di {giorni} giorni: la aggiorno tra poco" if AUTOUPDATE_ORE
                         else f"  <-- vecchia di {giorni} giorni: aggiorna con  pip install -U yt-dlp gallery-dl")
        log(f"{pacchetto} {v}{extra}")


# Avanzamento del download in corso ({"pct": 0-100, "n": file di gallery-dl, "fase": ...}): chi avvia il
# download mette qui un dict, il thread (che eredita il contesto) lo aggiorna e l'inline lo legge.
_AVANZ: contextvars.ContextVar = contextvars.ContextVar("avanzamento", default=None)


def progress_hook(d: dict):
    """Barra di avanzamento di yt-dlp, su una sola riga."""
    av = _AVANZ.get()
    if av is not None:
        if d["status"] == "downloading":
            tot = d.get("total_bytes") or d.get("total_bytes_estimate")
            if tot:
                av["pct"] = min(100.0, (d.get("downloaded_bytes") or 0) / tot * 100)
        elif d["status"] == "finished":
            av["pct"] = 100.0
    if d["status"] == "downloading":
        if not sys.stdout.isatty():
            return   # senza console (pythonw/file di log) la barra sporcherebbe il log
        done = d.get("downloaded_bytes") or 0
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        speed = d.get("speed")
        eta = d.get("eta")

        try:
            pct = f"{done / total * 100:5.1f}%" if total else "   ? %"
        except Exception:
            pct = "   ? %"

        line = f"    download {pct}  {mb(done)}"

        if total:
            line += f" / {mb(total)}"
        if speed:
            line += f"  {mb(speed)}/s"
        if eta:
            line += f"  ETA {int(eta)}s"

        print("\r" + line.ljust(80), end="", flush=True)

    elif d["status"] == "finished":
        if sys.stdout.isatty():
            print("\r" + " " * 80 + "\r", end="", flush=True)
        log(f"    scaricato: {Path(d.get('filename', '')).name}")


# ---------- cartella temporanea dei bot ----------
# Tutti i file di lavoro (download, compressioni) finiscono in una cartella
# dedicata a questo processo, che viene cancellata alla chiusura del bot.
# Se il processo viene ucciso di colpo (Gestione attività, crash), i resti
# vengono eliminati al prossimo avvio. La cache del bot Discord NON è qui.
BASE_TMP = Path(tempfile.gettempdir()) / "bot_tmp"
MY_TMP = BASE_TMP / str(os.getpid())
_CTRL_HANDLER = None


def _pid_vivo(pid: int) -> bool:
    """True se esiste ancora un processo con questo PID."""
    if sys.platform == "win32":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259     # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _cleanup_tmp():
    shutil.rmtree(MY_TMP, ignore_errors=True)


def setup_temp():
    global _CTRL_HANDLER
    try:
        BASE_TMP.mkdir(parents=True, exist_ok=True)
        for d in BASE_TMP.iterdir():
            if (d.is_dir() and d.name.isdigit() and int(d.name) != os.getpid()
                    and not _pid_vivo(int(d.name))
                    and time.time() - d.stat().st_mtime > 3600):   # solo se abbandonata da piu' di un'ora
                shutil.rmtree(d, ignore_errors=True)
                log(f"Pulizia: eliminata la cartella temporanea residua {d.name}")
        MY_TMP.mkdir(exist_ok=True)
    except Exception as e:
        log(f"Cartella temporanea dedicata non creata ({e}): uso quella di sistema")
        return
    tempfile.tempdir = str(MY_TMP)   # da qui TemporaryDirectory() lavora qui dentro

    # se la cartella sparisce (pulizia di un altro processo, Android...) la ricreo al volo
    _mkdtemp_orig = tempfile.mkdtemp

    def _mkdtemp_sicuro(*a, **k):
        MY_TMP.mkdir(parents=True, exist_ok=True)
        return _mkdtemp_orig(*a, **k)

    tempfile.mkdtemp = _mkdtemp_sicuro
    atexit.register(_cleanup_tmp)    # chiusura normale e Ctrl+C
    if sys.platform == "win32":      # chiusura della finestra / tab, logoff, spegnimento
        try:
            import ctypes
            handler_t = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

            def _on_console_event(evt):
                if evt in (2, 5, 6):   # CLOSE, LOGOFF, SHUTDOWN
                    _cleanup_tmp()
                return False           # lascio proseguire la chiusura normale

            _CTRL_HANDLER = handler_t(_on_console_event)   # riferimento da tenere vivo
            ctypes.windll.kernel32.SetConsoleCtrlHandler(_CTRL_HANDLER, True)
        except Exception as e:
            log(f"Pulizia alla chiusura della finestra non attivata: {e}")
    log(f"Cartella temporanea: {MY_TMP}")


setup_temp()

# ---------- ffmpeg senza lo shim di Chocolatey ----------
# Con ffmpeg installato da Chocolatey, il comando "ffmpeg" è un piccolo programma
# (shim, in ...\chocolatey\bin) che a sua volta lancia quello vero, e a ogni
# chiamata può far apparire una finestra "Chocolatey". Se lo riconosco, metto in
# testa al PATH la cartella dell'eseguibile vero: valgono per questi bot e per
# yt-dlp, che cerca ffmpeg nel PATH.
def _usa_ffmpeg_reale():
    if sys.platform != "win32":
        return
    exe = shutil.which("ffmpeg")
    if not exe or "chocolatey" not in exe.lower():
        return
    choco = Path(os.environ.get("ChocolateyInstall") or r"C:\ProgramData\chocolatey")
    try:
        reale = next((p for p in (choco / "lib").rglob("ffmpeg.exe")), None)
    except OSError:
        reale = None
    if reale is None:
        log("ffmpeg è uno shim di Chocolatey ma non trovo l'eseguibile vero: "
            "potrebbe aprirsi una finestra durante le conversioni")
        return
    os.environ["PATH"] = str(reale.parent) + os.pathsep + os.environ.get("PATH", "")
    log(f"ffmpeg: uso l'eseguibile vero ({reale}) invece dello shim di Chocolatey")


_usa_ffmpeg_reale()


# ---------- download ----------
def collect_files(folder: str) -> list[Path]:
    try:
        files = [
            p
            for p in Path(folder).rglob("*")
            if p.is_file() and p.suffix.lower() in ALL_EXT
        ]
    except Exception as e:
        raise RuntimeError(f"Errore durante la scansione dei file: {e}")

    return sorted(files, key=lambda p: p.name)


class DownloadError(RuntimeError):
    """Download fallito; `dettagli` ha il testo di yt-dlp e gallery-dl (serve a capire se sono i cookie)."""

    def __init__(self, msg: str, dettagli: str = ""):
        super().__init__(msg)
        self.dettagli = dettagli


class CookieError(RuntimeError):
    """Download fallito per cookie mancanti o non aggiornati: il messaggio è pronto da mostrare."""


# ---------- catena di cookie ----------
def _browser_installati() -> list[str]:
    """Browser che hanno una cartella profilo su questo computer (firefox, chrome, edge, brave).
    Su Android/Termux non ce ne sono: resta solo il file dei cookie."""
    home = Path.home()
    if sys.platform == "win32":
        roaming = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        cartelle = {"firefox": [roaming / "Mozilla" / "Firefox" / "Profiles"],
                    "chrome": [local / "Google" / "Chrome" / "User Data"],
                    "edge": [local / "Microsoft" / "Edge" / "User Data"],
                    "brave": [local / "BraveSoftware" / "Brave-Browser" / "User Data"]}
    elif sys.platform == "darwin":
        sup = home / "Library" / "Application Support"
        cartelle = {"firefox": [sup / "Firefox" / "Profiles"],
                    "chrome": [sup / "Google" / "Chrome"],
                    "edge": [sup / "Microsoft Edge"],
                    "brave": [sup / "BraveSoftware" / "Brave-Browser"]}
    else:
        cfg = home / ".config"
        cartelle = {"firefox": [home / ".mozilla" / "firefox", home / "snap" / "firefox" / "common" / ".mozilla" / "firefox"],
                    "chrome": [cfg / "google-chrome"],
                    "edge": [cfg / "microsoft-edge"],
                    "brave": [cfg / "BraveSoftware" / "Brave-Browser"]}
    return [b for b, dirs in cartelle.items() if any(d.is_dir() for d in dirs)]


def _browser_cookie() -> tuple[list[str], bool]:
    """(browser da provare, rilevati automaticamente?). COOKIES_BROWSER vince; 'none' li disattiva."""
    cfg = (COOKIES_BROWSER or "").strip()
    if cfg.lower() in ("none", "no", "off", "0"):
        return [], False
    if cfg:
        return [b.strip() for b in cfg.split(",") if b.strip()], False
    return _browser_installati(), True


def sorgenti_cookie() -> list[tuple[str, str]]:
    """Sorgenti da provare in ordine: prima i browser (quelli di COOKIES_BROWSER, es. 'firefox,chrome', o
    quelli installati se la variabile manca), poi il file dei cookie. Se un browser non si legge si passa
    alla sorgente dopo: così lo stesso bot funziona su desktop (browser) e su Android (file)."""
    s = [("browser", b) for b in _browser_cookie()[0]]
    if COOKIES_FILE and Path(COOKIES_FILE).is_file():
        s.append(("file", COOKIES_FILE))
    return s


def etichetta_cookie(sorgente: tuple[str, str]) -> str:
    tipo, valore = sorgente
    return valore if tipo == "browser" else Path(valore).name


def descrivi_cookie() -> str:
    nomi = [etichetta_cookie(x) for x in sorgenti_cookie()]
    nota = f" (file {COOKIES_FILE} non trovato)" if COOKIES_FILE and not Path(COOKIES_FILE).is_file() else ""
    auto = " [browser rilevati in automatico]" if _browser_cookie()[1] and any(x[0] == "browser" for x in sorgenti_cookie()) else ""
    return (" -> ".join(nomi) if nomi else "NESSUNO") + auto + nota


# segni nel testo degli errori: cookie che non si riescono a leggere / sito che chiede il login
_SEGNI_ILLEGGIBILE = ("could not copy", "cookie database", "cookies database", "failed to decrypt",
                      "database is locked", "unsupported browser", "cookies.sqlite")
# Solo frasi tipiche di yt-dlp/gallery-dl quando il sito chiede davvero il login. Parole generiche
# come "private", "403", "forbidden", "cookie" o "rate limit" compaiono anche per video rimossi,
# blocchi geografici o limiti di richieste: con quelle il bot accusava i cookie a torto.
_SEGNI_LOGIN = ("log in for access", "login required", "log in to", "sign in to confirm",
                "you need to log in", "need to log in", "requires authentication",
                "authentication required", "authrequired", "authenticationerror",
                "authenticated cookies", "--cookies", "registered users", "nsfw",
                "401 unauthorized", "http error 401",
                "redirect to login", "login page", "accounts/login",
                "could not authenticate", "authenticate you")   # X/Twitter: codice 32


def _esito_cookie(dettagli: str) -> str | None:
    """'non leggibile', 'login richiesto' o None se l'errore non c'entra con i cookie."""
    d = dettagli.lower()
    if any(k in d for k in _SEGNI_ILLEGGIBILE):
        return "non leggibile"
    if any(k in d for k in _SEGNI_LOGIN):
        return "login richiesto"
    return None


def _messaggio_cookie(sito: str, fatti: list[tuple[str, str]], ultimo: "DownloadError | None") -> str:
    login = [n for n, e in fatti if e == "login richiesto"]
    illeg = [n for n, e in fatti if e == "non leggibile"]
    if login:
        testo = (f"COOKIE NON AGGIORNATI per {sito}: letti da {', '.join(login)} ma il sito chiede "
                 "ancora il login. Accedi di nuovo al sito e riesporta i cookie.")
        if illeg:
            testo += f" Non leggibili: {', '.join(illeg)}."
    elif illeg:
        testo = f"COOKIE MANCANTI per {sito}: non riesco a leggere {', '.join(illeg)}."
    else:
        testo = (f"COOKIE MANCANTI per {sito}: nessuna sorgente configurata (imposta COOKIES_BROWSER o "
                 "COOKIES_FILE in bots.env, oppure metti cookies.txt accanto a telegram_bot.py).")
    if not login and COOKIES_FILE and not Path(COOKIES_FILE).is_file():
        testo += f" File non trovato: {COOKIES_FILE}."
    righe = [r for r in (ultimo.dettagli if ultimo else "").splitlines() if r.strip()]
    if righe:
        testo += f"\nDettaglio: {righe[0].strip()[:200]}"
    return testo


@_sotto_lock
def download_ytdlp(url: str, folder: str, sorgente: tuple[str, str] | None = None) -> list[Path]:
    opts = {
        "outtmpl": f"{folder}/%(id)s.%(ext)s",
        "quiet": True,
        "noprogress": True,
        "noplaylist": True,
        "format": "bv*[ext=mp4]+ba/b[ext=mp4]/b",
        "merge_output_format": "mp4",
        "progress_hooks": [progress_hook],
    }
    if sorgente:
        tipo, valore = sorgente
        if tipo == "file":
            opts["cookiefile"] = valore
        else:
            opts["cookiesfrombrowser"] = (valore,)

    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=True)

    if info is None:
        raise RuntimeError("yt-dlp non ha restituito informazioni sul download")

    return collect_files(folder)


@_sotto_lock
def download_gallerydl(url: str, folder: str, sorgente: tuple[str, str] | None = None) -> list[Path]:
    cmd = [_python_console(), "-m", "gallery_dl", "-d", folder]
    if sorgente:
        tipo, valore = sorgente
        cmd += ["--cookies", valore] if tipo == "file" else ["--cookies-from-browser", valore]
    cmd.append(url)
    proc = popen_nowin(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    n, last_err = 0, ""
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        if line.startswith("[") or "error" in line.lower():
            last_err = line
        elif not line.startswith("#"):
            n += 1
            av = _AVANZ.get()
            if av is not None:
                av["n"] = n
            log(f"    gallery-dl: file {n}: {Path(line).name}")
    proc.wait()
    files = collect_files(folder)
    if not files and last_err:
        raise RuntimeError(last_err)
    return files


# domini di Twitter/X e dei suoi "fix" per l'embed: yt-dlp e gallery-dl vogliono x.com
_TW_HOSTS = {"twitter.com", "mobile.twitter.com", "m.twitter.com", "x.com", "fxtwitter.com",
             "vxtwitter.com", "fixupx.com", "fixvx.com", "twittpr.com"}


def normalizza_url(url: str) -> str:
    """I link di Twitter/X (anche fxtwitter, vxtwitter...) diventano https://x.com/... senza tracciamento."""
    u = urlsplit(url.strip())
    if u.netloc.lower().removeprefix("www.") in _TW_HOSTS:
        return urlunsplit(("https", "x.com", u.path.rstrip("/"), "", ""))
    return url


def _scarica(url: str, folder: str, sorgente: tuple[str, str] | None) -> list[Path]:
    """Un tentativo con una sola sorgente di cookie: prima yt-dlp, poi gallery-dl."""
    err_yt = ""
    log("  provo con yt-dlp…")
    try:
        files = download_ytdlp(url, folder, sorgente)
        if files:
            return files
        log("  yt-dlp: nessun file")
    except Exception as e:
        if sys.stdout.isatty():
            print()  # chiude l'eventuale riga di progresso
        righe = str(e).strip().splitlines()
        err_yt = righe[-1] if righe else "errore"
        log(f"  yt-dlp: {err_yt[:200]}")
    log("  provo con gallery-dl…")
    try:
        return download_gallerydl(url, folder, sorgente)
    except Exception as e:
        raise DownloadError(str(e), dettagli=f"{err_yt}\n{e}") from None


_TW_ID_RE = re.compile(r"/status(?:es)?/(\d+)")
_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}


def _is_twitter(url: str) -> bool:
    return urlsplit(url).netloc.lower().removeprefix("www.") in _TW_HOSTS


def download_fxtwitter(url: str, folder: str) -> list[Path]:
    """Ripiego senza login per i tweet pubblici: l'API di fxtwitter restituisce gli indirizzi dei media."""
    m = _TW_ID_RE.search(urlsplit(url).path)
    if not m:
        raise RuntimeError("link senza ID del tweet")
    tid = m.group(1)
    req = urllib.request.Request(f"https://api.fxtwitter.com/i/status/{tid}", headers=_UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        dati = json.load(r)
    media = ((dati.get("tweet") or {}).get("media") or {}).get("all") or []
    if not media:
        raise RuntimeError("fxtwitter: nessun media nel tweet (o tweet non pubblico)")
    for i, mdl in enumerate(media, 1):
        u = mdl.get("url")
        if not u:
            continue
        ext = Path(urlsplit(u).path).suffix.lower()
        if not ext:
            ext = ".mp4" if mdl.get("type") in ("video", "gif") else ".jpg"
        dest = Path(folder) / f"{tid}_{i}{ext}"
        log(f"    fxtwitter: scarico media {i}/{len(media)}")
        with urllib.request.urlopen(urllib.request.Request(u, headers=_UA), timeout=120) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
    return collect_files(folder)


def _download_cookie(url: str, folder: str) -> list[Path]:
    """Come _download_cookie_base, ma per Twitter/X se yt-dlp e gallery-dl falliscono prova fxtwitter."""
    try:
        return _download_cookie_base(url, folder)
    except (CookieError, DownloadError) as e:
        if not _is_twitter(normalizza_url(url)):
            raise
        log("  Twitter/X: provo il ripiego fxtwitter…")
        try:
            files = download_fxtwitter(normalizza_url(url), folder)
            if files:
                return files
        except Exception as e2:
            log(f"  fxtwitter: {str(e2)[:200]}")
        raise e


def _download_cookie_base(url: str, folder: str) -> list[Path]:
    """Scarica provando le sorgenti di cookie in ordine (es. firefox, chrome, cookies.txt).
    Se tutte falliscono per colpa dei cookie solleva CookieError (MANCANTI / NON AGGIORNATI)."""
    nuovo = normalizza_url(url)
    if nuovo != url:
        log(f"  link Twitter/X normalizzato: {nuovo}")
        url = nuovo

    sorgenti = sorgenti_cookie()
    fatti, ultimo = [], None
    for src in (sorgenti or [None]):
        nome = etichetta_cookie(src) if src else "nessun cookie"
        if len(sorgenti) > 1:
            log(f"  cookie: provo {nome}…")
        try:
            files = _scarica(url, folder, src)
            if fatti:
                log(f"  cookie: ha funzionato {nome} (prima: {', '.join(n for n, _ in fatti)})")
            return files
        except DownloadError as e:
            esito = _esito_cookie(e.dettagli)
            if esito is None:
                raise            # errore che non dipende dai cookie: inutile riprovare
            log(f"  cookie {nome}: {esito}")
            ultimo = e
            if src:
                fatti.append((nome, esito))
    sito = urlsplit(url).netloc.lower().removeprefix("www.")
    raise CookieError(_messaggio_cookie(sito, fatti, ultimo))


# ---------- fonte: post pubblici di Telegram ----------
# Link tipo https://t.me/canale/123 (anche t.me/s/canale/123). Si legge la pagina "embed" pubblica del
# post: niente login, niente account. Non funziona per canali privati/con contenuto protetto.
_TG_POST_RE = re.compile(r"^https?://(?:www\.)?(?:t|telegram)\.me/(?:s/)?([A-Za-z][A-Za-z0-9_]{3,})/(\d+)(?:[/?#].*)?$", re.I)
_TG_MEDIA_RE = re.compile(
    r"<video[^>]*?\ssrc=\"([^\"]+)\""                                              # video, GIF, video tondi
    r"|tgme_widget_message_photo_wrap[^>]*?background-image:\s*url\(['\"]?([^'\")]+)",  # foto
    re.I,
)
_TG_UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Mobile Safari/537.36"}


def _is_telegram_post(url: str) -> bool:
    return bool(_TG_POST_RE.match(url.strip()))


def _tg_media(pagina: str) -> list[tuple[str, str]]:
    """[(tipo, url)] nell'ordine in cui compaiono nella pagina, senza doppioni."""
    out, visti = [], set()
    for m in _TG_MEDIA_RE.finditer(pagina):
        u = html.unescape(m.group(1) or m.group(2))
        if u.startswith("//"):
            u = "https:" + u
        if u in visti or not u.startswith("http"):
            continue
        visti.add(u)
        out.append(("video" if m.group(1) else "foto", u))
    return out


def _tg_scarica_file(u: str, dest: Path, tentativi: int = 4):
    """Scarica un file dal CDN di Telegram. Gli errori temporanei (500/502/503, 429, timeout, rete) si
    riprovano con attesa crescente; 403/404 e simili no, perché ripeterli non serve."""
    for t in range(1, tentativi + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=_TG_UA), timeout=120) as r, \
                    open(dest, "wb") as f:
                shutil.copyfileobj(r, f)
            return
        except OSError as e:                      # URLError e HTTPError ne derivano
            dest.unlink(missing_ok=True)          # niente file a metà
            codice = e.code if isinstance(e, urllib.error.HTTPError) else None
            temporaneo = codice is None or codice == 429 or codice >= 500
            if not temporaneo or t == tentativi:
                raise
            attesa = 2 * t
            log(f"    errore temporaneo ({e}), riprovo tra {attesa}s ({t}/{tentativi - 1})")
            time.sleep(attesa)


def download_telegram(url: str, folder: str) -> list[Path]:
    m = _TG_POST_RE.match(url.strip())
    canale, post = m.group(1), m.group(2)
    log(f"  post pubblico di Telegram: {canale}/{post}")
    pagina = None
    for t in range(1, 4):
        try:
            req = urllib.request.Request(f"https://t.me/{canale}/{post}?embed=1&mode=tme", headers=_TG_UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                pagina = r.read().decode("utf-8", "replace")
            break
        except OSError as e:
            codice = e.code if isinstance(e, urllib.error.HTTPError) else None
            if t == 3 or (codice is not None and codice != 429 and codice < 500):
                raise RuntimeError(f"Telegram non raggiungibile: {e}") from None
            log(f"    pagina del post: errore temporaneo ({e}), riprovo…")
            time.sleep(2 * t)
    media = _tg_media(pagina)
    if not media:
        raise RuntimeError("Nessuna foto o video pubblico in questo post (solo testo, post cancellato, "
                           "canale privato o contenuto protetto?)")
    files = []
    for n, (tipo, u) in enumerate(media, 1):
        ext = Path(urlsplit(u).path).suffix.lower()
        if ext not in ALL_EXT:
            ext = ".mp4" if tipo == "video" else ".jpg"
        dest = Path(folder) / f"{canale}_{post}_{n}{ext}"
        log(f"    {tipo} {n}/{len(media)}…")
        try:
            _tg_scarica_file(u, dest)
        except OSError as e:
            cosa = "della foto" if tipo == "foto" else "del video"
            raise RuntimeError(f"download {cosa} {n} non riuscito: {e}") from None
        files.append(dest)
    return files


# ---------- protezione Instagram ----------
def _int_env(nome: str, default: int) -> int:
    try:
        return max(0, int(float(os.environ.get(nome, default))))
    except ValueError:
        return default


IG_AVVISO_ORA = _int_env("IG_AVVISO_ORA", 12)
IG_AVVISO_GIORNO = _int_env("IG_AVVISO_GIORNO", 60)
IG_MAX_ORA = _int_env("IG_MAX_ORA", 25)
IG_MAX_GIORNO = _int_env("IG_MAX_GIORNO", 100)
IG_PAUSA_SEC = float(_int_env("IG_PAUSA_SEC", 5))
IG_COOLDOWN_MIN = _int_env("IG_COOLDOWN_MIN", 30)
IG_STATO = Path(os.environ.get("IG_STATO_FILE") or Path(__file__).resolve().with_name("instagram_uso.json"))
_IG_HOSTS = ("instagram.com", "instagr.am", "ddinstagram.com")
# segni di una segnalazione di Instagram: i primi valgono sempre, gli altri solo se l'errore non è un
# CookieError (lì "rate-limit" compare insieme a "login required" e non dice quale dei due sia)
_IG_SEGNI_FORTI = ("http error 429", "too many requests", "wait a few minutes", "feedback_required",
                   "challenge_required", "checkpoint_required", "suspicious", "unusual activity", "action blocked")
_IG_SEGNI_DEBOLI = ("rate-limit", "rate limit", "ratelimit")
_IG_LOCK = threading.Lock()
_AVVISI: list[str] = []
_ig_ultimo_avviso = 0.0


class IgLimite(RuntimeError):
    """Download Instagram fermato per prudenza (tetto raggiunto o pausa dopo una segnalazione)."""


def _is_instagram(url: str) -> bool:
    host = urlsplit(url.strip()).netloc.lower().split("@")[-1].split(":")[0].removeprefix("www.")
    return any(host == h or host.endswith("." + h) for h in _IG_HOSTS)


def _minuti(sec: float) -> int:
    return max(1, int(sec / 60 + 0.999))


def _ig_leggi() -> dict:
    try:
        d = json.loads(IG_STATO.read_text(encoding="utf-8"))
        return {"t": sorted(float(x) for x in d.get("t", [])), "blocco_fino": float(d.get("blocco_fino") or 0)}
    except Exception:
        return {"t": [], "blocco_fino": 0.0}


def _ig_scrivi(d: dict):
    try:
        tmp = IG_STATO.with_name(f"{IG_STATO.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(d), encoding="utf-8")
        os.replace(tmp, IG_STATO)
    except OSError as e:
        log(f"  Instagram: contatore non salvato ({e})")


def prendi_avvisi() -> list[str]:
    """Avvisi accumulati dai download (es. Instagram): li restituisce e li svuota. Li mostrano i chiamanti."""
    with _IG_LOCK:
        a = _AVVISI[:]
        _AVVISI.clear()
        return a


def ig_avviso() -> str:
    """Come prendi_avvisi(), ma come testo unico già pronto da mostrare (stringa vuota se non ci sono avvisi).
    Lo usa org_bot.py (/invia) per accodare l'avviso Instagram al riepilogo."""
    avvisi = prendi_avvisi()
    return "⚠️ " + "\n⚠️ ".join(avvisi) if avvisi else ""


def _ig_prima():
    """Prima di ogni download Instagram: rispetta la pausa dopo una segnalazione, applica i tetti,
    aspetta la pausa minima, registra il download e prepara l'avviso se ci si avvicina ai tetti."""
    global _ig_ultimo_avviso
    with _IG_LOCK:
        ora = time.time()
        d = _ig_leggi()
        d["t"] = [x for x in d["t"] if ora - x < 86400]
        if d["blocco_fino"] > ora:
            raise IgLimite(f"Instagram in pausa per precauzione, ancora ~{_minuti(d['blocco_fino'] - ora)} min "
                           "(ha segnalato troppe richieste o attività sospetta).")
        recenti = [x for x in d["t"] if ora - x < 3600]
        n_ora, n_giorno = len(recenti), len(d["t"])
        if IG_MAX_ORA and n_ora >= IG_MAX_ORA:
            attesa = recenti[n_ora - IG_MAX_ORA] + 3600 - ora
            raise IgLimite(f"Limite Instagram: riprova tra ~{_minuti(attesa)} min "
                           f"({n_ora} download nell'ultima ora, tetto {IG_MAX_ORA}; IG_MAX_ORA=0 lo disattiva).")
        if IG_MAX_GIORNO and n_giorno >= IG_MAX_GIORNO:
            attesa = d["t"][n_giorno - IG_MAX_GIORNO] + 86400 - ora
            raise IgLimite(f"Limite Instagram: riprova tra ~{_minuti(attesa)} min "
                           f"({n_giorno} download in 24 h, tetto {IG_MAX_GIORNO}; IG_MAX_GIORNO=0 lo disattiva).")
        if IG_PAUSA_SEC and d["t"]:
            resta = d["t"][-1] + IG_PAUSA_SEC - ora
            if resta > 0:
                time.sleep(resta)    # sotto lock: i download Instagram di questo processo si mettono in fila
                ora = time.time()
        d["t"].append(ora)
        _ig_scrivi(d)
        n_ora += 1
        n_giorno += 1
        vicino = ((IG_AVVISO_ORA and n_ora >= IG_AVVISO_ORA) or (IG_AVVISO_GIORNO and n_giorno >= IG_AVVISO_GIORNO))
        if vicino and ora - _ig_ultimo_avviso > 600:    # al massimo un avviso ogni 10 minuti
            _ig_ultimo_avviso = ora
            tetti = []
            if IG_MAX_ORA:
                tetti.append(f"{IG_MAX_ORA}/ora")
            if IG_MAX_GIORNO:
                tetti.append(f"{IG_MAX_GIORNO}/24 h")
            testo = (f"Instagram: {n_ora} download nell'ultima ora e {n_giorno} nelle ultime 24 h. Troppe richieste "
                     "ravvicinate possono far scattare «attività sospetta» sull'account dei cookie: rallenta."
                     + (f" Blocco automatico a {' e '.join(tetti)}." if tetti else ""))
            _AVVISI.append(testo)
            log("  AVVISO " + testo)


def _ig_cooldown(motivo: str):
    with _IG_LOCK:
        d = _ig_leggi()
        d["blocco_fino"] = time.time() + IG_COOLDOWN_MIN * 60
        _ig_scrivi(d)
    log(f"  Instagram ha segnalato un problema ({motivo[:120]}): pausa di {IG_COOLDOWN_MIN} min")


# ---------- fonte: canali privati, con il TUO account personale (Telethon) ----------
# Tenuto separato dal bot: il bot (BOT_TOKEN) pubblica; l'account personale LEGGE i post di canali/gruppi
# privati di cui sei membro (link t.me/c/<id>/<post>) e, solo per «📚 Album» inline, INOLTRA nella chat
# l'album già inviato dal bot (compare come «Inoltrato da <bot>»). Ha sessione, contatore, pausa e righe di log proprie ("[account personale]").
# Setup: TG_API_ID e TG_API_HASH (da my.telegram.org) in bots.env, poi  python telegram_login.py  una volta.
_TG_PRIV_RE = re.compile(r"^https?://(?:www\.)?(?:t|telegram)\.me/c/(\d+)(?:/\d+)?/(\d+)(?:[/?#].*)?$", re.I)
TG_API_ID = int(os.environ.get("TG_API_ID") or 0)
TG_API_HASH = os.environ.get("TG_API_HASH", "")
TG_SESSION = os.environ.get("TG_SESSION") or str(Path(__file__).resolve().with_name("utente"))   # + ".session"
TG_UTENTE_PAUSA = float(_int_env("TG_UTENTE_PAUSA_SEC", 3))        # pausa minima tra due richieste
TG_UTENTE_MAX_GIORNO = _int_env("TG_UTENTE_MAX_GIORNO", 100)       # tetto richieste al giorno (0 = nessuno)
TG_UTENTE_MAX_MB = _int_env("TG_UTENTE_MAX_MB", 200)               # non scarica file più grandi
TG_UTENTE_STATO = Path(os.environ.get("TG_UTENTE_STATO_FILE")
                       or Path(__file__).resolve().with_name("telegram_utente_uso.json"))
_tg_utente_lock = threading.Lock()
_tg_utente_ultima = [0.0]


def _tg_ricarica():
    """Rilegge le impostazioni TG_*. Branch può essere avviato senza bots.env nel suo ambiente (i bot lo
    ricevono da bot_manager, Branch no): se i valori non ci sono nell'ambiente li cerco nel file."""
    global TG_API_ID, TG_API_HASH, TG_SESSION, TG_UTENTE_PAUSA, TG_UTENTE_MAX_GIORNO, TG_UTENTE_MAX_MB, TG_UTENTE_STATO
    env = dict(os.environ)
    try:
        import bot_manager
        env = bot_manager.carica_env()
    except Exception:
        pass

    def num(nome, default):
        try:
            return max(0, int(float(env.get(nome, default))))
        except ValueError:
            return default

    TG_API_ID = num("TG_API_ID", 0)
    TG_API_HASH = (env.get("TG_API_HASH") or "").strip()
    TG_SESSION = env.get("TG_SESSION") or str(Path(__file__).resolve().with_name("utente"))
    TG_UTENTE_PAUSA = float(num("TG_UTENTE_PAUSA_SEC", 3))
    TG_UTENTE_MAX_GIORNO = num("TG_UTENTE_MAX_GIORNO", 100)
    TG_UTENTE_MAX_MB = num("TG_UTENTE_MAX_MB", 200)
    TG_UTENTE_STATO = Path(env.get("TG_UTENTE_STATO_FILE")
                           or Path(__file__).resolve().with_name("telegram_utente_uso.json"))


def _is_telegram_private(url: str) -> bool:
    return bool(_TG_PRIV_RE.match(url.strip()))


def _tg_utente_conta() -> int:
    """Conta le richieste dell'account personale (a parte da quelle del bot) e applica il tetto giornaliero."""
    oggi = datetime.date.today().isoformat()
    try:
        d = json.loads(TG_UTENTE_STATO.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    n = int(d.get("n", 0)) if d.get("giorno") == oggi else 0
    if TG_UTENTE_MAX_GIORNO and n >= TG_UTENTE_MAX_GIORNO:
        raise RuntimeError(f"Account personale: raggiunto il tetto di {TG_UTENTE_MAX_GIORNO} richieste per oggi "
                           "(si cambia con TG_UTENTE_MAX_GIORNO)")
    try:
        TG_UTENTE_STATO.write_text(json.dumps({"giorno": oggi, "n": n + 1}), encoding="utf-8")
    except OSError as e:
        log(f"  [account personale] contatore non salvato: {e}")
    return n + 1


async def _tg_utente_client():
    """Client Telethon dell'account personale, già connesso e controllato (mai codici interattivi)."""
    from telethon import TelegramClient

    # flood_sleep_threshold=0: se Telegram chiede di aspettare non dormo in silenzio, mi fermo e lo dico
    client = TelegramClient(TG_SESSION, TG_API_ID, TG_API_HASH, flood_sleep_threshold=0)
    await client.connect()                       # niente start(): non deve mai chiedere codici da solo
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("sessione dell'account personale scaduta o assente: rilancia  python telegram_login.py")
        me = await client.get_me()
        if getattr(me, "bot", False):
            raise RuntimeError("La sessione salvata è di un BOT, non del tuo account: cancella utente.session e "
                               "rilancia  python telegram_login.py  inserendo il tuo NUMERO DI TELEFONO "
                               "(non il token del bot).")
    except BaseException:
        await client.disconnect()
        raise
    return client


def _tg_utente_esegui(descrizione: str, fabbrica, scrive: bool = False):
    """Controlli, lock, pausa minima e contatore comuni a tutte le richieste dell'account personale.
    `fabbrica` è una funzione senza argomenti che restituisce la coroutine da eseguire."""
    _tg_ricarica()
    mancano = [n for n, v in (("TG_API_ID", TG_API_ID), ("TG_API_HASH", TG_API_HASH)) if not v]
    if mancano:
        raise RuntimeError("Per questo link serve l'account personale: mancano " + " e ".join(mancano) + " in "
                           f"{Path(__file__).resolve().with_name('bots.env')} (vedi telegram_login.py).")
    try:
        import telethon  # noqa: F401
    except ImportError:
        raise RuntimeError("Manca la libreria telethon:  pip install telethon") from None
    if not Path(TG_SESSION + ".session").exists():
        raise RuntimeError("Account personale non collegato: lancia  python telegram_login.py  una volta.")
    with _tg_utente_lock:                        # una richiesta alla volta, con pausa minima
        attesa = TG_UTENTE_PAUSA - (time.time() - _tg_utente_ultima[0])
        if attesa > 0:
            time.sleep(attesa)
        n = _tg_utente_conta()
        log(f"  [account personale] richiesta n. {n} di oggi: {descrizione} "
            f"({'inoltro di un album del bot' if scrive else 'sola lettura'})")
        try:
            return asyncio.run(fabbrica())
        finally:
            _tg_utente_ultima[0] = time.time()


async def _tg_utente_scarica(cid: int, mid: int, folder: str) -> list[Path]:
    from telethon.errors import ChannelPrivateError, FloodWaitError
    from telethon.tl.types import PeerChannel

    peer = PeerChannel(cid)
    client = await _tg_utente_client()
    try:
        try:
            try:
                msg = await client.get_messages(peer, ids=mid)
            except ValueError:                   # canale non ancora nella cache della sessione
                await client.get_dialogs()
                msg = await client.get_messages(peer, ids=mid)
            if not msg:
                raise RuntimeError("Post non trovato: cancellato, oppure il tuo account non è nel canale.")
            msgs = [msg]
            if msg.grouped_id:                   # album: prendo i messaggi vicini dello stesso gruppo
                vicini = await client.get_messages(peer, ids=list(range(max(1, mid - 9), mid + 10)))
                msgs = sorted((m for m in vicini if m and m.grouped_id == msg.grouped_id), key=lambda m: m.id)
            files = []
            for m in msgs:
                if not (m.photo or m.video or m.gif or m.video_note):
                    continue
                size = getattr(m.file, "size", 0) or 0
                if TG_UTENTE_MAX_MB and size > TG_UTENTE_MAX_MB * 1_000_000:
                    log(f"  [account personale] salto un file da {mb(size)} (tetto {TG_UTENTE_MAX_MB} MB)")
                    continue
                p = await client.download_media(m, file=folder + os.sep)
                if p and Path(p).suffix.lower() in ALL_EXT:
                    files.append(Path(p))
            return files
        except ChannelPrivateError:
            raise RuntimeError("Il tuo account non ha accesso a questo canale (non sei membro?).") from None
        except FloodWaitError as e:
            raise RuntimeError(f"Telegram chiede di aspettare {e.seconds} s per l'account personale: "
                               "riprova più tardi.") from None
    finally:
        await client.disconnect()


def download_telegram_utente(url: str, folder: str) -> list[Path]:
    m = _TG_PRIV_RE.match(url.strip())
    cid, mid = int(m.group(1)), int(m.group(2))
    files = _tg_utente_esegui(f"canale {cid}, post {mid}", lambda: _tg_utente_scarica(cid, mid, folder))
    if not files:
        raise RuntimeError("Nessuna foto o video in questo post (solo testo, o file oltre il tetto di dimensione).")
    return files


# ---------- fonte: storie di Telegram ----------
# Link tipo https://t.me/utente/s/123. Le storie non sono visibili ai bot né dalla pagina pubblica: serve
# l'account personale (Telethon), con la stessa sessione, lo stesso contatore e le stesse pause dei canali privati.
# Funziona solo per le storie che il TUO account può vedere (attive, o fissate nel profilo).
_TG_STORIA_RE = re.compile(r"^https?://(?:www\.)?(?:t|telegram)\.me/([A-Za-z][A-Za-z0-9_]{3,})/s/(\d+)(?:[/?#].*)?$", re.I)


def _is_telegram_storia(url: str) -> bool:
    return bool(_TG_STORIA_RE.match(url.strip()))


async def _tg_utente_scarica_storia(utente: str, sid: int, folder: str) -> list[Path]:
    from telethon.errors import FloodWaitError, RPCError
    try:
        from telethon.tl.functions.stories import GetStoriesByIDRequest
    except ImportError:
        raise RuntimeError("Questa versione di telethon non supporta le storie:  pip install -U telethon") from None

    client = await _tg_utente_client()
    try:
        try:
            peer = await client.get_input_entity(utente)
            res = await client(GetStoriesByIDRequest(peer=peer, id=[sid]))
        except ValueError:
            raise RuntimeError(f"Utente o canale @{utente} non trovato.") from None
        except FloodWaitError as e:
            raise RuntimeError(f"Telegram chiede di aspettare {e.seconds} s per l'account personale: "
                               "riprova più tardi.") from None
        except RPCError as e:
            raise RuntimeError(f"Telegram ha rifiutato la richiesta della storia: {e}") from None
        files = []
        for st in res.stories:
            media = getattr(st, "media", None)   # le storie cancellate o saltate non hanno media
            if media is None:
                continue
            size = getattr(getattr(media, "document", None), "size", 0) or 0
            if TG_UTENTE_MAX_MB and size > TG_UTENTE_MAX_MB * 1_000_000:
                log(f"  [account personale] salto una storia da {mb(size)} (tetto {TG_UTENTE_MAX_MB} MB)")
                continue
            p = await client.download_media(media, file=folder + os.sep)
            if p and Path(p).suffix.lower() in ALL_EXT:
                files.append(Path(p))
        return files
    finally:
        await client.disconnect()


def download_telegram_storia(url: str, folder: str) -> list[Path]:
    m = _TG_STORIA_RE.match(url.strip())
    utente, sid = m.group(1), int(m.group(2))
    files = _tg_utente_esegui(f"storia {sid} di @{utente}", lambda: _tg_utente_scarica_storia(utente, sid, folder))
    if not files:
        raise RuntimeError("Nessun file in questa storia (scaduta, cancellata, non visibile al tuo account "
                           "o oltre il tetto di dimensione).")
    return files


def download(url: str, folder: str) -> list[Path]:
    """Punto d'ingresso dei download. Per i link Instagram aggiunge la protezione (conteggio, avviso,
    pausa minima, tetti e pausa dopo una segnalazione); poi scarica con _download_cookie."""
    if _is_telegram_storia(url):        # storia di Telegram: account personale, in sola lettura
        return download_telegram_storia(url, folder)
    if _is_telegram_private(url):       # canale privato: account personale, in sola lettura
        return download_telegram_utente(url, folder)
    if _is_telegram_post(url):          # post pubblico di Telegram: nessun cookie, nessun yt-dlp
        return download_telegram(url, folder)
    ig = _is_instagram(url)
    if ig:
        _ig_prima()
    try:
        return _download_cookie(url, folder)
    except Exception as e:
        if ig and IG_COOLDOWN_MIN:
            testo = f"{e} {getattr(e, 'dettagli', '')}".lower()
            forte = any(k in testo for k in _IG_SEGNI_FORTI)
            debole = not isinstance(e, CookieError) and any(k in testo for k in _IG_SEGNI_DEBOLI)
            if forte or debole:
                riga = next((r.strip() for r in f"{e}\n{getattr(e, 'dettagli', '')}".splitlines() if r.strip()), "")
                _ig_cooldown(riga)
                raise IgLimite(f"Instagram ha segnalato troppe richieste o attività sospetta: lo metto in pausa "
                               f"per {IG_COOLDOWN_MIN} min. Dettaglio: {riga[:150]}") from e
        raise


# ---------- cache dei file già inviati (file_id di Telegram) ----------
CACHE_GIORNI = _int_env("TG_CACHE_GIORNI", 30)       # 0 = disattivata
CACHE_FILE = Path(os.environ.get("TG_CACHE_FILE") or Path(__file__).resolve().with_name("download_cache.json"))
CACHE_MAX_VOCI = 2000
_CACHE_LOCK = threading.Lock()
# parametri di tracciamento che non cambiano il contenuto del link
_TRACK = {"igsh", "igshid", "_t", "_r", "_d", "is_from_webapp", "sender_device", "sender_web_id",
          "share_app_id", "share_author_id", "share_link_id", "share_item_id", "share_id",
          "si", "feature", "rdt", "context", "ref", "ref_source"}
_TIPI_CACHE = ("photo", "video", "animation", "document")


def chiave_url(url: str) -> str:
    """Identificativo stabile del link: stesso post condiviso in modi diversi = stessa chiave."""
    u = urlsplit(normalizza_url(url).strip())
    host = u.netloc.lower().removeprefix("www.")
    q = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
         if k.lower() not in _TRACK and not k.lower().startswith("utm_")]
    norm = urlunsplit(("https", host, u.path.rstrip("/"), urlencode(sorted(q)), ""))
    return hashlib.sha1(norm.encode()).hexdigest()[:16]


def _cache_carica() -> dict:
    """Voci valide del bot corrente (i file_id di un altro token non servono)."""
    try:
        d = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if d.get("bot") != TOKEN.split(":")[0]:
            return {}
        return d.get("voci", {})
    except Exception:
        return {}


def _cache_scrivi(voci: dict):
    try:
        if len(voci) > CACHE_MAX_VOCI:      # tengo le più recenti
            voci = dict(sorted(voci.items(), key=lambda kv: kv[1].get("t", 0))[-CACHE_MAX_VOCI:])
        tmp = CACHE_FILE.with_name(f"{CACHE_FILE.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"bot": TOKEN.split(":")[0], "voci": voci}), encoding="utf-8")
        os.replace(tmp, CACHE_FILE)
    except OSError as e:
        log(f"  cache non salvata ({e})")


def cache_leggi(url: str) -> list | None:
    """[[tipo, file_id, nome, byte], ...] di un link già inviato, oppure None (assente o scaduto)."""
    if not CACHE_GIORNI:
        return None
    with _CACHE_LOCK:
        voci = _cache_carica()
        e = voci.get(chiave_url(url))
        if not e:
            return None
        if time.time() - e.get("t", 0) > CACHE_GIORNI * 86400:
            voci.pop(chiave_url(url), None)
            _cache_scrivi(voci)
            return None
        f = e.get("f") or []
        return f if f and all(len(x) == 4 and x[0] in _TIPI_CACHE for x in f) else None


def cache_salva(url: str, file_list: list):
    if not CACHE_GIORNI or not file_list:
        return
    with _CACHE_LOCK:
        voci = _cache_carica()
        voci[chiave_url(url)] = {"t": time.time(), "f": file_list}
        _cache_scrivi(voci)


def cache_elimina(url: str):
    with _CACHE_LOCK:
        voci = _cache_carica()
        if voci.pop(chiave_url(url), None) is not None:
            _cache_scrivi(voci)


def voci_da_cache_invio(files: list[Path], cache: dict) -> list | None:
    """Dal dict riempito da send_files: la lista da salvare, solo se TUTTI i file hanno un file_id."""
    try:
        return [[*cache[str(p)], p.name, p.stat().st_size] for p in files]
    except (KeyError, OSError):
        return None


class CacheFallita(Exception):
    def __init__(self, msg: str, parziale: bool):
        super().__init__(msg)
        self.parziale = parziale     # True: qualcosa è già stato inviato


# ---------- invio ----------
def _ffmpeg(cmd: list[str], cosa: str):
    """Esegue ffmpeg; se fallisce solleva un errore con le ultime righe di stderr (non il solo codice di uscita)."""
    try:
        run_nowin(cmd, capture_output=True, check=True)
    except FileNotFoundError:
        raise RuntimeError("ffmpeg non trovato nel PATH") from None
    except subprocess.CalledProcessError as e:
        righe = (e.stderr or b"").decode(errors="replace").strip().splitlines()
        coda = " | ".join(r.strip() for r in righe[-3:]) or f"codice {e.returncode}"
        log(f"    ffmpeg ({cosa}) fallito:\n" + "\n".join(righe[-10:]))
        raise RuntimeError(f"ffmpeg ha fallito ({cosa}): {coda[:300]}") from None


COMPRESS_TENTATIVI = 3   # tentativi di compressione, ognuno con un bitrate più basso del precedente


def compress_video(path: Path, target_bytes: int = 45 * 1024 * 1024,
                   limite_bytes: int | None = None) -> Path:
    """Ricodifica il video con ffmpeg puntando a target_bytes. Se il risultato sfora comunque
    limite_bytes (default: target_bytes) riprova con un bitrate ridotto, fino a COMPRESS_TENTATIVI volte."""
    limite = limite_bytes or target_bytes
    out = path.with_name(path.stem + "_small.mp4")
    probe = run_nowin(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        raise RuntimeError(f"ffprobe fallito:\n{probe.stderr.strip()}")

    output = probe.stdout.strip()
    if not output:
        raise RuntimeError("ffprobe non ha restituito la durata del video")

    duration = float(output)
    if duration <= 0:
        raise ValueError("Durata video non valida")

    audio_bps = 96_000
    video_bps = int(target_bytes * 8 / duration) - audio_bps
    for tentativo in range(1, COMPRESS_TENTATIVI + 1):
        if video_bps < 100_000:
            raise ValueError(f"video troppo lungo per stare in {mb(limite)}")
        log(f"    comprimo {path.name} (~{video_bps // 1000} kbps, tentativo {tentativo}/{COMPRESS_TENTATIVI})…")
        _ffmpeg(["ffmpeg", "-y", "-i", str(path), "-c:v", "libx264", "-preset", "veryfast",
                 "-b:v", str(video_bps), "-maxrate", str(video_bps),
                 "-bufsize", str(video_bps * 2), "-c:a", "aac", "-b:a", "96k",
                 "-movflags", "+faststart", str(out)], "compressione")
        size = out.stat().st_size
        log(f"    compresso: {mb(size)}")
        if size <= limite or tentativo == COMPRESS_TENTATIVI:
            break
        # sforato: abbasso il bitrate in proporzione (almeno -15%) e riprovo
        video_bps = int(video_bps * min(0.85, limite * 0.95 / size))
        log(f"    ancora sopra {mb(limite)}: riprovo con un bitrate più basso")
    return out


MAX_GIF_DIM = 1280   # lato massimo (px) dell'mp4 ottenuto da una GIF


def _frazione(s) -> float:
    """'100/9' -> 11.1 ; 0 se non leggibile."""
    try:
        n, _, d = str(s).partition("/")
        return float(n) / float(d or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def gif_info(path: Path) -> dict | None:
    """Legge la GIF con ffprobe: larghezza, altezza, fotogrammi, fps e durata di un giro (s).
    None se ffprobe non riesce a leggerla."""
    r = run_nowin(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,nb_read_frames,avg_frame_rate,r_frame_rate:format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return None
    try:
        d = json.loads(r.stdout)
        s = d["streams"][0]
        frames = int(s.get("nb_read_frames") or 0)
        fps = _frazione(s.get("avg_frame_rate")) or _frazione(s.get("r_frame_rate")) or 10.0
        dur = float(d.get("format", {}).get("duration") or 0) or (frames / fps if fps else 0.0)
        return {"w": int(s["width"]), "h": int(s["height"]), "frames": frames, "fps": fps, "dur": dur}
    except (KeyError, IndexError, ValueError, TypeError, json.JSONDecodeError):
        return None


def gif_to_mp4(path: Path, target_bytes: int | None = None) -> Path:
    """Converte una GIF in mp4 H.264 muto (a parità di aspetto pesa molte volte meno), usando
    ffprobe per scegliere dimensioni pari, lato massimo, fps e, se serve, un tetto di bitrate
    perché il file stia sotto target_bytes. Una GIF senza animazione viene lasciata com'è
    (restituisce lo stesso percorso)."""
    info = gif_info(path)
    if info and info["frames"] <= 1:
        log(f"    {path.name}: GIF senza animazione, non la converto")
        return path
    out = path.with_name(path.stem + "_gif.mp4")

    filtri = []
    if info:
        if info["fps"] > 30:
            filtri.append("fps=30")
        k = min(1.0, MAX_GIF_DIM / max(info["w"], info["h"]))
        filtri.append(f"scale={max(2, int(info['w'] * k) // 2 * 2)}:{max(2, int(info['h'] * k) // 2 * 2)}")
        desc = f"{info['w']}x{info['h']}, {info['frames']} fotogrammi, {info['dur']:.1f}s"
    else:
        filtri.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
        desc = "ffprobe non l'ha letta"
    log(f"    converto {path.name} ({mb(path.stat().st_size)}; {desc}) in mp4…")

    cmd = ["ffmpeg", "-y", "-i", str(path), "-an", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "23", "-pix_fmt", "yuv420p", "-vf", ",".join(filtri)]
    if target_bytes and info and info["dur"] > 0:
        # qualità costante, ma con un tetto di bitrate così il file sta nel limite
        bps = max(100_000, int(target_bytes * 8 / info["dur"]))
        cmd += ["-maxrate", str(bps), "-bufsize", str(bps * 2)]
    cmd += ["-movflags", "+faststart", str(out)]
    _ffmpeg(cmd, "conversione GIF")
    log(f"    convertita: {mb(out.stat().st_size)}")
    return out


def _moov_all_inizio(path: Path) -> bool:
    """True se l'atom 'moov' precede 'mdat' (il video parte senza scaricare tutto il file)."""
    try:
        totale = path.stat().st_size
        with open(path, "rb") as f:
            pos = 0
            while pos + 8 <= totale:
                f.seek(pos)
                testa = f.read(16)
                size = int.from_bytes(testa[:4], "big")
                tipo = testa[4:8]
                if size == 1:
                    size = int.from_bytes(testa[8:16], "big")
                elif size == 0:
                    size = totale - pos
                if tipo == b"moov":
                    return True
                if tipo == b"mdat" or size < 8:
                    return False
                pos += size
    except Exception:
        pass
    return False


def _rendi_riproducibile(path: Path) -> Path:
    """Garantisce un .mp4 H.264 8-bit (yuv420p) con audio AAC/MP3 e moov all'inizio:
    è ciò che Telegram e Discord mostrano come video con anteprima. Un .m4v, .mkv o .webm
    arriva invece come semplice file. Se il file è già a posto lo lascia com'è."""
    r = run_nowin(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        log(f"  ffprobe non riesce a leggere {path.name}: lo mando com'è")
        return path
    streams = json.loads(r.stdout).get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"
              and not s.get("disposition", {}).get("attached_pic")), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if v is None:
        return path
    ok_v = (v.get("codec_name") == "h264" and v.get("pix_fmt") == "yuv420p"
            and v.get("width", 2) % 2 == 0 and v.get("height", 2) % 2 == 0)
    ok_a = a is None or a.get("codec_name") in ("aac", "mp3")
    if path.suffix.lower() == ".mp4" and ok_v and ok_a and _moov_all_inizio(path):
        return path

    desc = (f"video {v.get('codec_name')}/{v.get('pix_fmt')}, "
            f"audio {a.get('codec_name') if a else 'nessuno'}, contenitore {path.suffix.lower()}")
    out = path.with_name(path.stem + "_dc.mp4")
    cmd = ["ffmpeg", "-y", "-i", str(path), "-map", "0:v:0", "-map", "0:a:0?"]
    cmd += (["-c:v", "copy"] if ok_v else
            ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p",
             "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"])
    cmd += ["-c:a", "copy"] if ok_a else ["-c:a", "aac", "-b:a", "128k"]
    cmd += ["-movflags", "+faststart", str(out)]
    log(f"  {path.name}: {desc} -> " + ("rimballo in mp4" if ok_v else "ricodifico in H.264"))
    try:
        run_nowin(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        log(f"  ffmpeg fallito su {path.name}: {e.stderr.decode(errors='replace')[-200:]}")
        return path
    return out


async def rendi_riproducibile(path: Path) -> Path:
    if path.suffix.lower() not in VIDEO_EXT:
        return path
    return await asyncio.to_thread(_rendi_riproducibile, path)


def _id_file(msg) -> tuple[str, str] | None:
    """(tipo, file_id) di un file appena inviato: serve a rimandarlo ad altri canali senza ricaricarlo."""
    try:
        if msg.animation:
            return "animation", msg.animation.file_id
        if msg.video:
            return "video", msg.video.file_id
        if msg.photo:
            return "photo", msg.photo[-1].file_id
        if msg.document:
            return "document", msg.document.file_id
    except Exception:
        pass
    return None


async def _invia_per_id(bot, chat_id, tipo: str, file_id: str, **kw):
    if tipo == "animation":
        return await bot.send_animation(chat_id, file_id, **kw)
    if tipo == "video":
        return await bot.send_video(chat_id, file_id, supports_streaming=True, **kw)
    if tipo == "photo":
        return await bot.send_photo(chat_id, file_id, **kw)
    return await bot.send_document(chat_id, file_id, **kw)


async def send_single(bot, chat_id, path: Path, cache: dict | None = None, **kw):
    """`cache` (facoltativa, dict condiviso tra i canali): il primo canale carica il file, gli altri lo
    ricevono per file_id da Telegram, senza un nuovo upload (né ricompressione)."""
    chiave = str(path)
    if cache is not None and chiave in cache:
        tipo, fid = cache[chiave]
        try:
            await _invia_per_id(bot, chat_id, tipo, fid, **kw)
            log(f"    invio: {path.name} (già su Telegram, nessun nuovo upload)")
            return
        except Exception as e:
            log(f"    riuso di {path.name} non riuscito ({e}): lo carico di nuovo")
            cache.pop(chiave, None)
    ext, size = path.suffix.lower(), path.stat().st_size
    come_gif = ext in ANIM_EXT   # una GIF convertita in mp4 va mandata comunque come animazione
    if size > MAX_FILE:
        if ext in ANIM_EXT:
            # una GIF così grande diventa un mp4 muto, molto più leggero
            nuovo = await asyncio.to_thread(gif_to_mp4, path, int(MAX_FILE * 0.9))
            if nuovo == path:   # GIF senza animazione: non c'è niente da convertire
                raise ValueError(f"{path.name} supera i 50 MB")
            path = nuovo
            size = path.stat().st_size
            ext = path.suffix.lower()
        elif ext not in VIDEO_EXT:
            raise ValueError(f"{path.name} supera i 50 MB")
        if size > MAX_FILE:
            path = await asyncio.to_thread(compress_video, path, limite_bytes=MAX_FILE)
            size = path.stat().st_size
            if size > MAX_FILE:
                raise ValueError(f"{path.name} è ancora sopra i 50 MB")
            ext = path.suffix.lower()
    log(f"    invio: {path.name} ({mb(size)})")
    with open(path, "rb") as f:
        if come_gif or ext in ANIM_EXT:
            msg = await bot.send_animation(chat_id, f, **kw)
        elif ext in VIDEO_EXT:
            msg = await bot.send_video(chat_id, f, supports_streaming=True, **kw)
        elif ext in IMAGE_EXT and size <= MAX_PHOTO:
            try:
                msg = await bot.send_photo(chat_id, f, **kw)
            except Exception:
                f.seek(0)
                msg = await bot.send_document(chat_id, f, **kw)
        else:
            msg = await bot.send_document(chat_id, f, **kw)
    if cache is not None:
        info = _id_file(msg)
        if info:
            cache[chiave] = info


async def send_files(bot, chat_id, files: list[Path], cache: dict | None = None,
                     caption: str | None = None, **kw) -> list[str]:
    """`cache` (facoltativa): vedi send_single. Chi la passa deve usare lo stesso dict per tutti i canali.
    `caption`: didascalia (es. il link di origine): su ogni messaggio, e nell'album sul primo file."""
    caption = caption[:1024] if caption else None
    kw_cap = {**kw, "caption": caption} if caption else kw
    errors = []
    groupable, singles = [], []

    for p in files:
        ext, size = p.suffix.lower(), p.stat().st_size

        if ext in IMAGE_EXT and size <= MAX_PHOTO:
            groupable.append(p)
        elif ext in VIDEO_EXT and size <= MAX_FILE:
            groupable.append(p)
        else:
            singles.append(p)

    # album da massimo 10 elementi
    for i in range(0, len(groupable), 10):
        chunk = groupable[i:i + 10]

        if len(chunk) == 1:
            singles.append(chunk[0])
            continue

        log(f"    invio album di {len(chunk)} file…")

        handles = []
        media = []

        try:
            for p in chunk:
                didascalia = caption if not media else None     # nell'album la didascalia sta sul primo file
                nota = cache.get(str(p)) if cache is not None else None
                if nota and nota[0] in ("video", "photo"):      # già caricato su Telegram: uso il suo file_id
                    if nota[0] == "video":
                        media.append(InputMediaVideo(media=nota[1], supports_streaming=True, caption=didascalia))
                    else:
                        media.append(InputMediaPhoto(media=nota[1], caption=didascalia))
                    continue
                f = open(p, "rb")
                handles.append(f)

                if p.suffix.lower() in VIDEO_EXT:
                    media.append(InputMediaVideo(media=f, supports_streaming=True, caption=didascalia))
                else:
                    media.append(InputMediaPhoto(media=f, caption=didascalia))

            inviati = await bot.send_media_group(chat_id, media, **kw)
            if cache is not None:
                try:
                    for p, m in zip(chunk, inviati):
                        info = _id_file(m)
                        if info and str(p) not in cache:
                            cache[str(p)] = info
                except Exception:
                    pass
            await asyncio.sleep(0.3)

        except Exception as e:
            log(f"    album non riuscito ({e}), li mando uno per uno")
            singles.extend(chunk)

        finally:
            for f in handles:
                try:
                    f.close()
                except Exception:
                    pass

    for p in singles:
        try:
            await send_single(bot, chat_id, p, cache=cache, **kw_cap)
        except Exception as e:
            log(f"    ERRORE invio {p.name}: {e}")
            errors.append(f"{p.name}: {e}")

    return errors

async def invia_da_cache(bot, chat_id, voci: list, caption: str | None = None, **kw):
    """Rimanda per file_id i file già inviati. Se qualcosa non va solleva CacheFallita
    (parziale=True se almeno un messaggio è già partito: in quel caso non si riscarica, per non duplicare)."""
    caption = caption[:1024] if caption else None
    kw_cap = {**kw, "caption": caption} if caption else kw
    inviati = 0
    album = [v for v in voci if v[0] in ("photo", "video")]
    singoli = [v for v in voci if v[0] not in ("photo", "video")]
    try:
        for i in range(0, len(album), 10):
            chunk = album[i:i + 10]
            if len(chunk) == 1:
                singoli.append(chunk[0])
                continue
            media = [InputMediaVideo(media=v[1], supports_streaming=True, caption=caption if j == 0 else None)
                     if v[0] == "video" else InputMediaPhoto(media=v[1], caption=caption if j == 0 else None)
                     for j, v in enumerate(chunk)]
            await bot.send_media_group(chat_id, media, **kw)
            inviati += len(chunk)
            await asyncio.sleep(0.3)
        for v in singoli:
            await _invia_per_id(bot, chat_id, v[0], v[1], **kw_cap)
            inviati += 1
    except Exception as e:
        raise CacheFallita(str(e), inviati > 0) from e


async def report_from_channel(ctx: ContextTypes.DEFAULT_TYPE, channel_id: int, text: str):
    """Avviso in privato; se non è possibile, messaggio nel canale che si cancella da solo."""
    try:
        await ctx.bot.send_message(OWNER, text)
    except Exception:
        m = await ctx.bot.send_message(channel_id, text)
        await asyncio.sleep(20)
        try:
            await m.delete()
        except Exception:
            pass


# ---------- helper comuni ----------
ANONYMOUS_ADMIN_ID = 1087968824   # mittente dei messaggi di un admin "anonimo" nei gruppi


def kw_topic(msg) -> dict:
    """Se il messaggio è in un topic (forum), le risposte vanno nello stesso topic."""
    return {"message_thread_id": msg.message_thread_id} if msg.is_topic_message else {}


def e_owner(user, cosa: str) -> bool:
    """True se il mittente è OWNER_ID; altrimenti scrive il motivo nel log."""
    if user and user.id == OWNER:
        return True
    if user and user.id == ANONYMOUS_ADMIN_ID:
        log(f"Ignorato {cosa}: mittente anonimo (admin con «Resta anonimo»), non posso sapere chi sia")
    else:
        log(f"Ignorato {cosa} da {user.id if user else '?'}: non è OWNER_ID")
    return False


def chat_comandi(chat) -> bool:
    """I comandi /xxx funzionano in privato e in qualsiasi gruppo (nei canali non arrivano)."""
    return chat.type in (ChatType.PRIVATE, ChatType.GROUP, ChatType.SUPERGROUP)


# ---------- handler ----------
async def handle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat:
        return

    # chi può usare il bot, e dove serve il tag
    if chat.type == ChatType.CHANNEL:
        auto = chat.id in AUTO_CHANNELS
        if CHANNELS and chat.id not in CHANNELS and not auto:
            log(f"Ignorato post nel canale {chat.id}: non è in CHANNEL_ID")
            return
        needs_tag = not auto   # nei canali automatici il tag non serve
    elif chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        if not e_owner(user, "messaggio nel gruppo"):
            return
        needs_tag = True
    elif chat.type == ChatType.PRIVATE:
        if not e_owner(user, "messaggio privato"):
            return
        needs_tag = False
    else:
        return

    text = msg.text or msg.caption or ""
    via_me = bool(msg.via_bot and msg.via_bot.id == ctx.bot.id)   # inviato con l'inline mode di questo bot
    if via_me and text.startswith(ALBUM_MARK) and _album_utente_attivo():
        return                      # l'album lo inoltra l'account personale (vedi _album_scelto)
    if needs_tag and not via_me and f"@{ctx.bot.username}".lower() not in text.lower():
        return
    urls = URL_RE.findall(text)
    if urls:
        await processa_link(ctx, msg, chat, urls)


async def cmd_url(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/url <link> (oppure in risposta a un messaggio con un link): come incollare il link, ma
    funziona in qualsiasi gruppo senza tag."""
    msg, chat, user = update.effective_message, update.effective_chat, update.effective_user
    if not msg or not chat or not chat_comandi(chat) or not e_owner(user, "/url"):
        return
    urls = URL_RE.findall(msg.text or "")
    if not urls and msg.reply_to_message:
        r = msg.reply_to_message
        urls = URL_RE.findall(r.text or r.caption or "")
    if not urls:
        await msg.reply_text("Uso: /url <link>  (oppure rispondi a un messaggio con un link)", **kw_topic(msg))
        return
    await processa_link(ctx, msg, chat, urls)


async def cmd_riscarica(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/riscarica <link> (o in risposta a un messaggio col link): come /url ma ignora la cache."""
    msg, chat, user = update.effective_message, update.effective_chat, update.effective_user
    if not msg or not chat or not chat_comandi(chat) or not e_owner(user, "/riscarica"):
        return
    urls = URL_RE.findall(msg.text or "")
    if not urls and msg.reply_to_message:
        r = msg.reply_to_message
        urls = URL_RE.findall(r.text or r.caption or "")
    if not urls:
        await msg.reply_text("Uso: /riscarica <link>  (oppure rispondi a un messaggio con un link)", **kw_topic(msg))
        return
    await processa_link(ctx, msg, chat, urls, ricarica=True)


async def cmd_aggiorna(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/aggiorna: aggiorna subito yt-dlp e gallery-dl (di solito lo fa da solo ogni AUTOUPDATE_ORE)."""
    msg, chat, user = update.effective_message, update.effective_chat, update.effective_user
    if not msg or not chat or not chat_comandi(chat) or not e_owner(user, "/aggiorna"):
        return
    stato = await msg.reply_text("🔄 Aggiorno yt-dlp e gallery-dl…", **kw_topic(msg))
    ok, esito = await asyncio.to_thread(aggiorna_downloader)
    await stato.edit_text(("✅ " if ok else "⚠️ ") + esito)


async def processa_link(ctx: ContextTypes.DEFAULT_TYPE, msg, chat, urls: list[str], ricarica: bool = False):
    """Scarica i link e pubblica i file in chat; poi cancella il messaggio di richiesta (tranne in privato)."""
    is_channel = chat.type == ChatType.CHANNEL
    is_private = chat.type == ChatType.PRIVATE
    kw = kw_topic(msg)

    where = chat.title or "chat privata"
    log(f"Richiesta da «{where}»: {len(urls)} link")

    status = None
    if not is_channel:
        status = await ctx.bot.send_message(chat.id, "⏳ Scarico…", **kw)

    problems = []
    for n, url in enumerate(urls, 1):
        t0 = time.time()
        log(f"[{n}/{len(urls)}] {url}")
        voci = None if ricarica else cache_leggi(url)
        if voci:
            try:
                await invia_da_cache(ctx.bot, chat.id, voci, caption=url, **kw)
                log(f"  CACHE: rimandati {len(voci)} file senza riscaricare ({time.time() - t0:.0f}s)")
                continue
            except CacheFallita as e:
                log(f"  cache non utilizzabile ({e})")
                if e.parziale:
                    problems.append(f"{url}\nInvio dalla cache interrotto a metà: {e}\nRiprova con /riscarica")
                    continue
                cache_elimina(url)      # file_id non più validi: scarico di nuovo
        with tempfile.TemporaryDirectory() as d:
            try:
                files = await asyncio.to_thread(download, url, d)
            except Exception as e:
                log(f"  ERRORE download: {e}")
                problems.append(f"🍪 {e}\n{url}" if isinstance(e, CookieError) else f"{url}\n{e}")
                continue
            if not files:
                log("  nessun file trovato")
                problems.append(f"Niente da scaricare: {url}")
                continue
            files = [await rendi_riproducibile(p) for p in files]
            log(f"  trovati {len(files)} file, invio su Telegram…")
            ids: dict = {}
            errs = await send_files(ctx.bot, chat.id, files, cache=ids, caption=url, **kw)
            problems.extend(errs)
            if not errs:
                cache_salva(url, voci_da_cache_invio(files, ids))
        log(f"  completato in {time.time() - t0:.0f}s")

    if status:
        try:
            await status.delete()
        except Exception:
            pass

    for avviso in prendi_avvisi():      # es. troppi download Instagram: avviso privato, mai nel canale
        try:
            await ctx.bot.send_message(OWNER, "⚠️ " + avviso)
        except Exception as e:
            log(f"  non riesco a inviare l'avviso in privato: {e}")

    if problems:
        # il tuo messaggio resta, così puoi riprovare
        err = "⚠️ " + "\n⚠️ ".join(problems)
        if not is_private:
            err = f"Errore in «{where}»:\n" + err
        err = err[:4000]
        if is_channel:
            await report_from_channel(ctx, chat.id, err)   # privato; ripiego temporaneo nel canale
        else:
            # gli errori vanno nella chat privata con il bot; se non è possibile, nella chat d'origine
            try:
                await ctx.bot.send_message(OWNER, err)
            except Exception as e:
                log(f"  non riesco a scrivere in privato ({e}): rispondo nella chat")
                await ctx.bot.send_message(chat.id, err, **kw)
    elif not is_private:
        try:
            await msg.delete()
        except Exception:
            log("  non riesco a cancellare il messaggio (manca il permesso?)")


# ---------- inline con anteprima: il file è già pronto quando lo scegli ----------
_PREPARATI: dict = {}      # url -> {"t": istante, "task": Task che dà [(tipo, file_id, nome, byte)]}
_ULTIMA_INLINE: dict = {}  # utente -> id dell'ultima richiesta inline (serve ad aspettare che finisci di scrivere)
PREP_VITA = 1800           # secondi di validità di un file preparato
INLINE_PAUSA = 0.8         # attesa dopo l'ultimo carattere, prima di cominciare a scaricare


async def _prepara_url(bot, url: str, av: dict) -> list:
    """Scarica l'url e carica i file nella chat privata per ottenere i file_id (poi cancella la copia)."""
    pronti = []
    _AVANZ.set(av)
    gia = cache_leggi(url)
    if gia and len(gia) <= 10 and all(v[0] in ("photo", "video", "animation") for v in gia):
        log("  inline: file già in cache, nessun download")
        return [tuple(v) for v in gia]
    with tempfile.TemporaryDirectory() as d:
        files = await asyncio.to_thread(download, url, d)
        if not files:
            raise ValueError("niente da scaricare")
        av["fase"] = "carico"
        for p in [await rendi_riproducibile(f) for f in files][:10]:
            try:
                dim = p.stat().st_size
                _, privato = await _media_inline(bot, p)
            except Exception as e:
                log(f"  inline: salto {p.name} ({e})")
                continue
            info = _id_file(privato)
            try:
                await privato.delete()
            except Exception:
                pass
            if info:
                pronti.append((info[0], info[1], p.name, dim))
    if not pronti:
        raise ValueError("nessun file adatto a un messaggio inline")
    if len(pronti) == len(files):       # in cache solo se completo
        cache_salva(url, [list(v) for v in pronti])
    return pronti


def _avvia_preparazione(bot, url: str) -> dict:
    ora = time.time()
    for k in [k for k, v in _PREPARATI.items() if ora - v["t"] > PREP_VITA]:
        del _PREPARATI[k]
    e = _PREPARATI.get(url)
    if e:
        return e
    av: dict = {}
    e = {"t": ora, "av": av, "task": asyncio.create_task(_prepara_url(bot, url, av))}

    def finito(t):
        if t.cancelled() or t.exception():     # fallito: riprovabile dopo un minuto
            e["t"] = time.time() - PREP_VITA + 60
            if not t.cancelled():
                log(f"  inline: preparazione non riuscita ({t.exception()})")
    e["task"].add_done_callback(finito)
    _PREPARATI[url] = e
    return e


def _testo_avanzamento(av: dict) -> str:
    if av.get("fase") == "carico":
        return "⬆️ UPLOAD…"
    if av.get("pct") is not None:
        pieni = int(av["pct"] / 10)
        return f"⬇️ DOWNLOAD {'▓' * pieni}{'░' * (10 - pieni)} {int(av['pct'])}%"
    if av.get("n"):
        return f"⬇️ DOWNLOAD · {av['n']} file"
    return "⬇️ DOWNLOAD…"


async def _aggiorna_pulsante(bot, iid: str, av: dict):
    """Finché scarica, riscrive il pulsante del messaggio inline con la barra di avanzamento."""
    ultimo = "⬇️ DOWNLOAD…"
    while True:
        await asyncio.sleep(2.5)
        testo = _testo_avanzamento(av)
        if testo == ultimo:
            continue
        ultimo = testo
        try:
            await bot.edit_message_reply_markup(
                inline_message_id=iid,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(testo, callback_data="ph")]]))
        except Exception:
            pass


def _input_media(tipo: str, file_id: str, caption: str | None = None):
    if tipo == "video":
        return InputMediaVideo(media=file_id, supports_streaming=True, caption=caption)
    if tipo == "animation":
        return InputMediaAnimation(media=file_id, caption=caption)
    return InputMediaPhoto(media=file_id, caption=caption)


def _risultato_file(n: int, tipo: str, file_id: str, nome: str, dim: int, url: str):
    """Risultato inline col file vero: l'elenco mostra la sua miniatura; il link va in didascalia."""
    rid, titolo = f"f{n}:{uuid.uuid4().hex[:10]}", f"{nome[:45]} ({mb(dim)})"
    if tipo == "video":
        return InlineQueryResultCachedVideo(id=rid, video_file_id=file_id, title=titolo, caption=url,
                                            description=url[:80])
    if tipo == "animation":
        return InlineQueryResultCachedMpeg4Gif(id=rid, mpeg4_file_id=file_id, title=titolo, caption=url)
    return InlineQueryResultCachedPhoto(id=rid, photo_file_id=file_id, title=titolo, caption=url,
                                        description=url[:80])


_ALBUM_ATTIVO = [0.0, False]


def _album_utente_attivo() -> bool:
    """True se l'account personale è configurato e collegato (si ricontrolla al massimo ogni 30 s)."""
    ora = time.time()
    if ora - _ALBUM_ATTIVO[0] > 30:
        _tg_ricarica()
        try:
            import telethon  # noqa: F401
            ok = bool(TG_API_ID and TG_API_HASH and Path(TG_SESSION + ".session").exists())
        except ImportError:
            ok = False
        _ALBUM_ATTIVO[:] = [ora, ok]
    return _ALBUM_ATTIVO[1]


async def _album_inoltra(bot_id: int, bot_username: str, n: int, url: str) -> str:
    """Con l'account personale: trova il messaggio inline appena inviato (ultime chat), vi inoltra gli ultimi
    `n` messaggi ricevuti dal bot (l'album) e cancella il messaggio col link. Restituisce il nome della chat.
    Gli id vanno letti dal lato dell'account personale: in privato non coincidono con quelli del bot."""
    client = await _tg_utente_client()
    try:
        ids: list[int] = []
        for _ in range(10):                         # l'album può impiegare un attimo ad arrivare
            ultimi = await client.get_messages(bot_username, limit=n + 5)
            ids = sorted(m.id for m in ultimi if m and not m.out and m.media)[-n:]
            if len(ids) == n:
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError(f"nella chat col bot trovo solo {len(ids)} file su {n}")
        for _ in range(10):                         # il messaggio inline può impiegare un attimo ad apparire
            async for d in client.iter_dialogs(limit=20):
                m = d.message
                if (m and m.out and getattr(m, "via_bot_id", None) == bot_id
                        and (m.message or "").startswith(ALBUM_MARK.strip()) and url in (m.message or "")):
                    fwd = await client.forward_messages(d.entity, ids, from_peer=bot_username)
                    fwd = [x for x in (fwd if isinstance(fwd, list) else [fwd]) if x]
                    if not fwd:
                        raise RuntimeError("Telegram non ha inoltrato nulla (chat con inoltro bloccato o "
                                           "senza permessi di scrittura?)")
                    try:
                        await client.delete_messages(d.entity, [m.id])
                    except Exception as e:
                        log(f"  album: messaggio col link non cancellato ({e})")
                    return d.name or str(d.id)
            await asyncio.sleep(1)
        raise RuntimeError("non trovo il messaggio inline che hai appena inviato (controlla che la chat sia "
                           "tra le prime 20 e non archiviata)")
    finally:
        await client.disconnect()


async def _album_scelto(ctx, r):
    """Hai toccato «📚 Album»: il bot manda l'album a te in privato, il tuo account lo inoltra nella chat."""
    bot = ctx.bot
    inviati: list[int] = []
    url = ""
    try:
        urls = URL_RE.findall(r.query or "")
        if not urls:
            raise ValueError("nessun link nella richiesta")
        url = urls[0]
        log(f"Inline «album»: {url}")
        pronti = await asyncio.shield(_avvia_preparazione(bot, url)["task"])
        foto_video = [v for v in pronti if v[0] in ("photo", "video")]
        altri = [v for v in pronti if v[0] not in ("photo", "video")]
        primo = True
        for i in range(0, len(foto_video), 10):
            chunk = foto_video[i:i + 10]
            if len(chunk) == 1:
                altri.insert(0, chunk[0])
                continue
            media = [_input_media(v[0], v[1], url if (primo and j == 0) else None) for j, v in enumerate(chunk)]
            primo = False
            msgs = await bot.send_media_group(OWNER, media)
            inviati += [m.message_id for m in msgs]
        for v in altri:
            if v[0] == "video":
                m = await bot.send_video(OWNER, v[1], caption=url if primo else None, supports_streaming=True)
            elif v[0] == "animation":
                m = await bot.send_animation(OWNER, v[1], caption=url if primo else None)
            else:
                m = await bot.send_photo(OWNER, v[1], caption=url if primo else None)
            primo = False
            inviati.append(m.message_id)
        chat = await asyncio.to_thread(_tg_utente_esegui, f"album di {len(inviati)} file", 
                                       lambda: _album_inoltra(bot.id, bot.username, len(inviati), url),
                                       True)
        log(f"  album inoltrato in «{chat}»")
        for mid in inviati:                         # le copie private non servono più
            try:
                await bot.delete_message(OWNER, mid)
            except Exception:
                pass
    except Exception as e:
        log(f"  ERRORE album: {e}")
        try:
            await bot.send_message(OWNER, (f"⚠️ Album non inoltrato: {e}" + (f"\n{url}" if url else ""))[:4000])
        except Exception as e2:
            log(f"  non riesco a scrivere in privato: {e2}")


async def handle_inline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """@nomedelbot <link>: propone un risultato che, toccato, invia
    "<link> @nomedelbot" nella chat; poi lo gestisce handle()."""
    q = update.inline_query
    if not q:
        return
    is_owner = q.from_user.id == OWNER
    cmd = _inline_comando(q.query) if is_owner else None
    if cmd:                      # "@bot ricerca ..." / "@bot booru ...": vedi _risposta_inline_comando
        await _risposta_inline_comando(q, cmd)
        return
    urls = URL_RE.findall(q.query or "") if is_owner else []
    if q.query:
        if not is_owner:
            esito = f"IGNORATA: il tuo ID ({q.from_user.id}) non coincide con OWNER_ID"
        elif not urls:
            esito = "nessun link http(s) nel testo"
        else:
            esito = "risultato inviato"
        log(f"Inline da {q.from_user.id}: «{q.query[:60]}» -> {esito}")
    if not urls:
        await q.answer([], cache_time=0, is_personal=True)
        return
    # aspetto che tu finisca di scrivere/incollare, poi scarico subito in background
    uid = q.from_user.id
    _ULTIMA_INLINE[uid] = q.id
    await asyncio.sleep(INLINE_PAUSA)
    if _ULTIMA_INLINE.get(uid) != q.id:
        return                      # nel frattempo hai scritto altro: risponderà quella richiesta
    e = _avvia_preparazione(ctx.bot, urls[0])
    ant = _ANTEPRIME.get(urls[0])
    if ant is None and INLINE_SEGNAPOSTO:     # miniatura del post, in parallelo al download
        if len(_ANTEPRIME) > 50:
            _ANTEPRIME.clear()
        ant = _ANTEPRIME[urls[0]] = asyncio.create_task(_anteprima(ctx.bot, urls[0]))
    try:
        pronti = await asyncio.wait_for(asyncio.shield(e["task"]), INLINE_ATTESA)
    except Exception:       # non ancora pronto o fallito: nessuna barra, elenco vuoto
        pass
    else:
        risultati = [_risultato_file(n, *f, urls[0]) for n, f in enumerate(pronti)]
        if INLINE_ALBUM and len(pronti) > 1:
            if _album_utente_attivo():          # inoltrato dal tuo account: funziona in ogni chat
                risultati.insert(0, InlineQueryResultArticle(
                    id="al:" + uuid.uuid4().hex[:12],
                    title=f"📚 Album ({len(pronti)} file) · inoltrato dal bot",
                    description=urls[0][:80],
                    input_message_content=InputTextMessageContent(ALBUM_MARK + urls[0])))
            else:
                risultati.insert(0, InlineQueryResultArticle(
                    id=uuid.uuid4().hex,
                    title=f"📚 Album ({len(pronti)} file) · solo nelle chat col bot",
                    description=urls[0][:80],
                    input_message_content=InputTextMessageContent(
                        " ".join(urls) + (f" @{ctx.bot.username}" if INLINE_TAG else ""))))
        try:
            await q.answer(risultati, cache_time=0, is_personal=True)
        except Exception as err2:
            log(f"  inline: risposta non consegnata ({err2})")
        return
    text = " ".join(urls) + (f" @{ctx.bot.username}" if INLINE_TAG else "")
    result = InlineQueryResultArticle(
        id=uuid.uuid4().hex,
        title="⬇️ Scarica e pubblica",
        description=urls[0][:80],
        input_message_content=InputTextMessageContent(text),
    )
    fid = None
    if ant:
        try:
            fid = await asyncio.wait_for(asyncio.shield(ant), 1)
        except Exception:
            pass
    qui = _risultato_qui("dl", "📎 Scarica qui (il bot non serve nella chat)", urls[0][:80], fid)
    # finché il file non è pronto l'elenco resta vuoto; il segnaposto torna con INLINE_SEGNAPOSTO=1
    risultati = [r for r in (qui if INLINE_SEGNAPOSTO else None, result if INLINE_PUBBLICA else None) if r]
    try:
        await q.answer(risultati, cache_time=0, is_personal=True)
    except Exception as err2:
        log(f"  inline: risposta non consegnata ({err2})")


# ---------- Graves: /ricerca <cosa cercare> [-n 1-10] ----------
# Modulo facoltativo (graves.py): se manca o non si carica, il bot parte lo stesso senza /ricerca.
try:
    import graves
    graves.log = log
except Exception as e:
    graves = None
    log(f"graves.py non si carica ({e!r}): il comando /ricerca non è attivo")


async def _invia_come_file(bot, chat_id, files: list[Path], **kw) -> list[str]:
    """GRAVES_ORIGINALE=1: le immagini partono come documenti, senza la ricompressione che Telegram applica
    alle foto. Prima provo un album (a gruppi di 10); se Telegram lo rifiuta le mando una per una."""
    errori = []
    for i in range(0, len(files), 10):
        gruppo = files[i:i + 10]
        if len(gruppo) > 1:
            handles = [open(p, "rb") for p in gruppo]
            try:
                log(f"    invio album di {len(gruppo)} file (come documenti)…")
                await bot.send_media_group(chat_id, [InputMediaDocument(media=h) for h in handles], **kw)
                await asyncio.sleep(0.3)
                continue
            except Exception as e:
                log(f"    album di documenti non riuscito ({e}), li mando uno per uno")
            finally:
                for h in handles:
                    h.close()
        for p in gruppo:
            try:
                log(f"    invio come file: {p.name} ({mb(p.stat().st_size)})")
                with open(p, "rb") as f:
                    await bot.send_document(chat_id, f, **kw)
                await asyncio.sleep(0.3)
            except Exception as e:
                log(f"    ERRORE invio come file di {p.name}: {e}")
                errori.append(f"{p.name}: {e}")
    return errori


async def cmd_ricerca(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg, chat, user = update.effective_message, update.effective_chat, update.effective_user
    if not msg or not chat or not chat_comandi(chat) or not e_owner(user, "/ricerca"):
        return
    await _ricerca_core(ctx, msg, chat, list(ctx.args or []))


async def _ricerca_core(ctx: ContextTypes.DEFAULT_TYPE, msg, chat, args: list, cancella: bool = False):
    """Corpo di /ricerca: usato da cmd_ricerca e dal comando inline (cancella=True: toglie il messaggio)."""
    kw = kw_topic(msg)

    async def avvisa(testo: str):
        # come per i link: gli errori vanno nella chat privata con il bot; se non è possibile, in questa
        try:
            await ctx.bot.send_message(OWNER, testo[:4000])
        except Exception as e:
            log(f"  non riesco a scrivere in privato ({e}): rispondo nella chat")
            await ctx.bot.send_message(chat.id, testo[:4000], **kw)

    if graves is None:
        await avvisa("⚠️ Il modulo Graves non è caricato: manca graves.py accanto a telegram_bot.py.")
        return
    try:
        query, n = graves.parse_richiesta(" ".join(args))
    except graves.GravesErrore as e:
        await avvisa(f"ℹ️ {e}")
        return

    where = chat.title or "chat privata"
    log(f"/ricerca da «{where}»: {query}")
    status = await ctx.bot.send_message(chat.id, f"🔎 Cerco «{query}»…", **kw)
    t0 = time.time()
    problems = []
    with tempfile.TemporaryDirectory() as d:
        try:
            files = await asyncio.to_thread(graves.cerca_e_scarica, query, d, n)
        except Exception as e:
            log(f"  ERRORE Graves: {e}")
            problems.append(str(e))
        else:
            log(f"  trovate {len(files)} immagini, invio su Telegram…")
            if graves.originale():
                problems.extend(await _invia_come_file(ctx.bot, chat.id, files, **kw))
            else:
                problems.extend(await send_files(ctx.bot, chat.id, files, **kw))
    log(f"  completato in {time.time() - t0:.0f}s")
    try:
        await status.delete()
    except Exception:
        pass
    if cancella and not problems:
        try:
            await msg.delete()
        except Exception:
            log("  non riesco a cancellare il messaggio del comando (manca il permesso?)")
    if problems:
        err = "⚠️ " + "\n⚠️ ".join(problems)
        if chat.type != ChatType.PRIVATE:
            err = f"Errore in «{where}»:\n" + err
        await avvisa(err)


_BOORU_PENDENTI: dict = {}   # token -> {post, chat, kw}: risultati in attesa di Invia/Scarta (si perdono al riavvio)


def _booru_tastiera(token: str, invia: str = "📤 Invia") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(invia, callback_data=f"bo:{token}:ok"),
                                  InlineKeyboardButton("🔄 Altro", callback_data=f"bo:{token}:ri"),
                                  InlineKeyboardButton("🗑 Scarta", callback_data=f"bo:{token}:no")]])


async def _booru_manda_anteprima(bot, path, testo: str, tastiera):
    if path is None:
        await bot.send_message(OWNER, testo, reply_markup=tastiera)
        return
    with open(path, "rb") as f:
        try:
            await bot.send_photo(OWNER, f, caption=testo, reply_markup=tastiera)
        except Exception:       # per esempio una gif: la mando come documento
            f.seek(0)
            await bot.send_document(OWNER, f, caption=testo, reply_markup=tastiera)


async def cmd_booru(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/booru <tag> [-n 1-5] [-s r34|gb|db|e621|rg] [-r]: anteprime PRIVATE (chat col bot) con Invia/Scarta; il file parte nella chat solo se scegli Invia."""
    msg, chat, user = update.effective_message, update.effective_chat, update.effective_user
    if not msg or not chat or not chat_comandi(chat) or not e_owner(user, "/booru"):
        return
    await _booru_core(ctx, msg, chat, list(ctx.args or []))


async def _booru_core(ctx: ContextTypes.DEFAULT_TYPE, msg, chat, args: list):
    """Corpo di /booru: usato da cmd_booru e dal comando inline (anche nei canali)."""
    kw = kw_topic(msg)

    async def avvisa(testo: str):
        try:
            await ctx.bot.send_message(OWNER, testo[:4000])
        except Exception as e:
            log(f"  non riesco a scrivere in privato ({e}): rispondo nella chat")
            await ctx.bot.send_message(chat.id, testo[:4000], **kw)

    if graves is None:
        await avvisa("⚠️ Il modulo Graves non è caricato: manca graves.py accanto a telegram_bot.py.")
        return
    try:
        rich = graves.parse_booru(" ".join(args))
    except graves.GravesErrore as e:
        await avvisa(f"ℹ️ {e}")
        return

    where = chat.title or "chat privata"
    log(f"/booru da «{where}» ({rich.sito}, {len(rich.tags)} tag, n={rich.n})")
    # anteprime e pulsanti vanno SOLO nella chat privata con il bot; il file parte in «chat» solo se scegli Invia
    try:
        status = await ctx.bot.send_message(OWNER, "🔎 Cerco…")
    except Exception as e:
        await ctx.bot.send_message(chat.id, f"⚠️ Non riesco a scriverti in privato ({e}): apri il bot e premi Start.", **kw)
        return
    t0 = time.time()
    problems = []
    with tempfile.TemporaryDirectory() as d:
        try:
            trovati = await graves.booru_anteprime(rich, d)
        except Exception as e:
            log(f"  ERRORE Graves: {e}")
            trovati, problems = [], [str(e)]
        visti = {p.id for p, _ in trovati}
        for post, path in trovati:
            token = uuid.uuid4().hex[:10]
            while len(_BOORU_PENDENTI) >= 200:
                _BOORU_PENDENTI.pop(next(iter(_BOORU_PENDENTI)))
            _BOORU_PENDENTI[token] = {"post": post, "chat": chat.id, "kw": kw, "rich": rich, "visti": visti, "where": where}
            tastiera = _booru_tastiera(token)
            testo = f"{post.etichetta()}\n{post.pagina}\n→ destinazione: «{where}»"
            try:
                if path is None:
                    await ctx.bot.send_message(OWNER, testo, reply_markup=tastiera)
                else:
                    with open(path, "rb") as f:
                        try:
                            await ctx.bot.send_photo(OWNER, f, caption=testo, reply_markup=tastiera)
                        except Exception:       # per esempio una gif: la mando come documento
                            f.seek(0)
                            await ctx.bot.send_document(OWNER, f, caption=testo, reply_markup=tastiera)
            except Exception as e:
                _BOORU_PENDENTI.pop(token, None)
                problems.append(f"{post.etichetta()}: anteprima non inviata ({e})")
    log(f"  anteprime pronte in {time.time() - t0:.0f}s ({len(trovati)})")
    try:
        await status.delete()
    except Exception:
        pass
    if trovati and len(problems) < len(trovati):
        try:   # tolgo anche il comando digitato (mostrerebbe i tag): in un gruppo serve "Elimina messaggi"
            await msg.delete()
        except Exception:
            log("  non riesco a cancellare il comando /booru (manca il permesso?)")
    if problems:
        await avvisa("⚠️ " + "\n⚠️ ".join(problems))


async def on_booru_scelta(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Pulsanti 📤 Invia / 🗑 Scarta sotto le anteprime private di /booru."""
    q = update.callback_query
    if not q or not q.data or not q.data.startswith("bo:") or not q.message:
        return
    if q.from_user.id != OWNER:
        await q.answer("Non autorizzato.", show_alert=True)
        return
    try:
        _, token, azione = q.data.split(":")
    except ValueError:
        await q.answer()
        return

    async def scrivi(testo: str, tastiera=None):
        try:
            if q.message.photo or q.message.document or q.message.animation or q.message.video:
                await q.edit_message_caption(caption=testo, reply_markup=tastiera)
            else:
                await q.edit_message_text(testo, reply_markup=tastiera)
        except Exception as e:
            log(f"  modifica dell'anteprima non riuscita: {e}")

    base = (q.message.caption or q.message.text or "").split("\n→")[0]

    async def elimina(ripiego: str):
        """L'anteprima privata sparisce subito; se Telegram non la lascia cancellare, la segno nel testo."""
        try:
            await q.message.delete()
        except Exception as e:
            log(f"  anteprima privata non eliminata: {e}")
            await scrivi(ripiego)
    if azione == "ri":
        voce = _BOORU_PENDENTI.get(token)
        if voce is None:
            await q.answer("Scaduta (il bot è stato riavviato): rilancia /booru.", show_alert=True)
            await scrivi(base + "\n(scaduta)")
            return
        if voce.get("occupato"):
            await q.answer()
            return
        voce["occupato"] = True
        await q.answer("Cerco un altro risultato…")
        await scrivi(base + "\n⏳ Cerco un altro risultato…")
        try:
            with tempfile.TemporaryDirectory() as d:
                post, path = await graves.booru_altro(voce["rich"], d, voce["visti"])
                voce["visti"].add(post.id)
                voce["post"] = post
                testo = f"{post.etichetta()}\n{post.pagina}\n→ destinazione: «{voce['where']}»"
                await _booru_manda_anteprima(ctx.bot, path, testo, _booru_tastiera(token))
            try:
                await q.message.delete()
            except Exception as e:
                log(f"  anteprima precedente non eliminata: {e}")
        except Exception as e:
            log(f"  ERRORE nuovo risultato: {e}")
            await scrivi(base + f"\n⚠️ {str(e)[:200]}", _booru_tastiera(token))
        finally:
            voce["occupato"] = False
        return
    voce = _BOORU_PENDENTI.pop(token, None)     # pop subito: un doppio tocco non invia due volte
    if voce is None:
        await q.answer("Scaduta (il bot è stato riavviato): rilancia /booru.", show_alert=True)
        await scrivi(base + "\n(scaduta)")
        return
    if azione == "no":
        await q.answer("Scartato")
        await elimina(base + "\n🗑 Scartato")
        return

    await q.answer("Scarico e invio…")
    await scrivi(base + "\n⏳ Invio in corso…")
    try:
        with tempfile.TemporaryDirectory() as d:
            path = await graves.booru_file(voce["post"], d)
            await send_single(ctx.bot, voce["chat"], path, **voce["kw"])
        log(f"  /booru: inviato {voce['post'].etichetta()}")
        await elimina(base + "\n✅ Inviato")
    except Exception as e:
        log(f"  ERRORE invio {voce['post'].etichetta()}: {e}")
        _BOORU_PENDENTI[token] = voce           # si può riprovare
        await scrivi(base + f"\n⚠️ Invio non riuscito: {str(e)[:200]}", _booru_tastiera(token, "📤 Riprova"))


# ---------- /ricerca e /booru via @bot (inline): gruppi e canali ----------
# Nei canali i comandi /xxx non arrivano (i post non hanno un mittente): si scrive
#   @nomedelbot ricerca <cosa cercare> [-n 1-10]      @nomedelbot booru <tag> [-n 1-5] [-s sito] [-r]
# handle_inline propone un risultato; toccandolo parte nella chat "ricerca ..." o "booru ..." (senza
# barra, così non lo prende anche CommandHandler) e handle_comando_inline lo esegue.
_INLINE_CMD_RE = re.compile(r"\s*/?(ricerca|booru)(?:\s+(.*))?$", re.I | re.S)


def _inline_comando(testo: str):
    """('ricerca'|'booru', argomenti) se il testo è un comando inline, altrimenti None."""
    m = _INLINE_CMD_RE.match(testo or "")
    if not m:
        return None
    return m.group(1).lower(), " ".join((m.group(2) or "").split())


async def _risposta_inline_comando(q, cmd):
    """Risultato inline di un comando; con argomenti non validi non propone niente."""
    nome, args = cmd
    try:
        if graves is None:
            raise RuntimeError("graves.py non caricato")
        if nome == "ricerca":
            query, n = graves.parse_richiesta(args)
            titolo = f"🔎 Cerca immagini: {query[:50]}"
            desc = f"{n} immagini" if n else "numero di immagini di default"
        else:
            rich = graves.parse_booru(args)
            titolo = f"🏷 Booru ({rich.sito}): {' '.join(rich.tags)[:50]}"
            desc = f"{rich.n} risultati" + (" · casuali" if rich.casuale else "") + " · anteprime in privato"
    except Exception as e:
        if args:   # senza argomenti è solo la parola digitata a metà: niente da segnalare
            log(f"Inline /{nome}: non propongo il risultato ({str(e)[:100]})")
        await q.answer([], cache_time=0, is_personal=True)
        return
    result = InlineQueryResultArticle(
        id=uuid.uuid4().hex,
        title=titolo,
        description=desc,
        input_message_content=InputTextMessageContent(f"{nome} {args}"),
    )
    risultati = [result]
    if nome == "ricerca":
        qui = _risultato_qui("rc", titolo.replace("Cerca immagini", "Cerca qui, senza bot nella chat", 1),
                             "1 immagine · funziona anche dove il bot non c'è")
        if qui:
            risultati = [qui] if not INLINE_PUBBLICA else [qui, result]
    await q.answer(risultati, cache_time=0, is_personal=True)


async def handle_comando_inline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Messaggio "ricerca ..." / "booru ..." inviato via @bot (inline) in un gruppo, canale o chat privata."""
    msg, chat, user = update.effective_message, update.effective_chat, update.effective_user
    if not msg or not chat or not msg.via_bot or msg.via_bot.id != ctx.bot.id:
        return
    cmd = _inline_comando(msg.text or "")
    if not cmd:
        return
    # stesse regole di handle(): dove e per chi (il risultato inline lo propone comunque solo a OWNER)
    if chat.type == ChatType.CHANNEL:
        if CHANNELS and chat.id not in CHANNELS and chat.id not in AUTO_CHANNELS:
            log(f"Ignorato comando inline nel canale {chat.id}: non è in CHANNEL_ID")
            return
    elif chat_comandi(chat):
        if not e_owner(user, "comando inline"):
            return
    else:
        return
    nome, args = cmd
    if nome == "ricerca":
        await _ricerca_core(ctx, msg, chat, args.split(), cancella=True)
    else:
        await _booru_core(ctx, msg, chat, args.split())


# ---------- /url e /ricerca via @bot anche dove il bot NON è nella chat ----------
# Il risultato inline è un segnaposto (immagine grigia + pulsante) che, una volta toccato, il bot
# sostituisce col file vero con editMessageMedia. Richiede /setinlinefeedback = Enabled su @BotFather.
_PLACEHOLDER_IDS: dict = {}   # tipo ("dl"/"rc") -> file_id del segnaposto (vuoto = funzione non disponibile)
_SEGNAPOSTO_FILE = Path(__file__).resolve().with_name("inline_segnaposto.json")

# Nell'elenco inline Telegram NON mostra titolo e descrizione dei risultati-foto, solo l'immagine:
# il testo che spiega cosa fa il risultato sta quindi dentro l'immagine (righe: testo, grandezza).
_SEGNAPOSTI = {
    "dl": [("SCARICA", 8), ("QUI", 8), ("SENZA BOT NELLA CHAT", 3)],
    "rc": [("CERCA", 8), ("QUI", 8), ("1 IMMAGINE", 3)],
}

# carattere 5x7 incorporato (solo le lettere che servono): niente Pillow
_FONT = {
    "A": ".###.|#...#|#...#|#####|#...#|#...#|#...#", "B": "####.|#...#|#...#|####.|#...#|#...#|####.",
    "C": ".####|#....|#....|#....|#....|#....|.####", "D": "####.|#...#|#...#|#...#|#...#|#...#|####.",
    "E": "#####|#....|#....|####.|#....|#....|#####", "G": ".####|#....|#....|#..##|#...#|#...#|.###.",
    "H": "#...#|#...#|#...#|#####|#...#|#...#|#...#", "I": "#####|..#..|..#..|..#..|..#..|..#..|#####",
    "L": "#....|#....|#....|#....|#....|#....|#####", "M": "#...#|##.##|#.#.#|#.#.#|#...#|#...#|#...#",
    "N": "#...#|##..#|#.#.#|#..##|#...#|#...#|#...#", "O": ".###.|#...#|#...#|#...#|#...#|#...#|.###.",
    "Q": ".###.|#...#|#...#|#...#|#.#.#|#..#.|.##.#", "R": "####.|#...#|#...#|####.|#.#..|#..#.|#...#",
    "S": ".####|#....|#....|.###.|....#|....#|####.", "T": "#####|..#..|..#..|..#..|..#..|..#..|..#..",
    "U": "#...#|#...#|#...#|#...#|#...#|#...#|.###.", "Z": "#####|....#|...#.|..#..|.#...|#....|#####",
    "1": "..#..|.##..|..#..|..#..|..#..|..#..|.###.",
}


def _png(w: int, h: int, raw: bytes) -> bytes:
    def blocco(tipo: bytes, dati: bytes) -> bytes:
        return struct.pack(">I", len(dati)) + tipo + dati + struct.pack(">I", zlib.crc32(tipo + dati) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + blocco(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + blocco(b"IDAT", zlib.compress(raw, 9)) + blocco(b"IEND", b""))


def _png_testo(righe, w: int = 480, h: int = 270, sfondo=(28, 28, 28), colore=(235, 235, 235)) -> bytes:
    """PNG con le righe di testo centrate (righe = [(testo, scala), ...]), senza librerie esterne."""
    pix = [bytearray(bytes(sfondo) * w) for _ in range(h)]
    gap = 14
    y = (h - (sum(7 * sc for _, sc in righe) + gap * (len(righe) - 1))) // 2
    for testo, sc in righe:
        x = (w - (len(testo) * 6 * sc - sc)) // 2
        for ch in testo:
            for r, bits in enumerate(_FONT.get(ch, "").split("|")):
                for c, b in enumerate(bits):
                    if b == "#":
                        for dy in range(sc):
                            for dx in range(sc):
                                i = (x + c * sc + dx) * 3
                                pix[y + r * sc + dy][i:i + 3] = bytes(colore)
            x += 6 * sc
        y += 7 * sc + gap
    return _png(w, h, b"".join(b"\x00" + bytes(r) for r in pix))


async def prepara_segnaposto(bot):
    """Ricava (e ricorda) i file_id dei segnaposto: li manda una volta sola a OWNER e li cancella."""
    try:
        d = json.loads(_SEGNAPOSTO_FILE.read_text(encoding="utf-8"))
        if d.get("bot") == bot.id and d.get("v") == 2 and set(d.get("ids", {})) >= set(_SEGNAPOSTI):
            _PLACEHOLDER_IDS.update(d["ids"])
            log("Inline «qui»: segnaposto pronto (ricordati di /setinlinefeedback su @BotFather)")
            return
    except Exception:
        pass
    try:
        ids = {}
        for tipo, righe in _SEGNAPOSTI.items():
            m = await bot.send_photo(OWNER, _png_testo(righe), caption="Segnaposto per l'inline (si cancella da solo).")
            ids[tipo] = m.photo[-1].file_id
            try:
                await m.delete()
            except Exception:
                pass
        _PLACEHOLDER_IDS.update(ids)
        _SEGNAPOSTO_FILE.write_text(json.dumps({"bot": bot.id, "v": 2, "ids": ids}), encoding="utf-8")
        log("Inline «qui»: segnaposto creato (ricordati di /setinlinefeedback su @BotFather)")
    except Exception as e:
        log(f"Inline «qui» NON attivo: non riesco a creare il segnaposto ({e}). Apri il bot in privato e premi Start.")


def _risultato_qui(tipo: str, titolo: str, descrizione: str, file_id: str | None = None):
    """Risultato inline modificabile (segnaposto + pulsante), o None se il segnaposto non c'è.
    Con file_id mostra quella immagine (anteprima del post) al posto del segnaposto grigio."""
    if not (file_id or _PLACEHOLDER_IDS.get(tipo)):
        return None
    return InlineQueryResultCachedPhoto(
        id=f"{tipo}:{uuid.uuid4().hex[:12]}",
        photo_file_id=file_id or _PLACEHOLDER_IDS[tipo],
        title=titolo[:100],
        description=descrizione[:100],
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬇️ DOWNLOAD…", callback_data="ph")]]),
    )


_ANTEPRIME: dict = {}   # url -> task che restituisce il file_id della miniatura del post (o None)


def _miniatura_url(url: str) -> str | None:
    """URL della miniatura del post dai metadati di yt-dlp, senza scaricare il video."""
    for sorg in [None] + sorgenti_cookie():
        opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True,
                "socket_timeout": 10}
        if sorg:
            if sorg[0] == "file":
                opts["cookiefile"] = sorg[1]
            else:
                opts["cookiesfrombrowser"] = (sorg[1],)
        try:
            with yt_dlp.YoutubeDL(opts) as y:
                info = y.extract_info(url, download=False) or {}
        except Exception:
            continue
        cand = [t.get("url") for t in reversed(info.get("thumbnails") or []) if t.get("url")]
        buone = [u for u in cand if u.split("?")[0].lower().endswith((".jpg", ".jpeg", ".png"))]
        u = (buone or [info.get("thumbnail")])[0]
        if u:
            return u
    return None


def _scarica_bytes(u: str) -> bytes:
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read(10_000_000)


async def _anteprima(bot, url: str) -> str | None:
    """file_id della miniatura del post (caricata una volta in privato e cancellata), o None."""
    try:
        u = await asyncio.to_thread(_miniatura_url, url)
        if not u:
            return None
        m = await bot.send_photo(OWNER, await asyncio.to_thread(_scarica_bytes, u))
        fid = m.photo[-1].file_id
        try:
            await m.delete()
        except Exception:
            pass
        return fid
    except Exception as e:
        log(f"  inline: anteprima non disponibile ({e})")
        return None


async def on_segnaposto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q:
        await q.answer("Sto scaricando…")


async def _media_inline(bot, path: Path, caption: str | None = None):
    """Carica il file nella chat privata per ottenere un file_id e restituisce (InputMedia, messaggio privato).
    Un messaggio inline può essere modificato solo con un file_id (o un URL), non con un upload."""
    ext, size = path.suffix.lower(), path.stat().st_size
    gif = ext in ANIM_EXT
    if gif and size > MAX_FILE:
        nuovo = await asyncio.to_thread(gif_to_mp4, path, int(MAX_FILE * 0.9))
        if nuovo == path:
            raise ValueError(f"{path.name} supera i 50 MB")
        path, ext, size = nuovo, nuovo.suffix.lower(), nuovo.stat().st_size
    if ext in VIDEO_EXT and size > MAX_FILE:
        path = await asyncio.to_thread(compress_video, path, limite_bytes=MAX_FILE)
        ext, size = path.suffix.lower(), path.stat().st_size
        if size > MAX_FILE:
            raise ValueError(f"{path.name} è ancora sopra i 50 MB")
    log(f"    inline: preparo {path.name} ({mb(size)})")
    with open(path, "rb") as f:
        if gif:
            m = await bot.send_animation(OWNER, f)
            fid = (m.animation or m.document).file_id
            return InputMediaAnimation(media=fid, caption=caption), m
        if ext in VIDEO_EXT:
            m = await bot.send_video(OWNER, f, supports_streaming=True)
            if m.video:
                return InputMediaVideo(media=m.video.file_id, supports_streaming=True, caption=caption), m
            return InputMediaAnimation(media=m.animation.file_id, caption=caption), m
        if ext in IMAGE_EXT and size <= MAX_PHOTO:
            m = await bot.send_photo(OWNER, f)
            return InputMediaPhoto(media=m.photo[-1].file_id, caption=caption), m
    raise ValueError(f"{path.name}: formato o dimensione non adatti a un messaggio inline (immagini max 10 MB)")


async def on_inline_scelto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Hai toccato «Scarica qui» / «Cerca qui»: scarico e sostituisco il segnaposto col file."""
    r = update.chosen_inline_result
    if r and r.from_user.id == OWNER and r.result_id.startswith("al:"):
        ctx.application.create_task(_album_scelto(ctx, r))      # non blocca gli altri aggiornamenti
        return
    if not r or r.from_user.id != OWNER or not r.inline_message_id:
        return
    tipo = r.result_id.split(":")[0]
    if tipo not in ("dl", "rc"):
        return
    iid = r.inline_message_id
    t0 = time.time()
    url, extra, privato, media = "", 0, None, None
    try:
        with tempfile.TemporaryDirectory() as d:
            if tipo == "dl":
                urls = URL_RE.findall(r.query or "")
                if not urls:
                    raise ValueError("nessun link nella richiesta")
                url = urls[0]
                log(f"Inline «qui»: {url}")
                e = _avvia_preparazione(ctx.bot, url)   # già in corso/finita se l'anteprima l'aveva avviata
                barra = asyncio.create_task(_aggiorna_pulsante(ctx.bot, iid, e["av"]))
                try:
                    pronti = await asyncio.shield(e["task"])
                finally:
                    barra.cancel()
                media = _input_media(pronti[0][0], pronti[0][1], url)
                extra = (len(pronti) - 1) + (len(urls) - 1)
            else:
                cmd = _inline_comando(r.query or "")
                if graves is None or not cmd:
                    raise ValueError("Graves non è caricato: manca graves.py accanto a telegram_bot.py")
                query, _ = graves.parse_richiesta(cmd[1])
                log("Inline «qui»: ricerca immagini")
                files = await asyncio.to_thread(graves.cerca_e_scarica, query, d, 1)
            if media is None:
                media, privato = await _media_inline(ctx.bot, files[0], caption=url or None)
            await ctx.bot.edit_message_media(media=media, inline_message_id=iid)
            log(f"  segnaposto sostituito in {time.time() - t0:.0f}s")
        if extra:
            await ctx.bot.send_message(OWNER, f"ℹ️ Un messaggio inline contiene un solo file: ne ho inviato 1, "
                                              f"gli altri {extra} non sono partiti.")
    except Exception as e:
        log(f"  ERRORE inline «qui»: {e}")
        try:
            await ctx.bot.edit_message_caption(inline_message_id=iid, caption="⚠️ Non riuscito (dettagli in privato)")
        except Exception as e2:
            log(f"  segnaposto non aggiornato: {e2}")
        testo = f"🍪 {e}" if isinstance(e, CookieError) else f"⚠️ {e}"
        try:
            await ctx.bot.send_message(OWNER, (testo + (f"\n{url}" if url else ""))[:4000])
        except Exception as e3:
            log(f"  non riesco a scrivere in privato: {e3}")
    finally:
        if privato is not None:   # la copia privata serviva solo per il file_id
            try:
                await privato.delete()
            except Exception:
                pass
    for avviso in prendi_avvisi():
        try:
            await ctx.bot.send_message(OWNER, "⚠️ " + avviso)
        except Exception:
            pass


async def log_update(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Diagnostica: una riga per ogni messaggio/post che arriva al bot (prima di qualsiasi filtro)."""
    m = update.effective_message
    if not m:
        return
    u = update.effective_user
    log(f"ARRIVATO: {m.chat.type} «{m.chat.title or 'privata'}» da {u.id if u else '-'}: {(m.text or m.caption or '')[:50]!r}")


async def on_error(update, ctx: ContextTypes.DEFAULT_TYPE):
    log(f"ERRORE: {ctx.error}")

    traceback.print_exception(
        type(ctx.error),
        ctx.error,
        ctx.error.__traceback__,
    )


async def post_init(app):
    log(f"Bot avviato: @{app.bot.username}. In attesa di link…")
    if AUTOUPDATE_ORE > 0:
        threading.Thread(target=_ciclo_aggiornamento, name="autoupdate", daemon=True).start()
        log(f"Aggiornamento automatico di yt-dlp e gallery-dl: ogni {AUTOUPDATE_ORE:g} h")
    else:
        log("Aggiornamento automatico di yt-dlp e gallery-dl: disattivato (AUTOUPDATE_ORE=0)")
    await prepara_segnaposto(app.bot)


def main():
    if not TOKEN or not OWNER:
        sys.exit("Imposta BOT_TOKEN e OWNER_ID (vedi avvia_bot.bat).")
    log_versioni()
    log("Cookie: " + descrivi_cookie())
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .read_timeout(120)
        .write_timeout(600)
        .connect_timeout(30)
        .pool_timeout(30)
        .post_init(post_init)
        .build()
    )
    app.add_handler(TypeHandler(Update, log_update), group=-1)
    app.add_handler(InlineQueryHandler(handle_inline, block=False))   # non blocca gli altri aggiornamenti mentre aspetta
    app.add_handler(CommandHandler("url", cmd_url))
    app.add_handler(CommandHandler("riscarica", cmd_riscarica))
    app.add_handler(CommandHandler("aggiorna", cmd_aggiorna))
    app.add_handler(CommandHandler("ricerca", cmd_ricerca))
    app.add_handler(CommandHandler("booru", cmd_booru))
    app.add_handler(CallbackQueryHandler(on_booru_scelta, pattern=r"^bo:"))
    app.add_handler(   # group=1: gira in aggiunta a handle() (group 0), che ignora questi messaggi senza link
        MessageHandler((filters.UpdateType.MESSAGE | filters.UpdateType.CHANNEL_POST) & filters.TEXT,
                       handle_comando_inline),
        group=1,
    )
    app.add_handler(ChosenInlineResultHandler(on_inline_scelto))
    app.add_handler(CallbackQueryHandler(on_segnaposto, pattern=r"^ph$"))
    app.add_handler(
        MessageHandler(
            (filters.UpdateType.MESSAGE | filters.UpdateType.CHANNEL_POST)
            & (filters.TEXT | filters.CAPTION)
            & ~filters.COMMAND,
            handle,
        )
    )
    app.add_error_handler(on_error)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()