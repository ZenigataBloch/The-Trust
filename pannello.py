#!/usr/bin/env python3
"""
pannello.py - Branch come webapp locale (pensato per Termux/Android).

Uso:  python pannello.py     poi apri  http://localhost:8080  in Chrome.

Riusa bot_manager.py (avvio/arresto dei bot, aggiornamento da GitHub) e org_bot.py (liste, canali,
invio Telegram): la logica è quella di Branch, qui cambia solo l'interfaccia.
  - avvio del server -> se nessun bot gira crea il flag di arresto: i bot partono solo quando apri l'app
  - apri la pagina  -> accende i bot che non girano (e toglie il flag di arresto)
  - chiudi la pagina -> i bot restano accesi
  - scheda Cookie    -> incolla i cookie dagli appunti (JSON o cookies.txt), li controlla e aggiorna cookies.txt
  - pulsante ⟳       -> git pull e, se serve, riavvio di bot e pannello
  - clic sul led     -> spegne i bot (crea bots_fermi.flag, lo stesso di avvia_bots.py stop)
"""
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path, PurePath
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import bot_manager as BM

# BOT_TOKEN, cookie ecc. da bots.env: vanno nell'ambiente PRIMA di importare org_bot
_env = BM.carica_env()
_env.pop("BOT_LOG_FILE", None)
os.environ.update(_env)

try:
    import org_bot as O
except ImportError as e:
    raise SystemExit(f"Non riesco a importare org_bot.py: {e}\n"
                     "Se manca tkinter o Pillow dimmelo: branch_tema.py va reso importabile senza.")

PORTA = 8080
HOSTS = {f"localhost:{PORTA}", f"127.0.0.1:{PORTA}"}   # blocca il DNS rebinding
FLAG = BM.BASE / "bots_fermi.flag"
MANUALE = BM.BASE / "bots_spenti_a_mano.flag"   # li hai spenti tu dal led: l'apertura/refresh della pagina NON li riaccende
HTML = BM.BASE / "pannello.html"
OGNI_MIN = 30
log = O._log_gui
g = BM.GestoreBot(log=log)
inv = {}                       # stato dell'invio Telegram in corso o appena finito
inv_lock = threading.Lock()


# ------------------------------------------------------------ bot (led)
def bg(fn):
    if g.occupato:
        return
    g.occupato = True

    def run():
        try:
            fn()
        except Exception as e:
            log(f"bot: errore {e!r}")
        finally:
            g.occupato = False
    threading.Thread(target=run, daemon=True).start()


def r_bots(_):
    out = {}
    for n, a in g.stato().items():
        pronto = bool(a) and g.pronto(n)
        err = g.errori.get(n)
        if a and not pronto and not err and g.secondi_da_avvio(n) > 90:
            err = "avviato ma non ancora collegato a Discord: controlla il log"
        out[n] = {"nome": BM.MODULI[n][0], "acceso": bool(a), "pronto": pronto, "errore": err}
    return 200, {"occupato": g.occupato, "bot": out}


def r_bots_start(_):
    """Accensione ESPLICITA (clic sul led): toglie anche lo spegnimento manuale."""
    FLAG.unlink(missing_ok=True)
    MANUALE.unlink(missing_ok=True)
    bg(g.avvia_mancanti)
    return 200, {}


def r_bots_apri(_):
    """Chiamata dalla pagina al caricamento/refresh: accende i bot SOLO se non li hai spenti a mano."""
    if MANUALE.exists():
        return 200, {"manuale": True}
    FLAG.unlink(missing_ok=True)
    bg(g.avvia_mancanti)
    return 200, {}


def r_bots_stop(_):
    ora = time.strftime("%Y-%m-%d %H:%M:%S")
    for f in (FLAG, MANUALE):
        try:
            f.write_text(ora, encoding="utf-8")
        except OSError:
            pass
    bg(g.ferma_tutti)
    return 200, {}


def ciclo():
    """Ogni 30 minuti: aggiorna da GitHub e riaccende i bot caduti (salvo flag di arresto)."""
    while True:
        time.sleep(OGNI_MIN * 60)
        if FLAG.exists() or g.occupato:
            continue
        try:
            g.aggiorna()
            g.avvia_mancanti()
        except Exception as e:
            log(f"ciclo: errore {e!r}")


