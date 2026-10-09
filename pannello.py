#!/usr/bin/env python3
"""
pannello.py - Branch come webapp locale (pensato per Termux/Android).

Uso:  python pannello.py     poi apri  http://localhost:8080  in Chrome.

Riusa bot_manager.py (avvio/arresto dei bot, aggiornamento da GitHub) e org_bot.py (liste, canali,
invio Telegram): la logica è quella di Branch, qui cambia solo l'interfaccia.
  - apri la pagina  -> accende i bot che non girano (e toglie il flag di arresto)
  - chiudi la pagina -> i bot restano accesi
  - clic sul led     -> spegne i bot (crea bots_fermi.flag, lo stesso di avvia_bots.py stop)
"""
import contextlib
import json
import os
import re
import threading
import time
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
    return 200, {"occupato": g.occupato,
                 "bot": {n: {"nome": BM.MODULI[n][0], "acceso": bool(a), "errore": g.errori.get(n)}
                         for n, a in g.stato().items()}}


def r_bots_start(_):
    FLAG.unlink(missing_ok=True)
    bg(g.avvia_mancanti)
    return 200, {}


def r_bots_stop(_):
    try:
        FLAG.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
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


# ------------------------------------------------------------ HTTP
MANIFEST = json.dumps({
    "name": "Branch", "short_name": "Branch", "start_url": "/", "display": "standalone",
    "background_color": "#1b1718", "theme_color": "#1b1718",
    "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml"}]})
ICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" rx="22" '
        'fill="#1b1718"/><circle cx="50" cy="50" r="24" fill="#2ecc71"/></svg>')

GET = {"/api/bots": r_bots, "/api/persone": r_persone, "/api/persona": r_persona, "/api/tg": r_tg}
POST = {"/api/bots/start": r_bots_start, "/api/bots/stop": r_bots_stop, "/api/righe": r_righe,
        "/api/persona/salva": r_p_salva, "/api/persona/nuova": r_p_nuova, "/api/persona/elimina": r_p_elimina,
        "/api/persona/scollega": r_p_scollega, "/api/tg/salva": r_t_salva, "/api/tg/toggle": r_t_toggle,
        "/api/tg/rimuovi": r_t_rimuovi, "/api/tg/aggiungi": r_t_aggiungi, "/api/tg/nomi": r_t_nomi,
        "/api/tg/invia": r_t_invia, "/api/tg/ferma": r_t_ferma}


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
        if u.path == "/icon.svg":
            return self._send(200, ICON, "image/svg+xml")
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
    threading.Thread(target=ciclo, daemon=True).start()
    log(f"Branch su http://localhost:{PORTA}  (Ctrl+C per uscire: i bot restano accesi)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
