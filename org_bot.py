"""
Branch (org_bot.py) - supplemento FACOLTATIVO dei bot (telegram_bot.py / discord_bot.py).

Se questo file non c'è, i bot funzionano esattamente come prima: discord_bot.py
lo carica solo se lo trova. telegram_bot.py non lo conosce nemmeno.

Cosa aggiunge
-------------
1. Una GUI per preparare le liste di link, una per persona.
2. Il comando Discord  /collega nome:marco  che collega la chat in cui lo lanci a «marco»
   (solo il collegamento: non invia niente; senza nome mostra a chi è collegata).
3. Il comando Discord  /invia  che manda la lista nella chat in cui lo lanci.
   La prima volta scrivi  /invia nome:marco  e il bot COLLEGA quella chat a
   «marco». Da quel momento, in quella chat, basta  /invia.

Come si usa
-----------
- GUI:   python org_bot.py      (su Windows senza console:  pythonw org_bot.py)
  A sinistra le persone, a destra la lista: un link per riga. Le righe che
  iniziano con  >  sono messaggi di testo ("a seguire", tra un link e l'altro).
  Le righe con  #  sono commenti. Premi Salva.
- Discord: apri la chat con quella persona e scrivi  /invia.
  Il bot manda messaggi e link (scaricati e allegati) in ordine, con una pausa
  tra un invio e l'altro, e TOGLIE dalla lista quello che è partito. Quello che
  non parte (link che non si scarica) resta in lista per il prossimo /invia.
  La cronologia è in invii/<nome>.inviati.log

Più link in un messaggio
------------------------
Una riga con PIÙ link (separati da spazio) è un solo messaggio: i link vengono scaricati tutti e i file
partono insieme come allegati (si divide in più messaggi solo oltre 10 allegati o il limite di MB). Un link
che non si scarica resta in lista, gli altri partono. Con scarica:False i link vanno insieme in un messaggio
di testo. Su Telegram la riga diventa un album per ogni canale. «Incolla in 1 riga» (GUI) mette tutti i link
degli appunti su una riga sola; «Incolla dagli appunti» ne mette uno per riga, come prima.

Limiti di Discord (non aggirabili)
----------------------------------
Un'app installata sul tuo account può scrivere solo come risposta a un tuo
comando, nella chat dove lo lanci, e solo per 15 minuti. Il bot si ferma a 13
minuti e ti dice di rilanciare /invia: riparte da dove era arrivato.

Opzioni del comando
-------------------
  nome:     persona (si completa da solo); serve solo la prima volta in una chat
  scarica:False   manda i link come testo invece di scaricare e allegare i file
  riduci:False    non riduce le immagini sopra il limite di upload (default: le riduce, vedi Pillow)
  prova:True      non invia niente: mostra cosa verrebbe inviato e quanto ci mette

Variabili d'ambiente (opzionali)
--------------------------------
  DISCORD_INVII_DIR   cartella delle liste (default: "invii" accanto a questo file)
  INVII_PAUSA_MIN     pausa minima tra due invii, in secondi (default 3)
  INVII_PAUSA_MAX     pausa massima tra due invii, in secondi (default 7)
  INVII_EXTRA_OGNI    ogni quanti messaggi fare una pausa più lunga (default 10)
  INVII_AUTOSAVE_SEC  ogni quanti secondi la GUI salva da sola le modifiche (default 30, 0 = mai)
  INVII_BACKUP_MAX    quante copie di backup tenere per persona (default 30)
  INVII_BACKUP_OGNI_SEC  distanza minima tra due backup automatici, in secondi (default 300)
  (Nessun messaggio di conferma a fine lista: compare solo se c'è un problema
  — link falliti, interruzione, limite dei 15 minuti — e resta finché non lo chiudi.)

Scheda Telegram (GUI)
---------------------
La GUI ha due schede: «Discord» (liste per persona, come prima) e «Telegram».
In «Telegram» c'è UNA lista condivisa e, a sinistra, i canali/gruppi con una spunta ciascuno:
«Invia ora» manda la lista a tutti quelli spuntati (scarica una volta sola e pubblica in ognuno).
Le righe partite per TUTTI i canali spuntati spariscono dalla lista; se un canale fallisce, la
riga resta e al prossimo invio i canali che l'hanno già ricevuta vengono saltati (invii/telegram/stato.json).
- «Aggiungi ID…»: incolla ID (-100…), @username o link t.me; il nome si legge da Telegram
  (il bot deve essere nel canale/gruppo) e viene semplificato (font strani ed emoji tolti).
- Serve BOT_TOKEN nell'ambiente (lo stesso di telegram_bot.py): mettilo nel .bat che avvia la GUI,
  insieme ad eventuali COOKIES_BROWSER / COOKIES_FILE. telegram_bot.py deve stare accanto a questo file.
- File: invii/telegram/lista.txt, canali.json, lista.inviati.log; backup in invii/backup/_telegram/.

Avvio dei bot da Branch
-----------------------
Sotto l'intestazione c'è un led: all'apertura Branch accende telegram_bot.py e discord_bot.py (se non
girano già). Chiudendo Branch i bot RESTANO accesi; riaprendo Branch li ritrova (led verde) e si
spengono solo cliccando il led (diventa rosso). Clic sul led rosso = li riaccende.
Le variabili (BOT_TOKEN, OWNER_ID, DISCORD_TOKEN, DISCORD_OWNER_ID, COOKIES_*) si leggono da bots.env
o da avvia_bot.bat: vedi bot_manager.py.

Salvataggio e backup
--------------------
- La GUI salva da sola le modifiche ogni 30 secondi (oltre al tasto Salva / Ctrl+S).
- Se lanci /invia mentre nella GUI ci sono modifiche non ancora salvate, il bot chiede alla GUI
  di salvarle subito (basta che la GUI sia aperta) e poi esegue il comando sulla lista aggiornata.
- Prima di ogni salvataggio che cambia la lista, e prima di ogni /invia o eliminazione, una copia
  della lista com'era finisce in  invii/backup/<nome>/AAAAMMGG-OOMMSS.txt  (se ne tengono 30).
  Per recuperare una lista basta copiare uno di quei file al posto di  invii/<nome>.txt.

Barra di avanzamento (GUI)
--------------------------
- Scheda Telegram: barra «elementi inviati / totale» più una barra che scorre mentre si scarica o
  si pubblica, con stima del tempo rimasto (media delle righe già partite, pause comprese).
- Scheda Discord: mentre /invia lavora sulla persona selezionata, il bot scrive ogni 5 s lo stato in
  invii/.progresso.<nome>.json e la GUI lo mostra (barra, tempo rimasto, conto alla rovescia verso il
  limite dei 13 minuti; avvisa se la lista non farà in tempo e servirà un altro /invia). Se il file
  non viene aggiornato da più di 20 s (bot chiuso o in crash) la GUI lo ignora; all'avvio il bot
  cancella gli stati rimasti.

Log
---
Avviato con pythonw (GUI senza console) scrive in org_bot.log accanto allo script; il file
ruota da solo sopra i 2 MB (restano org_bot.log.1 e .2, vedi bot_log.py). Quando è caricato da discord_bot.py usa il log di quest'ultimo.
"""
import sys
from pathlib import Path

# Senza console (pythonw) stdout/stderr sono None: li giro su un file .log con rotazione.
from bot_log import attiva_log_su_file
attiva_log_su_file()

import branch_tema as T   # aspetto grafico, immagini e avatar (deve stare accanto a questo file)
import bot_manager as BM   # avvio/arresto dei bot Telegram e Discord (deve stare accanto a questo file)

import asyncio
import contextlib
import json
import os
import queue
import random
import re
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

BASE = Path(__file__).resolve().parent
INVII_DIR = Path(os.environ.get("DISCORD_INVII_DIR") or BASE / "invii")
CHAT_FILE = INVII_DIR / "chat.json"        # {id chat: nome persona}
AVATAR_DIR = INVII_DIR / "avatar"          # persona_<nome>.png (Discord), tg_<id>.jpg (canali Telegram)


def avatar_persona(nome: str) -> Path:
    return AVATAR_DIR / f"persona_{nome}.png"


def avatar_tg(chat_id: int) -> Path:
    return AVATAR_DIR / f"tg_{chat_id}.jpg"

URL_RE = re.compile(r"https?://[^\s<>\"']+")

PAUSA_MIN = float(os.environ.get("INVII_PAUSA_MIN", "3"))
PAUSA_MAX = max(PAUSA_MIN, float(os.environ.get("INVII_PAUSA_MAX", "7")))
EXTRA_OGNI = max(1, int(os.environ.get("INVII_EXTRA_OGNI", "10")))
EXTRA_MIN, EXTRA_MAX = 15.0, 25.0          # pausa più lunga ogni EXTRA_OGNI messaggi
LIMITE_SEC = 13 * 60                       # i token delle interazioni durano 15 minuti
AUTOSAVE_SEC = max(0.0, float(os.environ.get("INVII_AUTOSAVE_SEC", "30")))   # 0 = disattivato
BACKUP_DIR = INVII_DIR / "backup"
BACKUP_MAX = max(1, int(os.environ.get("INVII_BACKUP_MAX", "30")))
BACKUP_OGNI = max(0.0, float(os.environ.get("INVII_BACKUP_OGNI_SEC", "300")))
GUI_VIVA = INVII_DIR / ".gui_attiva"            # la GUI lo aggiorna ogni 3 s finché è aperta
RICHIESTA = INVII_DIR / ".salva_richiesta"      # il bot lo crea per chiedere alla GUI di salvare
ATTESA_GUI = 1.5                                # secondi massimi di attesa (Discord vuole risposta in 3 s)
PROGRESSO_VECCHIO = 20.0                        # oltre questi secondi senza aggiornamenti lo stato si ignora
PROGRESSO_FINE = 3.0                            # quanto resta visibile la barra piena a invio completato


def _log_gui(msg: str):
    """Riga con orario su stdout (finisce in org_bot.log se non c'è console)."""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ======================= logica comune (bot e GUI) =======================
_RISERVATI_WIN = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                  *(f"lpt{i}" for i in range(1, 10))}


def nome_valido(nome: str) -> bool:
    if not nome or nome in (".", "..") or any(c in nome for c in '/\\:*?"<>|'):
        return False
    if any(ord(c) < 32 for c in nome) or nome != nome.rstrip(" ."):
        return False   # Windows toglie punti e spazi finali: il file avrebbe un altro nome
    return nome.split(".")[0].lower() not in _RISERVATI_WIN   # CON.txt, NUL.txt... sono dispositivi


def nomi_persone() -> list[str]:
    return sorted((p.stem for p in INVII_DIR.glob("*.txt")), key=str.lower)


def file_persona(nome: str) -> Path:
    return INVII_DIR / f"{nome}.txt"


def classifica(riga: str):
    """("testo", [messaggio]) / ("link", [url, ...]) / None per righe da ignorare."""
    r = riga.strip()
    if not r or r.startswith("#"):
        return None
    if r.startswith(">"):
        t = r[1:].strip()
        return ("testo", [t]) if t else None
    urls = URL_RE.findall(r)
    return ("link", urls) if urls else None


def leggi_coda(nome: str, path: Optional[Path] = None) -> list[tuple[str, str, list[str]]]:
    """Elementi in coda, in ordine: (riga originale, tipo, valori)."""
    coda = []
    for riga in (path or file_persona(nome)).read_text(encoding="utf-8-sig").splitlines():
        c = classifica(riga)
        if c:
            coda.append((riga, c[0], c[1]))
    return coda


def conta(coda) -> tuple[int, int]:
    """(numero di link, numero di messaggi) di una coda."""
    link = sum(len(v) for _, t, v in coda if t == "link")
    testi = sum(1 for _, t, _ in coda if t == "testo")
    return link, testi


def riassumi(contenuto: str) -> tuple[int, int, int]:
    """(link, messaggi, righe ignorate) di un testo di lista."""
    link = testi = ignorate = 0
    for riga in contenuto.splitlines():
        c = classifica(riga)
        if c is None:
            r = riga.strip()
            if r and not r.startswith("#"):
                ignorate += 1
        elif c[0] == "link":
            link += len(c[1])
        else:
            testi += 1
    return link, testi, ignorate


