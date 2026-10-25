"""
Graves - ricerca di immagini su Google per i bot.

Usato da:
  telegram_bot.py   /ricerca <cosa cercare> [-n 1-10]
  discord_bot.py    /ricerca query:<cosa cercare> quante:<1-10>

Solo libreria standard: non serve installare nulla.

Come funziona: chiede i risultati di Google Immagini a un provider, SCARICA le immagini sul disco
(i siti d'origine spesso bloccano l'hotlink, quindi mandare il solo URL a Telegram/Discord fallisce
spesso) e restituisce i file. Ne chiede il doppio di quelle richieste e tiene le prime che si
scaricano davvero, in ordine di risultato.

PROVIDER (scegline uno, in bots.env). La Custom Search JSON API di Google è chiusa ai nuovi clienti
e verrà spenta il 1 gennaio 2027: per un account nuovo servono i primi due.
  serper    GRAVES_SERPER_KEY=...      https://serper.dev (POST google.serper.dev/images)
  serpapi   GRAVES_SERPAPI_KEY=...     https://serpapi.com (engine google_images)
  cse       GOOGLE_API_KEY=...  GOOGLE_CX=...   (solo se ce l'hai già: Programmable Search Engine
            con la ricerca immagini attiva)
GRAVES_PROVIDER forza la scelta (serper, serpapi, cse); se manca si usa il primo con le chiavi
presenti, in questo ordine: serper, serpapi, cse.

Altre variabili (tutte opzionali):
  GRAVES_RISULTATI    quante immagini di default (default 6, massimo 10)
  GRAVES_SAFE         active = SafeSearch acceso (default), off = spento. Per Serper il parametro
                      viene inviato ma non ho verificato che lo applichi
  GRAVES_LINGUA       lingua dei risultati (default it)
  GRAVES_PAESE        paese dei risultati (default it)
  GRAVES_MIN_PX       lato lungo minimo (pixel) delle immagini preferite (default 1000; 0 = nessuna
                      preferenza). Le più piccole vengono messe in fondo: si usano solo se le grandi
                      non bastano a raggiungere il numero richiesto
  GRAVES_ORIGINALE    1 = su Telegram manda le immagini come FILE (identiche all'originale) invece che
                      come foto: Telegram ricomprime le foto a circa 1280 px. Niente galleria in chat
  GRAVES_MAX_MB       non scarica immagini più grandi di così (default 15)
  GRAVES_MAX_GIORNO   tetto di ricerche al giorno, contate a parte per ogni provider
                      (default 80; 0 = nessun tetto). I tetti scelti dalle interfacce (IMPOSTAZIONI -> Tetto,
                      salvati in graves_uso.json sotto "tetti") hanno la precedenza e valgono subito
  GRAVES_STATO_FILE   contatore (default: graves_uso.json accanto allo script)

Sicurezza: gli URL delle immagini arrivano da pagine web qualsiasi. Prima di scaricarli (e a ogni
redirect) controllo che l'indirizzo sia pubblico: niente localhost, rete di casa o indirizzi interni.
Le chiavi API non finiscono mai nei messaggi di errore né nel log.

BOORU (modulo per tag su rule34.xxx e siti simili)
  telegram_bot.py   /booru <tag> [-n 1-5] [-s r34|gb|db|e621|rg] [-r]
  discord_bot.py    /booru tag:<tag> sito:<...> quante:<1-5> casuale:<si/no>
Per ogni risultato arriva prima l'ANTEPRIMA (immagine leggera con sito, id, tipo, punteggio e link al post)
e poi il file completo (immagine, gif o video). L'anteprima e il file si scaricano in parallelo.
Tag: separati da spazio (hatsune_miku solo -cat) oppure da virgola se hanno spazi (hatsune miku, solo).
-n quanti risultati (default 3, max 5), -s il sito, -r risultati casuali invece dei più recenti.
RedGifs (-s rg): nessuna chiave. I tag sono testo libero (hatsune_miku diventa 'hatsune miku') e le
esclusioni -tag vengono applicate in locale ai risultati. Il token ospite resta in graves_redgifs_token.json.
Variabili RedGifs (opzionali): GRAVES_RG_ORDINE = trending (default), latest, top, top28, best, oldest;
GRAVES_RG_PAGINE = quante pagine di risultati scorrere per trovare abbastanza post con tutti i tag (default 3,
massimo 8). Le risposte dell'API restano in memoria 5 minuti (il tasto «altro» non rifà le richieste).
Chiavi in bots.env (rule34.xxx e Gelbooru NON funzionano senza: l'API vuole account e chiave):
  GRAVES_R34_KEY, GRAVES_R34_USER            rule34.xxx (Account -> Options -> API Access Credentials)
  GRAVES_GELBOORU_KEY, GRAVES_GELBOORU_USER  Gelbooru
  GRAVES_DANBOORU_USER, GRAVES_DANBOORU_KEY  Danbooru (facoltative; senza, max 2 tag per ricerca)
  GRAVES_E621_USER, GRAVES_E621_KEY          e621 (facoltative; GRAVES_E621_UA per lo user-agent)
Altre variabili (opzionali):
  GRAVES_BOORU_SITO        sito di default (default r34)
  GRAVES_BOORU_RISULTATI   quanti di default (default 3, massimo 5)
  GRAVES_BOORU_MAX_MB      non scarica file più grandi di così (default 100; poi i bot comprimono)
  GRAVES_BOORU_ANTEPRIMA   0 = niente anteprima, manda solo il file
  GRAVES_BOORU_BLACKLIST   tag in più da escludere, separati da virgola
Filtro fisso (non disattivabile): le ricerche con tag che riguardano minori vengono rifiutate e i post che
li hanno vengono scartati. Su Discord il comando gira solo in DM, gruppi privati e canali con limite di età.
Il tetto GRAVES_MAX_GIORNO vale anche qui (contato a parte per ogni sito).
"""
from __future__ import annotations

import asyncio
import base64
import datetime
import hashlib
import ipaddress
import json
import os
import random
import re
import shutil
import socket
import struct
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path


def log(msg: str):
    """I bot lo sostituiscono con il proprio log (graves.log = log)."""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class GravesErrore(RuntimeError):
    """Errore con un messaggio già pronto da mostrare all'utente."""


@dataclass
class Risultato:
    url: str              # immagine a piena risoluzione
    titolo: str = ""
    pagina: str = ""      # pagina web che la contiene
    miniatura: str = ""
    w: int = 0            # dimensioni dichiarate dal provider (0 = sconosciute)
    h: int = 0


def _px(x) -> int:
    try:
        return max(0, int(x))
    except (TypeError, ValueError):
        return 0


MAX_RISULTATI = 10
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"
STATO = Path(os.environ.get("GRAVES_STATO_FILE") or Path(__file__).resolve().with_name("graves_uso.json"))
_lock = threading.Lock()


