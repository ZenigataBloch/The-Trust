"""
heartbeat.py - dice al telefono che i bot girano già sul PC (e al PC che girano già sul telefono),
passando da Telegram.

Come funziona
-------------
  PC (ruolo "desktop")    un piccolo processo STACCATO (come i bot: sopravvive alla chiusura di Branch)
                          tiene aggiornato un messaggio fissato nella chat privata col bot:
                              BRANCH|ON|<nome pc>|<epoch>      ogni 20 s finché almeno un bot gira
                              BRANCH|OFF|<nome pc>|<epoch>     appena i bot si spengono
  telefono (ruolo "telefono")
                          il pannello legge il messaggio fissato con getChat (NON getUpdates: non
                          interferisce col polling di telegram_bot.py) ogni 15 s.
                          "Desktop attivo" = ON e il valore cambia entro 70 s (non conta l'orologio del PC).
                          Torna "spento" dopo 2 letture di fila senza heartbeat valido.
                          Se Telegram non è raggiungibile lo stato NON cambia (senza rete i bot non girano comunque).

  Direzione inversa (telefono -> PC): c'è UN SOLO messaggio fissato per chat, quindi lo condividono. Ognuno
  riscrive solo la propria metà, leggendo prima il messaggio com'è adesso:
      BRANCH|ON|<pc>|<epoch>|ANDROID|ON|<telefono>|<epoch>
  Le prime quattro voci sono quelle di sempre (un lettore vecchio le capisce ancora). Il telefono ora
  pubblica anche lui (il processo staccato parte con i bot, come sul PC) e il PC lo legge con heartbeat.LA:
  app desktop -> led blu «BOT ATTIVI SU ANDROID». Se due scritture si sovrappongono una metà può andare
  persa, ma viene riscritta al giro dopo (20 s).

Configurazione (bots.env, tutto facoltativo):
  HB_RUOLO=desktop|telefono|off   default: "telefono" se gira in Termux, altrimenti "desktop"
  HB_CHAT=<chat id>               default: OWNER_ID (chat privata col bot)
Usa BOT_TOKEN dello stesso bot di telegram_bot.py. Nella chat non fissare altri messaggi: getChat restituisce
l'ultimo fissato.
"""
import json
import os
import signal
import subprocess
import sys
import threading
import time
import socket
import urllib.error
import urllib.request
from pathlib import Path

import bot_manager as BM

BASE = BM.BASE
PID_FILE = BASE / "hb_pid.json"
LOG_FILE = BASE / "heartbeat.log"
PREFISSO = "BRANCH"
INVIO_S = 20          # ogni quanto il PC aggiorna il messaggio
CONTROLLO_S = 5       # ogni quanto il PC guarda se i bot sono accesi/spenti (per segnalare lo spegnimento subito)
LETTURA_S = 15        # ogni quanto il telefono legge
FRESCO_S = 70         # un heartbeat che non cambia da più di così è considerato morto
CONFERME_OFF = 2      # letture "non valide" di fila prima di dichiarare il desktop spento
TOLLERANZA_S = 300    # alla prima lettura: scarto massimo tra l'ora scritta dall'altro dispositivo e la mia


class ApiErr(Exception):
    pass


def _log(msg):
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 200_000:
            LOG_FILE.write_text("", encoding="utf-8")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n")
    except OSError:
        pass


def _cfg():
    """(ruolo, token, chat). ruolo: desktop | telefono | off."""
    e = BM.carica_env()
    ruolo = e.get("HB_RUOLO", "").strip().lower()
    if ruolo not in ("desktop", "telefono", "off"):
        termux = bool(e.get("TERMUX_VERSION")) or "com.termux" in e.get("PREFIX", "")
        ruolo = "telefono" if termux else "desktop"
    chat = (e.get("HB_CHAT") or e.get("OWNER_ID") or "").strip()
    return ruolo, e.get("BOT_TOKEN", "").strip(), chat