# ------------------------------------------------------------ liste (comune)
def salva_lista(path, nome_backup, b, lock=None):
    mt = float(b.get("mtime") or 0)
    if path.exists() and not b.get("forza") and abs(path.stat().st_mtime - mt) > 1e-6:
        return 409, {"errore": "lista cambiata"}
    testo = str(b.get("testo", ""))
    if testo and not testo.endswith("\n"):
        testo += "\n"
    with (lock or contextlib.nullcontext()):
        O.fai_backup(nome_backup, src=path)
        O.scrivi_atomico(path, testo)
    link, testi, ign = O.riassumi(testo)
    return 200, {"mtime": path.stat().st_mtime, "link": link, "testi": testi, "ignorate": ign}


def r_righe(b):
    return 200, {"righe": O.righe_da_appunti(str(b.get("testo", "")), bool(b.get("unisci")))}


def progresso(p):
    if not p:
        return None
    n, tot = int(p["n"]), int(p["tot"])
    r = O.stima_rimasto(n, tot, float(p["t_inizio"]))
    return {"n": n, "tot": tot, "fine": bool(p.get("fine")),
            "rimasto": O.formatta_durata(r) if r is not None else None}


# ------------------------------------------------------------ Discord: persone
def persona_ok(n):
    return isinstance(n, str) and O.nome_valido(n) and O.file_persona(n).exists()


def r_persone(_):
    out = []
    for n in O.nomi_persone():
        try:
            link, _t = O.conta(O.leggi_coda(n))
        except Exception:
            link = 0
        out.append({"nome": n, "link": link})
    return 200, {"persone": out}


def r_persona(q):
    n = q.get("nome", "")
    if not persona_ok(n):
        return 404, {"errore": "Persona non trovata"}
    p = O.file_persona(n)
    try:
        link, testi = O.conta(O.leggi_coda(n))
    except Exception:
        link = testi = 0
    return 200, {"nome": n, "testo": p.read_text(encoding="utf-8-sig"), "mtime": p.stat().st_mtime,
                 "link": link, "testi": testi,
                 "chat": sum(1 for v in O.carica_chat().values() if v == n),
                 "inviati": O.conta_cronologia(n), "progresso": progresso(O.leggi_progresso(n))}


def r_p_salva(b):
    n = b.get("nome", "")
    if not persona_ok(n):
        return 404, {"errore": "Persona non trovata"}
    return salva_lista(O.file_persona(n), n, b)


def r_p_nuova(b):
    n = str(b.get("nome", "")).strip()
    if not O.nome_valido(n):
        return 400, {"errore": 'Nome non valido: evita / \\ : * ? " < > |'}
    p = O.file_persona(n)
    if not p.exists():
        O.INVII_DIR.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")
    return 200, {"nome": n}


def r_p_elimina(b):
    n = b.get("nome", "")
    if not persona_ok(n):
        return 404, {"errore": "Persona non trovata"}
    O.fai_backup(n, forza=True)          # resta recuperabile in invii/backup/
    O.file_persona(n).unlink(missing_ok=True)
    O.scollega(n)
    return 200, {}


def r_p_scollega(b):
    n = b.get("nome", "")
    if not persona_ok(n):
        return 404, {"errore": "Persona non trovata"}
    return 200, {"n": O.scollega(n)}


# ------------------------------------------------------------ Telegram
def invio_stato():
    with inv_lock:
        if not inv:
            return None
        d = {k: v for k, v in inv.items() if k != "stop"}
    if d.get("attivo") and d.get("tot"):
        r = O.stima_rimasto(d["n"], d["tot"], d["t0"])
        d["rimasto"] = O.formatta_durata(r) if r is not None else None
    return d


def r_tg(_):
    O.TG_DIR.mkdir(parents=True, exist_ok=True)
    if not O.TG_LISTA.exists():
        O.TG_LISTA.write_text("", encoding="utf-8")
    try:
        link, testi = O.conta(O.leggi_coda(O.TG_NOME, O.TG_LISTA))
    except Exception:
        link = testi = 0
    return 200, {
        "token": bool(os.environ.get("BOT_TOKEN")),
        "canali": [{"id": c["id"], "tipo": c["tipo"], "attivo": c["attivo"],
                    "nome": O.semplifica_nome(c["nome"], f"Canale {c['id']}")} for c in O.carica_canali()],
        "testo": O.TG_LISTA.read_text(encoding="utf-8-sig"), "mtime": O.TG_LISTA.stat().st_mtime,
        "link": link, "testi": testi, "inviati": O.conta_cronologia(O.TG_NOME, O.TG_DIR),
        "invio": invio_stato()}


def r_t_salva(b):
    O.TG_DIR.mkdir(parents=True, exist_ok=True)
    return salva_lista(O.TG_LISTA, O.TG_NOME, b, O._TG_LOCK)