# ---------- configurazione (letta a ogni ricerca, non all'import) ----------
def _env(nome: str, default: str = "") -> str:
    return (os.environ.get(nome) or default).strip()


def _int_env(nome: str, default: int) -> int:
    try:
        return max(0, int(float(_env(nome, str(default)))))
    except ValueError:
        return default


def _safe() -> bool:
    return _env("GRAVES_SAFE", "active").lower() not in ("off", "no", "0", "false")


_CHIAVI = {
    "serper": ("GRAVES_SERPER_KEY",),
    "serpapi": ("GRAVES_SERPAPI_KEY",),
    "cse": ("GOOGLE_API_KEY", "GOOGLE_CX"),
}


def _provider() -> str:
    scelto = _env("GRAVES_PROVIDER").lower()
    if scelto:
        if scelto not in _CHIAVI:
            raise GravesErrore(f"GRAVES_PROVIDER «{scelto}» non valido: usa serper, serpapi o cse.")
        mancano = [k for k in _CHIAVI[scelto] if not _env(k)]
        if mancano:
            raise GravesErrore(f"Graves: per il provider {scelto} mancano {' e '.join(mancano)} in bots.env.")
        return scelto
    for nome, chiavi in _CHIAVI.items():
        if all(_env(k) for k in chiavi):
            return nome
    raise GravesErrore("Graves non è configurato: metti GRAVES_SERPER_KEY (o GRAVES_SERPAPI_KEY, oppure "
                       "GOOGLE_API_KEY e GOOGLE_CX) in bots.env e riavvia i bot. Vedi l'inizio di graves.py.")


def originale() -> bool:
    return _env("GRAVES_ORIGINALE").lower() in ("1", "si", "sì", "yes", "true", "on")


def configurato() -> bool:
    try:
        _provider()
        return True
    except GravesErrore:
        return False


# ---------- tetto giornaliero ----------
# graves_uso.json: {"giorno": "2026-10-16", "booru-r34": 12, ..., "tetti": {"*": 200, "booru-r34": 80}}
# I contatori ripartono a ogni nuovo giorno, "tetti" resta. Ordine: tetto del provider -> tetto "*" (per tutti)
# -> GRAVES_MAX_GIORNO -> 80. Il file si rilegge a ogni ricerca: cambiare i tetti non richiede di riavviare i bot.
_RISERVATE = ("giorno", "tetti")
TETTO_MAX = 100000


def _leggi_stato(path=None) -> dict:
    try:
        d = json.loads(Path(path or STATO).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


def _scrivi_stato(d: dict, path=None):
    path = Path(path or STATO)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(d), encoding="utf-8")
    os.replace(tmp, path)


