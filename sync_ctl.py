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

Se Syncthing risulta già avviato (anche da fuori, o non riconoscibile dai processi) NON ne viene lanciata una seconda
copia: l'errore "Failed to acquire lock" nel log viene letto come "c'è già un'istanza". Se l'istanza risponde sulla GUI
la lascio stare; se non risponde (bloccata) la chiudo e la riavvio una volta sola.
"""
import os
import shutil
import signal
import socket
import subprocess
import threading
import time

import bot_manager as BM

ATTESA_S = 300
CONTROLLO_S = 30
PROVA_AVVIO_S = 3.0           # tanto aspetto per vedere se il processo resta vivo
LOG_FILE = BM.BASE / "syncthing.log"
RIPROVA_DOPO_S = 60           # dopo un avvio fallito non ci riprovo per un minuto (niente raffica di tentativi)
log = print

try:
    ATTESA_S = max(60, int(float(os.environ.get("SYNC_ATTESA_MIN", "5")) * 60))
except ValueError:
    pass

try:
    PORTA_GUI = int(os.environ.get("SYNC_GUI_PORT", "8384"))
except ValueError:
    PORTA_GUI = 8384

_contatto = time.monotonic()
_fallito = -1e9
_cache = {"t": -1e9, "v": False}
_lock = threading.Lock()


def _exe():
    if os.environ.get("SYNC_AUTO", "1").strip() == "0":
        return None
    return shutil.which("syncthing")


def _pids() -> list:
    """PID dei processi Syncthing, leggendo /proc: guardo i primi argomenti della riga di comando (su Android
    l'eseguibile può partire tramite linker64) e anche il nome breve del processo (comm)."""
    out = []
    me = os.getpid()
    try:
        voci = os.listdir("/proc")
    except OSError:
        return out
    for v in voci:
        if not v.isdigit() or int(v) == me:
            continue
        try:
            with open(f"/proc/{v}/cmdline", "rb") as f:
                arg = f.read().split(b"\0")[:3]
            trovato = any(os.path.basename(a.decode("utf-8", "replace")) == "syncthing" for a in arg if a)
            if not trovato:
                with open(f"/proc/{v}/comm", "rb") as f:
                    trovato = f.read().strip() == b"syncthing"
            if trovato:
                out.append(int(v))
        except OSError:
            continue
    return out


def _porta_aperta() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", PORTA_GUI), timeout=0.5):
            return True
    except OSError:
        return False


def _gira() -> bool:
    """Syncthing c'è se lo vedo tra i processi O se la sua interfaccia risponde (anche se l'ha avviato un altro)."""
    return bool(_pids()) or _porta_aperta()


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


def _termina(pids: list):
    """SIGTERM (chiusura pulita) e, se non basta, SIGKILL. Aspetta che i processi spariscano."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for p in pids:
            try:
                os.kill(p, sig)
            except OSError:
                pass
        for _ in range(50):
            if not _pids():
                return
            time.sleep(0.2)
        pids = _pids()


def _lock_nel_log(da: int) -> bool:
    """Nel log di Syncthing, dopo il byte `da`, c'è l'errore del lock? (= un'altra istanza è già in esecuzione)"""
    try:
        with open(LOG_FILE, "rb") as f:
            f.seek(da)
            return b"acquire lock" in f.read()
    except OSError:
        return False


def _prova_avvio(exe: str, env: dict):
    """Lancia Syncthing e aspetta qualche secondo. Ritorna "ok", "lock" (c'è già un'istanza) o "fallito"."""
    for args in (["serve", "--no-browser"], ["--no-browser"]):         # versioni nuove / vecchie
        try:
            dim = LOG_FILE.stat().st_size if LOG_FILE.exists() else 0
            with open(LOG_FILE, "ab") as f:
                p = subprocess.Popen([exe, *args], cwd=str(BM.BASE), env=env, stdin=subprocess.DEVNULL,
                                     stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as e:
            log(f"Syncthing: avvio non riuscito: {e}")
            return "fallito"
        time.sleep(PROVA_AVVIO_S)
        if p.poll() is None:
            return "ok"
        if _lock_nel_log(dim):         # si è chiuso per il lock: inutile provare l'altra sintassi
            return "lock"
    return "fallito"


def _avvia():
    exe = _exe()
    if exe is None:
        return
    global _fallito
    with _lock:
        # i thread rimasti in coda mentre un altro avviava (apri() ne lancia uno per ogni contatto) escono qui
        if time.monotonic() - _fallito < RIPROVA_DOPO_S:
            return
        if _gira():
            _cache.update(t=time.monotonic(), v=True)
            return
        env = dict(os.environ, STNORESTART="1", STNOUPGRADE="1")
        esito = _prova_avvio(exe, env)
        if esito == "ok":
            log("Syncthing avviato")
            _cache.update(t=time.monotonic(), v=True)
            return
        if esito == "lock":
            # c'è già un'istanza che tiene il lock ma non l'ho riconosciuta tra i processi
            if _porta_aperta():
                log("Syncthing: è già in esecuzione, non lo riavvio")
                _cache.update(t=time.monotonic(), v=True)
                _fallito = time.monotonic()
                return
            pids = _pids()
            if pids:
                log("Syncthing: istanza bloccata (la GUI non risponde), la chiudo e la riavvio")
                _termina(pids)
                if _prova_avvio(exe, env) == "ok":
                    log("Syncthing riavviato")
                    _cache.update(t=time.monotonic(), v=True)
                    return
            else:
                log("Syncthing: un'altra istanza tiene il lock e non riesco a trovarla: fermala a mano (pkill -f syncthing)")
        _fallito = time.monotonic()
        log(f"Syncthing non parte: guarda {LOG_FILE.name}")


def apri():
    """Apertura vera (pagina caricata o tornata visibile, widget): contatto + avvio se non gira. Non blocca."""
    viva()
    if _exe() is not None and not attivo(max_eta=2.0) and time.monotonic() - _fallito > RIPROVA_DOPO_S:
        threading.Thread(target=_avvia, daemon=True).start()


def ferma():
    if not _gira():
        _cache.update(t=time.monotonic(), v=False)
        return
    pids = _pids()
    if not pids:
        log("Syncthing: gira ma non trovo il processo da fermare (fermalo a mano)")
        return
    log("Syncthing: nessun contatto dalla web app, lo fermo")
    _termina(pids)
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
