"""Diagnostica del modulo booru di Graves. Mettilo accanto a graves.py e lancia:

    python diag_booru.py hatsune_miku            (tag a piacere; default: hatsune_miku)
    python diag_booru.py hatsune_miku gelbooru   (per provare un altro sito: r34, gelbooru, danbooru, e621)

Non stampa mai le chiavi API. Non scarica niente: guarda solo cosa risponde il sito.
"""
import json
import os
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
os.chdir(AQUI)
sys.path.insert(0, str(AQUI))


def carica_env() -> dict:
    try:
        import bot_manager
        return dict(bot_manager.carica_env())
    except Exception:
        pass
    env = {}
    f = AQUI / "bots.env"
    if f.exists():
        for riga in f.read_text(encoding="utf-8", errors="replace").splitlines():
            riga = riga.strip()
            if riga and not riga.startswith("#") and "=" in riga:
                k, v = riga.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


os.environ.update(carica_env())
tag = sys.argv[1] if len(sys.argv) > 1 else "hatsune_miku"
sito = (sys.argv[2] if len(sys.argv) > 2 else "r34").lower()
UA = "Mozilla/5.0 (diag)"


def titolo(t):
    print("\n=== " + t)


titolo("1. Chiavi presenti in bots.env (solo si/no)")
for k in ("GRAVES_R34_KEY", "GRAVES_R34_USER", "GRAVES_GELBOORU_KEY", "GRAVES_GELBOORU_USER",
          "GRAVES_BOORU_SITO", "GRAVES_BOORU_BLACKLIST"):
    v = os.environ.get(k, "")
    print(f"  {k}: {'impostata' if v else 'VUOTA'}" + (f" = {v}" if k in ("GRAVES_BOORU_SITO", "GRAVES_BOORU_BLACKLIST") and v else ""))

titolo("1b. Forma delle credenziali (i valori non vengono mostrati)")
for nome, kk, uu in (("rule34", "GRAVES_R34_KEY", "GRAVES_R34_USER"), ("gelbooru", "GRAVES_GELBOORU_KEY", "GRAVES_GELBOORU_USER")):
    k0, u0 = os.environ.get(kk, ""), os.environ.get(uu, "")
    if not (k0 or u0):
        continue
    print(f"  {nome}: chiave {len(k0)} caratteri, user {len(u0)} caratteri")
    print(f"    user e' solo cifre: {'si' if u0.strip().isdigit() else 'NO (deve essere il NUMERO user_id, non il nome utente)'}")
    for nome_c, v in (("chiave", k0), ("user", u0)):
        problemi = [t for t, c in (("spazi", " "), ("'&'", "&"), ("'='", "="), ("virgolette", '"'), ("apici", "'")) if c in v]
        if problemi:
            print(f"    {nome_c} contiene: {', '.join(problemi)}  (graves.py ora ripulisce da solo '&api_key=..&user_id=..')")

if sito in ("r34", "rule34", "gelbooru", "gb"):
    gb = sito in ("gelbooru", "gb")
    host = "gelbooru.com" if gb else "api.rule34.xxx"
    k = os.environ.get("GRAVES_GELBOORU_KEY" if gb else "GRAVES_R34_KEY", "")
    u = os.environ.get("GRAVES_GELBOORU_USER" if gb else "GRAVES_R34_USER", "")

    try:
        import graves as _g
        k, u = _g._credenziali(k, u)      # stessa ripulitura che fa il bot
    except Exception:
        pass

    titolo(f"2. Raggiungibilità e certificato di {host}")
    try:
        ip = socket.gethostbyname(host)
        print(f"  DNS: {host} -> {ip}")
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=15) as s:
            with ctx.wrap_socket(s, server_hostname=host) as ss:
                emittente = dict(x[0] for x in ss.getpeercert()["issuer"])
                print(f"  certificato OK, emesso da: {emittente.get('organizationName') or emittente}")
    except ssl.SSLCertVerificationError as e:
        print(f"  CERTIFICATO NON VALIDO: {e.verify_message}")
        print("  -> qualcosa tra te e il sito presenta un certificato finto (DNS filtrante, VPN, antivirus,")
        print("     controllo parentale, blocco dell'operatore). Prova a cambiare DNS / spegnere VPN e antivirus HTTPS.")
    except Exception as e:
        print(f"  non raggiungibile: {e}")

    titolo(f"3. Risposta grezza di {host} (senza filtro, 3 risultati)")
    if not (k and u):
        print("  salto: chiave o user mancanti in bots.env")
    else:
        p = {"page": "dapi", "s": "post", "q": "index", "json": "1", "limit": 3, "pid": 0,
             "tags": tag, "api_key": k, "user_id": u}
        url = f"https://{host}/index.php?" + urllib.parse.urlencode(p)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=25) as r:
                corpo = r.read().decode("utf-8", "replace")
                print(f"  HTTP {r.status}, {len(corpo)} caratteri")
        except urllib.error.HTTPError as e:
            corpo = e.read().decode("utf-8", "replace")
            print(f"  HTTP {e.code}")
        except Exception as e:
            corpo = None
            print(f"  errore di rete: {e}")
        if corpo is None:
            pass
        elif not corpo.strip():
            print("  corpo VUOTO: il sito non trova niente per questo tag (o la chiave non e' valida)")
        else:
            print("  primi 400 caratteri:", corpo[:400].replace(k, "***").replace(u, "***"))
            try:
                dati = json.loads(corpo)
                if isinstance(dati, str):
                    print("  -> il sito risponde con un MESSAGGIO D'ERRORE (sopra): vedi la forma delle credenziali al punto 1b")
                lista = dati.get("post") if isinstance(dati, dict) else dati
                for i in (lista if isinstance(lista, list) else [])[:3]:
                    if not isinstance(i, dict):
                        continue
                    print(f"   - id {i.get('id')}  file_url={str(i.get('file_url'))[:80]}")
                    print(f"     sample_url={str(i.get('sample_url'))[:80]}")
                    print(f"     tags={str(i.get('tags'))[:100]}")
            except json.JSONDecodeError:
                print("  (non e' JSON: e' un messaggio di errore del sito)")

titolo("4. Ricerca completa con graves.booru_cerca (come fa il bot)")
try:
    import graves
    graves.log = lambda m: print("  LOG", m)
    graves.STATO = AQUI / "diag_uso.json"      # il contatore giornaliero di prova non tocca quello vero
    rich = graves.parse_booru(tag, n=3, sito=sito)
    risultati = graves.booru_cerca(rich)
    for p in risultati[:5]:
        print(f"  OK {p.etichetta()}  file={p.url[:70]}  anteprima={'si' if p.anteprima else 'no'}")
except Exception as e:
    print(f"  ERRORE: {e}")
(AQUI / "diag_uso.json").unlink(missing_ok=True)
print("\nFatto. Se mi mandi questo output (non contiene le chiavi) vedo subito dov'e' il problema.")