def _intero(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _tetti_validi(d: dict) -> dict:
    t = d.get("tetti")
    return {k: v for k, v in t.items() if isinstance(k, str) and _intero(v) and 0 <= v <= TETTO_MAX} \
        if isinstance(t, dict) else {}


def tetto_per(provider: str, d: dict | None = None) -> int:
    """Tetto giornaliero di un provider (0 = nessun tetto)."""
    t = _tetti_validi(_leggi_stato() if d is None else d)
    if provider in t:
        return t[provider]
    if "*" in t:
        return t["*"]
    return _int_env("GRAVES_MAX_GIORNO", 80)


def _conta(provider: str):
    oggi = datetime.date.today().isoformat()
    with _lock:
        d = _leggi_stato()
        if d.get("giorno") != oggi:
            t = _tetti_validi(d)
            d = {"giorno": oggi, **({"tetti": t} if t else {})}
        massimo = tetto_per(provider, d)
        n = d.get(provider, 0)
        n = n if _intero(n) else 0
        if massimo and n >= massimo:
            raise GravesErrore(f"Graves: raggiunto il tetto di {massimo} ricerche per oggi "
                               "(si cambia da IMPOSTAZIONI \u2192 Tetto, o con GRAVES_MAX_GIORNO; 0 = nessun tetto).")
        d[provider] = n + 1
        try:
            _scrivi_stato(d)
        except OSError as e:
            log(f"  Graves: contatore non salvato ({e})")


def uso_leggi(path=None) -> dict:
    """Per le interfacce: contatori di oggi e tetti, provider per provider."""
    d = _leggi_stato(path)
    oggi = datetime.date.today().isoformat()
    usi = {k: v for k, v in d.items() if k not in _RISERVATE and _intero(v)} if d.get("giorno") == oggi else {}
    nomi = [f"booru-{s}" for s in _SITI] + list(_PROVIDER)
    nomi += [k for k in usi if k not in nomi]
    t = _tetti_validi(d)
    return {"giorno": oggi, "base": _int_env("GRAVES_MAX_GIORNO", 80), "predefinito": t.get("*"),
            "providers": [{"nome": n, "usate": usi.get(n, 0), "tetto": t.get(n), "effettivo": tetto_per(n, d)}
                          for n in nomi]}


def tetti_imposta(tetti: dict, path=None):
    """tetti: {'*': 200, 'booru-r34': 80, 'booru-redgifs': None}. None toglie l'impostazione; 0 = nessun tetto."""
    if not isinstance(tetti, dict):
        raise ValueError("tetti non valido")
    for k, v in tetti.items():
        if not isinstance(k, str) or not k or len(k) > 60 or not (v is None or (_intero(v) and 0 <= v <= TETTO_MAX)):
            raise ValueError(f"tetto non valido per {str(k)[:40]!r} (serve un intero da 0 a {TETTO_MAX})")
    with _lock:
        d = _leggi_stato(path)
        t = _tetti_validi(d)
        for k, v in tetti.items():
            if v is None:
                t.pop(k, None)
            else:
                t[k] = v
        if t:
            d["tetti"] = t
        else:
            d.pop("tetti", None)
        d.setdefault("giorno", datetime.date.today().isoformat())
        _scrivi_stato(d, path)


def uso_azzera(provider: str | None = None, path=None):
    """Azzera il conteggio di oggi (di un provider, o di tutti). I tetti restano."""
    oggi = datetime.date.today().isoformat()
    with _lock:
        d = _leggi_stato(path)
        t = _tetti_validi(d)
        if provider and d.get("giorno") == oggi:
            d.pop(provider, None)
        else:
            d = {"giorno": oggi}
        if t:
            d["tetti"] = t
        _scrivi_stato(d, path)


# ---------- provider ----------
def _http_json(nome: str, req: urllib.request.Request, timeout: int = 20, grezzo: bool = False):
    """Esegue la richiesta e restituisce il JSON. Gli errori non contengono mai l'URL (che per alcuni
    provider include la chiave API)."""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            testo = r.read().decode("utf-8", "replace")
            return testo if grezzo else json.loads(testo)
    except urllib.error.HTTPError as e:
        try:
            corpo = e.read().decode("utf-8", "replace")
        except Exception:
            corpo = ""
        dett = " ".join(corpo.split())[:200]
        basso = corpo.lower()
        if e.code == 429 or "limitexceeded" in basso or "quota" in basso or "credits" in basso:
            raise GravesErrore(f"{nome}: quota o limite di richieste esaurito. {dett}".strip()) from None
        if e.code in (401, 403):
            raise GravesErrore(f"{nome}: chiave rifiutata (HTTP {e.code}). {dett}".strip()) from None
        raise GravesErrore(f"{nome}: errore HTTP {e.code}. {dett}".strip()) from None
    except json.JSONDecodeError:
        raise GravesErrore(f"{nome}: risposta non valida") from None
    except OSError as e:     # URLError, timeout, rete assente
        raise GravesErrore(f"{nome}: servizio non raggiungibile ({getattr(e, 'reason', e)})") from None


def _serper(query: str, quanti: int) -> list[Risultato]:
    corpo = {"q": query, "num": quanti, "hl": _env("GRAVES_LINGUA", "it"), "gl": _env("GRAVES_PAESE", "it")}
    if _safe():
        corpo["safe"] = "active"
    req = urllib.request.Request(
        "https://google.serper.dev/images", data=json.dumps(corpo).encode(), method="POST",
        headers={"X-API-KEY": _env("GRAVES_SERPER_KEY"), "Content-Type": "application/json", "User-Agent": UA})
    dati = _http_json("Serper", req)
    return [Risultato(url=i.get("imageUrl") or "", titolo=i.get("title") or "",
                      pagina=i.get("link") or "", miniatura=i.get("thumbnailUrl") or "",
                      w=_px(i.get("imageWidth")), h=_px(i.get("imageHeight")))
            for i in dati.get("images") or [] if isinstance(i, dict)]


def _serpapi(query: str, quanti: int) -> list[Risultato]:
    q = {"engine": "google_images", "q": query, "api_key": _env("GRAVES_SERPAPI_KEY"), "ijn": "0",
         "hl": _env("GRAVES_LINGUA", "it"), "gl": _env("GRAVES_PAESE", "it"),
         "safe": "active" if _safe() else "off"}
    req = urllib.request.Request("https://serpapi.com/search.json?" + urllib.parse.urlencode(q),
                                 headers={"User-Agent": UA})
    dati = _http_json("SerpApi", req, timeout=40)
    if dati.get("error"):
        if "hasn't returned any results" in str(dati["error"]).lower():
            return []
        raise GravesErrore(f"SerpApi: {str(dati['error'])[:200]}")
    return [Risultato(url=i.get("original") or "", titolo=i.get("title") or "",
                      pagina=i.get("link") or "", miniatura=i.get("thumbnail") or "",
                      w=_px(i.get("original_width")), h=_px(i.get("original_height")))
            for i in (dati.get("images_results") or [])[:quanti] if isinstance(i, dict)]


def _cse(query: str, quanti: int) -> list[Risultato]:
    q = {"key": _env("GOOGLE_API_KEY"), "cx": _env("GOOGLE_CX"), "q": query, "searchType": "image",
         "num": min(10, quanti), "hl": _env("GRAVES_LINGUA", "it"), "gl": _env("GRAVES_PAESE", "it"),
         "safe": "active" if _safe() else "off"}
    req = urllib.request.Request("https://www.googleapis.com/customsearch/v1?" + urllib.parse.urlencode(q),
                                 headers={"User-Agent": UA})
    dati = _http_json("Google CSE", req)
    out = []
    for i in dati.get("items") or []:
        if isinstance(i, dict):
            img = i.get("image") or {}
            out.append(Risultato(url=i.get("link") or "", titolo=i.get("title") or "",
                                 pagina=img.get("contextLink") or "", miniatura=img.get("thumbnailLink") or "",
                                 w=_px(img.get("width")), h=_px(img.get("height"))))
    return out


_PROVIDER = {"serper": _serper, "serpapi": _serpapi, "cse": _cse}


# ---------- richiesta dell'utente ----------
_N_RE = re.compile(r"(?:^|\s)-n\s*(\d+)\s*$", re.I)


def parse_richiesta(testo: str) -> tuple[str, int | None]:
    """'gatti arancioni -n 5' -> ('gatti arancioni', 5). Senza -n il numero è None (= GRAVES_RISULTATI)."""
    testo = " ".join((testo or "").split())
    n = None
    m = _N_RE.search(testo)
    if m:
        n = int(m.group(1))
        testo = testo[:m.start()].strip()
    testo = "".join(c for c in testo if c.isprintable())[:200].strip()
    if not testo:
        raise GravesErrore("Uso: /ricerca <cosa cercare> [-n 1-10]")
    return testo, n


def _quante(n: int | None) -> int:
    n = n or _int_env("GRAVES_RISULTATI", 6) or 6
    return max(1, min(MAX_RISULTATI, n))


def cerca(query: str, n: int | None = None) -> list[Risultato]:
    """Elenco di risultati (circa il doppio di n: alcuni URL non si scaricheranno)."""
    n = _quante(n)
    provider = _provider()
    _conta(provider)
    quanti = min(20, max(n * 3, n + 6))
    log(f"  Graves: cerco «{query}» con {provider} (voglio {n} immagini)")
    grezzi = _PROVIDER[provider](query, quanti)
    visti, out = set(), []
    for r in grezzi:
        if r.url.startswith(("http://", "https://")) and r.url not in visti:
            visti.add(r.url)
            out.append(r)
    if not out:
        raise GravesErrore(f"Nessun risultato per «{query}».")
    minimo = _int_env("GRAVES_MIN_PX", 1000)
    if minimo:    # le immagini che il provider dichiara piccole vanno in fondo (ordine di Google per il resto)
        piccola = lambda r: bool(r.w and r.h and max(r.w, r.h) < minimo)
        out = [r for r in out if not piccola(r)] + [r for r in out if piccola(r)]
    return out


# ---------- download ----------
def _host_pubblico(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    try:
        return bool(infos) and all(ipaddress.ip_address(i[4][0].split("%")[0]).is_global for i in infos)
    except ValueError:
        return False


def _controlla_url(url: str):
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise GravesErrore("URL non valido")
    if not _host_pubblico(u.hostname):
        raise GravesErrore("indirizzo non pubblico")


class _Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _controlla_url(newurl)      # anche ogni redirect deve restare su indirizzi pubblici
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_Redirect)


def _estensione(testa: bytes) -> str | None:
    if testa.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if testa.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if testa.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if testa[:4] == b"RIFF" and testa[8:12] == b"WEBP":
        return ".webp"
    return None


def _dimensioni(path: Path) -> tuple[int, int]:
    """(larghezza, altezza) letta dall'intestazione del file; (0, 0) se non riesco."""
    try:
        with open(path, "rb") as f:
            b = f.read(65536)
        if b.startswith(b"\x89PNG"):
            return struct.unpack(">II", b[16:24])
        if b.startswith(b"GIF"):
            return struct.unpack("<HH", b[6:10])
        if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
            tipo = b[12:16]
            if tipo == b"VP8X":
                return 1 + int.from_bytes(b[24:27], "little"), 1 + int.from_bytes(b[27:30], "little")
            if tipo == b"VP8L":
                bit = int.from_bytes(b[21:25], "little")
                return 1 + (bit & 0x3FFF), 1 + ((bit >> 14) & 0x3FFF)
            if tipo == b"VP8 ":
                return int.from_bytes(b[26:28], "little") & 0x3FFF, int.from_bytes(b[28:30], "little") & 0x3FFF
        if b.startswith(b"\xff\xd8"):
            i = 2
            while i + 9 < len(b):
                if b[i] != 0xFF:
                    i += 1
                    continue
                m = b[i + 1]
                if m == 0xFF:
                    i += 1
                elif m == 0x01 or 0xD0 <= m <= 0xD9:
                    i += 2
                elif 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">HH", b[i + 5:i + 9])
                    return w, h
                else:
                    i += 2 + struct.unpack(">H", b[i + 2:i + 4])[0]
    except Exception:
        pass
    return 0, 0


