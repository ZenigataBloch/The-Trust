#!/usr/bin/env python3
"""
Aggiorna cookies.txt per i bot a partire da un export di Chrome/Firefox
(Cookie-Editor, "Get cookies.txt LOCALLY"...). Accetta formato Netscape o JSON.

Per ogni sito presente nell'export (tiktok, instagram, reddit) sostituisce i vecchi
cookie di QUEL sito in cookies.txt e lascia intatti gli altri: puoi quindi esportare
un social alla volta e rilanciare lo script ogni volta.

Uso:
  python aggiorna_cookies.py --clipboard      legge dagli appunti (Termux:API)
  python aggiorna_cookies.py                  legge tutti.txt (qui o in Download)
  python aggiorna_cookies.py percorso/file    legge quel file
  opzioni: --out percorso/cookies.txt   --da-zero   --elimina

Il vecchio cookies.txt viene salvato come cookies.txt.bak.
I bot rileggono il file a ogni download: non serve riavviarli.
L'ultima riga stampata è sempre un riepilogo di una riga (usata per il toast).
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

# siti da tenere: aggiungi qui altri domini se servono
DOMINI = ["tiktok.com", "instagram.com", "reddit.com", "x.com"]

HEADER = "# Netscape HTTP Cookie File"
NOME_INPUT = "tutti.txt"


def esci(msg: str, codice: int = 1):
    print(msg)
    sys.exit(codice)


def trova_input() -> Path | None:
    home = Path.home()
    candidati = [
        Path.cwd() / NOME_INPUT,
        Path(__file__).resolve().parent / NOME_INPUT,
        home / "Downloads" / NOME_INPUT,                          # Windows
        home / "Download" / NOME_INPUT,
        home / "storage" / "shared" / "Download" / NOME_INPUT,    # Termux
        home / "storage" / "downloads" / NOME_INPUT,
    ]
    return next((p for p in candidati if p.is_file()), None)


def dominio_di(riga: str) -> str | None:
    """Dominio di una riga cookie (anche con prefisso #HttpOnly_). None se non è un cookie."""
    campi = riga.rstrip("\r\n").split("\t")
    if len(campi) < 7:
        return None
    d = campi[0]
    if d.startswith("#HttpOnly_"):
        d = d[len("#HttpOnly_"):]
    elif d.startswith("#"):
        return None
    return d.lstrip(".").lower()


def sito_di(dominio: str | None) -> str | None:
    if not dominio:
        return None
    for s in DOMINI:
        if dominio == s or dominio.endswith("." + s):
            return s
    return None


def da_json(testo: str) -> list[str]:
    """Converte l'export JSON di Cookie-Editor in righe Netscape."""
    dati = json.loads(testo)
    if isinstance(dati, dict):
        dati = dati.get("cookies", [dati])
    righe = []
    for c in dati:
        try:
            dom = str(c["domain"])
            host_only = c.get("hostOnly", not dom.startswith("."))
            if not host_only and not dom.startswith("."):
                dom = "." + dom
            scad = 0 if c.get("session") else int(c.get("expirationDate") or c.get("expires") or 0)
            campi = [
                ("#HttpOnly_" if c.get("httpOnly") else "") + dom,
                "FALSE" if host_only else "TRUE",
                c.get("path", "/"),
                "TRUE" if c.get("secure") else "FALSE",
                str(scad),
                str(c["name"]),
                str(c.get("value", "")),
            ]
            righe.append("\t".join(campi))
        except (KeyError, TypeError, ValueError):
            continue
    return righe


def estrai_righe(testo: str) -> list[str]:
    """Righe cookie (Netscape) dei soli siti in DOMINI, da testo Netscape o JSON."""
    testo = testo.lstrip("\ufeff")
    if testo.lstrip()[:1] in ("[", "{"):
        try:
            righe = da_json(testo)
        except json.JSONDecodeError:
            esci("Il testo sembra JSON ma non è valido: riesporta e riprova.")
    else:
        righe = testo.splitlines()
    return [r.rstrip("\r\n") for r in righe if sito_di(dominio_di(r))]


def leggi_appunti() -> str:
    try:
        r = subprocess.run(["termux-clipboard-get"], capture_output=True, text=True, timeout=15)
    except FileNotFoundError:
        esci("ERRORE: manca termux-api (pkg install termux-api + app Termux:API).")
    except subprocess.TimeoutExpired:
        esci("ERRORE: gli appunti non rispondono (app Termux:API installata?).")
    if r.returncode != 0 or not r.stdout.strip():
        esci("ERRORE: appunti vuoti. Esporta i cookie (Copia) e riprova.")
    return r.stdout


def main() -> int:
    ap = argparse.ArgumentParser(description="Aggiorna cookies.txt per i bot.")
    ap.add_argument("input", nargs="?", help=f"file esportato (default: cerca {NOME_INPUT})")
    ap.add_argument("--clipboard", action="store_true", help="leggi dagli appunti (Termux:API)")
    ap.add_argument("--out", help="file di uscita (default: cookies.txt accanto allo script)")
    ap.add_argument("--da-zero", action="store_true", help="ignora il vecchio cookies.txt invece di unire")
    ap.add_argument("--elimina", action="store_true", help="cancella il file di input alla fine")
    a = ap.parse_args()

    src = None
    if a.clipboard:
        testo = leggi_appunti()
    else:
        src = Path(a.input).expanduser() if a.input else trova_input()
        if not src or not src.is_file():
            esci(f"ERRORE: non trovo {NOME_INPUT} (indica il percorso del file).")
        testo = src.read_text(encoding="utf-8-sig", errors="replace")

    nuove = estrai_righe(testo)
    if not nuove:
        esci(f"ERRORE: nessun cookie di {', '.join(s.split('.')[0] for s in DOMINI)} "
             "nel testo. Hai esportato dal sito giusto, dopo il login?")

    out = Path(a.out).expanduser() if a.out else Path(__file__).resolve().parent / "cookies.txt"
    vecchie = []
    if out.exists():
        shutil.copy2(out, out.with_name(out.name + ".bak"))
        if not a.da_zero:
            vecchie = [r.rstrip("\r\n") for r in out.read_text(encoding="utf-8-sig").splitlines()
                       if dominio_di(r)]

    siti_nuovi = {sito_di(dominio_di(r)) for r in nuove}
    tenute = [r for r in vecchie if sito_di(dominio_di(r)) not in siti_nuovi]
    finale = tenute + nuove

    with open(out, "w", encoding="utf-8", newline="\n") as f:   # fine riga Unix
        f.write(HEADER + "\n" + "\n".join(finale) + "\n")

    ora = time.time()
    conteggio = {s: 0 for s in DOMINI}
    scaduti = {s: 0 for s in DOMINI}
    for r in finale:
        s = sito_di(dominio_di(r))
        if s not in conteggio:
            continue
        conteggio[s] += 1
        try:
            scad = int(r.split("\t")[4])
            if 0 < scad < ora:
                scaduti[s] += 1
        except (ValueError, IndexError):
            pass

    if a.clipboard:   # i cookie sono sensibili: svuoto gli appunti
        try:
            subprocess.run(["termux-clipboard-set"], input="", text=True, timeout=10)
        except Exception:
            pass
    if a.elimina and src:
        src.unlink()

    print(f"Scritto {out}")
    print("Aggiornati: " + ", ".join(sorted(s.split(".")[0] for s in siti_nuovi)))
    mancano = [s.split(".")[0] for s in DOMINI if conteggio[s] == 0]
    vecchi = [s.split(".")[0] for s in DOMINI if conteggio[s] and scaduti[s] == conteggio[s]]
    riepilogo = "OK: " + ", ".join(f"{s.split('.')[0]} {conteggio[s]}" for s in DOMINI)
    if mancano:
        riepilogo += f" | mancano: {', '.join(mancano)}"
    if vecchi:
        riepilogo += f" | scaduti: {', '.join(vecchi)}"
    print(riepilogo)   # ultima riga: riepilogo
    return 0


if __name__ == "__main__":
    sys.exit(main())
