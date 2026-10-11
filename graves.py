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
  GRAVES_MAX_MB       non scarica immagini più grandi di così (default 15)
  GRAVES_MAX_GIORNO   tetto di ricerche al giorno, contate a parte per ogni provider
                      (default 80; 0 = nessun tetto)
  GRAVES_STATO_FILE   contatore (default: graves_uso.json accanto allo script)

Sicurezza: gli URL delle immagini arrivano da pagine web qualsiasi. Prima di scaricarli (e a ogni
redirect) controllo che l'indirizzo sia pubblico: niente localhost, rete di casa o indirizzi interni.
Le chiavi API non finiscono mai nei messaggi di errore né nel log.
"""
from __future__ import annotations

import datetime
import ipaddress
import json
import os
import re
import socket
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


def configurato() -> bool:
    try:
        _provider()
        return True
    except GravesErrore:
        return False


# ---------- tetto giornaliero ----------
def _conta(provider: str):
    massimo = _int_env("GRAVES_MAX_GIORNO", 80)
    oggi = datetime.date.today().isoformat()
    with _lock:
        try:
            d = json.loads(STATO.read_text(encoding="utf-8"))
        except Exception:
            d = {}
        if d.get("giorno") != oggi:
            d = {"giorno": oggi}
        n = int(d.get(provider, 0))
        if massimo and n >= massimo:
            raise GravesErrore(f"Graves: raggiunto il tetto di {massimo} ricerche per oggi "
                               "(si cambia con GRAVES_MAX_GIORNO, 0 = nessun tetto).")
        d[provider] = n + 1
        try:
            tmp = STATO.with_name(f"{STATO.name}.{os.getpid()}.tmp")
            tmp.write_text(json.dumps(d), encoding="utf-8")
            os.replace(tmp, STATO)
        except OSError as e:
            log(f"  Graves: contatore non salvato ({e})")


# ---------- provider ----------
def _http_json(nome: str, req: urllib.request.Request, timeout: int = 20) -> dict:
    """Esegue la richiesta e restituisce il JSON. Gli errori non contengono mai l'URL (che per alcuni
    provider include la chiave API)."""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
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
                      pagina=i.get("link") or "", miniatura=i.get("thumbnailUrl") or "")
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
                      pagina=i.get("link") or "", miniatura=i.get("thumbnail") or "")
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
                                 pagina=img.get("contextLink") or "", miniatura=img.get("thumbnailLink") or ""))
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
    quanti = min(20, max(n * 2, n + 4))
    log(f"  Graves: cerco «{query}» con {provider} (voglio {n} immagini)")
    grezzi = _PROVIDER[provider](query, quanti)
    visti, out = set(), []
    for r in grezzi:
        if r.url.startswith(("http://", "https://")) and r.url not in visti:
            visti.add(r.url)
            out.append(r)
    if not out:
        raise GravesErrore(f"Nessun risultato per «{query}».")
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
    """Scarica i risultati in parallelo e restituisce i primi n riusciti, nell'ordine di Google."""
    n = _quante(n)
    cartella = Path(cartella)
    max_bytes = _int_env("GRAVES_MAX_MB", 15) * 1024 * 1024 or 15 * 1024 * 1024
    files: list[Path] = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futuri = [ex.submit(_scarica_uno, r, cartella, i, max_bytes) for i, r in enumerate(risultati)]
        for r, fut in zip(risultati, futuri):
            if len(files) >= n:
                fut.cancel()
                continue
            try:
                files.append(fut.result())
            except Exception as e:
                host = urllib.parse.urlsplit(r.url).netloc
                log(f"    Graves: scartata un'immagine di {host} ({e})")
    for p in cartella.glob("graves_*"):     # download extra finiti dopo che n era già raggiunto
        if p not in files:
            p.unlink(missing_ok=True)
    log(f"  Graves: scaricate {len(files)} immagini su {len(risultati)} risultati")
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
