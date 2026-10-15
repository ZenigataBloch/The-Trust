"""
impostazioni.py - cookie, chiavi API e tetto giornaliero delle ricerche: la logica sta qui e la usano
sia il pannello web (pannello.py, Android) sia l'app desktop (org_bot.py, scheda IMPOSTAZIONI).

  cookie   cookie_stato / cookie_analizza / cookie_applica     -> cookies.txt (Netscape)
  chiavi   chiavi_leggi / chiavi_salva                         -> righe di bots.env (le chiavi non tornano mai intere)
  tetto    cap_leggi / cap_salva / cap_azzera                  -> graves_uso.json (vedi graves.py), vale subito

Dipende solo da bot_manager (e da graves per il tetto): niente tkinter, niente org_bot.
"""
import contextlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path

import bot_manager as BM

log = print          # chi importa lo sostituisce con il proprio log (es. IMP.log = O._log_gui)


def _env() -> dict:
    """Ambiente dei bot: variabili del processo + bots.env (come lo vedono i bot quando partono)."""
    return BM.carica_env()


def scrivi_atomico(path: Path, testo: str):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(testo, encoding="utf-8")
    os.replace(tmp, path)


# ------------------------------------------------------------ cookie
# Siti tenuti (gli altri cookie dell'export vengono scartati). Modificabili con COOKIE_DOMINI in bots.env.
COOKIE_DOMINI = [d.strip().lower().lstrip(".") for d in
                 _env().get("COOKIE_DOMINI", "tiktok.com,instagram.com,reddit.com,x.com").split(",") if d.strip()]
# cookie che provano il login: se mancano, probabilmente non eri loggato quando hai esportato
COOKIE_LOGIN = {"tiktok.com": ("sessionid", "sid_tt"), "instagram.com": ("sessionid",),
                "reddit.com": ("reddit_session", "token_v2"), "x.com": ("auth_token",)}
HTTPONLY = "#HttpOnly_"
HEADER_COOKIE = "# Netscape HTTP Cookie File"
_HOST_RE = re.compile(r"[A-Za-z0-9._\-]+")


def cookie_file() -> Path:
    f = _env().get("COOKIES_FILE")
    return Path(f).expanduser() if f else BM.BASE / "cookies.txt"


def _dominio(campo: str) -> str:
    return campo.removeprefix(HTTPONLY).lstrip(".").lower()


def _sito(dominio: str):
    for s in COOKIE_DOMINI:
        if dominio == s or dominio.endswith("." + s):
            return s
    return None


def _campi_valido(c):
    """I 7 campi Netscape normalizzati, oppure None se la riga non è un cookie."""
    if len(c) < 7:
        return None
    c = c[:6] + ["\t".join(c[6:])] if len(c) > 7 else list(c)
    dom = _dominio(c[0])
    if not dom or "." not in dom or not _HOST_RE.fullmatch(dom):
        return None
    if c[1].upper() not in ("TRUE", "FALSE") or c[3].upper() not in ("TRUE", "FALSE"):
        return None
    if not re.fullmatch(r"\d+", c[4].strip()) or not c[2].startswith("/") or not c[5].strip():
        return None
    return [c[0], c[1].upper(), c[2], c[3].upper(), c[4].strip(), c[5], c[6]]


def _da_json(testo: str):
    """Export JSON (Cookie-Editor...) -> (cookie in campi Netscape, quanti elementi scartati)."""
    dati = json.loads(testo)
    if isinstance(dati, dict):
        dati = dati["cookies"] if isinstance(dati.get("cookies"), list) else [dati]
    if not isinstance(dati, list):
        raise ValueError("json")
    ok, scartati = [], 0
    for c in dati:
        try:
            dom, nome = str(c["domain"]), str(c["name"])
            solo_host = bool(c.get("hostOnly", not dom.startswith(".")))
            if not solo_host and not dom.startswith("."):
                dom = "." + dom
            scad = 0 if c.get("session") else max(0, int(float(c.get("expirationDate") or c.get("expires") or 0)))
            riga = _campi_valido([(HTTPONLY if c.get("httpOnly") else "") + dom, "FALSE" if solo_host else "TRUE",
                                  str(c.get("path") or "/"), "TRUE" if c.get("secure") else "FALSE",
                                  str(scad), nome, str(c.get("value", ""))])
        except (KeyError, TypeError, ValueError, AttributeError):
            riga = None
        if riga:
            ok.append(riga)
        else:
            scartati += 1
    return ok, scartati