def righe_da_appunti(testo: str, unisci: bool = False) -> list[str]:
    """Trasforma il testo incollato in righe di lista: link uno per riga, il resto diventa messaggio.
    Con unisci=True tutti i link finiscono su UNA riga (nel punto del primo link): partono insieme."""
    out, posto, tutti = [], None, []
    for riga in testo.splitlines():
        r = riga.strip()
        if not r:
            continue
        urls = URL_RE.findall(r)
        if urls and unisci:
            if posto is None:
                posto = len(out)
                out.append("")
            tutti.extend(urls)
        elif urls:
            out.extend(urls)
        elif r.startswith(">"):
            out.append(r)
        else:
            out.append("> " + r)
    if posto is not None:
        out[posto] = " ".join(tutti)
    return out


def scrivi_atomico(path: Path, testo: str):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(testo, encoding="utf-8")
    os.replace(tmp, path)


def aggiorna_riga(nome: str, riga: str, nuova: Optional[str], path: Optional[Path] = None) -> bool:
    """Toglie dalla lista la riga inviata (o la sostituisce con quello che non è partito)."""
    path = path or file_persona(nome)
    righe = path.read_text(encoding="utf-8-sig").splitlines()
    for i, r in enumerate(righe):
        if r == riga:
            if nuova is None:
                del righe[i]
            else:
                righe[i] = nuova
            scrivi_atomico(path, "\n".join(righe) + ("\n" if righe else ""))
            return True
    return False


def fai_backup(nome: str, forza: bool = False, src: Optional[Path] = None) -> bool:
    """Copia la lista com'è ora su disco in backup/<nome>/ (salta se uguale all'ultimo backup;
    senza forza, al massimo uno ogni BACKUP_OGNI secondi). Tiene solo gli ultimi BACKUP_MAX."""
    try:
        contenuto = (src or file_persona(nome)).read_text(encoding="utf-8-sig")
        if not contenuto.strip():
            return False
        d = BACKUP_DIR / nome
        d.mkdir(parents=True, exist_ok=True)
        copie = sorted(d.glob("*.txt"))
        if copie:
            ultima = copie[-1]
            if ultima.read_text(encoding="utf-8-sig") == contenuto:
                return False
            if not forza and time.time() - ultima.stat().st_mtime < BACKUP_OGNI:
                return False
        scrivi_atomico(d / f"{time.strftime('%Y%m%d-%H%M%S')}.txt", contenuto)
        for vecchia in sorted(d.glob("*.txt"))[:-BACKUP_MAX]:
            vecchia.unlink()
        return True
    except Exception as e:   # un backup mancato non deve bloccare niente
        _log_gui(f"backup di «{nome}» non riuscito: {e!r}")
        return False


def gui_aperta() -> bool:
    """True se la GUI è aperta (il suo file-segnale è stato aggiornato negli ultimi secondi)."""
    try:
        return time.time() - GUI_VIVA.stat().st_mtime < 10
    except OSError:
        return False


def cronologia(nome: str, voce: str, base: Optional[Path] = None):
    try:
        with open((base or INVII_DIR) / f"{nome}.inviati.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M')}\t{voce}\n")
    except OSError:
        pass


def conta_cronologia(nome: str, base: Optional[Path] = None) -> int:
    try:
        with open((base or INVII_DIR) / f"{nome}.inviati.log", encoding="utf-8") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def carica_chat() -> dict:
    try:
        return json.loads(CHAT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def salva_chat(d: dict):
    scrivi_atomico(CHAT_FILE, json.dumps(d, ensure_ascii=False, indent=1))


def scollega(nome: str) -> int:
    """Toglie il collegamento chat -> persona. Restituisce quante chat erano collegate."""
    d = carica_chat()
    restanti = {k: v for k, v in d.items() if v != nome}
    if len(restanti) != len(d):
        salva_chat(restanti)
    return len(d) - len(restanti)


# ======================= avanzamento (bot e GUI) =======================
def formatta_durata(sec: float) -> str:
    sec = max(0, int(round(sec)))
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h} h {m:02d} min"
    if m:
        return f"{m} min {s:02d} s"
    return f"{s} s"


def stima_rimasto(fatti: int, tot: int, t_inizio: float, adesso: Optional[float] = None) -> Optional[float]:
    """Secondi rimasti, in base al tempo medio degli elementi già fatti (pause incluse).
    None finché non ne è partito almeno uno, o se è tutto finito."""
    if fatti < 1 or fatti >= tot:
        return None
    adesso = time.time() if adesso is None else adesso
    return max(0.0, (adesso - t_inizio) / fatti * (tot - fatti))


def file_progresso(nome: str) -> Path:
    return INVII_DIR / f".progresso.{nome}.json"


def leggi_progresso(nome: str) -> Optional[dict]:
    """Stato scritto dal bot durante /invia, o None se assente, illeggibile o non più aggiornato."""
    try:
        d = json.loads(file_progresso(nome).read_text(encoding="utf-8"))
        # a invio finito lo stato resta pochi secondi (barra piena + «Completato»), poi la GUI lo ignora
        if time.time() - float(d["agg"]) > (PROGRESSO_FINE if d.get("fine") else PROGRESSO_VECCHIO):
            return None
        int(d["n"]), int(d["tot"]), float(d["t_inizio"])
        return d
    except Exception:
        return None


# ======================= Telegram: logica comune (GUI e invio) =======================
TG_DIR = INVII_DIR / "telegram"
TG_LISTA = TG_DIR / "lista.txt"        # lista condivisa, inviata a tutti i canali spuntati
TG_CANALI = TG_DIR / "canali.json"     # [{"id": -100..., "nome": "...", "tipo": "...", "attivo": true}]
TG_STATO = TG_DIR / "stato.json"       # {link o testo: [id dei canali che l'hanno già ricevuto]}
TG_NOME = "_telegram"                  # nome usato per backup e cronologia della lista condivisa
_TG_LOCK = threading.Lock()            # GUI e thread di invio non scrivono la lista insieme

_TIPI = {"channel": "canale", "supergroup": "gruppo", "group": "gruppo", "private": "privata"}


def semplifica_nome(titolo: str, fallback: str = "") -> str:
    """Nome adatto alla GUI: font 'strani' (𝓜𝓪𝓻𝓬𝓸, ＭＡＲＣＯ) riportati a lettere normali,
    emoji, simboli, caratteri di controllo e accenti impilati tolti, spazi ripuliti."""
    s = unicodedata.normalize("NFKC", titolo or "")
    pulito = []
    for ch in s:
        cat = unicodedata.category(ch)
        if ch in "\t\r\n" or cat.startswith("Z"):
            pulito.append(" ")
        elif ord(ch) > 0xFFFF or cat[0] == "C" or cat in ("So", "Mn", "Me", "Sk"):
            continue
        else:
            pulito.append(ch)
    nome = " ".join("".join(pulito).split())
    if sum(c.isalnum() for c in nome) < 2:
        return fallback
    return nome[:40]


def normalizza_destinazione(testo: str) -> Optional[str]:
    """ID numerico, @username o link t.me -> valore da passare a getChat (None se non riconosciuto)."""
    t = (testo or "").strip().strip("<>\"'")
    if re.fullmatch(r"-?\d{5,}", t):
        return t
    m = re.fullmatch(r"(?:https?://)?(?:www\.)?t\.me/c/(\d+)(?:/\d+)*/?", t, re.I)
    if m:
        return "-100" + m.group(1)
    m = re.fullmatch(r"(?:https?://)?(?:www\.)?t\.me/([A-Za-z]\w{3,31})(?:/\d+)?/?", t, re.I)
    if m:
        return "@" + m.group(1)
    m = re.fullmatch(r"@?([A-Za-z]\w{3,31})", t)
    if m:
        return "@" + m.group(1)
    return None


def telegram_api(token: str, metodo: str, **params):
    """Chiamata semplice alla Bot API (solo lettura). Il token non finisce mai nei messaggi d'errore."""
    url = f"https://api.telegram.org/bot{token}/{metodo}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            dati = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            dati = json.loads(e.read().decode("utf-8"))
        except Exception:
            raise RuntimeError(f"errore HTTP {e.code}") from None
    except Exception as e:
        raise RuntimeError(f"rete non raggiungibile ({e.__class__.__name__})") from None
    if not dati.get("ok"):
        raise RuntimeError(dati.get("description") or "risposta non valida")
    return dati["result"]


def info_chat(token: str, dest: str) -> dict:
    """{'id', 'titolo', 'tipo'} di un canale/gruppo, dal suo ID o @username (il bot deve vederlo)."""
    tentativi = [dest]
    if re.fullmatch(r"\d{6,}", dest):          # ID di canale copiato senza il prefisso -100
        tentativi.append("-100" + dest)
    ultimo = RuntimeError("chat non trovata")
    for t in tentativi:
        try:
            r = telegram_api(token, "getChat", chat_id=t)
            return {"id": int(r["id"]),
                    "titolo": r.get("title") or r.get("first_name") or r.get("username") or "",
                    "tipo": _TIPI.get(r.get("type", ""), r.get("type", "")),
                    "foto": (r.get("photo") or {}).get("small_file_id") or ""}
        except RuntimeError as e:
            ultimo = e
    raise ultimo


def scarica_avatar_tg(token: str, file_id: str, dest: Path):
    """Foto del canale: getFile dà il percorso, poi si scarica da api.telegram.org/file/."""
    r = telegram_api(token, "getFile", file_id=file_id)
    T.scarica(f"https://api.telegram.org/file/bot{token}/{r['file_path']}", dest)


def carica_canali() -> list[dict]:
    try:
        dati = json.loads(TG_CANALI.read_text(encoding="utf-8"))
        return [{"id": int(c["id"]), "nome": str(c.get("nome") or ""), "tipo": str(c.get("tipo") or ""),
                 "attivo": bool(c.get("attivo", False))} for c in dati]
    except Exception:
        return []


def salva_canali(canali: list[dict]):
    TG_DIR.mkdir(parents=True, exist_ok=True)
    scrivi_atomico(TG_CANALI, json.dumps(canali, ensure_ascii=False, indent=1))