def _scarica_uno(r: Risultato, cartella: Path, i: int, max_bytes: int) -> Path:
    _controlla_url(r.url)
    u = urllib.parse.urlsplit(r.url)
    req = urllib.request.Request(r.url, headers={
        "User-Agent": UA, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
        "Referer": f"{u.scheme}://{u.netloc}/"})
    tmp = cartella / f"graves_{i:02d}.part"
    try:
        with _OPENER.open(req, timeout=15) as resp:
            try:
                if int(resp.headers.get("Content-Length") or 0) > max_bytes:
                    raise GravesErrore("troppo grande")
            except ValueError:
                pass
            testa = resp.read(16)
            ext = _estensione(testa)
            if not ext:
                raise GravesErrore("non è un jpg, png, webp o gif")
            totale = len(testa)
            with open(tmp, "wb") as f:
                f.write(testa)
                while True:
                    blocco = resp.read(65536)
                    if not blocco:
                        break
                    totale += len(blocco)
                    if totale > max_bytes:
                        raise GravesErrore("troppo grande")
                    f.write(blocco)
        if totale < 2048:
            raise GravesErrore("troppo piccola")
        dest = cartella / f"graves_{i:02d}{ext}"
        os.replace(tmp, dest)
        return dest
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def scarica(risultati: list[Risultato], cartella: str | Path, n: int | None = None) -> list[Path]:
    """Scarica i risultati in parallelo e restituisce n file: prima le immagini con il lato lungo di almeno
    GRAVES_MIN_PX, nell'ordine di Google; se non bastano, le più piccole a completare."""
    n = _quante(n)
    cartella = Path(cartella)
    minimo = _int_env("GRAVES_MIN_PX", 1000)
    max_bytes = _int_env("GRAVES_MAX_MB", 15) * 1024 * 1024 or 15 * 1024 * 1024
    grandi: list[Path] = []
    piccole: list[Path] = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futuri = [ex.submit(_scarica_uno, r, cartella, i, max_bytes) for i, r in enumerate(risultati)]
        for r, fut in zip(risultati, futuri):
            if len(grandi) >= n:
                fut.cancel()
                continue
            host = urllib.parse.urlsplit(r.url).netloc
            try:
                p = fut.result()
            except Exception as e:
                log(f"    Graves: scartata un'immagine di {host} ({e})")
                continue
            w, h = _dimensioni(p)
            kb = p.stat().st_size // 1024
            log(f"    Graves: {host} {w}x{h} px, {kb} KB")
            (grandi if not minimo or max(w, h) >= minimo else piccole).append(p)
    files = (grandi + piccole)[:n]
    for p in cartella.glob("graves_*"):     # download extra, o finiti dopo che n era già raggiunto
        if p not in files:
            p.unlink(missing_ok=True)
    if minimo and len(grandi) < len(files):
        log(f"  Graves: solo {len(grandi)} immagini sopra {minimo} px, le altre sono più piccole "
            "(abbassa GRAVES_MIN_PX o cerca in modo più specifico)")
    log(f"  Graves: consegno {len(files)} immagini su {len(risultati)} risultati")
    return files


def cerca_e_scarica(query: str, cartella: str | Path, n: int | None = None) -> list[Path]:
    """Punto d'ingresso per i bot: cerca, scarica e restituisce i file. Solleva GravesErrore con un
    messaggio pronto da mostrare."""
    risultati = cerca(query, n)
    files = scarica(risultati, cartella, n)
    if not files:
        raise GravesErrore(f"Ho trovato {len(risultati)} risultati per «{query}» ma nessuna immagine si è "
                           "scaricata (i siti bloccano il download). Riprova con un'altra ricerca.")
    return files


# ======================================================================================================
# BOORU - ricerca per tag su rule34.xxx e siti simili: prima l'anteprima, poi il video / l'immagine
# ======================================================================================================
_IMG_EXT = {"jpg", "jpeg", "png", "gif", "webp"}
_VID_EXT = {"mp4", "webm"}
MAX_BOORU = 5
USO_BOORU = "Uso: /booru <tag> [-n 1-5] [-s r34|gb|db|e621|rg] [-r]"

# Tag che riguardano minori. Elenco FISSO e non disattivabile: una ricerca che li contiene viene rifiutata
# e i post che li hanno vengono scartati dai risultati (si può solo ampliare con GRAVES_BOORU_BLACKLIST).
_VIETATI_RE = re.compile(r"^(?:loli|shota|toddler|infant|underage|under_age|preteen|prepubescent|child)")
_VIETATI = frozenset({"kid", "kids", "minor", "baby", "cub", "young", "younger",
                      "little_girl", "little_boy", "small_girl", "small_boy"})
_ESCLUDI_SERVER = ("loli", "shota", "child", "toddler", "underage", "young")


def tag_vietato(tag: str) -> bool:
    t = (tag or "").strip().lower().lstrip("-~")
    if not t:
        return False
    extra = {x.lower() for x in re.split(r"[,\s]+", _env("GRAVES_BOORU_BLACKLIST")) if x}
    return t in _VIETATI or t in extra or bool(_VIETATI_RE.match(t))


def _num(x) -> int:
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return 0


def _ext_url(url: str) -> str:
    nome = urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1]
    return nome.rsplit(".", 1)[-1].lower() if "." in nome else ""


def _https(u) -> str:
    u = str(u or "").strip()
    if u.startswith("//"):
        u = "https:" + u
    return u if u.startswith(("http://", "https://")) else ""


@dataclass
class RichiestaBooru:
    tags: list
    n: int
    sito: str
    casuale: bool = False


