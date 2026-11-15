"""Icona di Branch nell'area di notifica (in basso a destra in Windows).

Richiede: pip install pystray pillow
Se le librerie mancano, avvia() restituisce (None, None) e la GUI si comporta come prima.

Eventi nella coda (letti dalla GUI Tk con root.after, perché Tk non è thread-safe):
  "mostra"  -> click sull'icona o voce «Apri Branch»
  "esci"    -> voce «Esci»
"""
import queue
import threading
from pathlib import Path

try:
    import pystray
    from PIL import Image
except ImportError:
    pystray = None


def avvia(base: Path, titolo: str = "Branch"):
    if pystray is None:
        return None, None
    coda = queue.Queue()
    try:
        immagine = Image.open(base / "assets" / "icona.png")
    except Exception:
        immagine = Image.new("RGB", (64, 64), (30, 30, 30))
    menu = pystray.Menu(
        pystray.MenuItem("Apri Branch", lambda icona, voce: coda.put("mostra"), default=True),
        pystray.MenuItem("Esci", lambda icona, voce: coda.put("esci")),
    )
    icona = pystray.Icon("Branch", immagine, titolo, menu)
    threading.Thread(target=icona.run, daemon=True).start()
    return coda, icona.stop