def _api(token, metodo, **par):
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{metodo}",
                                 data=json.dumps(par).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            d = json.loads(e.read())
        except Exception:
            raise ApiErr(f"{metodo}: HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise ApiErr(f"{metodo}: rete non raggiungibile ({e.reason})") from None
    if not d.get("ok"):
        raise ApiErr(f"{metodo}: {d.get('description', '?')}")
    return d["result"]


# ================================================================ PC: mittente
def _nome_pc():
    return "".join(c for c in socket.gethostname() if c.isalnum() or c in "-_.")[:30] or "pc"


def _parti(testo) -> dict:
    """'BRANCH|ON|pc|t[|ANDROID|ON|tel|t]' -> {'desktop': (stato, host, t), 'android': (...)} (vuoto se non è nostro)."""
    p = (testo or "").split("|")
    out = {}
    if len(p) < 4 or p[0] != PREFISSO:
        return out
    if p[1] in ("ON", "OFF"):
        out["desktop"] = (p[1], p[2], p[3])
    if len(p) >= 8 and p[4] == "ANDROID" and p[5] in ("ON", "OFF"):
        out["android"] = (p[5], p[6], p[7])
    return out


def _testo(parti: dict) -> str:
    d = parti.get("desktop") or ("OFF", "", "0")
    t = f"{PREFISSO}|{d[0]}|{d[1]}|{d[2]}"
    a = parti.get("android")
    if a:
        t += f"|ANDROID|{a[0]}|{a[1]}|{a[2]}"
    return t


class _Pubblicatore:
    def __init__(self, token, chat, parte="desktop"):
        self.token, self.chat, self.parte = token, chat, parte    # parte: "desktop" | "android"

    def pubblica(self, acceso: bool):
        mio = ("ON" if acceso else "OFF", _nome_pc(), str(int(time.time())))
        # leggo il messaggio fissato com'è adesso: l'altra metà non va persa (se getChat fallisce non scrivo)
        m = _api(self.token, "getChat", chat_id=self.chat).get("pinned_message") or {}
        parti = _parti(m.get("text"))
        mid = m.get("message_id") if parti else None      # fissato e nostro -> lo modifico
        parti[self.parte] = mio
        testo = _testo(parti)
        if mid:
            try:
                _api(self.token, "editMessageText", chat_id=self.chat, message_id=mid, text=testo)
                return
            except ApiErr as e:
                s = str(e).lower()
                if "not modified" in s:
                    return
                if not any(x in s for x in ("not found", "can't be edited", "message_id_invalid", "to edit")):
                    raise
                _log("messaggio heartbeat sparito: ne creo uno nuovo")
        r = _api(self.token, "sendMessage", chat_id=self.chat, text=testo, disable_notification=True)
        try:
            _api(self.token, "pinChatMessage", chat_id=self.chat, message_id=r["message_id"],
                 disable_notification=True)
        except ApiErr as e:
            _log(f"fissaggio non riuscito (l'altro dispositivo non vedrà il messaggio): {e}")


def _leggi_pid():
    try:
        d = json.loads(PID_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _vivo(v):
    return bool(v) and BM._stesso(BM._vita(int(v.get("pid", 0))), v.get("t"))


def sender():
    """Ciclo del processo staccato (python heartbeat.py --sender)."""
    ruolo, token, chat = _cfg()
    if ruolo not in ("desktop", "telefono") or not token or not chat:
        return
    v = _leggi_pid()
    if _vivo(v) and int(v["pid"]) != os.getpid():
        return                                   # c'è già un mittente
    pub = _Pubblicatore(token, chat, "desktop" if ruolo == "desktop" else "android")
    g = BM.GestoreBot(log=_log)
    _log(f"mittente avviato (pid {os.getpid()})")
    ultimo = None            # ultimo stato pubblicato (True/False)
    t_invio = 0.0
    while True:
        try:
            acceso = any(g.stato().values())
            if acceso != ultimo or (acceso and time.time() - t_invio >= INVIO_S):
                pub.pubblica(acceso)
                ultimo, t_invio = acceso, time.time()
        except Exception as e:
            _log(f"errore: {e}")
        time.sleep(CONTROLLO_S)


def assicura_sender(log=print) -> bool:
    """Chiamata da bot_manager dopo l'avvio/adozione dei bot: fa partire il mittente (PC o telefono) se non c'è."""
    ruolo, token, chat = _cfg()
    if ruolo not in ("desktop", "telefono") or not token or not chat:
        return False
    if _vivo(_leggi_pid()):
        return True
    exe = sys.executable
    cmd_extra = {}
    if BM._IS_WIN:
        pw = Path(exe).with_name("pythonw.exe")
        if pw.exists():
            exe = str(pw)
        flag = 0x00000008 | 0x00000200            # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        cmd_extra["start_new_session"] = True
        flag = 0
    cmd = [exe, str(BASE / "heartbeat.py"), "--sender"]
    kw = dict(cwd=str(BASE), env=BM.carica_env(), stdin=subprocess.DEVNULL,
              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **cmd_extra)
    try:
        try:
            p = subprocess.Popen(cmd, close_fds=True, **({"creationflags": flag | 0x01000000} if BM._IS_WIN else {}), **kw)
        except OSError:
            if not BM._IS_WIN:
                raise
            p = subprocess.Popen(cmd, close_fds=True, creationflags=flag, **kw)
    except Exception as e:
        log(f"heartbeat: avvio non riuscito: {e}")
        return False
    try:
        PID_FILE.write_text(json.dumps({"pid": p.pid, "t": BM._vita(p.pid) or 0.0}), encoding="utf-8")
    except OSError:
        pass
    log(f"heartbeat: mittente avviato (pid {p.pid})")
    return True


def riavvia_sender(log=print):
    """Dopo un aggiornamento da GitHub di heartbeat.py."""
    v = _leggi_pid()
    if _vivo(v):
        pid = int(v["pid"])
        try:
            if BM._IS_WIN:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=0x08000000)
            else:
                os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        for _ in range(30):
            if BM._vita(pid) is None:
                break
            time.sleep(0.1)
    PID_FILE.unlink(missing_ok=True)
    if any(BM.GestoreBot(log=log).stato().values()):
        assicura_sender(log)


# ================================================================ telefono: lettore
class Lettore:
    def __init__(self, parte="desktop"):
        self.parte = parte           # metà letta: "desktop" (lo usa il telefono) o "android" (lo usa il PC)
        self.ruolo = "telefono" if parte == "desktop" else "desktop"      # ruolo di chi legge
        self.attivo = False          # True = l'altro dispositivo ha i bot accesi
        self.host = ""
        self.errore = None
        self._letto = threading.Event()   # settato dopo la prima lettura riuscita
        self._primo = True
        self._ultimo_t = None
        self._visto = -1e9
        self._off = 0
        self._su_cambio = None
        self._log = _log

    def avvia(self, su_cambio=None, log=None) -> bool:
        """Parte solo con il ruolo di chi legge (telefono per L, desktop per LA). su_cambio(attivo: bool)
        viene chiamata a ogni cambio di stato."""
        self._su_cambio = su_cambio
        if log:
            self._log = log
        ruolo, token, chat = _cfg()
        if ruolo != self.ruolo or not token or not chat:
            self._letto.set()
            return False
        threading.Thread(target=self._ciclo, args=(token, chat), daemon=True).start()
        return True

    def attendi(self, secondi: float = 8.0):
        """Prima di accendere i bot: aspetta la prima lettura (o il timeout se Telegram non risponde)."""
        self._letto.wait(secondi)

    def info(self) -> dict:
        return {"attivo": self.attivo, "host": self.host, "errore": self.errore}

    def _ciclo(self, token, chat):
        while True:
            try:
                m = _api(token, "getChat", chat_id=chat).get("pinned_message") or {}
                self.errore = None
                self.elabora(m)
                self._letto.set()
            except Exception as e:
                self.errore = str(e)[:150]       # stato invariato: senza rete nemmeno i bot funzionano
            time.sleep(LETTURA_S)

    def elabora(self, m: dict, adesso=None):
        """Aggiorna lo stato da un messaggio fissato (separato da _ciclo per poterlo provare)."""
        adesso = time.monotonic() if adesso is None else adesso
        h = _parti(m.get("text")).get(self.parte)
        acceso = bool(h) and h[0] == "ON"
        if acceso:
            self.host = h[1]
            t = h[2]
            if self._ultimo_t is None:
                # primo ON visto: mi fido dell'ora di Telegram solo per decidere se è recente. Il messaggio
                # è condiviso (l'altro dispositivo lo modifica di continuo), quindi controllo anche l'ora
                # scritta nella metà letta, con ampia tolleranza per gli orologi sfasati
                eta = time.time() - float(m.get("edit_date") or m.get("date") or 0)
                try:
                    sfasamento = abs(time.time() - float(t))
                except ValueError:
                    sfasamento = 1e9
                self._visto = adesso if (eta <= FRESCO_S and sfasamento <= TOLLERANZA_S) else -1e9
            elif t != self._ultimo_t:
                self._visto = adesso               # il valore è cambiato: il PC è vivo
            self._ultimo_t = t
        else:
            self._ultimo_t = None
        fresco = acceso and adesso - self._visto <= FRESCO_S
        if fresco:
            self._off = 0
            nuovo = True
        else:
            self._off += 1
            nuovo = False if (self._primo or self._off >= CONFERME_OFF) else self.attivo
        self._primo = False
        if nuovo != self.attivo:
            self.attivo = nuovo
            self._log(f"heartbeat: {self.parte} {'ATTIVO' if nuovo else 'spento'}")
            if self._su_cambio:
                try:
                    self._su_cambio(nuovo)
                except Exception as e:
                    self._log(f"heartbeat: errore nel callback {e!r}")


L = Lettore("desktop")       # per il telefono: il PC ha i bot accesi?
LA = Lettore("android")      # per il PC: il telefono ha i bot accesi?

if __name__ == "__main__":
    if "--sender" in sys.argv:
        sender()