@dataclass
class PostBooru:
    sito: str
    id: str
    url: str                    # file a piena risoluzione (immagine, gif o video)
    anteprima: str              # immagine leggera per l'anteprima ("" = nessuna)
    ext: str
    tags: frozenset
    score: int = 0
    alt: str = ""               # file di riserva (es. RedGifs sd) se quello principale non si scarica

    @property
    def video(self) -> bool:
        return self.ext in _VID_EXT

    @property
    def pagina(self) -> str:
        return _SITI[self.sito]["link"].format(id=self.id)

    def etichetta(self) -> str:
        tipo = "video" if self.video else ("gif" if self.ext == "gif" else "immagine")
        return f"{_SITI[self.sito]['nome']} #{self.id} · {tipo} · ★{self.score}"

    def scarica(self, cartella: Path, i: int = 0) -> Path:
        """Scarica il file completo (SSRF e redirect controllati come per le immagini di Google)."""
        mb = _int_env("GRAVES_BOORU_MAX_MB", 100) or 100
        cartella = Path(cartella)
        base, ref = cartella / f"booru_{i:02d}", _SITI[self.sito]["referer"]

        def reale(_url, folder) -> list[Path]:
            b = Path(folder) / base.name
            try:
                return [_scarica_media(self.url, b, ref, mb * 1024 * 1024, solo_immagini=False)]
            except Exception as e:
                if not self.alt:
                    raise
                log(f"    Graves: {self.etichetta()}: file principale non scaricato ({e}), provo la versione ridotta")
                return [_scarica_media(self.alt, b, ref, mb * 1024 * 1024, solo_immagini=False)]

        try:
            import coda_dl
        except ImportError:                 # senza coda_dl.py si scarica come prima
            return reale(None, cartella)[0]
        # cache condivisa (stesso post già scaricato da /booru, anche da un altro bot): niente nuova richiesta.
        # Niente coda FIFO: i file booru partono in parallelo all'anteprima, non devono aspettare yt-dlp.
        tmp = Path(tempfile.mkdtemp(dir=cartella))
        try:
            chiave = hashlib.sha1(("booru:" + self.url).encode()).hexdigest()[:16]
            f = coda_dl.scarica(self.url, str(tmp), reale, chiave, False, log, coda=False)[0]
            dest = cartella / (base.name + f.suffix)
            os.replace(f, dest)
            return dest
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def _post(sito, id_, url, anteprime, tags, score, alt=""):
    url = _https(url)
    ext = _ext_url(url) if url else ""
    if ext not in _IMG_EXT | _VID_EXT or id_ in (None, ""):
        return None
    prev = next((a for a in map(_https, anteprime) if a and _ext_url(a) in _IMG_EXT), "")
    if isinstance(tags, str):
        tags = tags.split()
    return PostBooru(sito=sito, id=str(id_), url=url, anteprima=prev, ext=ext,
                     tags=frozenset(str(t).lower() for t in tags or ()), score=_num(score),
                     alt=_https(alt) if _ext_url(_https(alt)) in _IMG_EXT | _VID_EXT else "")


def _con_esclusioni(tags: list) -> list:
    presenti = {t.lstrip("-~").lower() for t in tags}
    return list(tags) + [f"-{t}" for t in _ESCLUDI_SERVER if t not in presenti]


def _basic(utente: str, chiave: str) -> dict:
    if utente and chiave:
        return {"Authorization": "Basic " + base64.b64encode(f"{utente}:{chiave}".encode()).decode()}
    return {}


def _json_o_vuoto(nome: str, req: urllib.request.Request):
    testo = _http_json(nome, req, 25, grezzo=True)
    if not testo.strip():       # rule34 risponde con un corpo vuoto quando non trova niente
        return None
    try:
        dati = json.loads(testo)
    except json.JSONDecodeError:
        raise GravesErrore(f"{nome}: {' '.join(testo.split())[:200]}") from None
    if isinstance(dati, str):       # rule34 risponde cosi' ("Missing authentication...") con HTTP 200
        raise GravesErrore(f"{nome}: {' '.join(dati.split())[:200]}")
    return dati


# ---------- i siti ----------
def _credenziali(k: str, u: str) -> tuple:
    """Il sito mostra le credenziali come '&api_key=XXXX&user_id=123': se hai incollato quella stringa (in una
    qualsiasi delle due variabili) ne estraggo i due valori; tolgo anche spazi e virgolette."""
    blocco = f"{k}&{u}"
    mk = re.search(r"api_key=([^&\s\"']+)", blocco)
    mu = re.search(r"user_id=([^&\s\"']+)", blocco)
    return (mk.group(1) if mk else k.strip().strip("\"'")), (mu.group(1) if mu else u.strip().strip("\"'"))


def _dapi(nome: str, base: str, k: str, u: str, tags: list, quanti: int, casuale: bool) -> list:
    """API 'dapi' (rule34.xxx e Gelbooru). Prima chiede con le esclusioni dei tag vietati lato server; se non
    esce niente (alcuni siti rispondono vuoto con troppi tag) riprova senza: il filtro locale resta sempre."""
    k, u = _credenziali(k, u)

    def chiedi(q: list):
        p = {"page": "dapi", "s": "post", "q": "index", "json": "1", "limit": quanti, "pid": 0,
             "tags": " ".join(q + (["sort:random"] if casuale else [])), "api_key": k, "user_id": u}
        dati = _json_o_vuoto(nome, urllib.request.Request(base + "?" + urllib.parse.urlencode(p),
                                                          headers={"User-Agent": UA}))
        lista = dati.get("post") if isinstance(dati, dict) else dati
        return [i for i in (lista or []) if isinstance(i, dict)]
    lista = chiedi(_con_esclusioni(tags))
    if not lista:
        lista = chiedi(list(tags))
        if lista:
            log(f"    Graves: {nome} risponde vuoto con le esclusioni lato server: uso solo il filtro locale")
    return lista


def _r34(tags: list, quanti: int, casuale: bool) -> list:
    k, u = _env("GRAVES_R34_KEY"), _env("GRAVES_R34_USER")
    if not (k and u):
        raise GravesErrore("rule34.xxx vuole una chiave API: metti GRAVES_R34_KEY e GRAVES_R34_USER in bots.env "
                           "(dal sito: Account → Options → API Access Credentials) e riavvia i bot.")
    return [_post("r34", i.get("id"), i.get("file_url"), (i.get("sample_url"), i.get("preview_url")),
                  i.get("tags"), i.get("score"))
            for i in _dapi("rule34.xxx", "https://api.rule34.xxx/index.php", k, u, tags, quanti, casuale)]


