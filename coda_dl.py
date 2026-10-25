"""
coda_dl.py - coda dei download + cache condivisa (Discord, Telegram, org_bot).

Lo chiama telegram_bot.download(). Se questo file non c'è, i bot scaricano come prima.

Cosa fa, per ogni link:
  1. cache: se il file è già stato scaricato (da chiunque, anche da un altro bot) lo copia subito
     nella cartella di lavoro, senza yt-dlp / gallery-dl;
  2. stesso link già in scarico (persona 1 sta scaricando, persona 2 chiede lo stesso): persona 2
     aspetta che sia pronto in cache e lo riceve appena finisce, senza riscaricare;
  3. link diversi: si mettono in fila e scaricano uno alla volta, nell'ordine di arrivo (FIFO).

La cache sta su disco, quindi la condividono anche i processi separati (discord_bot, telegram_bot,
org_bot). Contiene i file come scaricati, prima di compressione/conversione: ogni bot li adatta
poi ai propri limiti.

Variabili d'ambiente (tutte facoltative, mettile in bots.env):
  DL_CACHE_ORE     validità di un file in cache, in ore (default 12; 0 = cache e coda disattivate)
  DL_CACHE_MAX_MB  tetto della cache (default 1500): oltre, si eliminano i file usati meno di recente
  DL_CACHE_DIR     dove sta la cache (default invii/.dl_cache accanto allo script: già in .gitignore)
"""
import collections
import contextlib
import os
import shutil
import threading
import time
from pathlib import Path


def _num(nome: str, default: float) -> float:
    try:
        return float(os.environ.get(nome, default))
    except ValueError:
        return default


ORE = _num("DL_CACHE_ORE", 12)
MAX_BYTE = int(_num("DL_CACHE_MAX_MB", 1500) * 1024 * 1024)
DIR = Path(os.environ.get("DL_CACHE_DIR") or Path(__file__).resolve().parent / "invii" / ".dl_cache")
ATTESA_MAX = 900        # s: oltre, smetto di aspettare chi sta scaricando lo stesso link e scarico io
LOCK_VECCHIO = 90       # s: un lock non rinnovato da tanto è di un processo morto
POLL = 0.5


# ---------- coda FIFO (un download alla volta, nell'ordine di arrivo) ----------
class _Fifo:
    def __init__(self):
        self._c = threading.Condition()
        self._fila: collections.deque = collections.deque()
        self._occupato = False

    @contextlib.contextmanager
    def turno(self, log, url: str):
        t = object()
        with self._c:
            self._fila.append(t)
            davanti = len(self._fila) - 1 + (1 if self._occupato else 0)
            if davanti:
                log(f"  coda download: {davanti} davanti a {url[:60]}")
            while self._occupato or self._fila[0] is not t:
                self._c.wait()
            self._fila.popleft()
            self._occupato = True
        try:
            yield
        finally:
            with self._c:
                self._occupato = False
                self._c.notify_all()


_FIFO = _Fifo()


# ---------- cache su disco ----------
def _file_di(d: Path) -> list[Path]:
    return sorted(p for p in d.iterdir() if p.is_file() and not p.name.startswith("."))


def _elimina(d: Path):
    shutil.rmtree(d, ignore_errors=True)


def _da_cache(key: str, folder: str, log) -> list[Path] | None:
    d = DIR / key
    try:
        if not d.is_dir():
            return None
        if time.time() - (d / ".ok").stat().st_mtime > ORE * 3600:
            _elimina(d)                     # scaduta
            return None
        src = _file_di(d)
        if not src:
            _elimina(d)
            return None
        out = []
        for p in src:
            dest = Path(folder) / p.name
            shutil.copy2(p, dest)           # copia vera: chi la riceve può modificarla senza toccare la cache
            out.append(dest)
        os.utime(d)                         # usata di recente (serve alla pulizia)
        log(f"  CACHE download: {len(out)} file già pronti, nessun yt-dlp/gallery-dl")
        return out
    except OSError:
        return None


