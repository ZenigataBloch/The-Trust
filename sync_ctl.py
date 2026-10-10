"""
sync_ctl.py - tiene acceso Syncthing (pacchetto Termux) solo mentre la web app di Branch è aperta.

  - la pagina si apre / si ricarica / torna in primo piano, o parte il widget  -> apri(): avvia Syncthing se non gira
  - la pagina interroga il pannello (ogni 3 s)                                -> viva(): azzera il conto alla rovescia
  - nessun contatto per ATTESA_S secondi (web app chiusa o in background)     -> ciclo(): ferma Syncthing
  - i bot NON c'entrano: restano accesi, li gestisce solo bot_manager.

Syncthing parte in una sessione sua, quindi sopravvive se il pannello viene riavviato (il widget fa pkill
pannello.py) e il pannello nuovo lo ritrova. Il polling della pagina NON riavvia Syncthing dopo lo stop:
lo riavvia solo un'apertura vera (apri), così una pagina rimasta in background non lo riaccende in continuazione.

bots.env (facoltativo):  SYNC_ATTESA_MIN=5   minuti senza contatto prima dello stop
                         SYNC_AUTO=0         disattiva tutto (Syncthing lo gestisci tu)
Il Syncthing dell'app Android deve restare spento: userebbe le stesse porte.
"""
import os
import shutil
import subprocess
import threading
import time

import bot_manager as BM

ATTESA_S = 300
CONTROLLO_S = 30
PROVA_AVVIO_S = 3.0           # tanto aspetto per vedere se il processo resta vivo
LOG_FILE = BM.BASE / "syncthing.log"
log = print

try:
    ATTESA_S = max(60, int(float(os.environ.get("SYNC_ATTESA_MIN", "5")) * 60))
except ValueError:
    pass

_contatto = time.monotonic()
_cache = {"t": -1e9, "v": False}
_lock = threading.Lock()


def _exe():
    if os.environ.get("SYNC_AUTO", "1").strip() == "0":
        return None
    return shutil.which("syncthing")


def _gira() -> bool:
    try:
        return subprocess.run(["pgrep", "-x", "syncthing"], capture_output=True, timeout=3).returncode == 0
    except Exception:
        return False


def attivo(max_eta: float = 10.0) -> bool:
    """Syncthing sta girando? (risposta in cache per non lanciare pgrep a ogni richiesta della pagina)"""
    if _exe() is None:
        return False
    if time.monotonic() - _cache["t"] > max_eta:
        _cache.update(t=time.monotonic(), v=_gira())
    return _cache["v"]


def viva():
    """La pagina è aperta: riparte il conto alla rovescia. Non avvia nulla."""
    global _contatto
    _contatto = time.monotonic()


def _avvia():
    exe = _exe()
    if exe is None:
        return
    with _lock:
        if _gira():
            _cache.update(t=time.monotonic(), v=True)
            return
        env = dict(os.environ, STNORESTART="1", STNOUPGRADE="1")
        for args in (["serve", "--no-browser"], ["--no-browser"]):     # versioni nuove / vecchie
            try:
                with open(LOG_FILE, "ab") as f:
                    p = subprocess.Popen([exe, *args], cwd=str(BM.BASE), env=env, stdin=subprocess.DEVNULL,
                                         stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
            except OSError as e:
                log(f"Syncthing: avvio non riuscito: {e}")
                return
            time.sleep(PROVA_AVVIO_S)
            if p.poll() is None:
                log("Syncthing avviato")
                _cache.update(t=time.monotonic(), v=True)
                return
        log(f"Syncthing non parte: guarda {LOG_FILE.name}")


def apri():
    """Apertura vera (pagina caricata o tornata visibile, widget): contatto + avvio se non gira. Non blocca."""
    viva()
    if _exe() is not None and not attivo(max_eta=2.0):
        threading.Thread(target=_avvia, daemon=True).start()


def ferma():
    if not _gira():
        _cache.update(t=time.monotonic(), v=False)
        return
    log("Syncthing: nessun contatto dalla web app, lo fermo")
    subprocess.run(["pkill", "-TERM", "-x", "syncthing"], capture_output=True)
    for _ in range(50):
        if not _gira():
            break
        time.sleep(0.2)
    else:
        subprocess.run(["pkill", "-KILL", "-x", "syncthing"], capture_output=True)
    _cache.update(t=time.monotonic(), v=False)


def ciclo():
    """Thread del pannello: ferma Syncthing quando la web app non si fa viva da ATTESA_S secondi."""
    while True:
        time.sleep(CONTROLLO_S)
        try:
            if _exe() is not None and time.monotonic() - _contatto > ATTESA_S:
                ferma()
        except Exception as e:
            log(f"Syncthing: errore {e!r}")