def _gelbooru(tags: list, quanti: int, casuale: bool) -> list:
    k, u = _env("GRAVES_GELBOORU_KEY"), _env("GRAVES_GELBOORU_USER")
    if not (k and u):
        raise GravesErrore("Gelbooru vuole una chiave API: metti GRAVES_GELBOORU_KEY e GRAVES_GELBOORU_USER "
                           "in bots.env (dal sito: Account → Options) e riavvia i bot.")
    return [_post("gelbooru", i.get("id"), i.get("file_url"), (i.get("sample_url"), i.get("preview_url")),
                  i.get("tags"), i.get("score"))
            for i in _dapi("Gelbooru", "https://gelbooru.com/index.php", k, u, tags, quanti, casuale)]


def _danbooru(tags: list, quanti: int, casuale: bool) -> list:
    q = list(tags) + (["order:random"] if casuale else [])
    p = {"tags": " ".join(q), "limit": min(100, quanti)}
    h = {"User-Agent": UA, **_basic(_env("GRAVES_DANBOORU_USER"), _env("GRAVES_DANBOORU_KEY"))}
    dati = _json_o_vuoto("Danbooru", urllib.request.Request(
        "https://danbooru.donmai.us/posts.json?" + urllib.parse.urlencode(p), headers=h))
    return [_post("danbooru", i.get("id"), i.get("file_url"), (i.get("large_file_url"), i.get("preview_file_url")),
                  i.get("tag_string"), i.get("score")) for i in (dati or []) if isinstance(i, dict)]


def _e621(tags: list, quanti: int, casuale: bool) -> list:
    utente = _env("GRAVES_E621_USER")
    ua = _env("GRAVES_E621_UA") or (f"Graves/1.0 (by {utente} on e621)" if utente else "Graves/1.0 (personal bot)")
    q = _con_esclusioni(tags) + (["order:random"] if casuale else [])
    p = {"tags": " ".join(q), "limit": min(75, quanti)}
    h = {"User-Agent": ua, **_basic(utente, _env("GRAVES_E621_KEY"))}
    dati = _json_o_vuoto("e621", urllib.request.Request(
        "https://e621.net/posts.json?" + urllib.parse.urlencode(p), headers=h))
    out = []
    for i in (dati or {}).get("posts") or []:
        if not isinstance(i, dict):
            continue
        t = i.get("tags") if isinstance(i.get("tags"), dict) else {}
        tutti = [x for lista in t.values() if isinstance(lista, list) for x in lista]
        f, s, a = i.get("file") or {}, i.get("sample") or {}, i.get("preview") or {}
        out.append(_post("e621", i.get("id"), f.get("url"), (s.get("url"), a.get("url")), tutti,
                         (i.get("score") or {}).get("total")))
    return out


# RedGifs: nessuna chiave da registrare, ma serve un token "ospite" (GET /v2/auth/temporary) legato a IP e
# user-agent, che dura circa un giorno. C'e' un limite orario alle richieste di token (se lo superi il blocco
# dura a lungo), quindi lo salvo su file e lo riuso; se l'API risponde 401 ne chiedo uno nuovo, una volta sola.
_RG_H = {"User-Agent": UA, "Accept": "application/json",
         "Referer": "https://www.redgifs.com/", "Origin": "https://www.redgifs.com"}


def _rg_token(rinnova: bool = False) -> str:
    f = STATO.with_name("graves_redgifs_token.json")
    if not rinnova:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("token") and time.time() - float(d.get("t", 0)) < 20 * 3600:
                return d["token"]
        except Exception:
            pass
    dati = _http_json("RedGifs", urllib.request.Request("https://api.redgifs.com/v2/auth/temporary", headers=_RG_H))
    tok = dati.get("token") if isinstance(dati, dict) else None
    if not tok:
        raise GravesErrore("RedGifs: non sono riuscito a ottenere il token temporaneo.")
    try:
        tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"token": tok, "t": time.time()}), encoding="utf-8")
        os.replace(tmp, f)
    except OSError as e:
        log(f"    Graves: token RedGifs non salvato ({e})")
    return tok


def _rg_sq(s) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def _rg_corrisponde(positivo: str, tag_sq: list) -> bool:
    p = _rg_sq(positivo)
    return not p or any(p == t or (len(p) >= 4 and p in t) for t in tag_sq)


_RG_ORDINI = ("trending", "latest", "top", "top28", "best", "oldest")
_RG_CACHE: dict = {}
_RG_CACHE_S = 300


def _redgifs(tags: list, quanti: int, casuale: bool) -> list:
    """Il '_' diventa spazio. Provo piu' formulazioni (prima '#lisa ann', poi 'lisa ann', poi con il parametro
    tags) e mi fermo alla prima che da' risultati con TUTTI i tag richiesti (nei tag del post, nei niche, nel
    nome della creator o nella descrizione, senza badare a spazi, underscore e maiuscole). Per ogni formulazione
    scorro fino a GRAVES_RG_PAGINE pagine finche' non ho abbastanza candidati. Niente ripieghi su risultati che
    non corrispondono. Le esclusioni '-tag' le applico io. Ogni post porta anche la versione sd come riserva."""
    positivi = [t.lstrip("~") for t in tags if not t.startswith("-") and t.lstrip("~")]
    esclusi = [_rg_sq(t[1:]) for t in tags if t.startswith("-") and len(t) > 1]
    nomi = [t.replace("_", " ") for t in positivi]
    if not nomi:
        raise GravesErrore("RedGifs: serve almeno un tag in positivo (le sole esclusioni -tag non bastano).")
    varianti = [{"search_text": " ".join("#" + n for n in nomi)},
                {"search_text": " ".join(nomi)},
                {"search_text": " ".join(nomi), "tags": ",".join(n.title() for n in nomi)}]
    o = _env("GRAVES_RG_ORDINE", "trending").lower()
    ordine = o if o in _RG_ORDINI else "trending"
    max_pag = max(1, min(8, _int_env("GRAVES_RG_PAGINE", 3) or 3))

    def chiedi(extra: dict, pagina: int, rinnova: bool):
        p = {**extra, "order": ordine, "count": 100, "page": pagina}
        h = {**_RG_H, "Authorization": "Bearer " + _rg_token(rinnova)}
        return _http_json("RedGifs", urllib.request.Request(
            "https://api.redgifs.com/v2/gifs/search?" + urllib.parse.urlencode(p), headers=h), 25)

    def pagina_dati(extra: dict, pagina: int) -> tuple:
        """(gifs, numero di pagine totali); con cache di 5 minuti."""
        chiave = (tuple(sorted(extra.items())), ordine, pagina)
        with _lock:
            hit = _RG_CACHE.get(chiave)
        if hit and time.time() - hit[0] < _RG_CACHE_S:
            return hit[1], hit[2]
        try:
            dati = chiedi(extra, pagina, False)
        except GravesErrore as e:
            if "HTTP 401" in str(e):
                dati = chiedi(extra, pagina, True)      # token scaduto o legato a un altro IP
            elif "limite di richieste" in str(e):
                time.sleep(2)                            # limite al secondo: riprovo una volta
                dati = chiedi(extra, pagina, False)
            else:
                raise
        d = dati if isinstance(dati, dict) else {}
        gifs = [x for x in d.get("gifs") or [] if isinstance(x, dict)]
        pagine = _num(d.get("pages")) or 1
        with _lock:
            if len(_RG_CACHE) > 40:
                _RG_CACHE.clear()
            _RG_CACHE[chiave] = (time.time(), gifs, pagine)
        return gifs, pagine

    def filtra(gifs: list) -> list:
        out = []
        for gif in gifs:
            u = gif.get("urls") or {}
            tag = [str(x).lower().replace(" ", "_") for x in gif.get("tags") or []]
            niche = [str(x).lower().replace(" ", "_") for x in gif.get("niches") or [] if isinstance(x, str)]
            sq = ([_rg_sq(x) for x in tag + niche]
                  + [_rg_sq(gif.get("userName")), _rg_sq(gif.get("description"))])
            if any(e in sq for e in esclusi) or not all(_rg_corrisponde(p, sq) for p in positivi):
                continue
            hd, sd = u.get("hd"), u.get("sd")
            out.append(_post("redgifs", gif.get("id"), hd or sd, (u.get("poster"), u.get("thumbnail")),
                             tag, gif.get("likes"), alt=sd if hd and sd and sd != hd else ""))
        return out

    inizio = random.randint(1, 3) if casuale else 1
    out, visti, riuscite, ultimo = [], set(), 0, None
    for i, extra in enumerate(varianti, 1):
        pagina, ini, letti, ok = inizio, inizio, 0, False
        while pagina < ini + max_pag:
            try:
                gifs, pagine = pagina_dati(extra, pagina)
            except GravesErrore as e:
                ultimo = e
                log(f"    Graves: RedGifs variante {i}, pagina {pagina}: {e}")
                break
            ok = True
            if not gifs and pagina == ini and ini > 1:      # pagina casuale oltre la fine: riparto dalla 1
                ini = pagina = 1
                continue
            letti += len(gifs)
            for p in filtra(gifs):
                if p and p.id not in visti:
                    visti.add(p.id)
                    out.append(p)
            if len(out) >= quanti or not gifs or pagina >= pagine:
                break
            pagina += 1
        riuscite += ok
        log(f"    Graves: RedGifs variante {i}/{len(varianti)}: {letti} risultati letti, {len(out)} con tutti i tag")
        if out:
            break
    if not riuscite and ultimo:
        raise ultimo
    if casuale:
        random.shuffle(out)
    return out