def carica_stato_tg() -> dict:
    try:
        return json.loads(TG_STATO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def salva_stato_tg(stato: dict):
    if stato:
        scrivi_atomico(TG_STATO, json.dumps(stato, ensure_ascii=False))
    else:
        try:
            TG_STATO.unlink()
        except OSError:
            pass


def _togli_riga_tg(riga: str, nuova: Optional[str]):
    with _TG_LOCK:
        aggiorna_riga(TG_NOME, riga, nuova, TG_LISTA)


async def _pausa(stop, secondi: float):
    fine = time.time() + secondi
    while time.time() < fine and not stop.is_set():
        await asyncio.sleep(0.25)


async def _invia_testo(bot, chat_id: int, testo: str):
    from telegram.error import RetryAfter
    for _ in range(3):
        try:
            await bot.send_message(chat_id, testo)
            return
        except RetryAfter as e:                      # Telegram chiede di rallentare
            attesa = e.retry_after
            attesa = attesa.total_seconds() if hasattr(attesa, "total_seconds") else float(attesa)
            await asyncio.sleep(attesa + 1)
    raise RuntimeError("Telegram chiede di rallentare (troppi messaggi)")


async def _gruppo_telegram(bot, ids: list[int], nomi: dict, valori: list[str], stato: dict, stop,
                           falliti: list[str]):
    """Più link sulla stessa riga: li scarico una volta sola e li mando insieme (album) a ogni canale.
    Restituisce (inviato, resto): resto = i link non ancora consegnati a tutti i canali."""
    from telegram_bot import download, rendi_riproducibile, send_files, log
    serviti = {u: set(stato.get(u, [])) for u in valori}
    inviato = False
    with contextlib.ExitStack() as pila:
        pronti: dict[str, list[Path]] = {}
        for u in valori:
            if u in pronti or all(i in serviti[u] for i in ids):
                continue
            if stop.is_set():
                break
            d = pila.enter_context(tempfile.TemporaryDirectory())
            try:
                log(f"  gruppo: scarico {u}")
                files = await asyncio.to_thread(download, u, d)
                if not files:
                    raise RuntimeError("niente da scaricare")
                pronti[u] = [await rendi_riproducibile(p) for p in files]
            except Exception as e:
                log(f"  ERRORE: {e}")
                falliti.append(f"{u[:60]} ({str(e)[:60]})")
        for i in ids:
            if stop.is_set():
                break
            invio = [(u, p) for u in valori if u in pronti and i not in serviti[u] for p in pronti[u]]
            if not invio:
                continue
            errs = await send_files(bot, i, [p for _, p in invio])
            falliti_url = {u for u, p in invio if any(e.startswith(p.name + ":") for e in errs)}
            if errs and not falliti_url:
                falliti_url = {u for u, _ in invio}      # errore non attribuibile a un link: li riprovo tutti
            for u in dict.fromkeys(u for u, _ in invio):
                if u in falliti_url:
                    falliti.append(f"{nomi[i]}: {u[:50]} ({errs[0][:50]})")
                else:
                    serviti[u].add(i)
                    inviato = True
                    cronologia(TG_NOME, f"{nomi[i]}\t{u}", TG_DIR)
    resto = []
    for u in valori:
        if all(i in serviti[u] for i in ids):
            stato.pop(u, None)
        else:
            if serviti[u]:
                stato[u] = sorted(serviti[u])
            if u not in resto:
                resto.append(u)
    return inviato, resto


async def _invia_telegram(canali: list[dict], stop, riporta):
    token = os.environ.get("BOT_TOKEN", "")
    if not token:
        raise RuntimeError("BOT_TOKEN non impostato")
    try:
        from telegram import Bot
        from telegram.request import HTTPXRequest
        from telegram_bot import download, rendi_riproducibile, send_files, log
    except ImportError as e:
        raise RuntimeError(f"manca un modulo ({e.name}); telegram_bot.py deve stare accanto a org_bot.py") from e

    ids = [c["id"] for c in canali]
    nomi = {c["id"]: semplifica_nome(c["nome"], f"Canale {c['id']}") for c in canali}
    stato = carica_stato_tg()
    coda = leggi_coda(TG_NOME, TG_LISTA)
    pub, falliti, fermato = 0, [], False
    log(f"Telegram: invio di {len(coda)} elementi a {len(ids)} canali")

    request = HTTPXRequest(read_timeout=120, write_timeout=600, connect_timeout=30, pool_timeout=30)
    async with Bot(token, request=request) as bot:
        for n, (riga, tipo, valori) in enumerate(coda, 1):
            if stop.is_set():
                break
            riporta({"msg": f"Invio {n}/{len(coda)} a {len(ids)} canali…",
                     "n": n - 1, "tot": len(coda), "occupato": True})
            unita = [(riga, valori[0])] if tipo == "testo" else [(u, u) for u in valori]
            inviato, resto = False, []
            gruppo = tipo == "link" and len(valori) > 1
            if gruppo:   # più link sulla stessa riga: un solo invio (album) per canale
                inviato, resto = await _gruppo_telegram(bot, ids, nomi, valori, stato, stop, falliti)
                salva_stato_tg(stato)
            for chiave, contenuto in ([] if gruppo else unita):
                serviti = set(stato.get(chiave, []))
                da_fare = [i for i in ids if i not in serviti]
                if da_fare:
                    try:
                        if tipo == "testo":
                            for i in da_fare:
                                if stop.is_set():
                                    break
                                try:
                                    await _invia_testo(bot, i, contenuto)
                                    serviti.add(i)
                                    inviato = True
                                    cronologia(TG_NOME, f"{nomi[i]}\t{contenuto}", TG_DIR)
                                except Exception as e:
                                    falliti.append(f"{nomi[i]}: {str(e)[:60]}")
                        else:
                            log(f"  [{n}/{len(coda)}] {contenuto}")
                            with tempfile.TemporaryDirectory() as d:
                                files = await asyncio.to_thread(download, contenuto, d)
                                if not files:
                                    raise RuntimeError("niente da scaricare")
                                files = [await rendi_riproducibile(p) for p in files]
                                for i in da_fare:
                                    if stop.is_set():
                                        break
                                    errs = await send_files(bot, i, files)
                                    if errs:
                                        falliti.append(f"{nomi[i]}: {contenuto[:50]} ({errs[0][:50]})")
                                    else:
                                        serviti.add(i)
                                        inviato = True
                                        cronologia(TG_NOME, f"{nomi[i]}\t{contenuto}", TG_DIR)
                    except Exception as e:
                        log(f"  ERRORE: {e}")
                        falliti.append(f"{contenuto[:60]} ({str(e)[:60]})")
                if all(i in serviti for i in ids):
                    stato.pop(chiave, None)
                else:
                    if serviti:
                        stato[chiave] = sorted(serviti)
                    resto.append(chiave)
                salva_stato_tg(stato)
            if resto != [k for k, _ in unita]:        # qualcosa è partito per tutti: aggiorno la lista
                _togli_riga_tg(riga, (resto[0] if tipo == "testo" else " ".join(resto)) if resto else None)
            if inviato and n < len(coda) and not stop.is_set():
                pub += 1
                pausa = random.uniform(PAUSA_MIN, PAUSA_MAX)
                if pub % EXTRA_OGNI == 0:
                    pausa += random.uniform(EXTRA_MIN, EXTRA_MAX)
                riporta({"msg": f"Pausa di {pausa:.0f} s prima del prossimo invio…",
                         "n": n, "tot": len(coda), "occupato": False})
                await _pausa(stop, pausa)
        fermato = stop.is_set()
    log(f"Telegram: finito ({len(falliti)} non consegnati{', fermato' if fermato else ''})")
    riporta({"fine": True, "falliti": falliti, "fermato": fermato, "errore": None})


def lavora_telegram(canali: list[dict], stop, riporta):
    """Corpo del thread di invio (la GUI non si blocca): manda la lista condivisa ai canali."""
    try:
        asyncio.run(_invia_telegram(canali, stop, riporta))
    except Exception as e:
        _log_gui(f"invio Telegram: errore {e!r}")
        riporta({"fine": True, "falliti": [], "fermato": False, "errore": str(e)[:150]})


# ======================= avatar e diagnostica Discord =======================
def _canale_grezzo(interaction) -> dict:
    """Il pezzo «channel» del payload originale dell'interazione (se discord.py lo conserva)."""
    for attr in ("_original_data", "_data"):
        raw = getattr(interaction, attr, None)
        if isinstance(raw, dict) and isinstance(raw.get("channel"), dict):
            return raw["channel"]
    return {}


def diagnostica_interazione(interaction, log):
    """Scrive nel log cosa contiene un comando lanciato in una chat: serve a capire se nei DM
    si riesce a risalire all'altra persona (e quindi al suo avatar)."""
    try:
        ch = interaction.channel
        log("  DIAG chat: "
            f"channel={type(ch).__name__}, tipo={getattr(ch, 'type', None)!r}, "
            f"recipient={getattr(ch, 'recipient', None)!r}, guild_id={interaction.guild_id}, "
            f"context={getattr(interaction, 'context', None)!r}")
        grezzo = _canale_grezzo(interaction)
        log("  DIAG payload channel: " + (json.dumps(grezzo, default=str, ensure_ascii=False)[:700]
                                         if grezzo else "non disponibile (discord.py non conserva il payload)"))
        log("  DIAG data comando: " + json.dumps(interaction.data, default=str, ensure_ascii=False)[:500])
        log(f"  DIAG utente che scrive: {interaction.user.id}")
    except Exception as e:
        log(f"  DIAG non riuscita: {e!r}")


def avatar_url_discord(interaction) -> Optional[str]:
    """URL dell'avatar dell'altra persona in un DM, o None (server, gruppi, dati assenti)."""
    rec = getattr(interaction.channel, "recipient", None)
    if rec is not None and getattr(rec, "id", None) != interaction.user.id:
        return str(rec.display_avatar.replace(size=128, format="png").url)
    grezzo = _canale_grezzo(interaction)
    recs = [r for r in (grezzo.get("recipients") or []) if str(r.get("id")) != str(interaction.user.id)]
    if grezzo.get("type") == 1 and len(recs) == 1:
        r = recs[0]
        if r.get("avatar"):
            return f"https://cdn.discordapp.com/avatars/{r['id']}/{r['avatar']}.png?size=128"
        return f"https://cdn.discordapp.com/embed/avatars/{(int(r['id']) >> 22) % 6}.png"
    return None


async def salva_avatar_discord(interaction, nome: str, log, utente=None):
    try:
        if utente is not None:
            url = str(utente.display_avatar.replace(size=128, format="png").url)
        else:
            url = avatar_url_discord(interaction)
        if not url:
            log("  avatar Discord: non ricavabile da questa chat (server, gruppo o dati assenti)")
            return
        await asyncio.to_thread(T.scarica, url, avatar_persona(nome))
        log(f"  avatar Discord salvato per «{nome}»")
    except Exception as e:
        log(f"  avatar Discord non salvato: {e}")


# ======================= comando Discord /invia =======================
def registra(client, owner: int, fit, batches):
    """Aggiunge /invia al bot Discord (chiamata da discord_bot.py, se questo file esiste)."""
    import discord
    from discord import app_commands
    from telegram_bot import IgLimite, download, ig_avviso, log, rendi_riproducibile

    INVII_DIR.mkdir(parents=True, exist_ok=True)
    in_corso: set[str] = set()   # evita due invii contemporanei della stessa persona
    for vecchio in INVII_DIR.glob(".progresso.*.json"):   # stati rimasti da un'esecuzione interrotta
        try:
            vecchio.unlink()
        except OSError:
            pass

    class _Fallito(Exception):
        """Il link non si è potuto scaricare/preparare (non è un errore di Discord)."""

    async def completa(interaction: discord.Interaction, current: str):
        return [app_commands.Choice(name=n, value=n)
                for n in nomi_persone() if current.lower() in n.lower()][:25]

    async def prepara_link(url: str, d: str, riduci: bool = True) -> list[Path]:
        """Scarica il link in d e restituisce i file pronti per Discord. _Fallito se non si riesce."""
        try:
            files = await asyncio.to_thread(download, url, d)
            if not files:
                raise _Fallito("niente da scaricare")
            return [await fit(await rendi_riproducibile(p), riduci) for p in files]
        except (_Fallito, IgLimite):
            raise
        except Exception as e:
            log(f"  ERRORE download: {e}")
            raise _Fallito(str(e)) from e

    async def spedisci(interaction, pronti: list[Path], stat: dict, dopo_lotto=None):
        """Manda i file in messaggi da max 10 allegati e dimensione totale nel limite."""
        for batch in batches(pronti):
            handles = [discord.File(p) for p in batch]
            try:
                await interaction.followup.send(files=handles)
                stat["pub"] += 1
            finally:
                for h in handles:
                    h.close()
            if dopo_lotto:
                dopo_lotto(batch)

    async def invia_link(interaction, url: str, scarica: bool, stat: dict, riduci: bool = True):
        """Invia un link. _Fallito se non si scarica; gli errori di Discord salgono."""
        if not scarica:
            await interaction.followup.send(url)
            stat["pub"] += 1
            return
        with tempfile.TemporaryDirectory() as d:
            await spedisci(interaction, await prepara_link(url, d, riduci), stat)

    async def invia_gruppo(interaction, urls: list[str], scarica: bool, stat: dict,
                           fatti: list[str], falliti: list[str], scadenza: float, riduci: bool = True):
        """Più link sulla stessa riga = un solo messaggio (si divide solo oltre 10 allegati o il limite
        di MB). Aggiunge a `fatti` i link consegnati per intero e a `falliti` quelli non preparati."""
        if not scarica:   # solo testo: i link vanno insieme, in messaggi sotto i 2000 caratteri
            parti, corrente, dentro = [], "", []
            for u in urls:
                if corrente and len(corrente) + 1 + len(u) > 1900:
                    parti.append((corrente, dentro))
                    corrente, dentro = u, [u]
                else:
                    corrente = f"{corrente}\n{u}" if corrente else u
                    dentro.append(u)
            if corrente:
                parti.append((corrente, dentro))
            for testo_msg, dentro in parti:
                await interaction.followup.send(testo_msg)
                stat["pub"] += 1
                fatti.extend(dentro)
            return
        with contextlib.ExitStack() as pila:     # le cartelle temporanee vivono fino a invio finito
            pronti, di_chi = [], {}
            for url in urls:
                if time.time() > scadenza:        # i link non ancora scaricati restano in lista
                    falliti.append(f"{url[:80]} (limite di 15 minuti: resta in lista)")
                    continue
                log(f"  gruppo: preparo {url}")
                d = pila.enter_context(tempfile.TemporaryDirectory())
                try:
                    files = await prepara_link(url, d, riduci)
                except _Fallito as e:
                    falliti.append(f"{url[:80]} ({str(e)[:60]})")
                    continue
                pronti.extend(files)
                for p in files:
                    di_chi[p] = url
            mancano = {}
            for u in di_chi.values():
                mancano[u] = mancano.get(u, 0) + 1

            def lotto_partito(batch):             # un link è "fatto" quando sono partiti tutti i suoi file
                for p in batch:
                    u = di_chi[p]
                    mancano[u] -= 1
                    if mancano[u] == 0:
                        fatti.append(u)

            await spedisci(interaction, pronti, stat, lotto_partito)

    async def salva_dalla_gui(nome: str):
        """Se la GUI è aperta, le chiedo di salvare subito le modifiche non salvate di «nome»."""
        if not gui_aperta():
            return
        try:
            scrivi_atomico(RICHIESTA, nome)
        except OSError:
            return
        limite = time.time() + ATTESA_GUI
        while RICHIESTA.exists():
            if time.time() > limite:
                log(f"  la GUI non ha risposto entro {ATTESA_GUI:g} s: uso la lista già salvata")
                try:
                    RICHIESTA.unlink()
                except OSError:
                    pass
                return
            await asyncio.sleep(0.1)

    @client.tree.command(name="invia", description="Invia i link in coda per questa chat")
    @app_commands.describe(
        nome="Persona (serve solo la prima volta in una chat: poi la chat resta collegata)",
        scarica="Scarica e allega i file (False = manda i link come testo)",
        riduci="Riduci le immagini sopra il limite invece di scartarle (default sì)",
        prova="Non inviare niente: mostra cosa verrebbe inviato",
    )
    @app_commands.autocomplete(nome=completa)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def cmd_invia(interaction: discord.Interaction, nome: Optional[str] = None,
                        scarica: bool = True, prova: bool = False, riduci: bool = True):
        if interaction.user.id != owner:
            log(f"Ignorato /invia da {interaction.user.id}: non è DISCORD_OWNER_ID")
            await interaction.response.send_message("Non sei autorizzato.", ephemeral=True)
            return

        chat_id = str(interaction.channel_id)
        mappa = carica_chat()
        if nome and nome.strip():
            nome = nome.strip()
            if not nome_valido(nome) or not file_persona(nome).is_file():
                await interaction.response.send_message(
                    f"Persona «{nome}» non trovata. Disponibili: {', '.join(nomi_persone()) or 'nessuna'}. "
                    "Creala dalla GUI (python org_bot.py).", ephemeral=True)
                return
        else:
            nome = mappa.get(chat_id)
            if not nome:
                await interaction.response.send_message(
                    "Questa chat non è ancora collegata a nessuna persona. Scrivi "
                    "/collega nome:<persona> (oppure /invia nome:<persona>, che collega e invia). "
                    f"Disponibili: {', '.join(nomi_persone()) or 'nessuna'}.", ephemeral=True)
                return
            if not file_persona(nome).is_file():
                await interaction.response.send_message(
                    f"La lista di «{nome}» non esiste più. Ricreala dalla GUI o usa /invia nome:...",
                    ephemeral=True)
                return
        if nome in in_corso:
            await interaction.response.send_message(f"«{nome}» è già in corso di invio.", ephemeral=True)
            return

        await salva_dalla_gui(nome)         # eventuali modifiche non salvate nella GUI
        coda = leggi_coda(nome)
        if not coda:
            await interaction.response.send_message(f"Niente in coda per «{nome}».", ephemeral=True)
            return
        n_link, n_testi = conta(coda)

        if prova:
            n_msg = len(coda)
            stima = n_msg * (PAUSA_MIN + PAUSA_MAX) / 2 + (n_msg // EXTRA_OGNI) * (EXTRA_MIN + EXTRA_MAX) / 2
            righe = [f"«{nome}»: {n_link} link e {n_testi} messaggi in coda.",
                     f"Tempo stimato: circa {int(stima // 60)} min {int(stima % 60)} s, "
                     "più il tempo dei download."]
            for n, (_, tipo, valori) in enumerate(coda[:15], 1):
                icona = "💬" if tipo == "testo" else ("📦" if len(valori) > 1 else "🔗")   # 📦 = gruppo
                righe.append(f"{n}. {icona} {' '.join(valori)[:80]}")
            if len(coda) > 15:
                righe.append(f"… e altri {len(coda) - 15}")
            await interaction.response.send_message("\n".join(righe)[:1900], ephemeral=True)
            return

        nuova_chat = mappa.get(chat_id) != nome
        if nuova_chat:                      # collego questa chat alla persona
            mappa[chat_id] = nome
            salva_chat(mappa)

        # Discord vuole una risposta entro 3 secondi: rispondo subito, poi lavoro
        await interaction.response.defer(thinking=True)
        in_corso.add(nome)
        if nuova_chat:
            diagnostica_interazione(interaction, log)
            await salva_avatar_discord(interaction, nome, log)
        await asyncio.to_thread(fai_backup, nome, True)   # copia della lista prima che si svuoti
        t0 = time.time()
        stat = {"pub": 0}                   # messaggi partiti nella chat
        falliti: list[str] = []
        errore = None
        fermato = False
        stop_ig = None
        completato = False                  # True solo se il ciclo arriva in fondo senza interrompersi

        # stato per la barra di avanzamento della GUI (invii/.progresso.<nome>.json)
        prog = {"nome": nome, "n": 0, "tot": len(coda), "t_inizio": t0, "scadenza": t0 + LIMITE_SEC,
                "occupato": True, "msg": "", "agg": t0}

        def scrivi_prog(**kw):
            prog.update(kw)
            prog["agg"] = time.time()
            try:
                scrivi_atomico(file_progresso(nome), json.dumps(prog, ensure_ascii=False))
            except OSError:
                pass   # la GUI può leggere il file in quel momento: riprovo al prossimo giro

        async def battito_prog():   # tiene "fresco" il file anche durante un download lungo
            while True:
                scrivi_prog()
                await asyncio.sleep(5)

        task_prog = asyncio.create_task(battito_prog())
        try:
            log(f"/invia «{nome}»: {len(coda)} elementi in coda")
            for n, (riga, tipo, valori) in enumerate(coda, 1):
                if time.time() - t0 > LIMITE_SEC:
                    fermato = True
                    break
                scrivi_prog(n=n - 1, occupato=True,
                            msg="messaggio di testo" if tipo == "testo"
                            else valori[0][:60] + (f" (+{len(valori) - 1})" if len(valori) > 1 else ""))
                prima = stat["pub"]
                try:
                    if tipo == "testo":
                        await interaction.followup.send(valori[0])
                        stat["pub"] += 1
                        aggiorna_riga(nome, riga, None)
                        cronologia(nome, riga)
                    else:
                        fatti = []
                        try:
                            if len(valori) > 1:     # più link sulla stessa riga = un solo messaggio
                                log(f"  [{n}/{len(coda)}] gruppo di {len(valori)} link in un messaggio")
                                await invia_gruppo(interaction, valori, scarica, stat, fatti, falliti,
                                                   t0 + LIMITE_SEC, riduci)
                            else:
                                url = valori[0]
                                log(f"  [{n}/{len(coda)}] {url}")
                                try:
                                    await invia_link(interaction, url, scarica, stat, riduci)
                                    fatti.append(url)
                                except _Fallito as e:
                                    falliti.append(f"{url[:80]} ({str(e)[:60]})")
                        finally:
                            # tolgo dalla lista ciò che è partito, anche se mi interrompo a metà
                            restanti = [u for u in valori if u not in fatti]
                            aggiorna_riga(nome, riga, " ".join(restanti) if restanti else None)
                            for u in fatti:
                                cronologia(nome, u)
                except IgLimite as e:     # soglia alta Instagram: mi fermo, il resto resta in lista
                    stop_ig = str(e)
                    log(f"  {e}")
                    break
                except discord.DiscordException as e:
                    errore = str(e)[:150]
                    log(f"  ERRORE Discord: {e}")
                    break
                scrivi_prog(n=n, occupato=False, msg="Pausa tra gli invii…")
                if stat["pub"] > prima and n < len(coda):    # pausa tra un invio e l'altro
                    pausa = random.uniform(PAUSA_MIN, PAUSA_MAX)
                    if stat["pub"] // EXTRA_OGNI > prima // EXTRA_OGNI:
                        pausa += random.uniform(EXTRA_MIN, EXTRA_MAX)
                    await asyncio.sleep(pausa)
            else:
                completato = True
        finally:
            in_corso.discard(nome)
            task_prog.cancel()
            if completato:   # barra piena per qualche secondo; poi la GUI lo ignora da sola
                scrivi_prog(n=len(coda), occupato=False, msg="Completato", fine=True)
            else:
                try:
                    file_progresso(nome).unlink()
                except OSError:
                    pass

        rimasto = leggi_coda(nome)
        r_link, r_testi = conta(rimasto)
        righe = [f"✅ «{nome}»: partiti {stat['pub']} messaggi."]
        if falliti:
            righe.append("⚠️ Non partiti (restano in lista):\n" + "\n".join(f"• {f}" for f in falliti))
        if errore:
            righe.append(f"⚠️ Interrotto da Discord: {errore}")
        if fermato:
            righe.append("⏸ Fermato per il limite di 15 minuti di Discord.")
        if stop_ig:
            righe.append("⏸ " + stop_ig)
        avviso_ig = ig_avviso()
        if avviso_ig:
            righe.append(avviso_ig)
        if rimasto:
            righe.append(f"In lista restano {r_link} link e {r_testi} messaggi: rilancia /invia per continuare.")
        if nuova_chat:
            righe.append(f"🔗 Questa chat è collegata a «{nome}»: la prossima volta basta /invia.")
        log(f"/invia «{nome}»: finito ({stat['pub']} messaggi, {len(falliti)} falliti)"
            + (f", interrotto da Discord: {errore}" if errore else "")
            + (", fermato per il limite dei 15 minuti" if fermato else ""))

        tutto_ok = stat["pub"] > 0 and not (falliti or errore or fermato or stop_ig or avviso_ig)
        if tutto_ok:
            return   # è partito tutto: nessun messaggio di conferma (resta nel log)

        if stat["pub"] == 0:
            # tolgo il "sta pensando…" pubblico, così l'altra persona non vede errori
            try:
                await interaction.delete_original_response()
            except Exception:
                pass
        await interaction.followup.send("\n".join(righe)[:1900], ephemeral=True)


    @client.tree.command(name="collega", description="Collega questa chat a una persona (poi basta /invia)")
    @app_commands.describe(
        nome="Persona a cui collegare questa chat (senza nome: mostra il collegamento attuale)",
        utente="Facoltativo: l'utente Discord, per prenderne l'avatar")
    @app_commands.autocomplete(nome=completa)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def cmd_collega(interaction: discord.Interaction, nome: Optional[str] = None,
                          utente: Optional[discord.User] = None):
        if interaction.user.id != owner:
            log(f"Ignorato /collega da {interaction.user.id}: non è DISCORD_OWNER_ID")
            await interaction.response.send_message("Non sei autorizzato.", ephemeral=True)
            return

        diagnostica_interazione(interaction, log)   # cosa arriva da questa chat (vedi org_bot.log)
        chat_id = str(interaction.channel_id)
        mappa = carica_chat()
        disponibili = ", ".join(nomi_persone()) or "nessuna"

        if not nome or not nome.strip():          # solo informazioni
            attuale = mappa.get(chat_id)
            if attuale:
                testo = f"Questa chat è collegata a «{attuale}». Per cambiarla: /collega nome:<persona>."
            else:
                testo = f"Questa chat non è collegata a nessuna persona. Disponibili: {disponibili}."
            await interaction.response.send_message(testo, ephemeral=True)
            return

        nome = nome.strip()
        if not nome_valido(nome) or not file_persona(nome).is_file():
            await interaction.response.send_message(
                f"Persona «{nome}» non trovata. Disponibili: {disponibili}. "
                "Creala dalla GUI (python org_bot.py).", ephemeral=True)
            return

        prima = mappa.get(chat_id)
        if prima == nome:
            await interaction.response.send_message(
                f"Questa chat è già collegata a «{nome}».", ephemeral=True)
            await salva_avatar_discord(interaction, nome, log, utente)   # rinfresca l'avatar
            return

        mappa[chat_id] = nome
        salva_chat(mappa)
        log(f"/collega: chat {chat_id} -> «{nome}»" + (f" (prima «{prima}»)" if prima else ""))
        n_link, n_testi = conta(leggi_coda(nome))
        testo = f"🔗 Questa chat è ora collegata a «{nome}»"
        if prima:
            testo += f" (prima era «{prima}»)"
        testo += f". In coda: {n_link} link e {n_testi} messaggi. Scrivi /invia per mandarli."
        await interaction.response.send_message(testo, ephemeral=True)
        await salva_avatar_discord(interaction, nome, log, utente)


# ======================= GUI =======================
class PannelloProgresso:
    """Barra «fatti/totale» + barra che scorre mentre c'è un'attività, con tempo rimasto.
    Si inserisce nel layout (prima del widget `prima`) solo quando serve e sparisce a fine invio."""

    def __init__(self, parent, prima, tk, ttk):
        self._prima = prima
        self.frame = tk.Frame(parent)
        self.etichetta = tk.Label(self.frame, anchor="w", justify="left", fg=T.INFO)
        self.etichetta.pack(fill="x")
        self.barra = ttk.Progressbar(self.frame, mode="determinate")
        self.barra.pack(fill="x", pady=(2, 0))
        self.attivita = ttk.Progressbar(self.frame, mode="indeterminate")
        self.attivita.pack(fill="x", pady=(2, 0))
        self._visibile = False
        self._scorre = False

    def mostra(self, fatti: int, tot: int, t_inizio: float, occupato: bool,
               testo: str = "", scadenza: Optional[float] = None):
        if not self._visibile:
            self.frame.pack(fill="x", pady=(4, 0), before=self._prima)
            self._visibile = True
        self.barra.config(maximum=max(1, tot))
        self.barra["value"] = min(fatti, tot)
        if occupato and not self._scorre:
            self.attivita.start(15)
            self._scorre = True
        elif not occupato and self._scorre:
            self.attivita.stop()
            self._scorre = False
        parti = [f"{fatti}/{tot} elementi"]
        colore = T.INFO
        resto = stima_rimasto(fatti, tot, t_inizio)
        if resto is not None:
            parti.append(f"circa {formatta_durata(resto)} rimasti")
        if scadenza is not None:
            mancano = scadenza - time.time()
            parti.append(f"limite Discord tra {formatta_durata(mancano)}")
            if resto is not None and resto > mancano:
                parti.append("⚠ non basterà: servirà un altro /invia")
                colore = T.WARN
        self.etichetta.config(text=(testo + "\n" if testo else "") + "  ·  ".join(parti), fg=colore)

    def nascondi(self):
        if not self._visibile:
            return
        self.attivita.stop()
        self._scorre = False
        self.frame.pack_forget()
        self._visibile = False


def crea_scheda_telegram(root, scheda, tk, ttk, messagebox, simpledialog, subprocess):
    """Scheda «Telegram»: canali spuntabili a sinistra, lista condivisa a destra."""
    import queue

    TG_DIR.mkdir(parents=True, exist_ok=True)
    if not TG_LISTA.exists():
        TG_LISTA.write_text("", encoding="utf-8")
    st = {"mtime": 0.0, "canali": carica_canali(), "invio": None}
    code = queue.Queue()        # i thread (ricerca nomi, invio) lasciano qui i risultati per la GUI

    # ---- colonna sinistra: canali e gruppi ----
    sx = tk.Frame(scheda)
    sx.pack(side="left", fill="y", padx=(10, 4), pady=10)
    tk.Label(sx, text="Canali e gruppi", font=T.F_TITOLO).pack(anchor="w")
    if os.environ.get("BOT_TOKEN"):
        tk.Label(sx, text="Spunta dove inviare la lista.", fg=T.MUTED).pack(anchor="w")
    else:
        tk.Label(sx, text="⚠ BOT_TOKEN non impostato: senza non\nposso leggere i nomi né inviare.",
                 fg=T.ERR, justify="left").pack(anchor="w")
    bt_sx = tk.Frame(sx)
    bt_sx.pack(side="bottom", fill="x")
    cn = T.ListaCanali(sx, width=270)        # canali disegnati sul Canvas, con lo sfondo dietro
    cn.pack(side="left", fill="both", expand=True, pady=4)

    # ---- colonna destra: lista condivisa ----
    dx = tk.Frame(scheda)
    dx.pack(side="left", fill="both", expand=True, padx=(4, 10), pady=10)
    info = tk.Label(dx, text="", anchor="w", font=("Segoe UI", 10, "bold"))
    info.pack(fill="x")
    tk.Label(dx, anchor="w", justify="left", fg=T.MUTED,
             text="Lista condivisa: va a tutti i canali spuntati. Un link per riga; più link sulla stessa "
                  "riga = un solo invio (album).\nLe righe che iniziano con > sono messaggi di testo; # = commento. "
                  "Con «Invia ora» le righe partite spariscono da qui."
                  + (f" Salvataggio automatico ogni {AUTOSAVE_SEC:g} s." if AUTOSAVE_SEC else "")
             ).pack(fill="x", pady=(0, 4))
    cornice = tk.Frame(dx)
    cornice.pack(fill="both", expand=True)
    barra = tk.Scrollbar(cornice)
    barra.pack(side="right", fill="y")
    testo = tk.Text(cornice, wrap="word", undo=True, font=("Consolas", 10), yscrollcommand=barra.set)
    testo.pack(side="left", fill="both", expand=True)
    barra.config(command=testo.yview)
    msg = tk.Label(dx, text="", anchor="w", justify="left", fg=T.OK, wraplength=620)
    msg.pack(fill="x", pady=(4, 0))
    bt_dx = tk.Frame(dx)
    bt_dx.pack(fill="x", pady=(4, 0))
    pannello = PannelloProgresso(dx, bt_dx, tk, ttk)

    def dirty() -> bool:
        return testo.edit_modified()

    def in_thread(fn, cb):
        """Esegue fn in un thread e poi chiama cb(risultato o eccezione) nella GUI."""
        def run():
            try:
                r = fn()
            except Exception as e:
                r = e
            code.put(("cb", cb, r))
        threading.Thread(target=run, daemon=True).start()

    # ---------------- lista condivisa ----------------
    def carica_lista():
        try:
            contenuto = TG_LISTA.read_text(encoding="utf-8-sig")
            st["mtime"] = TG_LISTA.stat().st_mtime
        except OSError as e:
            messagebox.showerror("Errore", f"Non riesco a leggere la lista: {e}")
            return
        testo.delete("1.0", "end")
        testo.insert("1.0", contenuto)
        testo.edit_modified(False)
        testo.edit_reset()

    def aggiorna_info():
        try:
            link, testi = conta(leggi_coda(TG_NOME, TG_LISTA))
        except Exception:
            link = testi = 0
        att = sum(1 for c in st["canali"] if c["attivo"])
        info.config(text=f"Lista Telegram: in coda {link} link e {testi} messaggi  |  "
                         f"canali spuntati: {att}  |  già inviati: {conta_cronologia(TG_NOME, TG_DIR)}")

    def salva(auto: bool = False, motivo: str = "Salvato") -> bool:
        if TG_LISTA.exists() and TG_LISTA.stat().st_mtime != st["mtime"]:
            if auto:
                return False        # l'ha cambiata l'invio: senza chiedere non la sovrascrivo
            if not messagebox.askyesno(
                    "Lista cambiata",
                    "L'invio ha modificato questa lista nel frattempo (ha inviato dei link).\n"
                    "Sovrascrivere con quello che vedi?\n\nScegli No per ricaricare la lista aggiornata."):
                testo.edit_modified(False)
                carica_lista()
                return False
        contenuto = testo.get("1.0", "end-1c")
        if contenuto and not contenuto.endswith("\n"):
            contenuto += "\n"
        with _TG_LOCK:
            fai_backup(TG_NOME, src=TG_LISTA)
            scrivi_atomico(TG_LISTA, contenuto)
            st["mtime"] = TG_LISTA.stat().st_mtime
        testo.edit_modified(False)
        link, testi, ignorate = riassumi(contenuto)
        extra = f", {ignorate} righe ignorate (senza link né >)" if ignorate else ""
        msg.config(text=f"{motivo} ({time.strftime('%H:%M:%S')}): {link} link, {testi} messaggi{extra}.",
                   fg=T.WARN if ignorate else T.OK)
        aggiorna_info()
        return True

    def chiedi_salvataggio() -> bool:
        if not dirty():
            return True
        r = messagebox.askyesnocancel("Modifiche non salvate", "Salvare le modifiche alla lista Telegram?")
        if r is None:
            return False
        return salva() if r else True

    def incolla(unisci: bool = False):
        try:
            clip = root.clipboard_get()
        except tk.TclError:
            clip = ""
        nuove = righe_da_appunti(clip, unisci)
        if not nuove:
            messagebox.showinfo("Incolla", "Negli appunti non c'è niente da aggiungere.")
            return
        corrente = testo.get("1.0", "end-1c")
        if corrente and not corrente.endswith("\n"):
            testo.insert("end", "\n")
        testo.insert("end", "\n".join(nuove) + "\n")
        testo.see("end")
        msg.config(text=f"Aggiunte {len(nuove)} righe: ricorda di salvare.", fg=T.WARN)

    def apri_cartella():
        try:
            if sys.platform == "win32":
                os.startfile(TG_DIR)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(TG_DIR)])
            else:
                subprocess.Popen(["xdg-open", str(TG_DIR)])
        except Exception as e:
            messagebox.showerror("Errore", str(e))

    # ---------------- canali / gruppi ----------------
    def ridisegna():
        cn.imposta(st["canali"], lambda c: semplifica_nome(c["nome"], f"Canale {c['id']}"),
                   lambda c: avatar_tg(c["id"]), toggle, rimuovi)

    def toggle(c, valore):
        c["attivo"] = bool(valore)
        salva_canali(st["canali"])
        ridisegna()
        aggiorna_info()

    def rimuovi(c):
        nome = semplifica_nome(c["nome"], f"Canale {c['id']}")
        if not messagebox.askyesno("Rimuovi", f"Togliere «{nome}» dall'elenco?\n(Non lascia il canale: toglie solo la voce.)"):
            return
        st["canali"] = [x for x in st["canali"] if x["id"] != c["id"]]
        salva_canali(st["canali"])
        ridisegna()
        aggiorna_info()

    def risolvi(destinazioni):
        """(thread) per ogni destinazione: (dest, info della chat o None, errore o None)."""
        token = os.environ.get("BOT_TOKEN", "")
        out = []
        for d in destinazioni:
            if not token:
                out.append((d, None, "BOT_TOKEN non impostato"))
                continue
            try:
                ch = info_chat(token, d)
                if ch.get("foto"):
                    try:
                        scarica_avatar_tg(token, ch["foto"], avatar_tg(ch["id"]))
                    except Exception as e:      # senza foto resta l'iniziale
                        _log_gui(f"avatar canale {ch['id']}: {e}")
                out.append((d, ch, None))
            except Exception as e:
                out.append((d, None, str(e)[:80]))
        return out

    def applica(risultati, scartati=()):
        if isinstance(risultati, Exception):
            msg.config(text=f"⚠ Ricerca non riuscita: {risultati}", fg=T.ERR)
            return
        agg, problemi = 0, [f"{x}: non è un ID, @username o link t.me" for x in scartati]
        for dest, ch, err in risultati:
            if ch:
                cid = ch["id"]
                nome = semplifica_nome(ch["titolo"], f"Canale {cid}")
                tipo = ch["tipo"]
            elif re.fullmatch(r"-?\d+", dest):
                cid, nome, tipo = int(dest), f"Canale {int(dest)}", ""
                problemi.append(f"{dest}: nome non letto ({err})")
            else:
                problemi.append(f"{dest}: non trovato ({err})")
                continue
            esiste = next((c for c in st["canali"] if c["id"] == cid), None)
            if esiste:
                if ch:
                    esiste["nome"], esiste["tipo"] = nome, tipo
            else:
                st["canali"].append({"id": cid, "nome": nome, "tipo": tipo, "attivo": False})
                agg += 1
        salva_canali(st["canali"])
        ridisegna()
        aggiorna_info()
        base = f"Aggiunti {agg} canali/gruppi (spuntali per usarli)." if agg else "Elenco aggiornato."
        if problemi:
            for p in problemi:
                _log_gui(f"canali Telegram: {p}")
            msg.config(text="⚠ " + base + "\n" + "\n".join(problemi[:4]) +
                            ("\n…(altri nel log)" if len(problemi) > 4 else ""), fg=T.WARN)
        else:
            msg.config(text=base, fg=T.OK)

    def aggiungi():
        dlg = tk.Toplevel(root)
        dlg.title("Aggiungi canali / gruppi")
        dlg.transient(root)
        tk.Label(dlg, justify="left",
                 text="Incolla uno o più ID (es. -1001234567890), @username o link t.me,\n"
                      "uno per riga o separati da virgola. Il nome si legge da solo\n"
                      "(il bot deve essere nel canale/gruppo, meglio se amministratore).").pack(
            padx=10, pady=(10, 4), anchor="w")
        t = tk.Text(dlg, width=52, height=6)
        t.pack(padx=10)
        t.focus_set()

        def ok():
            grezzi = [x for x in re.split(r"[\s,;]+", t.get("1.0", "end").strip()) if x]
            dlg.destroy()
            validi, scartati = [], []
            for x in grezzi:
                n = normalizza_destinazione(x)
                if n:
                    validi.append(n)
                else:
                    scartati.append(x)
            validi = list(dict.fromkeys(validi))
            if not validi:
                msg.config(text="⚠ Nessun ID, @username o link t.me riconosciuto.", fg=T.ERR)
                return
            msg.config(text="Cerco i nomi…", fg=T.INFO)
            in_thread(lambda: risolvi(validi), lambda r: applica(r, scartati))

        bt = tk.Frame(dlg)
        bt.pack(pady=10)
        tk.Button(bt, text="Aggiungi", command=ok).pack(side="left", padx=4)
        tk.Button(bt, text="Annulla", command=dlg.destroy).pack(side="left", padx=4)

    def aggiorna_nomi():
        if not st["canali"]:
            return
        msg.config(text="Aggiorno i nomi…", fg=T.INFO)
        ids = [str(c["id"]) for c in st["canali"]]
        in_thread(lambda: risolvi(ids), applica)

    # ---------------- invio ----------------
    def aggiorna_bottoni():
        invio = st["invio"] is not None
        bt_invia.config(state="disabled" if invio else "normal")
        bt_ferma.config(state="normal" if invio else "disabled")

    def invia():
        if st["invio"]:
            return
        attivi = [c for c in st["canali"] if c["attivo"]]
        if not attivi:
            messagebox.showinfo("Invia", "Spunta almeno un canale a sinistra.")
            return
        if not os.environ.get("BOT_TOKEN"):
            messagebox.showerror("Invia", "BOT_TOKEN non impostato: avvia la GUI dal .bat con le stesse "
                                          "variabili del bot Telegram.")
            return
        if dirty() and not salva(auto=True, motivo="Salvato prima dell'invio"):
            messagebox.showwarning("Invia", "La lista è stata cambiata altrove: salvala (o ricaricala) e riprova.")
            return
        try:
            link, testi = conta(leggi_coda(TG_NOME, TG_LISTA))
        except Exception:
            link = testi = 0
        if not (link or testi):
            messagebox.showinfo("Invia", "Niente in coda.")
            return
        elenco = "\n".join("• " + semplifica_nome(c["nome"], f"Canale {c['id']}") for c in attivi)
        if not messagebox.askyesno("Invia ora", f"Inviare {link} link e {testi} messaggi a:\n{elenco}\n\nProcedo?"):
            return
        stop = threading.Event()
        st["invio"] = {"stop": stop, "t0": time.time()}
        aggiorna_bottoni()
        msg.config(text="Avvio dell'invio…", fg=T.INFO)
        riporta = lambda d: code.put(("rep", d))
        threading.Thread(target=lavora_telegram, args=([dict(c) for c in attivi], stop, riporta),
                         daemon=True).start()

    def ferma():
        if st["invio"]:
            st["invio"]["stop"].set()
            msg.config(text="Mi fermo dopo l'invio in corso…", fg=T.WARN)

    def finito(d):
        corsa, st["invio"] = st["invio"], None
        if corsa and corsa.get("tot") and not (d.get("errore") or d.get("falliti") or d.get("fermato")):
            pannello.mostra(corsa["tot"], corsa["tot"], corsa["t0"], False)   # barra piena per un attimo
            root.after(2000, lambda: None if st["invio"] else pannello.nascondi())
        else:
            pannello.nascondi()
        aggiorna_bottoni()
        try:
            rl, rt = conta(leggi_coda(TG_NOME, TG_LISTA))
        except Exception:
            rl = rt = 0
        problemi = []
        if d.get("errore"):
            problemi.append(f"errore: {d['errore']}")
        if d.get("falliti"):
            problemi.append(f"{len(d['falliti'])} non consegnati (restano in lista)")
            for f in d["falliti"]:
                _log_gui(f"  non consegnato: {f}")
        if d.get("fermato"):
            problemi.append("invio fermato")
        if problemi:
            msg.config(text="⚠ " + "; ".join(problemi) + f". In lista restano {rl} link e {rt} messaggi. "
                            "Dettagli in org_bot.log.", fg=T.WARN)
        else:
            msg.config(text="")           # tutto partito: nessun messaggio di conferma
        if not dirty():
            carica_lista()
        aggiorna_info()

    def poll():
        try:
            while True:
                try:
                    voce = code.get_nowait()
                except queue.Empty:
                    break
                if voce[0] == "cb":
                    voce[1](voce[2])
                elif voce[1].get("fine"):
                    finito(voce[1])
                elif st["invio"]:
                    d = voce[1]
                    if "msg" in d:
                        msg.config(text=d["msg"], fg=T.INFO)
                    if "tot" in d:
                        st["invio"]["tot"] = d["tot"]
                        pannello.mostra(d["n"], d["tot"], st["invio"]["t0"], d.get("occupato", False))
        except Exception as e:
            _log_gui(f"scheda Telegram: errore {e!r}")
        root.after(200, poll)

    def tick():
        """Ogni 3 secondi: ricarica la lista se è cambiata (invio in corso) e aggiorna i conteggi."""
        try:
            if TG_LISTA.exists() and TG_LISTA.stat().st_mtime != st["mtime"]:
                if dirty():
                    if st["invio"]:
                        msg.config(text="⚠ La lista è cambiata durante l'invio: salvando potresti "
                                        "reinviare link già partiti.", fg=T.ERR)
                else:
                    carica_lista()
            aggiorna_info()
        except Exception as e:
            _log_gui(f"scheda Telegram, tick: errore {e!r}")
        root.after(3000, tick)

    def autosalva():
        try:
            if dirty():
                salva(auto=True, motivo="Salvataggio automatico")
        except Exception as e:
            _log_gui(f"scheda Telegram, salvataggio automatico: errore {e!r}")
        root.after(int(AUTOSAVE_SEC * 1000), autosalva)

    for txt, cmd in (("Aggiungi ID…", aggiungi), ("Aggiorna nomi", aggiorna_nomi)):
        tk.Button(bt_sx, text=txt, command=cmd).pack(side="left", expand=True, fill="x", padx=1, pady=(4, 0))
    riga1 = tk.Frame(bt_dx)     # modifica della lista
    riga1.pack(fill="x")
    riga2 = tk.Frame(bt_dx)     # invio: su una riga a parte, così non sparisce a finestra stretta
    riga2.pack(fill="x", pady=(4, 0))
    for txt, cmd in (("Incolla dagli appunti", incolla), ("Incolla in 1 riga", lambda: incolla(True)),
                     ("Salva", salva), ("Apri cartella", apri_cartella)):
        tk.Button(riga1, text=txt, command=cmd).pack(side="left", padx=(0, 4))
    bt_invia = tk.Button(riga2, text="Invia ora", command=invia, font=("Segoe UI", 9, "bold"))
    bt_invia.pack(side="right")
    bt_ferma = tk.Button(riga2, text="Ferma", command=ferma, state="disabled")
    bt_ferma.pack(side="right", padx=(0, 6))

    carica_lista()
    ridisegna()
    aggiorna_info()
    root.after(200, poll)
    root.after(3000, tick)
    if AUTOSAVE_SEC > 0:
        root.after(int(AUTOSAVE_SEC * 1000), autosalva)
    return {"salva": salva, "chiedi_salvataggio": chiedi_salvataggio,
            "invio_in_corso": lambda: st["invio"] is not None, "ferma": ferma}


