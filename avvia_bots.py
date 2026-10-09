#!/usr/bin/env python3
"""
avvia_bots.py - gestione dei bot da terminale, senza Branch (pensato per Termux/Android e server Linux).

Uso:
  python avvia_bots.py start      aggiorna da GitHub, avvia i bot che non girano e resta in esecuzione
                                  controllando GitHub ogni 30 minuti (Ctrl+C per uscire: i bot RESTANO accesi)
  python avvia_bots.py avvia      come start ma esce subito dopo l'avvio (nessun controllo periodico)
  python avvia_bots.py stop       ferma i bot
  python avvia_bots.py stato      mostra quali bot girano
  python avvia_bots.py update     controlla GitHub e aggiorna ora
  opzione:  --ogni MINUTI         intervallo del controllo periodico di "start" (default 30, 0 = mai)

Legge bots.env accanto agli script, come Branch (vedi bot_manager.py).
"""
import argparse
import sys
import time

import bot_manager as BM


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def stampa_stato(g: "BM.GestoreBot"):
    for nome, acceso in g.stato().items():
        log(f"{BM.MODULI[nome][0]}: {'ACCESO' if acceso else 'spento'}"
            + (f"  ({g.errori[nome]})" if nome in g.errori else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description="Gestione dei bot da terminale.")
    ap.add_argument("comando", choices=["start", "avvia", "stop", "stato", "update"])
    ap.add_argument("--ogni", type=float, default=30, help="minuti tra i controlli di GitHub (start)")
    a = ap.parse_args()

    g = BM.GestoreBot(log=log)

    if a.comando == "stato":
        stampa_stato(g)
        return 0
    if a.comando == "stop":
        g.ferma_tutti()
        stampa_stato(g)
        return 0
    if a.comando == "update":
        log(g.aggiorna())
        return 0

    log(g.aggiorna())
    g.avvia_mancanti()
    stampa_stato(g)
    if a.comando == "avvia":
        return 0

    log("In esecuzione. Ctrl+C per uscire (i bot restano accesi).")
    try:
        while True:
            if a.ogni > 0:
                time.sleep(a.ogni * 60)
                g.aggiorna()
            else:
                time.sleep(3600)
            g.avvia_mancanti()       # se un bot si è chiuso, lo riaccende
    except KeyboardInterrupt:
        log("Uscito: i bot restano accesi (per spegnerli: python avvia_bots.py stop).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