def r_t_toggle(b):
    canali = O.carica_canali()
    for c in canali:
        if c["id"] == b.get("id"):
            c["attivo"] = bool(b.get("attivo"))
    O.salva_canali(canali)
    return 200, {}


def r_t_rimuovi(b):
    O.salva_canali([c for c in O.carica_canali() if c["id"] != b.get("id")])
    return 200, {}


def _aggiorna_canali(destinazioni, nuovi_attivi=False):
    token = os.environ.get("BOT_TOKEN", "")
    canali = O.carica_canali()
    per_id = {c["id"]: c for c in canali}
    ok, errori = 0, []
    for d in destinazioni:
        try:
            ch = O.info_chat(token, d)
        except Exception as e:
            errori.append(f"{d}: {str(e)[:80]}")
            continue
        c = per_id.get(ch["id"])
        if c:
            c["nome"], c["tipo"] = ch["titolo"], ch["tipo"]
        else:
            c = {"id": ch["id"], "nome": ch["titolo"], "tipo": ch["tipo"], "attivo": nuovi_attivi}
            canali.append(c)
            per_id[c["id"]] = c
        ok += 1
    O.salva_canali(canali)
    return ok, errori


def r_t_aggiungi(b):
    if not os.environ.get("BOT_TOKEN"):
        return 400, {"errore": "BOT_TOKEN non impostato (mettilo in bots.env)"}
    validi, scartati = [], []
    for x in (x for x in re.split(r"[\s,;]+", str(b.get("testo", "")).strip()) if x):
        n = O.normalizza_destinazione(x)
        (validi if n else scartati).append(n or x)
    if not validi:
        return 400, {"errore": "Nessun ID, @username o link t.me riconosciuto."}
    ok, errori = _aggiorna_canali(list(dict.fromkeys(validi)))
    return 200, {"aggiunti": ok, "errori": errori, "scartati": scartati}


def r_t_nomi(_):
    if not os.environ.get("BOT_TOKEN"):
        return 400, {"errore": "BOT_TOKEN non impostato (mettilo in bots.env)"}
    ok, errori = _aggiorna_canali([str(c["id"]) for c in O.carica_canali()])
    return 200, {"aggiunti": ok, "errori": errori, "scartati": []}


def _riporta(d):
    with inv_lock:
        if d.get("fine"):
            inv.update(attivo=False, occupato=False, msg="",
                       esito={"falliti": d.get("falliti") or [], "fermato": bool(d.get("fermato")),
                              "errore": d.get("errore")})
        else:
            for k in ("msg", "n", "tot", "occupato"):
                if k in d:
                    inv[k] = d[k]


def r_t_invia(_):
    with inv_lock:
        if inv.get("attivo"):
            return 409, {"errore": "Invio già in corso"}
    attivi = [c for c in O.carica_canali() if c["attivo"]]
    if not attivi:
        return 400, {"errore": "Spunta almeno un canale."}
    if not os.environ.get("BOT_TOKEN"):
        return 400, {"errore": "BOT_TOKEN non impostato (mettilo in bots.env)"}
    try:
        link, testi = O.conta(O.leggi_coda(O.TG_NOME, O.TG_LISTA))
    except Exception:
        link = testi = 0
    if not (link or testi):
        return 400, {"errore": "Niente in coda."}
    stop = threading.Event()
    with inv_lock:
        inv.clear()
        inv.update(attivo=True, t0=time.time(), stop=stop, msg="Avvio dell'invio…", n=0, tot=0,
                   occupato=True, esito=None)
    threading.Thread(target=O.lavora_telegram, args=(attivi, stop, _riporta), daemon=True).start()
    return 200, {}


def r_t_ferma(_):
    with inv_lock:
        if inv.get("attivo"):
            inv["stop"].set()
            inv["msg"] = "Mi fermo dopo l'invio in corso…"
    return 200, {}


# ------------------------------------------------------------ cookie
# Siti tenuti (gli altri cookie dell'export vengono scartati). Modificabili con COOKIE_DOMINI in bots.env.
COOKIE_DOMINI = [d.strip().lower().lstrip(".") for d in
                 os.environ.get("COOKIE_DOMINI", "tiktok.com,instagram.com,reddit.com,x.com").split(",") if d.strip()]
# cookie che provano il login: se mancano, probabilmente non eri loggato quando hai esportato
COOKIE_LOGIN = {"tiktok.com": ("sessionid", "sid_tt"), "instagram.com": ("sessionid",),
                "reddit.com": ("reddit_session", "token_v2"), "x.com": ("auth_token",)}