# ---------------------------------------------------------------- aggiornamento da GitHub (pulsante)
# stessa logica del pulsante ⟳ di pannello.py: git pull --ff-only, poi si riavvia solo ciò che è cambiato
FILE_GUI = {"org_bot.py", "bot_manager.py", "bot_log.py", "branch_tema.py", "sendbot_tema.py"}
FILE_BOT = {"telegram_bot.py", "discord_bot.py", "org_bot.py", "bot_log.py"}
_HEAD_AVVIO: Optional[str] = None     # commit al momento dell'apertura della GUI (per accorgersi di update già scaricati)


def _git(*args, timeout: int = 90):
    import subprocess
    extra = {"creationflags": 0x08000000} if os.name == "nt" else {}      # niente finestra console su Windows
    r = subprocess.run(["git", *args], cwd=BM.BASE, capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}, **extra)
    return r.returncode, (r.stdout + r.stderr).strip()


def ricorda_head_avvio():
    global _HEAD_AVVIO
    try:
        c, h = _git("rev-parse", "HEAD")
        if not c:
            _HEAD_AVVIO = h
    except Exception:
        pass


def git_pull() -> dict:
    """git pull --ff-only. Ritorna {ok, output} se fallisce, altrimenti {ok, cambiati, gui, bot}.
    I file cambiati si contano dal commit di apertura della GUI: se l'aggiornamento automatico ha già
    scaricato qualcosa, il codice in esecuzione è comunque vecchio e il riavvio viene proposto."""
    global _HEAD_AVVIO
    import subprocess
    try:
        c, _o = _git("rev-parse", "--is-inside-work-tree")
        if c:
            return {"ok": False, "output": "Questa cartella non è una repo git."}
        _c, prima = _git("rev-parse", "HEAD")
        c, out = _git("pull", "--ff-only")
        if c:
            return {"ok": False, "output": out[-500:]}
        _c, dopo = _git("rev-parse", "HEAD")
        base = _HEAD_AVVIO or prima
        cambiati = []
        if dopo != base:
            _c, d = _git("diff", "--name-only", base, dopo)
            cambiati = d.splitlines()
        _HEAD_AVVIO = dopo
    except FileNotFoundError:
        return {"ok": False, "output": "git non è installato."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": "Timeout: GitHub non risponde (rete?)."}
    nomi = {os.path.basename(x) for x in cambiati}
    _log_gui(f"git pull: {len(cambiati)} file cambiati")
    return {"ok": True, "cambiati": cambiati, "gui": bool(nomi & FILE_GUI), "bot": bool(nomi & FILE_BOT)}


def riavvia_processo():
    """Rilancia questa stessa GUI (da chiamare dopo root.destroy())."""
    if os.name == "nt":
        import subprocess
        subprocess.Popen([sys.executable] + sys.argv, cwd=BM.BASE)     # su Windows execv non è affidabile
    else:
        os.execv(sys.executable, [sys.executable] + sys.argv)


def crea_barra_bot(root, tk):
    """Barra sotto l'intestazione: un led che mostra lo stato dei due bot (Telegram + Discord).
    Verde = entrambi accesi, rosso = spenti, arancione = uno solo / in corso.
    Un clic: se almeno un bot gira li spegne tutti, altrimenti li accende tutti.
    I bot sono processi indipendenti: chiudere Branch NON li spegne (vedi bot_manager.py)."""
    gestore = BM.GestoreBot(log=_log_gui)
    barra = tk.Frame(root, bg=T.BG)
    barra.pack(fill="x")
    bt_git = tk.Button(barra, text="⟳ Aggiorna da GitHub")
    bt_git.pack(side="right", padx=(0, 10))
    cv = tk.Canvas(barra, height=34, bg=T.BG, highlightthickness=0, cursor="hand2")
    cv.pack(side="left", fill="x", expand=True, padx=10)
    ultimo = {"firma": None, "stato": {}, "occupato": False, "msg": ""}

    def disegna(stato: dict, occupato: bool, msg: str):
        firma = (tuple(sorted(stato.items())), occupato, msg, cv.winfo_width())
        if firma == ultimo["firma"]:
            return
        ultimo["firma"] = firma
        accesi = sum(1 for v in stato.values() if v)
        if occupato:
            colore, titolo = T.WARN, msg or "BOT IN CORSO…"
        elif accesi == len(stato):
            colore, titolo = T.OK, "BOT ATTIVI"
        elif accesi == 0:
            colore, titolo = T.ERR, "BOT SPENTI"
        else:
            colore, titolo = T.WARN, "BOT PARZIALI"
        cv.delete("all")
        cy = 17
        cv.create_oval(6, cy - 11, 28, cy + 11, fill=T.BG, outline=colore, width=1)     # alone
        cv.create_oval(10, cy - 7, 24, cy + 7, fill=colore, outline="")                 # led
        cv.create_text(40, cy, text=titolo, anchor="w", fill=colore, font=T.F_NOME)
        x = 40 + 9 * len(titolo) + 24
        for nome, (etichetta, _s, _v) in BM.MODULI.items():
            on = stato.get(nome, False)
            cv.create_oval(x, cy - 4, x + 8, cy + 4, fill=T.OK if on else T.ROSSO_SCURO, outline="")
            cv.create_text(x + 14, cy, text=etichetta, anchor="w", fill=T.FG if on else T.MUTED,
                           font=T.F_PICCOLO)
            x += 14 + 7 * len(etichetta) + 18
        errori = [f"{BM.MODULI[n][0]}: {e}" for n, e in gestore.errori.items()]
        cv.create_text(max(cv.winfo_width() - 8, x), cy, anchor="e", fill=T.ERR if errori else T.MUTED,
                       font=T.F_PICCOLO,
                       text=("  ·  ".join(errori) if errori else "clic sul led per accendere/spegnere i bot"))

    def aggiorna():
        try:
            disegna(gestore.stato(), gestore.occupato, ultimo["msg"])
        except Exception as e:
            _log_gui(f"stato bot: errore {e!r}")
        root.after(1500, aggiorna)

    def in_thread(fn, msg):
        if gestore.occupato:
            return
        gestore.occupato = True
        ultimo["msg"] = msg
        disegna(gestore.stato(), True, msg)

        def corpo():
            try:
                fn()
            except Exception as e:
                _log_gui(f"bot: errore {e!r}")
            finally:
                gestore.occupato = False
        threading.Thread(target=corpo, daemon=True).start()

    def clic(_=None):
        if gestore.occupato:
            return
        if any(gestore.stato().values()):
            in_thread(gestore.ferma_tutti, "SPEGNIMENTO…")
        else:
            in_thread(gestore.avvia_mancanti, "AVVIO…")

    # ---- pulsante «Aggiorna da GitHub»
    from tkinter import messagebox
    esiti = queue.SimpleQueue()
    hook = {"riavvia": None}          # lo imposta avvia_gui: salva le liste, controlla gli invii, riavvia

    def lavoro_git():
        try:
            esiti.put(git_pull())
        except Exception as e:
            esiti.put({"ok": False, "output": repr(e)})

    def aggiorna_ora():
        if gestore.occupato:
            return
        bt_git.config(state="disabled")
        in_thread(lavoro_git, "AGGIORNAMENTO…")

    def riavvia_bot():
        if any(gestore.stato().values()):          # riaccendo solo se giravano
            gestore.ferma_tutti()
            gestore.avvia_mancanti()

    def esito_git(r):
        if gestore.occupato:                       # il thread del pull non ha ancora finito
            root.after(200, lambda: esito_git(r))
            return
        bt_git.config(state="normal")
        if not r["ok"]:
            messagebox.showwarning("Aggiornamento", r.get("output") or "git pull non riuscito.")
            return
        if not r["cambiati"]:
            messagebox.showinfo("Aggiornamento", "Già all'ultima versione.")
            return
        testo = f"Aggiornati {len(r['cambiati'])} file."
        if r["bot"]:
            in_thread(riavvia_bot, "RIAVVIO BOT…")
            testo += "\nI bot vengono riavviati con il codice nuovo."
        if r["gui"] and hook["riavvia"]:
            if messagebox.askyesno("Aggiornamento", testo + "\n\nPer applicare le modifiche a Branch serve "
                                   "riavviarlo.\nRiavviare ora?"):
                hook["riavvia"]()
        else:
            messagebox.showinfo("Aggiornamento", testo)

    def poll_esiti():
        try:
            r = esiti.get_nowait()
        except queue.Empty:
            r = None
        if r is not None:
            try:
                esito_git(r)
            except Exception as e:
                _log_gui(f"aggiornamento: errore {e!r}")
                bt_git.config(state="normal")
        root.after(300, poll_esiti)

    bt_git.config(command=aggiorna_ora)
    root.after(300, poll_esiti)

    cv.bind("<Button-1>", clic)
    cv.bind("<Configure>", lambda e: (ultimo.update(firma=None), disegna(gestore.stato(), gestore.occupato,
                                                                        ultimo["msg"])))

    # all'apertura: prima controlla GitHub, poi accende i bot che non girano già
    def avvio_con_update():
        ricorda_head_avvio()
        gestore.aggiorna()
        gestore.avvia_mancanti()
    root.after(400, lambda: in_thread(avvio_con_update, "AGGIORNAMENTO…"))

    # controllo periodico (ogni 30 minuti); se un'operazione è in corso, in_thread salta il giro
    def controllo_periodico():
        in_thread(gestore.aggiorna, "AGGIORNAMENTO…")
        root.after(30 * 60 * 1000, controllo_periodico)
    root.after(30 * 60 * 1000, controllo_periodico)
    root.after(1500, aggiorna)
    return {"gestore": gestore, "clic": clic, "imposta_riavvio": lambda f: hook.update(riavvia=f)}


def avvia_gui():
    import subprocess
    import tkinter as tk
    from tkinter import messagebox, simpledialog, ttk

    INVII_DIR.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    T.init(root)
    root.title("Branch")
    root.geometry("980x600")
    root.minsize(920, 480)

    if hasattr(T, "Banner"):
        T.Banner(root).pack(fill="x")          # illustrazione scurita + logo + nome
    else:
        testa = tk.Frame(root)
        testa.pack(fill="x")
        tk.Label(testa, text="BRANCH", font=T.F_LOGO, fg=T.ROSSO).pack(side="left", padx=(14, 8), pady=(6, 2))
    tk.Frame(root, height=2, bg=T.ROSSO).pack(fill="x")
    barra_bot = crea_barra_bot(root, tk)       # led di stato dei bot (si avviano da soli all'apertura)

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True)
    scheda_dc = tk.Frame(nb)
    scheda_tg = tk.Frame(nb)
    nb.add(scheda_dc, text="  Discord  ")
    nb.add(scheda_tg, text="  Telegram  ")
    tg = crea_scheda_telegram(root, scheda_tg, tk, ttk, messagebox, simpledialog, subprocess)

    st = {"nome": None, "mtime": 0.0, "nomi": [], "etichette": None}

    # ---- colonna sinistra: persone ----
    sx = tk.Frame(scheda_dc)
    sx.pack(side="left", fill="y", padx=(10, 4), pady=10)
    tk.Label(sx, text="Persone", font=T.F_TITOLO).pack(anchor="w")
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    lista = T.ListaAvatar(sx, avatar_persona, width=250)
    lista.pack(fill="y", expand=True, pady=4)
    bt_sx = tk.Frame(sx)
    bt_sx.pack(fill="x")

    # ---- colonna destra: lista della persona ----
    dx = tk.Frame(scheda_dc)
    dx.pack(side="left", fill="both", expand=True, padx=(4, 10), pady=10)
    info = tk.Label(dx, text="", anchor="w", font=("Segoe UI", 10, "bold"))
    info.pack(fill="x")
    tk.Label(dx, anchor="w", justify="left", fg=T.MUTED,
             text="Un link per riga. Più link sulla stessa riga (separati da spazio) = un solo messaggio.\n"
                  "Le righe che iniziano con > sono messaggi di testo, quelle con # sono commenti.\n"
                  "Con /invia le righe partite spariscono da qui."
                  + (f" Salvataggio automatico ogni {AUTOSAVE_SEC:g} s." if AUTOSAVE_SEC else "")).pack(fill="x", pady=(0, 4))
    cornice = tk.Frame(dx)
    cornice.pack(fill="both", expand=True)
    barra = tk.Scrollbar(cornice)
    barra.pack(side="right", fill="y")
    testo = tk.Text(cornice, wrap="word", undo=True, font=("Consolas", 10), yscrollcommand=barra.set)
    testo.pack(side="left", fill="both", expand=True)
    barra.config(command=testo.yview)
    # senza una persona selezionata non c'è una lista in cui scrivere: l'editor resta spento
    segnaposto = T.SfondoVuoto(cornice, "Scegli una persona a sinistra\noppure creane una nuova.")
    msg = tk.Label(dx, text="", anchor="w", fg=T.OK)
    msg.pack(fill="x", pady=(4, 0))
    bt_dx = tk.Frame(dx)
    bt_dx.pack(fill="x", pady=(4, 0))
    pannello = PannelloProgresso(dx, bt_dx, tk, ttk)

    def dirty() -> bool:
        return st["nome"] is not None and testo.edit_modified()

    bottoni_persona = []    # i pulsanti che hanno senso solo con una persona selezionata

    def aggiorna_editor():
        """Editor e pulsanti attivi solo se c'è una persona selezionata."""
        attivo = st["nome"] is not None
        testo.config(state="normal" if attivo else "disabled", bg=T.INPUT if attivo else T.PANEL)
        for b in bottoni_persona:
            b.config(state="normal" if attivo else "disabled")
        if attivo:
            segnaposto.place_forget()
        else:
            segnaposto.place(x=0, y=0, relwidth=1, relheight=1)

    def etichetta(nome: str) -> str:
        try:
            link, _ = conta(leggi_coda(nome))
        except Exception:
            return nome
        return f"{nome}  ({link} link)" if link else nome

    def riempi_lista(seleziona: Optional[str] = None, forza: bool = False):
        nomi = nomi_persone()
        etichette = [etichetta(n) for n in nomi]
        if forza or etichette != st["etichette"] or nomi != st["nomi"]:
            st["nomi"], st["etichette"] = nomi, etichette
            lista.imposta(nomi, etichette)
        target = seleziona or st["nome"]
        if target in nomi:
            lista.selection_clear(0, "end")
            i = nomi.index(target)
            lista.selection_set(i)
            lista.see(i)
        lista.controlla()   # ridisegna se cambia la selezione o arriva un avatar nuovo

    def aggiorna_info():
        nome = st["nome"]
        if not nome:
            info.config(text="Scegli una persona a sinistra, oppure creane una nuova.")
            return
        try:
            link, testi = conta(leggi_coda(nome))
        except Exception:
            link = testi = 0
        chat = sum(1 for v in carica_chat().values() if v == nome)
        info.config(text=f"«{nome}»: in coda {link} link e {testi} messaggi  |  "
                         f"chat collegate: {chat}  |  già inviati: {conta_cronologia(nome)}")

    def carica(nome: str):
        st["nome"] = nome
        aggiorna_editor()           # con l'editor spento non si potrebbe scrivere la lista
        p = file_persona(nome)
        try:
            contenuto = p.read_text(encoding="utf-8-sig")
            st["mtime"] = p.stat().st_mtime
        except OSError as e:
            messagebox.showerror("Errore", f"Non riesco a leggere la lista: {e}")
            return
        testo.delete("1.0", "end")
        testo.insert("1.0", contenuto)
        testo.edit_modified(False)
        testo.edit_reset()
        msg.config(text="")
        aggiorna_info()

    def salva(auto: bool = False, motivo: str = "Salvato") -> bool:
        nome = st["nome"]
        if not nome:
            return False
        p = file_persona(nome)
        if p.exists() and p.stat().st_mtime != st["mtime"]:
            if auto:
                return False    # l'ha cambiata il bot: senza chiedere non la sovrascrivo
            if not messagebox.askyesno(
                    "Lista cambiata",
                    "Il bot ha modificato questa lista nel frattempo (ha inviato dei link).\n"
                    "Sovrascrivere con quello che vedi?\n\nScegli No per ricaricare la lista aggiornata."):
                testo.edit_modified(False)
                carica(nome)
                return False
        contenuto = testo.get("1.0", "end-1c")
        if contenuto and not contenuto.endswith("\n"):
            contenuto += "\n"
        fai_backup(nome)            # copia di com'era su disco prima di sovrascrivere
        scrivi_atomico(p, contenuto)
        st["mtime"] = p.stat().st_mtime
        testo.edit_modified(False)
        link, testi, ignorate = riassumi(contenuto)
        extra = f", {ignorate} righe ignorate (senza link né >)" if ignorate else ""
        msg.config(text=f"{motivo} ({time.strftime('%H:%M:%S')}): {link} link, {testi} messaggi{extra}.",
                   fg=T.WARN if ignorate else T.OK)
        riempi_lista()
        aggiorna_info()
        return True

    def chiedi_salvataggio() -> bool:
        if not dirty():
            return True
        r = messagebox.askyesnocancel("Modifiche non salvate", f"Salvare le modifiche a «{st['nome']}»?")
        if r is None:
            return False
        return salva() if r else True

    def salva_al_cambio() -> Optional[bool]:
        """Prima di cambiare persona: salva da solo le modifiche.
        True = salvate, False = niente da salvare (o scartate), None = annullato (si resta dov'è)."""
        if not dirty():
            return False
        if salva(auto=True, motivo="Salvato al cambio persona"):
            return True
        # salva(auto) rinuncia se il bot ha cambiato la lista nel frattempo: sovrascrivere va deciso a mano
        r = messagebox.askyesnocancel(
            "Modifiche non salvate",
            f"Non riesco a salvare da solo «{st['nome']}»: il bot ha cambiato la lista nel frattempo.\n"
            "Salvare comunque le tue modifiche?")
        if r is None:
            return None
        if r:
            return True if salva() else None
        return False

    def su_selezione(_=None):
        sel = lista.curselection()
        if not sel:
            return
        nome = st["nomi"][sel[0]]
        if nome == st["nome"]:
            return
        prec = st["nome"]
        salvate = salva_al_cambio()
        if salvate is None:
            riempi_lista()          # rimetto la selezione precedente
            return
        carica(nome)
        if salvate:
            msg.config(text=f"Modifiche a «{prec}» salvate prima di cambiare persona.", fg=T.OK)

    def nuova():
        if salva_al_cambio() is None:
            return
        nome = simpledialog.askstring("Nuova persona", "Nome della persona (es. Marco):", parent=root)
        if not nome:
            return
        nome = nome.strip()
        if not nome_valido(nome):
            messagebox.showerror("Nome non valido", 'Evita i caratteri  / \\ : * ? " < > |')
            return
        p = file_persona(nome)
        if not p.exists():
            p.write_text("", encoding="utf-8")
        riempi_lista(nome, forza=True)
        carica(nome)

    def elimina():
        nome = st["nome"]
        if not nome:
            return
        if not messagebox.askyesno("Elimina", f"Eliminare «{nome}» e la sua lista?"):
            return
        fai_backup(nome, forza=True)    # la lista eliminata resta recuperabile in backup/
        try:
            file_persona(nome).unlink()
        except OSError:
            pass
        scollega(nome)
        st["nome"] = None
        testo.delete("1.0", "end")
        testo.edit_modified(False)
        aggiorna_editor()
        riempi_lista(forza=True)
        aggiorna_info()

    def incolla(unisci: bool = False):
        if not st["nome"]:
            messagebox.showinfo("Incolla", "Scegli prima una persona.")
            return
        try:
            clip = root.clipboard_get()
        except tk.TclError:
            clip = ""
        nuove = righe_da_appunti(clip, unisci)
        if not nuove:
            messagebox.showinfo("Incolla", "Negli appunti non c'è niente da aggiungere.")
            return
        corrente = testo.get("1.0", "end-1c")
        if corrente and not corrente.endswith("\n"):
            testo.insert("end", "\n")
        testo.insert("end", "\n".join(nuove) + "\n")
        testo.see("end")
        msg.config(text=f"Aggiunte {len(nuove)} righe: ricorda di salvare.", fg=T.WARN)

    def scollega_chat():
        nome = st["nome"]
        if not nome:
            return
        n = scollega(nome)
        msg.config(text=f"Scollegate {n} chat da «{nome}»." if n else "Nessuna chat collegata.", fg=T.OK)
        aggiorna_info()

    def apri_cartella():
        try:
            if sys.platform == "win32":
                os.startfile(INVII_DIR)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(INVII_DIR)])
            else:
                subprocess.Popen(["xdg-open", str(INVII_DIR)])
        except Exception as e:
            messagebox.showerror("Errore", str(e))

    def tick():
        """Ogni 3 secondi: aggiorna conteggi e ricarica la lista se l'ha cambiata il bot."""
        battito()
        try:
            nome = st["nome"]
            if nome:
                p = file_persona(nome)
                if p.exists() and p.stat().st_mtime != st["mtime"]:
                    if dirty():
                        msg.config(text="⚠ Il bot ha modificato la lista: salvando potresti "
                                        "reinviare link già partiti.", fg=T.ERR)
                    else:
                        carica(nome)
                        msg.config(text="Lista aggiornata (il bot ha inviato qualcosa).", fg=T.OK)
                else:
                    aggiorna_info()
            riempi_lista()
        except Exception as e:
            _log_gui(f"tick: errore {e!r}")
        root.after(3000, tick)

    def battito():
        """Segnala al bot che la GUI è aperta (così /invia sa che può chiederle di salvare)."""
        try:
            GUI_VIVA.write_text(str(os.getpid()), encoding="utf-8")
        except OSError:
            pass

    def controlla_richiesta():
        """Il bot ha ricevuto /invia: salvo subito le modifiche non salvate, poi rispondo."""
        try:
            if RICHIESTA.exists():
                try:
                    chi = RICHIESTA.read_text(encoding="utf-8").strip()
                except OSError:
                    chi = ""
                if chi and chi == st["nome"] and dirty():
                    ok = salva(auto=True, motivo="Salvato prima dell'invio")
                    _log_gui(f"/invia: salvataggio richiesto per «{chi}»: " + ("fatto" if ok else
                             "NON fatto (la lista è stata cambiata dal bot nel frattempo)"))
                try:
                    RICHIESTA.unlink()
                except OSError:
                    pass
        except Exception as e:
            _log_gui(f"richiesta di salvataggio: errore {e!r}")
        root.after(300, controlla_richiesta)

    def autosalva():
        """Ogni AUTOSAVE_SEC secondi salva da sola le modifiche non salvate."""
        try:
            if dirty():
                salva(auto=True, motivo="Salvataggio automatico")
        except Exception as e:
            _log_gui(f"salvataggio automatico: errore {e!r}")
        root.after(int(AUTOSAVE_SEC * 1000), autosalva)

    def prepara_chiusura() -> bool:
        """Salvataggi, conferma se c'è un invio in corso, tolgo il segnale GUI. False = l'utente annulla."""
        if not chiedi_salvataggio() or not tg["chiedi_salvataggio"]():
            return False
        if tg["invio_in_corso"]():
            if not messagebox.askyesno(
                    "Invio in corso",
                    "È in corso un invio su Telegram: chiudendo si interrompe\n"
                    "(quello che è già partito è già stato tolto dalla lista).\n\nChiudere comunque?"):
                return False
            tg["ferma"]()
        try:
            GUI_VIVA.unlink()
        except OSError:
            pass
        return True

    def chiudi():
        if prepara_chiusura():
            root.destroy()

    def riavvia():
        """Usato dopo un aggiornamento da GitHub: chiude come chiudi() e rilancia la GUI."""
        if prepara_chiusura():
            root.destroy()
            riavvia_processo()

    barra_bot["imposta_riavvio"](riavvia)

    def aggiorna_progresso():
        """Ogni secondo: se il bot sta inviando la lista della persona selezionata, mostra la barra."""
        try:
            nome = st["nome"]
            d = leggi_progresso(nome) if nome else None
            if d:
                pannello.mostra(int(d["n"]), int(d["tot"]), float(d["t_inizio"]), bool(d.get("occupato")),
                                str(d.get("msg") or ""),
                                float(d["scadenza"]) if d.get("scadenza") and not d.get("fine") else None)
            else:
                pannello.nascondi()
        except Exception as e:
            _log_gui(f"avanzamento: errore {e!r}")
        root.after(1000, aggiorna_progresso)

    def salva_scheda_attiva(_=None):
        if nb.index(nb.select()) == 1:
            tg["salva"]()
        else:
            salva()

    for txt, cmd in (("Nuova persona", nuova), ("Elimina", elimina)):
        tk.Button(bt_sx, text=txt, command=cmd).pack(side="left", expand=True, fill="x", padx=1)
    for txt, cmd in (("Incolla dagli appunti", incolla), ("Incolla in 1 riga", lambda: incolla(True)),
                     ("Salva", salva), ("Scollega chat", scollega_chat), ("Apri cartella", apri_cartella)):
        b = tk.Button(bt_dx, text=txt, command=cmd)
        b.pack(side="left", padx=(0, 4))
        if cmd is not apri_cartella:
            bottoni_persona.append(b)

    lista.bind("<<ListboxSelect>>", su_selezione)
    root.bind("<Control-s>", salva_scheda_attiva)
    root.protocol("WM_DELETE_WINDOW", chiudi)
    riempi_lista(forza=True)
    aggiorna_editor()
    aggiorna_info()
    try:
        RICHIESTA.unlink()          # eventuale richiesta rimasta da una sessione precedente
    except OSError:
        pass
    battito()
    root.after(3000, tick)
    root.after(300, controlla_richiesta)
    root.after(1000, aggiorna_progresso)
    if AUTOSAVE_SEC > 0:
        root.after(int(AUTOSAVE_SEC * 1000), autosalva)
    root.mainloop()


if __name__ == "__main__":
    _log_gui("Avvio Branch (org_bot.py, GUI)")
    try:
        avvia_gui()
    except ImportError as e:
        _log_gui(f"Impossibile aprire la GUI: {e}")
        sys.exit(1)
    except Exception as e:
        _log_gui(f"GUI terminata per un errore: {e!r}")
        raise
    _log_gui("GUI chiusa")