_SITI = {
    "r34": {"nome": "rule34", "cerca": _r34, "referer": "https://rule34.xxx/",
            "link": "https://rule34.xxx/index.php?page=post&s=view&id={id}"},
    "gelbooru": {"nome": "gelbooru", "cerca": _gelbooru, "referer": "https://gelbooru.com/",
                 "link": "https://gelbooru.com/index.php?page=post&s=view&id={id}"},
    "danbooru": {"nome": "danbooru", "cerca": _danbooru, "referer": "https://danbooru.donmai.us/",
                 "link": "https://danbooru.donmai.us/posts/{id}"},
    "redgifs": {"nome": "redgifs", "cerca": _redgifs, "referer": "https://www.redgifs.com/",
                "link": "https://www.redgifs.com/watch/{id}"},
    "e621": {"nome": "e621", "cerca": _e621, "referer": "https://e621.net/",
             "link": "https://e621.net/posts/{id}"},
}
_ALIAS_SITI = {"r34": "r34", "rule34": "r34", "gb": "gelbooru", "gelbooru": "gelbooru",
               "db": "danbooru", "danbooru": "danbooru", "e621": "e621", "e6": "e621",
               "rg": "redgifs", "redgifs": "redgifs", "redgif": "redgifs"}


# ---------- richiesta ----------
def parse_booru(testo: str, n: int | None = None, sito: str | None = None, casuale: bool = False) -> RichiestaBooru:
    """'hatsune_miku solo -n 2 -s gb -r' -> tag, 2 risultati, gelbooru, casuali. Se c'è una virgola i tag
    sono separati da virgole e gli spazi diventano _ ('hatsune miku, solo'). Solleva GravesErrore."""
    toks = "".join(c for c in (testo or "") if c.isprintable() or c.isspace()).split()
    resto, i = [], 0
    while i < len(toks):
        t = toks[i].lower()
        if t in ("-n", "-s"):
            if i + 1 >= len(toks):
                raise GravesErrore(USO_BOORU)
            if t == "-n":
                try:
                    n = int(toks[i + 1])
                except ValueError:
                    raise GravesErrore(USO_BOORU) from None
            else:
                sito = toks[i + 1]
            i += 2
        elif t == "-r":
            casuale, i = True, i + 1
        else:
            resto.append(toks[i])
            i += 1
    riga = " ".join(resto)
    if "," in riga:
        tags = [x.strip().replace(" ", "_") for x in riga.split(",") if x.strip()]
    else:
        tags = riga.split()
    tags = [t[:80] for t in tags][:20]
    if not tags:
        raise GravesErrore(USO_BOORU)
    if any(tag_vietato(t) for t in tags if not t.startswith("-")):
        raise GravesErrore("Ricerca non eseguita: contiene tag che riguardano minori.")
    nome = _ALIAS_SITI.get((sito or _env("GRAVES_BOORU_SITO", "r34")).strip().lower())
    if not nome:
        raise GravesErrore("Sito non valido: usa r34, gelbooru (gb), danbooru (db), e621 o redgifs (rg).")
    if nome == "redgifs" and "," not in riga:       # su RedGifs "lisa ann" e' un nome solo, non due tag
        pos = [t.lstrip("~") for t in tags if not t.startswith("-")]
        if len(pos) > 1:
            tags = ["_".join(pos)] + [t for t in tags if t.startswith("-")]
    n = max(1, min(MAX_BOORU, n or _int_env("GRAVES_BOORU_RISULTATI", 3) or 3))
    return RichiestaBooru(tags=tags, n=n, sito=nome, casuale=bool(casuale))


def booru_cerca(rich: RichiestaBooru) -> list:
    """Candidati (circa 4 volte n: alcuni file non si scaricheranno), senza i post con tag vietati."""
    _conta(f"booru-{rich.sito}")
    quanti = min(40, max(rich.n * 4, 10))
    log(f"  Graves: cerco su {_SITI[rich.sito]['nome']} (voglio {rich.n}"
        f"{', casuali' if rich.casuale else ''})")
    grezzi = _SITI[rich.sito]["cerca"](rich.tags, quanti, rich.casuale)
    visti, out, scartati, inutili = set(), [], 0, 0
    for p in grezzi:
        if p is None:
            inutili += 1            # senza file, o in un formato che non gestisco (zip, swf...)
            continue
        if p.id in visti:
            continue
        visti.add(p.id)
        if any(tag_vietato(t) for t in p.tags):
            scartati += 1
            continue
        out.append(p)
    log(f"  Graves: il sito ha restituito {len(grezzi)} post: {len(out)} utilizzabili, "
        f"{scartati} scartati dal filtro tag, {inutili} senza file o formato non supportato")
    if not out:
        nome = _SITI[rich.sito]["nome"]
        if not grezzi:
            raise GravesErrore(f"{nome} non ha trovato niente per questi tag.")
        raise GravesErrore(f"{nome} ha restituito {len(grezzi)} post ma nessuno è utilizzabile "
                           f"({scartati} scartati dal filtro dei tag, {inutili} senza file o in formato non supportato).")
    return out