HTTPONLY = "#HttpOnly_"
HEADER_COOKIE = "# Netscape HTTP Cookie File"
_HOST_RE = re.compile(r"[A-Za-z0-9._\-]+")


def cookie_file() -> Path:
    f = os.environ.get("COOKIES_FILE")
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
    O.scrivi_atomico(out, HEADER_COOKIE + "\n" + "\n".join(tenute + res["righe"]) + "\n")
    try:
        os.chmod(out, 0o600)                           # i cookie sono sessioni: solo tu
    except OSError:
        pass
    log("cookie: aggiornati " + ", ".join(f"{s} ({d['n']})" for s, d in res["siti"].items()))
    return res


def r_cookie(_):
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
    return 200, {"esiste": out.exists(), "file": out.name, "siti": siti,
                 "mtime": out.stat().st_mtime if out.exists() else 0}


def r_c_analizza(b):
    res = cookie_analizza(str(b.get("testo", "")))
    res.pop("righe")
    return 200, res


def r_c_applica(b):
    res = cookie_applica(str(b.get("testo", "")))
    if res["errore"]:
        return 400, {"errore": res["errore"]}
    res.pop("righe")
    res["riepilogo"] = ("Aggiornati: " + ", ".join(f"{s.split('.')[0]} ({d['n']})" for s, d in res["siti"].items())
                        + f". Salvato in {cookie_file().name} (copia precedente in .bak): "
                          "i bot lo rileggono al prossimo download.")
    return 200, res


# ------------------------------------------------------------ git pull
FILE_SERVER = {"pannello.py", "org_bot.py", "bot_manager.py", "bot_log.py", "sendbot_tema.py"}
FILE_BOT = {"telegram_bot.py", "discord_bot.py", "org_bot.py", "bot_log.py"}