def _salva(key: str, files: list[Path], log):
    if not files or len({p.name for p in files}) != len(files):
        return
    try:
        if sum(p.stat().st_size for p in files) > MAX_BYTE:
            return
        DIR.mkdir(parents=True, exist_ok=True)
        tmp, d = DIR / f"{key}.tmp", DIR / key
        _elimina(tmp)
        tmp.mkdir()
        for p in files:
            shutil.copy2(p, tmp / p.name)
        (tmp / ".ok").write_text("", encoding="utf-8")
        _elimina(d)
        tmp.rename(d)
        _pulisci(d)
    except OSError as e:
        log(f"  cache download non salvata: {e}")


def _pulisci(tieni: Path):
    """Toglie le voci scadute e, se la cache supera il tetto, quelle usate meno di recente."""
    voci = []
    for x in DIR.iterdir():
        if x.is_dir() and x.name.endswith(".tmp") and time.time() - x.stat().st_mtime > 3600:
            _elimina(x)                     # resto di un salvataggio interrotto
        elif x.is_dir() and not x.name.endswith(".tmp"):
            voci.append(x)
    peso = lambda x: sum(f.stat().st_size for f in x.iterdir() if f.is_file())
    tot = sum(peso(x) for x in voci)
    for x in sorted(voci, key=lambda x: x.stat().st_mtime):
        if tot <= MAX_BYTE:
            break
        if x != tieni:
            tot -= peso(x)
            _elimina(x)


# ---------- lock per link, valido anche tra processi diversi ----------
def _prendi_lock(key: str, log, pronto) -> Path | None | str:
    """Aspetta il proprio turno su questo link. Restituisce il file di lock, None se non si riesce a
    usare il lock (si scarica comunque), o \"pronto\" se nel frattempo il file è comparso in cache."""
    p = DIR / f"{key}.lock"
    t0, detto = time.time(), False
    while True:
        try:
            os.close(os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return p
        except FileExistsError:
            try:
                if time.time() - p.stat().st_mtime > LOCK_VECCHIO:
                    p.unlink()              # chi lo teneva è morto
                    continue
            except OSError:
                continue
        except OSError:
            return None
        if pronto():
            return "pronto"
        if time.time() - t0 > ATTESA_MAX:
            return None
        if not detto:
            log("  stesso link già in scarico: aspetto che sia pronto in cache")
            detto = True
        time.sleep(POLL)


def _battito(p: Path, fine: threading.Event):
    while not fine.wait(15):
        try:
            os.utime(p)
        except OSError:
            return


def scarica(url: str, folder: str, reale, key: str, ricarica: bool = False, log=print,
            coda: bool = True) -> list[Path]:
    """Cache -> (attesa dello stesso link) -> coda FIFO -> reale(url, folder). `ricarica` ignora la cache;
    `coda=False` salta la fila FIFO (per download leggeri che non devono aspettare yt-dlp)."""
    if ORE <= 0:
        return reale(url, folder)
    try:
        DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return reale(url, folder)
    if ricarica:
        _elimina(DIR / key)
    else:
        f = _da_cache(key, folder, log)
        if f:
            return f

    def pronto() -> bool:
        return not ricarica and (DIR / key / ".ok").exists()

    lock = _prendi_lock(key, log, pronto)
    if lock == "pronto":
        f = _da_cache(key, folder, log)
        if f:
            return f
        lock = _prendi_lock(key, log, lambda: False)
    fine = threading.Event()
    if lock:
        threading.Thread(target=_battito, args=(lock, fine), daemon=True).start()
    try:
        if lock and not ricarica:
            f = _da_cache(key, folder, log)     # chi aveva il lock può aver finito proprio ora
            if f:
                return f
        with (_FIFO.turno(log, url) if coda else contextlib.nullcontext()):
            files = reale(url, folder)
        _salva(key, files, log)
        return files
    finally:
        fine.set()
        if lock:
            with contextlib.suppress(OSError):
                lock.unlink()