def _da_netscape(testo: str):
    ok, scartati = [], 0
    for riga in testo.splitlines():
        r = riga.rstrip("\r\n")
        s = r.lstrip()
        if not s or (s.startswith("#") and not s.startswith(HTTPONLY)):
            continue                                   # righe vuote e commenti non contano
        c = _campi_valido(r.split("\t")) or _campi_valido(re.split(r"\s+", s, maxsplit=6))   # tab persi negli appunti
        if c:
            ok.append(c)
        else:
            scartati += 1
    return ok, scartati


def cookie_analizza(testo: str) -> dict:
    """Controlla che il testo siano cookie (JSON o cookies.txt) e tiene solo i siti di COOKIE_DOMINI.
    Non restituisce mai il contenuto dei cookie negli errori."""
    testo = (testo or "").lstrip("\ufeff").strip()
    res = {"formato": None, "validi": 0, "altri": 0, "scartati": 0, "siti": {}, "righe": [], "errore": None}
    if not testo:
        res["errore"] = "Gli appunti sono vuoti."
        return res
    if testo[0] in "[{":
        res["formato"] = "JSON"
        try:
            campi, res["scartati"] = _da_json(testo)
        except ValueError:
            res["errore"] = "Sembra JSON ma non è valido: la copia è incompleta? Riesporta e riprova."
            return res
    else:
        res["formato"] = "Netscape (cookies.txt)"
        campi, res["scartati"] = _da_netscape(testo)
    res["validi"] = len(campi)
    if not campi:
        res["errore"] = "Non sono cookie: il testo non è un export di cookie (né JSON né cookies.txt)."
        return res
    ora, nomi = time.time(), {}
    for c in campi:
        s = _sito(_dominio(c[0]))
        if not s:
            res["altri"] += 1
            continue
        d = res["siti"].setdefault(s, {"n": 0, "scaduti": 0, "avviso": ""})
        d["n"] += 1
        if 0 < int(c[4]) < ora:
            d["scaduti"] += 1
        nomi.setdefault(s, set()).add(c[5])
        res["righe"].append("\t".join(c))
    if not res["siti"]:
        res["errore"] = (f"{len(campi)} cookie riconosciuti, ma nessuno dei siti supportati "
                         f"({', '.join(COOKIE_DOMINI)}). Hai esportato dal sito giusto?")
        return res
    for s, d in res["siti"].items():
        if s in COOKIE_LOGIN and not (set(COOKIE_LOGIN[s]) & nomi.get(s, set())):
            d["avviso"] = f"manca il cookie di accesso ({COOKIE_LOGIN[s][0]}): forse non eri loggato"
        elif d["scaduti"] == d["n"]:
            d["avviso"] = "sono tutti scaduti"
    return res


def cookie_applica(testo: str) -> dict:
    """Sostituisce in cookies.txt i cookie dei siti presenti nell'export e lascia intatti gli altri.
    Il vecchio file resta come cookies.txt.bak."""
    res = cookie_analizza(testo)
    if res["errore"]:
        return res
    out = cookie_file()
    tenute = []
    if out.exists():
        vecchio = out.read_text(encoding="utf-8-sig")
        shutil.copy2(out, out.with_name(out.name + ".bak"))
        for r in vecchio.splitlines():
            c = _campi_valido(r.split("\t"))
            if c and _sito(_dominio(c[0])) not in res["siti"]:
                tenute.append(r.rstrip("\r\n"))
    scrivi_atomico(out, HEADER_COOKIE + "\n" + "\n".join(tenute + res["righe"]) + "\n")
    try:
        os.chmod(out, 0o600)                           # i cookie sono sessioni: solo tu
    except OSError:
        pass
    log("cookie: aggiornati " + ", ".join(f"{s} ({d['n']})" for s, d in res["siti"].items()))
    return res



def cookie_stato() -> dict:
    out = cookie_file()
    siti = {s: {"n": 0, "scaduti": 0} for s in COOKIE_DOMINI}
    if out.exists():
        ora = time.time()
        for r in out.read_text(encoding="utf-8-sig").splitlines():
            c = _campi_valido(r.split("\t"))
            s = _sito(_dominio(c[0])) if c else None
            if s:
                siti[s]["n"] += 1
                if 0 < int(c[4]) < ora:
                    siti[s]["scaduti"] += 1
    return {"esiste": out.exists(), "file": out.name, "siti": siti,
                 "mtime": out.stat().st_mtime if out.exists() else 0}


