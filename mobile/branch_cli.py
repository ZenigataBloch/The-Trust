import sys
import bot_manager as BM

g = BM.GestoreBot()
cmd = sys.argv[1] if len(sys.argv) > 1 else "stato"
if cmd == "avvia":
    g.avvia_mancanti()
elif cmd == "ferma":
    g.ferma_tutti()
st = g.stato()
print(" | ".join(
    f"{BM.MODULI[n][0]}: {'acceso' if on else 'spento'}"
    + (f" ({g.errori[n]})" if n in g.errori else "")
    for n, on in st.items()))