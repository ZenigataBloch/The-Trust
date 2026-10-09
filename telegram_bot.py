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

Protezione Instagram (opzionale; 0 = disattivato). Troppe richieste ravvicinate fanno scattare
«attività sospetta» sull'account dei cookie: il bot le conta (tutti i moduli, anche dopo un riavvio),
ti avvisa, aspetta tra un download e l'altro e si ferma al raggiungimento di un tetto.
  IG_AVVISO_ORA / IG_AVVISO_GIORNO   avviso a N download in 1 h / 24 h (default 12 / 60)
  IG_MAX_ORA / IG_MAX_GIORNO         blocco a N download in 1 h / 24 h (default 25 / 100)
  IG_PAUSA_SEC                       pausa minima tra due download (default 5)
  IG_COOLDOWN_MIN                    pausa se Instagram segnala limiti o attività sospetta (default 30)
  IG_STATO_FILE                      contatore (default: instagram_uso.json accanto allo script)
Sono stime prudenti, non limiti ufficiali di Instagram: regolale in base a ciò che vedi.

Nei gruppi e nei canali il bot deve essere amministratore con i permessi
"Pubblica messaggi" ed "Elimina messaggi".
"""
import sys
from pathlib import Path

# Senza console (pythonw) stdout/stderr sono None: li giro su un file .log con rotazione.
from bot_log import attiva_log_su_file
attiva_log_su_file()

import asyncio
import atexit
import datetime
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import traceback
from importlib import metadata
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import yt_dlp
from telegram import (
    InlineQueryResultArticle,
    InputMediaPhoto,
    InputMediaVideo,
    InputTextMessageContent,
    Update,
)
from telegram.constants import ChatType
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

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

# cookie per i siti che richiedono il login (Instagram, TikTok, X...). Si provano in ordine:
#   COOKIES_BROWSER  uno o più browser separati da virgola, es. "firefox,chrome"
#   COOKIES_FILE     file Netscape (es. C:\bot\cookies.txt), provato per ultimo
COOKIES_FILE = os.environ.get("COOKIES_FILE")        # es. C:\bot\cookies.txt (formato Netscape)
COOKIES_BROWSER = os.environ.get("COOKIES_BROWSER")  # es. firefox

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
                extra = f"  <-- vecchia di {giorni} giorni: aggiorna con  pip install -U yt-dlp gallery-dl"
        log(f"{pacchetto} {v}{extra}")


def progress_hook(d: dict):
    """Barra di avanzamento di yt-dlp, su una sola riga."""
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
def sorgenti_cookie() -> list[tuple[str, str]]:
    """Sorgenti da provare in ordine: i browser di COOKIES_BROWSER (es. 'firefox,chrome'), poi il file."""
    s = [("browser", b.strip()) for b in (COOKIES_BROWSER or "").split(",") if b.strip()]
    if COOKIES_FILE and Path(COOKIES_FILE).is_file():
        s.append(("file", COOKIES_FILE))
    return s


def etichetta_cookie(sorgente: tuple[str, str]) -> str:
    tipo, valore = sorgente
    return valore if tipo == "browser" else Path(valore).name


def descrivi_cookie() -> str:
    nomi = [etichetta_cookie(x) for x in sorgenti_cookie()]
    nota = f" (file {COOKIES_FILE} non trovato)" if COOKIES_FILE and not Path(COOKIES_FILE).is_file() else ""
    return (" -> ".join(nomi) if nomi else "NESSUNO") + nota


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
                "401 unauthorized", "http error 401")


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
        testo = f"COOKIE MANCANTI per {sito}: nessuna sorgente configurata (imposta COOKIES_BROWSER o COOKIES_FILE)."
    if not login and COOKIES_FILE and not Path(COOKIES_FILE).is_file():
        testo += f" File non trovato: {COOKIES_FILE}."
    righe = [r for r in (ultimo.dettagli if ultimo else "").splitlines() if r.strip()]
    if righe:
        testo += f"\nDettaglio: {righe[0].strip()[:200]}"
    return testo


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


def _download_cookie(url: str, folder: str) -> list[Path]:
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


def download(url: str, folder: str) -> list[Path]:
    """Punto d'ingresso dei download. Per i link Instagram aggiunge la protezione (conteggio, avviso,
    pausa minima, tetti e pausa dopo una segnalazione); poi scarica con _download_cookie."""
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
            ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
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


async def send_single(bot, chat_id, path: Path, **kw):
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
            await bot.send_animation(chat_id, f, **kw)
        elif ext in VIDEO_EXT:
            await bot.send_video(chat_id, f, supports_streaming=True, **kw)
        elif ext in IMAGE_EXT and size <= MAX_PHOTO:
            try:
                await bot.send_photo(chat_id, f, **kw)
            except Exception:
                f.seek(0)
                await bot.send_document(chat_id, f, **kw)
        else:
            await bot.send_document(chat_id, f, **kw)


async def send_files(bot, chat_id, files: list[Path], **kw) -> list[str]:
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
                f = open(p, "rb")
                handles.append(f)

                if p.suffix.lower() in VIDEO_EXT:
                    media.append(
                        InputMediaVideo(
                            media=f,
                            supports_streaming=True,
                        )
                    )
                else:
                    media.append(
                        InputMediaPhoto(
                            media=f,
                        )
                    )

            await bot.send_media_group(chat_id, media, **kw)
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
            await send_single(bot, chat_id, p, **kw)
        except Exception as e:
            log(f"    ERRORE invio {p.name}: {e}")
            errors.append(f"{p.name}: {e}")

    return errors

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
        if not user or user.id != OWNER:
            log(f"Ignorato messaggio nel gruppo da {user.id if user else '?'}: non è OWNER_ID")
            return
        needs_tag = True
    elif chat.type == ChatType.PRIVATE:
        if not user or user.id != OWNER:
            log(f"Ignorato messaggio privato da {user.id if user else '?'}: non è OWNER_ID")
            return
        needs_tag = False
    else:
        return

    text = msg.text or msg.caption or ""
    via_me = bool(msg.via_bot and msg.via_bot.id == ctx.bot.id)   # inviato con l'inline mode di questo bot
    if needs_tag and not via_me and f"@{ctx.bot.username}".lower() not in text.lower():
        return
    urls = URL_RE.findall(text)
    if not urls:
        return

    is_channel = chat.type == ChatType.CHANNEL
    is_private = chat.type == ChatType.PRIVATE
    # se siamo in un topic (forum), rispondo nello stesso topic
    kw = {"message_thread_id": msg.message_thread_id} if msg.is_topic_message else {}

    where = chat.title or "chat privata"
    log(f"Richiesta da «{where}»: {len(urls)} link")

    status = None
    if not is_channel:
        status = await ctx.bot.send_message(chat.id, "⏳ Scarico…", **kw)

    problems = []
    for n, url in enumerate(urls, 1):
        t0 = time.time()
        log(f"[{n}/{len(urls)}] {url}")
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
            problems.extend(await send_files(ctx.bot, chat.id, files, **kw))
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


async def handle_inline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """@nomedelbot <link>: propone un risultato che, toccato, invia
    "<link> @nomedelbot" nella chat; poi lo gestisce handle()."""
    q = update.inline_query
    if not q:
        return
    is_owner = q.from_user.id == OWNER
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
    text = " ".join(urls) + (f" @{ctx.bot.username}" if INLINE_TAG else "")
    result = InlineQueryResultArticle(
        id=uuid.uuid4().hex,
        title="⬇️ Scarica e pubblica",
        description=urls[0][:80],
        input_message_content=InputTextMessageContent(text),
    )
    await q.answer([result], cache_time=0, is_personal=True)


async def on_error(update, ctx: ContextTypes.DEFAULT_TYPE):
    log(f"ERRORE: {ctx.error}")

    traceback.print_exception(
        type(ctx.error),
        ctx.error,
        ctx.error.__traceback__,
    )


async def post_init(app):
    log(f"Bot avviato: @{app.bot.username}. In attesa di link…")


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
    app.add_handler(InlineQueryHandler(handle_inline))
    app.add_handler(
        MessageHandler(
            (filters.UpdateType.MESSAGE | filters.UpdateType.CHANNEL_POST)
            & (filters.TEXT | filters.CAPTION)
            & ~filters.COMMAND,
            handle,
        )
    )
    app.add_error_handler(on_error)
    app.run_polling()


if __name__ == "__main__":
    main()