def _git(*args, timeout=90):
    r = subprocess.run(["git", *args], cwd=BM.BASE, capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    return r.returncode, (r.stdout + r.stderr).strip()


def r_git_pull(_):
    try:
        c, _o = _git("rev-parse", "--is-inside-work-tree")
        if c:
            return 400, {"errore": "Questa cartella non è una repo git."}
        _c, prima = _git("rev-parse", "HEAD")
        c, out = _git("pull", "--ff-only")
        if c:
            return 200, {"ok": False, "output": out[-500:]}
        _c, dopo = _git("rev-parse", "HEAD")
        cambiati = []
        if dopo != prima:
            _c, d = _git("diff", "--name-only", prima, dopo)
            cambiati = d.splitlines()
    except FileNotFoundError:
        return 400, {"errore": "git non è installato (pkg install git)."}
    except subprocess.TimeoutExpired:
        return 200, {"ok": False, "output": "Timeout: GitHub non risponde (rete?)."}
    nomi = {PurePath(x).name for x in cambiati}
    log(f"git pull: {len(cambiati)} file cambiati")
    return 200, {"ok": True, "cambiati": cambiati, "server": bool(nomi & FILE_SERVER), "bot": bool(nomi & FILE_BOT)}


def _riavvia(server: bool, bot: bool):
    g.occupato = True
    try:
        if bot and not FLAG.exists() and any(g.stato().values()):   # riaccendo solo se giravano
            g.ferma_tutti()
            g.avvia_mancanti()
    except Exception as e:
        log(f"riavvio bot: errore {e!r}")
    finally:
        g.occupato = False
    if server:
        time.sleep(1)                                   # lascio finire la risposta HTTP
        log("Riavvio del pannello per applicare l'aggiornamento")
        os.execv(sys.executable, [sys.executable] + sys.argv)


def r_git_riavvia(b):
    if inv.get("attivo") or any((d := O.leggi_progresso(n)) and not d.get("fine") for n in O.nomi_persone()):
        return 409, {"errore": "C'è un invio in corso: riavvia quando è finito."}
    if g.occupato:
        return 409, {"errore": "I bot sono occupati, riprova tra un attimo."}
    threading.Thread(target=_riavvia, args=(bool(b.get("server")), bool(b.get("bot"))), daemon=True).start()
    return 200, {}


# ------------------------------------------------------------ log
LOG_RE = re.compile(r"[\w.\-]+\.log(\.\d+)?$")


def _file_log():
    """File di log nella cartella dei bot (org_bot.log, discord_bot.log, pannello.log...), i più recenti prima."""
    try:
        fs = [p for p in BM.BASE.iterdir() if p.is_file() and LOG_RE.fullmatch(p.name)]
    except OSError:
        return []
    return sorted(fs, key=lambda p: p.stat().st_mtime, reverse=True)


def r_log(q):
    fs = _file_log()
    elenco = [{"nome": p.name, "kb": round(p.stat().st_size / 1024, 1), "mtime": p.stat().st_mtime} for p in fs]
    nome = q.get("file") or (elenco[0]["nome"] if elenco else "")
    if not nome:
        return 200, {"file": [], "nome": "", "testo": ""}
    p = next((x for x in fs if x.name == nome), None)      # solo i file dell'elenco: niente percorsi liberi
    if p is None:
        return 404, {"errore": "Log non trovato"}
    try:
        kb = max(1, min(int(q.get("kb") or 60), 500))
    except ValueError:
        kb = 60
    size = p.stat().st_size
    with open(p, "rb") as f:
        f.seek(max(0, size - kb * 1024))
        dati = f.read()
    testo = dati.decode("utf-8", errors="replace")
    if size > kb * 1024 and "\n" in testo:
        testo = testo.split("\n", 1)[1]                    # scarto la prima riga, tagliata a metà
    return 200, {"file": elenco, "nome": nome, "testo": testo, "kb": round(size / 1024, 1)}


# ------------------------------------------------------------ HTTP
MANIFEST = json.dumps({
    "name": "Branch", "short_name": "Branch", "start_url": "/", "scope": "/", "display": "standalone",
    "background_color": "#000000", "theme_color": "#1b1718",
    "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
              {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"}]})
# service worker minimo: Chrome lo vuole per considerare la pagina installabile (non memorizza nulla)
SW = "self.addEventListener('fetch',()=>{});"
ICONE = {"/icon-192.png": BM.BASE / "icon-192.png", "/icon-512.png": BM.BASE / "icon-512.png"}

GET = {"/api/bots": r_bots, "/api/persone": r_persone, "/api/persona": r_persona, "/api/tg": r_tg, "/api/log": r_log, "/api/cookie": r_cookie}
POST = {"/api/bots/start": r_bots_start, "/api/bots/apri": r_bots_apri, "/api/bots/stop": r_bots_stop, "/api/righe": r_righe,
        "/api/persona/salva": r_p_salva, "/api/persona/nuova": r_p_nuova, "/api/persona/elimina": r_p_elimina,
        "/api/persona/scollega": r_p_scollega, "/api/tg/salva": r_t_salva, "/api/tg/toggle": r_t_toggle,
        "/api/tg/rimuovi": r_t_rimuovi, "/api/tg/aggiungi": r_t_aggiungi, "/api/tg/nomi": r_t_nomi,
        "/api/tg/invia": r_t_invia, "/api/tg/ferma": r_t_ferma,
        "/api/cookie/analizza": r_c_analizza, "/api/cookie/applica": r_c_applica,
        "/api/git/pull": r_git_pull, "/api/git/riavvia": r_git_riavvia}


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj, ctype="application/json"):
        if isinstance(obj, bytes):
            data = obj
        elif isinstance(obj, str):
            data = obj.encode()
        else:
            data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.headers.get("Host") not in HOSTS:
            return self._send(403, {})
        u = urlparse(self.path)
        if u.path in GET:
            try:
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                return self._send(*GET[u.path](q))
            except Exception as e:
                log(f"{u.path}: errore {e!r}")
                return self._send(500, {"errore": str(e)[:150]})
        if u.path == "/manifest.json":
            return self._send(200, MANIFEST, "application/manifest+json")
        if u.path in ICONE and ICONE[u.path].exists():
            return self._send(200, ICONE[u.path].read_bytes(), "image/png")
        if u.path == "/sw.js":
            return self._send(200, SW, "text/javascript")
        self._send(200, HTML.read_bytes(), "text/html; charset=utf-8")

    def do_POST(self):
        if self.headers.get("Host") not in HOSTS or self.headers.get("X-Panel") != "1":
            return self._send(403, {})
        if self.path not in POST:
            return self._send(404, {})
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 4_000_000)
            b = json.loads(self.rfile.read(n) or b"{}")
            self._send(*POST[self.path](b if isinstance(b, dict) else {}))
        except Exception as e:
            log(f"{self.path}: errore {e!r}")
            self._send(500, {"errore": str(e)[:150]})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORTA), H)
    except OSError:
        raise SystemExit(f"Porta {PORTA} occupata: il pannello è probabilmente già in esecuzione.")
    if not FLAG.exists() and not any(g.stato().values()):
        # il server parte a bot spenti: li accende l'apertura dell'app (e il ciclo non li tocca prima)
        FLAG.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
    threading.Thread(target=ciclo, daemon=True).start()
    log(f"Branch su http://localhost:{PORTA}  (Ctrl+C per uscire: i bot restano accesi)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