# ------------------------------------------------------------ chiavi API (bots.env)
# Solo queste variabili si possono leggere/scrivere dal pannello: (variabile, etichetta, valore suggerito se manca)
CHIAVI_SITI = {
    "rule34.xxx": [("GRAVES_R34_USER", "user_id", "marquise"), ("GRAVES_R34_KEY", "api key", "")],
    "Gelbooru": [("GRAVES_GELBOORU_USER", "user_id", "marquise"), ("GRAVES_GELBOORU_KEY", "api key", "")],
    "Danbooru (facoltativo)": [("GRAVES_DANBOORU_USER", "utente", ""), ("GRAVES_DANBOORU_KEY", "api key", "")],
    "e621 (facoltativo)": [("GRAVES_E621_USER", "utente", ""), ("GRAVES_E621_KEY", "api key", "")],
    "Ricerca Google: Serper": [("GRAVES_SERPER_KEY", "chiave", "")],
    "Ricerca Google: SerpApi": [("GRAVES_SERPAPI_KEY", "chiave", "")],
}
CHIAVI_OK = {n: sito for sito, voci in CHIAVI_SITI.items() for n, _e, _s in voci}
_RE_RIGA_ENV = re.compile(r"^(\s*(?:export\s+)?)([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
_ENV_SICURO = re.compile(r"^[\w.@:/+,=-]*$")
_chiavi_lock = threading.Lock()


def env_file() -> Path:
    return getattr(BM, "ENV_FILE", BM.BASE / "bots.env")


def _env_pulisci(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def _env_formatta(v: str) -> str:
    return v if _ENV_SICURO.match(v) else "'" + v.replace("'", "'\\''") + "'"


class EnvFile:
    """bots.env letto come righe: cambia solo le variabili indicate, il resto (commenti, ordine, altre variabili,
    tipo di fine riga) resta com'è. Una variabile ripetuta viene tenuta una volta sola (l'ultima vince, per i bot)."""

    def __init__(self, path: Path):
        self.path = path
        try:
            grezzo = path.read_bytes().decode("utf-8-sig")
        except FileNotFoundError:
            grezzo = ""
        self.eol = "\r\n" if "\r\n" in grezzo else "\n"
        self.righe = grezzo.replace("\r\n", "\n").split("\n")
        if self.righe and self.righe[-1] == "":
            self.righe.pop()
        self.modificato = False

    def _pos(self, nome: str) -> list:
        out = []
        for i, r in enumerate(self.righe):
            m = _RE_RIGA_ENV.match(r)
            if m and m.group(2) == nome and not r.lstrip().startswith("#"):
                out.append(i)
        return out

    def leggi(self, nome: str):
        pos = self._pos(nome)
        return _env_pulisci(_RE_RIGA_ENV.match(self.righe[pos[-1]]).group(3)) if pos else None

    def imposta(self, nome: str, valore: str):
        pos = self._pos(nome)
        if pos:
            pref = _RE_RIGA_ENV.match(self.righe[pos[0]]).group(1)
            self.righe[pos[0]] = f"{pref}{nome}={_env_formatta(valore)}"
            for i in reversed(pos[1:]):
                del self.righe[i]
        else:
            self.righe.append(f"{nome}={_env_formatta(valore)}")
        self.modificato = True

    def rimuovi(self, nome: str) -> bool:
        pos = self._pos(nome)
        for i in reversed(pos):
            del self.righe[i]
        self.modificato = self.modificato or bool(pos)
        return bool(pos)

    def salva(self):
        if not self.modificato:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            shutil.copy2(self.path, self.path.with_name(self.path.name + ".bak"))
        testo = self.eol.join(self.righe) + (self.eol if self.righe else "")
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".bots.env.")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(testo.encode("utf-8"))
            with contextlib.suppress(OSError):
                os.chmod(tmp, 0o600)                       # contiene chiavi: solo tu
            os.replace(tmp, self.path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        self.modificato = False


def _maschera(nome: str, v):
    """Le chiavi non escono mai intere dal server: solo gli ultimi 4 caratteri."""
    if v is None:
        return ""
    if nome.endswith("_KEY"):
        return ("•••• " + v[-4:]) if len(v) > 8 else "••••"
    return v


def _credenziali_incollate(testo: str) -> dict:
    """Dal sito le credenziali sono '&api_key=XXXX&user_id=123': ne ricavo i due valori."""
    out = {}
    mk = re.search(r"api_key=([^&\s\"']+)", testo)
    mu = re.search(r"user_id=([^&\s\"']+)", testo)
    if mk:
        out["key"] = mk.group(1)
    if mu:
        out["user"] = mu.group(1)
    return out



def chiavi_leggi() -> dict:
    env = EnvFile(env_file())
    siti = []
    for sito, voci in CHIAVI_SITI.items():
        campi = []
        for nome, etichetta, suggerito in voci:
            v = env.leggi(nome)
            campi.append({"nome": nome, "etichetta": etichetta, "impostata": bool(v), "valore": _maschera(nome, v),
                          "segreta": nome.endswith("_KEY"), "suggerito": suggerito})
        siti.append({"sito": sito, "campi": campi})
    return {"file": env.path.name, "esiste": env.path.exists(), "siti": siti}


def chiavi_salva(valori, togli) -> dict:
    """Aggiunge/sostituisce/toglie le variabili in bots.env. ValueError con il motivo se la richiesta non è valida."""
    valori, togli = valori or {}, togli or []
    if not isinstance(valori, dict) or not isinstance(togli, list):
        raise ValueError("Richiesta non valida.")
    estranei = [n for n in list(valori) + togli if n not in CHIAVI_OK]
    if estranei:
        raise ValueError("Variabile non gestita dal pannello: " + ", ".join(map(str, estranei[:3])))
    with _chiavi_lock:
        env = EnvFile(env_file())
        nuovi, tolti = {}, []
        for nome, v in valori.items():
            v = str(v)
            cred = _credenziali_incollate(v)
            if cred:                                        # stringa &api_key=...&user_id=... incollata
                voci = [n for n, _e, _s in CHIAVI_SITI[CHIAVI_OK[nome]]]
                for n in voci:
                    if n.endswith("_KEY") and "key" in cred:
                        nuovi[n] = cred["key"]
                    if n.endswith("_USER") and "user" in cred:
                        nuovi[n] = cred["user"]
            elif v.strip():
                nuovi[nome] = _env_pulisci(v)
        for nome, v in nuovi.items():
            env.imposta(nome, v)
        for nome in togli:
            if nome not in nuovi and env.rimuovi(nome):
                tolti.append(nome)
        env.salva()
    for nome, v in nuovi.items():                            # i bot partono con l'ambiente del pannello + bots.env
        os.environ[nome] = v
    for nome in tolti:
        os.environ.pop(nome, None)
    cambiati = sorted(set(nuovi) | set(tolti))
    if cambiati:
        log("chiavi: aggiornate " + ", ".join(cambiati))     # solo i nomi, mai i valori
    return {"cambiati": cambiati, "impostate": sorted(nuovi), "tolte": tolti}


# ------------------------------------------------------------ tetto giornaliero (graves_uso.json)
_ETICHETTE = {"booru-r34": "rule34.xxx", "booru-gelbooru": "Gelbooru", "booru-danbooru": "Danbooru",
              "booru-redgifs": "RedGifs", "booru-e621": "e621", "serper": "Ricerca Google: Serper",
              "serpapi": "Ricerca Google: SerpApi", "cse": "Ricerca Google: Programmable Search"}


def _graves():
    import graves
    v = _env().get("GRAVES_MAX_GIORNO")
    if v and "GRAVES_MAX_GIORNO" not in os.environ:      # l'app desktop non carica bots.env nel proprio ambiente
        os.environ["GRAVES_MAX_GIORNO"] = v
    f = _env().get("GRAVES_STATO_FILE")
    return graves, (Path(f).expanduser() if f else None)


def cap_leggi() -> dict:
    G, path = _graves()
    r = G.uso_leggi(path)
    for p in r["providers"]:
        p["etichetta"] = _ETICHETTE.get(p["nome"], p["nome"])
    r["file"] = (path or G.STATO).name
    return r


def _tetto_valore(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, bool):
        raise ValueError("Il tetto deve essere un numero intero.")
    try:
        n = int(str(v).strip())
    except ValueError:
        raise ValueError("Il tetto deve essere un numero intero (0 = nessun tetto).") from None
    return n


def cap_salva(tetti) -> dict:
    """tetti: {'*': valore, 'booru-r34': valore, ...}. Vuoto/None = toglie l'impostazione (torna al predefinito);
    0 = nessun tetto. Vale subito, senza riavviare i bot."""
    if not isinstance(tetti, dict):
        raise ValueError("Richiesta non valida.")
    G, path = _graves()
    noti = {"*"} | {p["nome"] for p in G.uso_leggi(path)["providers"]}
    estranei = [k for k in tetti if k not in noti]
    if estranei:
        raise ValueError("Provider sconosciuto: " + ", ".join(map(str, estranei[:3])))
    try:
        G.tetti_imposta({k: _tetto_valore(v) for k, v in tetti.items()}, path)
    except ValueError as e:
        raise ValueError(str(e)) from None
    log("tetto ricerche: aggiornato")
    return cap_leggi()


def cap_azzera(provider=None) -> dict:
    G, path = _graves()
    G.uso_azzera(provider or None, path)
    log("tetto ricerche: conteggio azzerato" + (f" ({provider})" if provider else ""))
    return cap_leggi()