# ---------- download (immagini, gif e video) ----------
def _estensione_media(testa: bytes) -> str | None:
    e = _estensione(testa)
    if e:
        return e
    if testa[4:8] == b"ftyp":
        return ".mp4"
    if testa.startswith(b"\x1a\x45\xdf\xa3"):
        return ".webm"
    return None


def _scarica_media(url: str, base: Path, referer: str, max_bytes: int, solo_immagini: bool) -> Path:
    _controlla_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Referer": referer})
    tmp = base.with_name(base.name + ".part")
    try:
        with _OPENER.open(req, timeout=30) as resp:
            try:
                if int(resp.headers.get("Content-Length") or 0) > max_bytes:
                    raise GravesErrore("file troppo grande")
            except ValueError:
                pass
            testa = resp.read(16)
            ext = _estensione_media(testa)
            if not ext or (solo_immagini and ext in (".mp4", ".webm")):
                raise GravesErrore("formato non supportato")
            totale = len(testa)
            with open(tmp, "wb") as f:
                f.write(testa)
                while True:
                    blocco = resp.read(262144)
                    if not blocco:
                        break
                    totale += len(blocco)
                    if totale > max_bytes:
                        raise GravesErrore("file troppo grande")
                    f.write(blocco)
        if totale < 1024:
            raise GravesErrore("file troppo piccolo")
        dest = base.with_name(base.name + ext)
        os.replace(tmp, dest)
        return dest
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _scarica_anteprima(p: PostBooru, cartella: Path, i: int) -> Path | None:
    if not p.anteprima:
        return None
    try:
        return _scarica_media(p.anteprima, Path(cartella) / f"booru_{i:02d}_anteprima",
                              _SITI[p.sito]["referer"], 8 * 1024 * 1024, solo_immagini=True)
    except Exception as e:
        log(f"    Graves: anteprima di #{p.id} non scaricata ({e})")
        return None


# ---------- punto d'ingresso per i bot ----------
async def booru_esegui(rich: RichiestaBooru, cartella, anteprima_cb, file_cb,
                       scadenza: float | None = None) -> tuple[int, list]:
    """Cerca e, per ogni risultato: scarica anteprima e file in parallelo, chiama `await anteprima_cb(path|None, post)`
    appena l'anteprima è pronta e poi `await file_cb(path, post)` con il file completo. Si ferma a rich.n file
    inviati (o a `scadenza`, un time.time()). Restituisce (inviati, problemi). Solleva GravesErrore se la
    ricerca fallisce o non trova niente."""
    cartella = Path(cartella)
    candidati = await asyncio.to_thread(booru_cerca, rich)
    con_anteprima = _env("GRAVES_BOORU_ANTEPRIMA", "1").lower() not in ("0", "no", "off", "false")
    inviati, problemi = 0, []
    for i, p in enumerate(candidati):
        if inviati >= rich.n:
            break
        if scadenza and time.time() > scadenza:
            problemi.append("tempo quasi scaduto: mi fermo qui")
            break
        t_file = asyncio.create_task(asyncio.to_thread(p.scarica, cartella, i))   # parte subito, in parallelo
        prev = None
        if con_anteprima:
            try:
                prev = await asyncio.to_thread(_scarica_anteprima, p, cartella, i)
                await anteprima_cb(prev, p)
            except Exception as e:
                log(f"    Graves: anteprima di #{p.id} non inviata ({e})")
                problemi.append(f"{p.etichetta()}: anteprima non inviata ({e})")
        try:
            file = await t_file
        except Exception as e:
            log(f"    Graves: {p.etichetta()} non scaricato ({e})")
            problemi.append(f"{p.etichetta()}: non scaricato ({e})")
            if prev:
                prev.unlink(missing_ok=True)
            continue
        try:
            log(f"    Graves: invio {p.etichetta()} ({file.stat().st_size // 1024} KB)")
            await file_cb(file, p)
            inviati += 1
        except Exception as e:
            log(f"    Graves: invio di #{p.id} non riuscito ({e})")
            problemi.append(f"{p.etichetta()}: invio non riuscito ({e})")
        finally:
            for x in (file, prev):      # libero subito il disco: i video possono pesare decine di MB
                if x:
                    x.unlink(missing_ok=True)
    return inviati, problemi


# ---------- anteprima privata + scelta (usata da /booru dei bot) ----------
async def booru_anteprime(rich: RichiestaBooru, cartella) -> list:
    """Cerca e scarica SOLO le anteprime dei primi rich.n risultati (nessun file completo).
    Restituisce [(post, path_anteprima | None)]. Solleva GravesErrore se la ricerca fallisce o non trova niente."""
    cartella = Path(cartella)
    candidati = (await asyncio.to_thread(booru_cerca, rich))[:rich.n]
    con_anteprima = _env("GRAVES_BOORU_ANTEPRIMA", "1").lower() not in ("0", "no", "off", "false")

    async def una(i: int, p: PostBooru):
        if not con_anteprima:
            return p, None
        return p, await asyncio.to_thread(_scarica_anteprima, p, cartella, i)

    return list(await asyncio.gather(*(una(i, p) for i, p in enumerate(candidati))))


async def booru_file(post: PostBooru, cartella, i: int = 0) -> Path:
    """Scarica il file completo di un post scelto dall'utente."""
    return await asyncio.to_thread(post.scarica, Path(cartella), i)


async def booru_altro(rich: RichiestaBooru, cartella, visti) -> tuple:
    """Un altro risultato casuale con gli stessi tag, diverso da quelli gia' mostrati (`visti`: set di id).
    Restituisce (post, path_anteprima | None). Solleva GravesErrore se non ne trova altri."""
    cartella = Path(cartella)
    r = RichiestaBooru(tags=list(rich.tags), n=1, sito=rich.sito, casuale=True)
    nuovi = [p for p in await asyncio.to_thread(booru_cerca, r) if p.id not in visti]
    if not nuovi:
        raise GravesErrore("Nessun altro risultato diverso da quelli già visti.")
    p = random.choice(nuovi)
    if _env("GRAVES_BOORU_ANTEPRIMA", "1").lower() in ("0", "no", "off", "false"):
        return p, None
    return p, await asyncio.to_thread(_scarica_anteprima, p, cartella, len(visti) + 100)
