"""
bot_manager.py - avvia, ritrova e ferma telegram_bot.py e discord_bot.py per conto di Branch.

Idea
----
I bot sono processi INDIPENDENTI da Branch (staccati dalla sua finestra e dalla sua console):
  - Branch si apre  -> se i bot non girano li avvia; se girano già (lasciati da una sessione
                       precedente) li "adotta" senza riavviarli;
  - Branch si chiude -> i bot restano accesi;
  - i bot si fermano solo con il led di Branch (o con ferma_tutti()).

Per ritrovarli tra una sessione e l'altra salva i PID in  bots_pid.json  accanto a questo file
(con l'ora di creazione del processo, così un PID riciclato da Windows non viene scambiato per un bot).

Variabili d'ambiente dei bot (BOT_TOKEN, OWNER_ID, DISCORD_TOKEN, DISCORD_OWNER_ID, COOKIES_*, ...)
---------------------------------------------------------------------------------------------
Vengono raccolte in quest'ordine (l'ultima che vince):
  1. l'ambiente con cui è stato lanciato Branch;
  2. le righe  set NOME=valore  di avvia_bot.bat (se esiste accanto a questo file);
  3. il file  bots.env  accanto a questo file (righe NOME=valore, # per i commenti).
Se avvii Branch dal vecchio .bat non cambia nulla; altrimenti basta mettere i valori in bots.env.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
PID_FILE = BASE / "bots_pid.json"
ENV_FILE = BASE / "bots.env"
BAT_FILE = BASE / "launch.bat"

# nome interno -> (etichetta, script, variabili obbligatorie)
MODULI = {
    "telegram": ("Telegram", "telegram_bot.py", ("BOT_TOKEN", "OWNER_ID")),
    "discord": ("Discord", "discord_bot.py", ("DISCORD_TOKEN", "DISCORD_OWNER_ID")),
}

_IS_WIN = os.name == "nt"


# ---------------------------------------------------------------- ambiente
def _leggi_bat(p: Path) -> dict:
    out = {}
    try:
        righe = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for r in righe:
        m = re.match(r'\s*set\s+"?([A-Za-z_][A-Za-z0-9_]*)=(.*?)"?\s*$', r, re.I)
        if m and not re.match(r"\s*set\s+/[ap]\b", r, re.I):
            out[m.group(1)] = os.path.expandvars(m.group(2).strip())
    return out


def _leggi_env(p: Path) -> dict:
    out = {}
    try:
        righe = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for r in righe:
        r = r.strip()
        if not r or r.startswith("#") or "=" not in r:
            continue
        k, v = r.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip()] = os.path.expandvars(v)
    return out


def carica_env() -> dict:
    env = dict(os.environ)
    for k, v in _leggi_bat(BAT_FILE).items():
        env.setdefault(k, v)          # il .bat riempie solo ciò che manca
    env.update(_leggi_env(ENV_FILE))  # bots.env ha sempre l'ultima parola
    env["PYTHONUTF8"] = "1"
    env["BOT_LOG_FILE"] = "1"      # i bot scrivono su <script>.log (vedi bot_log.py)
    return env


# ---------------------------------------------------------------- processi
def _vita(pid: int):
    """None se il processo non esiste; altrimenti un numero che lo identifica (ora di creazione)."""
    if not pid or pid <= 0:
        return None
    if _IS_WIN:
        import ctypes
        from ctypes import wintypes
        k = ctypes.windll.kernel32
        k.OpenProcess.restype = wintypes.HANDLE
        h = k.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return None
        try:
            codice = wintypes.DWORD()
            if not k.GetExitCodeProcess(h, ctypes.byref(codice)) or codice.value != 259:   # STILL_ACTIVE
                return None
            c, e, kt, ut = (wintypes.FILETIME() for _ in range(4))
            if k.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(kt), ctypes.byref(ut)):
                return ((c.dwHighDateTime << 32) | c.dwLowDateTime) / 1e7
            return 0.0
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        pass
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        resto = stat.rsplit(")", 1)[1].split()
        if resto[0] == "Z":      # zombie = già morto
            return None
        return float(resto[19])
    except Exception:
        return 0.0


def _stesso(a, b) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) < 2.0


class GestoreBot:
    def __init__(self, log=print):
        self.log = log
        self._lock = threading.RLock()
        self._figli: dict[str, subprocess.Popen] = {}   # per far "raccogliere" i processi avviati da noi
        self.errori: dict[str, str] = {}
        self.occupato = False                           # True mentre si avvia/ferma

    # ---- file dei PID
    def _leggi(self) -> dict:
        try:
            d = json.loads(PID_FILE.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def _scrivi(self, d: dict):
        try:
            tmp = PID_FILE.with_name(PID_FILE.name + ".tmp")
            tmp.write_text(json.dumps(d), encoding="utf-8")
            os.replace(tmp, PID_FILE)
        except OSError as e:
            self.log(f"bots_pid.json non salvato: {e}")

    # ---- stato
    def attivo(self, nome: str) -> bool:
        with self._lock:
            f = self._figli.get(nome)
            if f is not None and f.poll() is not None:       # terminato: raccolto
                self.errori[nome] = (f"si è chiuso subito (codice {f.returncode}): "
                                     f"controlla il log di {MODULI[nome][1]}")
                self._figli.pop(nome, None)
            voce = self._leggi().get(nome)
            if not voce:
                return False
            return _stesso(_vita(int(voce.get("pid", 0))), voce.get("t"))

    def stato(self) -> dict:
        return {n: self.attivo(n) for n in MODULI}

    # ---- avvio
    def avvia(self, nome: str) -> bool:
        with self._lock:
            if self.attivo(nome):
                return True
            etichetta, script, richieste = MODULI[nome]
            self.errori.pop(nome, None)
            percorso = BASE / script
            if not percorso.exists():
                self.errori[nome] = f"{script} non trovato in {BASE}"
                return False
            env = carica_env()
            mancano = [v for v in richieste if not env.get(v)]
            if mancano:
                self.errori[nome] = "mancano " + ", ".join(mancano) + " (mettili in bots.env)"
                self.log(f"{etichetta}: non avviato, {self.errori[nome]}")
                return False
            exe = sys.executable
            kw = {}
            if _IS_WIN:
                pw = Path(exe).with_name("pythonw.exe")      # senza finestra di console
                if pw.exists():
                    exe = str(pw)
                kw["creationflags"] = 0x00000008 | 0x00000200   # DETACHED_PROCESS | NEW_PROCESS_GROUP
            else:
                kw["start_new_session"] = True
            cmd = [exe, str(percorso)]
            try:
                try:
                    if _IS_WIN:   # esce dal job di chi ci ha lanciato, così non muore con lui
                        p = subprocess.Popen(cmd, cwd=str(BASE), env=env, stdin=subprocess.DEVNULL,
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                                             creationflags=kw["creationflags"] | 0x01000000)
                    else:
                        p = subprocess.Popen(cmd, cwd=str(BASE), env=env, stdin=subprocess.DEVNULL,
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
                except OSError:
                    if not _IS_WIN:
                        raise
                    p = subprocess.Popen(cmd, cwd=str(BASE), env=env, stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                                         creationflags=kw["creationflags"])
            except Exception as e:
                self.errori[nome] = f"avvio non riuscito: {e}"
                self.log(f"{etichetta}: {self.errori[nome]}")
                return False
            self._figli[nome] = p
            d = self._leggi()
            d[nome] = {"pid": p.pid, "t": _vita(p.pid) or 0.0, "avviato": time.time()}
            self._scrivi(d)
            self.log(f"{etichetta}: avviato (pid {p.pid})")
            return True

    def avvia_mancanti(self):
        """Avvia solo i bot che non girano già (quelli lasciati accesi vengono adottati)."""
        self.occupato = True
        try:
            for n in MODULI:
                if self.attivo(n):
                    self.log(f"{MODULI[n][0]}: già in esecuzione, lo riprendo senza riavviarlo")
                else:
                    self.avvia(n)
            time.sleep(2.5)           # un bot che crasha subito (token sbagliato…) si vede qui
            self.stato()
        finally:
            self.occupato = False

    # ---- aggiornamento da GitHub
    def _git(self, *args):
        return subprocess.run(["git", *args], cwd=str(BASE), capture_output=True, text=True, timeout=90,
                              creationflags=0x08000000 if _IS_WIN else 0)

    def aggiorna(self, ramo: str = "main") -> str:
        """git fetch + fast-forward; riavvia solo i bot i cui file sono cambiati.
        Non tocca il flag 'occupato': lo gestisce chi lo chiama (in_thread in org_bot.py)."""
        if not shutil.which("git"):
            return "git non installato"
        if not (BASE / ".git").exists():
            return "la cartella non è un repository git"
        try:
            r = self._git("fetch", "origin", ramo)
            if r.returncode:
                msg = f"aggiornamento: fetch non riuscito: {r.stderr.strip()[:200]}"
                self.log(msg)
                return msg
            locale = self._git("rev-parse", "HEAD").stdout.strip()
            remoto = self._git("rev-parse", f"origin/{ramo}").stdout.strip()
            if not remoto or locale == remoto:
                return "già aggiornato"
            cambiati = set(self._git("diff", "--name-only", "HEAD", f"origin/{ramo}").stdout.split())
            r = self._git("merge", "--ff-only", f"origin/{ramo}")
            if r.returncode:
                msg = f"aggiornamento: merge non riuscito (modifiche locali?): {r.stderr.strip()[:200]}"
                self.log(msg)
                return msg
        except Exception as e:
            msg = f"aggiornamento non riuscito: {e}"
            self.log(msg)
            return msg

        da_riavviare = set()
        if cambiati & {"org_bot.py", "bot_log.py"}:      # org_bot è caricato anche da discord_bot
            da_riavviare = set(MODULI)
        if "telegram_bot.py" in cambiati:
            da_riavviare.add("telegram")
        if "discord_bot.py" in cambiati:
            da_riavviare.add("discord")
        for n in sorted(da_riavviare):
            if self.attivo(n):
                self.ferma(n)
                self.avvia(n)
        msg = f"aggiornato a {remoto[:7]}"
        if da_riavviare:
            msg += ", riavviati: " + ", ".join(sorted(da_riavviare))
        if cambiati & {"bot_manager.py", "branch_tema.py", "org_bot.py"}:
            msg += " (riavvia Branch per applicare le modifiche a Branch stesso)"
        self.log(msg)
        return msg

    # ---- arresto
    def ferma(self, nome: str):
        with self._lock:
            voce = self._leggi().get(nome)
            if voce and self.attivo(nome):
                pid = int(voce["pid"])
                try:
                    if _IS_WIN:    # /T: chiude anche ffmpeg, yt-dlp… lanciati dal bot
                        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                                       creationflags=0x08000000)
                    else:
                        try:
                            os.killpg(pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        for _ in range(50):
                            f = self._figli.get(nome)
                            if f is not None:
                                f.poll()
                            if _vita(pid) is None:
                                break
                            time.sleep(0.1)
                        else:
                            try:
                                os.killpg(pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                except Exception as e:
                    self.log(f"{MODULI[nome][0]}: arresto non riuscito: {e}")
                for _ in range(30):
                    if _vita(pid) is None:
                        break
                    time.sleep(0.1)
                self.log(f"{MODULI[nome][0]}: fermato (pid {pid})")
            f = self._figli.pop(nome, None)
            if f is not None:
                try:
                    f.wait(timeout=1)
                except Exception:
                    pass
            self.errori.pop(nome, None)
            d = self._leggi()
            if nome in d:
                d.pop(nome)
                self._scrivi(d)

    def ferma_tutti(self):
        self.occupato = True
        try:
            for n in MODULI:
                self.ferma(n)
        finally:
            self.occupato = False
