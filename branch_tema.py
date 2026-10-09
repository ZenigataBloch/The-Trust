"""
branch_tema.py - aspetto grafico della GUI di Branch (org_bot.py).

Stile: noir ispirato a 100 Bullets (nero quasi puro, rosso sangue come unico accento,
bianco sporco per il testo) con la colonna sinistra alla Discord: avatar tondo + nome.

Immagini (cartella "assets" accanto a questo file):
  assets/sfondo.jpg   illustrazione usata come banner in alto, dietro la lista delle persone
                      e nella schermata «scegli una persona» (sempre scurita, così il testo resta leggibile)
  assets/icona.png    icona della finestra (e icona.ico per Windows)
Se mancano, o manca Pillow, la GUI usa i colori piatti di sempre.

Deve stare accanto a org_bot.py. Pillow (pip install Pillow) serve per immagini e avatar tondi.
"""
import os
import sys
import urllib.request
from pathlib import Path

try:
    import tkinter as tk
except ImportError:          # server senza Tk: le costanti restano utilizzabili
    tk = None

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk
    PIL_OK = True
    _LANCZOS = getattr(Image, "Resampling", Image).LANCZOS
except ImportError:
    PIL_OK = False

NOME_APP = "Branch"
ASSET_DIR = Path(__file__).resolve().parent / "assets"
SFONDO = ASSET_DIR / "sfondo.jpg"
ICONA_PNG = ASSET_DIR / "icona.png"
ICONA_ICO = ASSET_DIR / "icona.ico"

# ---------- palette ----------
BG = "#0a0a0a"          # fondo finestra
PANEL = "#121212"       # colonne laterali
PANEL2 = "#1c1c1c"      # riga selezionata, pulsanti
INPUT = "#0f0f0f"       # editor di testo
BORDER = "#2a2a2a"
FG = "#e8e4da"          # bianco sporco (carta vecchia)
MUTED = "#8a867c"
ROSSO = "#c1121f"       # unico accento
ROSSO_SCURO = "#7a0c14"
OK = "#8fbf8f"
WARN = "#e0a030"
ERR = "#ff5252"
INFO = "#d9d4c7"

# ---------- font (init() sceglie un condensato se disponibile) ----------
F_TITOLO = ("Segoe UI", 11, "bold")
F_LOGO = ("Segoe UI", 20, "bold")
F_NOME = ("Segoe UI", 10, "bold")
F_PICCOLO = ("Segoe UI", 8)


def init(root):
    """Da chiamare subito dopo tk.Tk(), prima di creare i widget."""
    global F_TITOLO, F_LOGO, F_NOME
    from tkinter import font as tkfont, ttk

    famiglie = set(tkfont.families(root))
    cond = next((f for f in ("Bahnschrift SemiBold Condensed", "Bahnschrift", "Impact",
                             "Oswald", "Arial Narrow") if f in famiglie), None)
    if cond:
        peso = "" if cond == "Impact" else "bold"
        F_TITOLO = (cond, 13, peso) if peso else (cond, 13)
        F_LOGO = (cond, 26, peso) if peso else (cond, 26)
        F_NOME = (cond, 11, peso) if peso else (cond, 11)

    root.configure(bg=BG)
    base = ("Segoe UI", 10)
    for chiave, valore in (
            ("*Background", BG), ("*Foreground", FG), ("*Font", base),
            ("*Label.Background", BG), ("*Label.Foreground", FG),
            ("*Frame.Background", BG), ("*Toplevel.Background", BG),
            ("*Button.Background", PANEL2), ("*Button.Foreground", FG),
            ("*Button.ActiveBackground", ROSSO), ("*Button.ActiveForeground", "#ffffff"),
            ("*Button.Relief", "flat"), ("*Button.BorderWidth", 0),
            ("*Button.PadX", 10), ("*Button.PadY", 3),
            ("*Button.DisabledForeground", "#555555"),
            ("*Checkbutton.Background", BG), ("*Checkbutton.Foreground", FG),
            ("*Checkbutton.ActiveBackground", BG), ("*Checkbutton.ActiveForeground", FG),
            ("*Checkbutton.SelectColor", PANEL2),
            ("*Text.Background", INPUT), ("*Text.Foreground", FG),
            ("*Text.InsertBackground", ROSSO), ("*Text.SelectBackground", ROSSO_SCURO),
            ("*Text.SelectForeground", "#ffffff"), ("*Text.Relief", "flat"),
            ("*Text.HighlightThickness", 1), ("*Text.HighlightBackground", BORDER),
            ("*Text.HighlightColor", ROSSO),
            ("*Scrollbar.Background", PANEL2), ("*Scrollbar.TroughColor", BG)):
        root.option_add(chiave, valore)

    stile = ttk.Style(root)
    try:
        stile.theme_use("clam")
    except Exception:
        pass
    stile.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(8, 6, 0, 0))
    stile.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(16, 6),
                    borderwidth=0, font=F_NOME)
    stile.map("TNotebook.Tab",
              background=[("selected", ROSSO), ("active", PANEL2)],
              foreground=[("selected", "#ffffff"), ("active", FG)])
    stile.configure("TProgressbar", troughcolor=PANEL, background=ROSSO, bordercolor=BG,
                    lightcolor=ROSSO, darkcolor=ROSSO_SCURO, thickness=8)
    imposta_icona(root)


# ---------- icona della finestra ----------
def imposta_icona(root):
    """Icona della finestra e della barra delle applicazioni (assets/icona.png / icona.ico)."""
    try:
        if sys.platform == "win32":
            try:   # senza un AppUserModelID la barra delle applicazioni mostra l'icona di Python
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("branch.sendbot.gui")
            except Exception:
                pass
            if ICONA_ICO.is_file():
                root.iconbitmap(default=str(ICONA_ICO))
                return
        if ICONA_PNG.is_file():
            foto = tk.PhotoImage(file=str(ICONA_PNG))
            root.iconphoto(True, foto)
            root._icona_ref = foto       # Tk non tiene da solo il riferimento
    except Exception:
        pass


# ---------- immagini di sfondo ----------
_cache_img: dict = {}


def _sorgente():
    """L'illustrazione originale (None se manca il file o Pillow)."""
    if not PIL_OK or not SFONDO.is_file():
        return None
    try:
        chiave = ("src", SFONDO.stat().st_mtime)
        if chiave not in _cache_img:
            _cache_img[chiave] = Image.open(SFONDO).convert("RGB")
        return _cache_img[chiave]
    except Exception:
        return None


def foto_sfondo(w: int, h: int, buio: float = 0.75, fuoco_y: float = 0.5, sfuma_sinistra: float = 0.0):
    """PhotoImage dell'illustrazione, ritagliata a w x h (come «cover»), scurita verso il nero.
    buio: 0 = originale, 1 = nero. fuoco_y: 0 = parte alta dell'immagine, 1 = parte bassa.
    sfuma_sinistra: quanto scurire in più il lato sinistro (per far leggere il titolo). None senza immagine."""
    src = _sorgente()
    if src is None or w < 2 or h < 2:
        return None
    chiave = (w, h, round(buio, 2), round(fuoco_y, 2), round(sfuma_sinistra, 2))
    if chiave in _cache_img:
        return _cache_img[chiave]
    img = ImageOps.fit(src, (w, h), _LANCZOS, centering=(0.5, fuoco_y))
    nero = Image.new("RGB", (w, h), BG)
    img = Image.blend(img, nero, max(0.0, min(1.0, buio)))
    if sfuma_sinistra > 0:
        # maschera: 255 a sinistra (tutto scuro) -> 0 a destra (resta com'è)
        grad = Image.linear_gradient("L").rotate(90).resize((w, h))          # sinistra nero -> destra bianco
        mask = ImageOps.invert(grad).point(lambda v: int(v * sfuma_sinistra))
        img = Image.composite(nero, img, mask)
    foto = ImageTk.PhotoImage(img)
    if len(_cache_img) > 40:
        _cache_img.clear()
    _cache_img[chiave] = foto
    return foto


def _logo_piccolo(altezza: int):
    if not PIL_OK or not ICONA_PNG.is_file():
        return None
    try:
        im = Image.open(ICONA_PNG).convert("RGBA").resize((altezza, altezza), _LANCZOS)
        return ImageTk.PhotoImage(im)
    except Exception:
        return None


if tk:
    class Banner(tk.Canvas):
        """Intestazione: illustrazione scurita, logo e nome dell'app. Si adatta alla larghezza."""
        ALTEZZA = 92

        def __init__(self, parent, sottotitolo="//  coda di invio"):
            super().__init__(parent, height=self.ALTEZZA, bg=BG, highlightthickness=0)
            self._sotto = sottotitolo
            self._foto = None
            self._logo = _logo_piccolo(56)
            self._ultima = 0
            self.bind("<Configure>", self._disegna)

        def _disegna(self, e=None):
            w = max(self.winfo_width(), 100)
            self.delete("all")
            self._foto = foto_sfondo(w, self.ALTEZZA, buio=0.5, fuoco_y=0.18, sfuma_sinistra=0.85)
            if self._foto:
                self.create_image(0, 0, image=self._foto, anchor="nw")
            x = 16
            if self._logo:
                self.create_image(x, self.ALTEZZA / 2, image=self._logo, anchor="w")
                x += 56 + 14
            self.create_text(x + 1, self.ALTEZZA / 2 - 6, text=NOME_APP.upper(), anchor="w",
                             fill="#000000", font=F_LOGO)           # ombra
            self.create_text(x, self.ALTEZZA / 2 - 7, text=NOME_APP.upper(), anchor="w",
                             fill=ROSSO, font=F_LOGO)
            self.create_text(x + 2, self.ALTEZZA / 2 + 20, text=self._sotto, anchor="w",
                             fill=MUTED, font=F_PICCOLO)

    class SfondoVuoto(tk.Canvas):
        """Schermata «scegli una persona»: illustrazione molto scurita con il messaggio al centro."""

        def __init__(self, parent, testo):
            super().__init__(parent, bg=PANEL, highlightthickness=0)
            self._testo = testo
            self._foto = None
            self.bind("<Configure>", self._disegna)

        def _disegna(self, e=None):
            w, h = max(self.winfo_width(), 10), max(self.winfo_height(), 10)
            self.delete("all")
            self._foto = foto_sfondo(w, h, buio=0.82, fuoco_y=0.5)
            if self._foto:
                self.create_image(0, 0, image=self._foto, anchor="nw")
            self.create_text(w / 2, h / 2, text=self._testo, fill=FG, justify="center",
                             font=("Segoe UI", 12))


# ---------- avatar ----------
_COLORI_AVATAR = ("#8c0d16", "#3a3a3a", "#5a1a1f", "#4a4a44", "#6b2a2a", "#2f2f35", "#7a5a2a")


def colore_nome(nome: str) -> str:
    h = sum(ord(c) * (i + 1) for i, c in enumerate(nome or "?"))
    return _COLORI_AVATAR[h % len(_COLORI_AVATAR)]


def iniziale(nome: str) -> str:
    for ch in nome or "":
        if ch.isalnum():
            return ch.upper()
    return "?"


def _font_pil(px: int):
    for nome in ("arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(nome, px)
        except OSError:
            continue
    try:
        return ImageFont.load_default(px)
    except TypeError:
        return ImageFont.load_default()


def avatar_photo(nome: str, path, size: int):
    """PhotoImage tonda (foto ritagliata a cerchio, o iniziale su fondo colorato). None senza Pillow."""
    if not PIL_OK:
        return None
    S = size * 4      # si disegna grande e si riduce: il bordo del cerchio resta liscio
    img = None
    if path and Path(path).is_file():
        try:
            img = ImageOps.fit(Image.open(path).convert("RGBA"), (S, S), _LANCZOS)
        except Exception:
            img = None
    if img is None:
        img = Image.new("RGBA", (S, S), colore_nome(nome))
        d = ImageDraw.Draw(img)
        try:
            d.text((S / 2, S / 2), iniziale(nome), fill=FG, font=_font_pil(int(S * 0.5)), anchor="mm")
        except Exception:
            d.text((S * 0.35, S * 0.25), iniziale(nome), fill=FG, font=_font_pil(int(S * 0.5)))
    maschera = Image.new("L", (S, S), 0)
    ImageDraw.Draw(maschera).ellipse((0, 0, S - 1, S - 1), fill=255)
    img.putalpha(maschera)
    return ImageTk.PhotoImage(img.resize((size, size), _LANCZOS))


def disegna_avatar(canvas, cx, cy, size, nome, path, store: list, tag=None):
    """Disegna l'avatar sul Canvas. `store` tiene vivi i PhotoImage (Tk non li conserva da solo)."""
    foto = avatar_photo(nome, path, size)
    if foto is not None:
        store.append(foto)
        canvas.create_image(cx, cy, image=foto, tags=tag)
        return
    r = size / 2
    canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=colore_nome(nome), outline="", tags=tag)
    canvas.create_text(cx, cy, text=iniziale(nome), fill=FG, font=F_NOME, tags=tag)


def scarica(url: str, dest: Path, timeout: float = 10, max_byte: int = 3_000_000):
    """Scarica un'immagine in dest (scrittura atomica). L'URL non finisce mai nell'errore:
    per Telegram contiene il token."""
    dest = Path(dest)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": f"{NOME_APP}/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            dati = r.read(max_byte + 1)
    except Exception as e:
        raise RuntimeError(f"download non riuscito ({e.__class__.__name__})") from None
    if not dati or len(dati) > max_byte:
        raise RuntimeError("immagine vuota o troppo grande")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_bytes(dati)
    os.replace(tmp, dest)


# ---------- lista alla Discord: avatar tondo + nome + sottotitolo ----------
if tk:
    class ListaAvatar(tk.Canvas):
        """Sostituisce la Listbox delle persone. Espone gli stessi metodi usati da org_bot
        (selection_clear, selection_set, see, curselection, evento <<ListboxSelect>>).
        Dietro le righe c'è l'illustrazione, molto scurita."""
        RIGA = 54
        AV = 36

        def __init__(self, parent, avatar_fn, width=250, **kw):
            super().__init__(parent, width=width, bg=PANEL, highlightthickness=0,
                             yscrollincrement=18, **kw)
            self._avatar_fn = avatar_fn      # nome -> Path dell'immagine (o None)
            self._voci = []                  # [(nome, sottotitolo)]
            self._sel = None                 # indice selezionato
            self._store = []
            self._sfondo = None
            self._firma = ()
            self._sel_disegnata = None       # selezione mostrata nell'ultimo ridisegno
            self.bind("<Button-1>", self._clic)
            self.bind("<Configure>", lambda e: self._disegna())
            self.bind("<MouseWheel>", lambda e: self.yview_scroll(int(-e.delta / 120) * 3, "units"))
            self.bind("<Button-4>", lambda e: self.yview_scroll(-3, "units"))
            self.bind("<Button-5>", lambda e: self.yview_scroll(3, "units"))

        def _mtimes(self):
            out = []
            for nome, _ in self._voci:
                p = self._avatar_fn(nome)
                try:
                    out.append(p.stat().st_mtime if p else 0)
                except OSError:
                    out.append(0)
            return tuple(out)

        def imposta(self, nomi, etichette):
            """Nomi + etichette «nome  (N link)»: il nome va in grassetto, il resto sotto."""
            corrente = self._voci[self._sel][0] if self._sel is not None and self._sel < len(self._voci) else None
            self._voci = []
            for n, e in zip(nomi, etichette):
                sub = e[len(n):].strip().strip("()").strip() if e.startswith(n) else ""
                self._voci.append((n, sub or "lista vuota"))
            nomi_l = [n for n, _ in self._voci]
            self._sel = nomi_l.index(corrente) if corrente in nomi_l else None
            self._firma = self._mtimes()
            self._disegna()

        def controlla(self):
            """Ridisegna se è arrivato un avatar nuovo/cambiato o se la selezione è cambiata."""
            f = self._mtimes()
            if f != self._firma or self._sel != self._sel_disegnata:
                self._firma = f
                self._disegna()

        def _disegna(self):
            self.delete("all")
            self._store = []
            self._sel_disegnata = self._sel
            w = max(self.winfo_width(), int(self["width"]))
            h = max(self.winfo_height(), 10)
            self._sfondo = foto_sfondo(w, h, buio=0.86, fuoco_y=0.55)
            if self._sfondo:
                self.create_image(0, 0, image=self._sfondo, anchor="nw", tags="sfondo")
            for i, (nome, sub) in enumerate(self._voci):
                y0 = i * self.RIGA
                if i == self._sel:
                    self.create_rectangle(0, y0, w, y0 + self.RIGA, fill=PANEL2, outline="")
                    self.create_rectangle(0, y0, 3, y0 + self.RIGA, fill=ROSSO, outline="")
                cy = y0 + self.RIGA / 2
                disegna_avatar(self, 16 + self.AV / 2, cy, self.AV, nome, self._avatar_fn(nome), self._store)
                x = 16 + self.AV + 10
                self.create_text(x, cy - 8, text=nome, anchor="w", fill=FG, font=F_NOME)
                self.create_text(x, cy + 10, text=sub, anchor="w", fill=MUTED, font=F_PICCOLO)
                self.create_line(0, y0 + self.RIGA - 1, w, y0 + self.RIGA - 1, fill=BORDER)
            self.configure(scrollregion=(0, 0, w, max(h, len(self._voci) * self.RIGA)))

        def _clic(self, e):
            i = int(self.canvasy(e.y) // self.RIGA)
            if 0 <= i < len(self._voci):
                self._sel = i
                self._disegna()
                self.event_generate("<<ListboxSelect>>")

        # --- interfaccia compatibile con tk.Listbox ---
        def curselection(self):
            return (self._sel,) if self._sel is not None else ()

        def selection_clear(self, *_):
            self._sel = None          # il ridisegno lo fa controlla(): niente sfarfallio ogni 3 secondi

        def selection_set(self, i, *_):
            if 0 <= i < len(self._voci):
                self._sel = i

        def see(self, i):
            totale = max(1, len(self._voci) * self.RIGA)
            y, h, alto = i * self.RIGA, self.winfo_height(), self.canvasy(0)
            if y < alto:
                self.yview_moveto(y / totale)
            elif y + self.RIGA > alto + h:
                self.yview_moveto(max(0, (y + self.RIGA - h) / totale))


# ---------- lista dei canali Telegram: spunta + avatar + nome, con lo sfondo dietro ----------
if tk:
    class ListaCanali(tk.Canvas):
        """Elenco di canali/gruppi disegnato sul Canvas (i widget Tk non possono essere trasparenti,
        quindi per vedere l'illustrazione dietro le righe serve disegnarle qui).
        Clic sulla riga = spunta/togli; clic sulla × = rimuovi."""
        RIGA = 54
        AV = 34

        def __init__(self, parent, width=270, **kw):
            super().__init__(parent, width=width, bg=PANEL, highlightthickness=0,
                             yscrollincrement=18, **kw)
            self._canali = []
            self._nome_fn = lambda c: str(c.get("nome") or c.get("id"))
            self._avatar_fn = lambda c: None
            self._on_toggle = lambda c, v: None
            self._on_remove = lambda c: None
            self._store = []
            self._sfondo = None
            self.bind("<Button-1>", self._clic)
            self.bind("<Configure>", lambda e: self._disegna())
            self.bind("<MouseWheel>", lambda e: self.yview_scroll(int(-e.delta / 120) * 3, "units"))
            self.bind("<Button-4>", lambda e: self.yview_scroll(-3, "units"))
            self.bind("<Button-5>", lambda e: self.yview_scroll(3, "units"))

        def imposta(self, canali, nome_fn, avatar_fn, on_toggle, on_remove):
            self._canali = canali
            self._nome_fn, self._avatar_fn = nome_fn, avatar_fn
            self._on_toggle, self._on_remove = on_toggle, on_remove
            self._disegna()

        def _disegna(self):
            self.delete("all")
            self._store = []
            w = max(self.winfo_width(), int(self["width"]))
            h = max(self.winfo_height(), 10)
            self._sfondo = foto_sfondo(w, h, buio=0.86, fuoco_y=0.55)
            if self._sfondo:
                self.create_image(0, 0, image=self._sfondo, anchor="nw")
            if not self._canali:
                self.create_text(16, 20, anchor="nw", fill=MUTED, font=F_PICCOLO,
                                 text="Nessun canale.\nPremi «Aggiungi ID…».")
            for i, c in enumerate(self._canali):
                y0 = i * self.RIGA
                cy = y0 + self.RIGA / 2
                attivo = bool(c.get("attivo"))
                if attivo:
                    self.create_rectangle(0, y0, 3, y0 + self.RIGA, fill=ROSSO, outline="")
                # casella di spunta
                self.create_rectangle(12, cy - 8, 28, cy + 8, outline=ROSSO if attivo else MUTED,
                                      fill=ROSSO if attivo else "", width=2)
                if attivo:
                    self.create_text(20, cy, text="✓", fill="#ffffff", font=("Segoe UI", 9, "bold"))
                disegna_avatar(self, 28 + 10 + self.AV / 2, cy, self.AV, self._nome_fn(c),
                               self._avatar_fn(c), self._store)
                x = 28 + 10 + self.AV + 10
                nome = self._nome_fn(c)
                if len(nome) > 21:
                    nome = nome[:20] + "…"
                self.create_text(x, cy - 8, text=nome, anchor="w", fill=FG if attivo else INFO, font=F_NOME)
                sub = str(c.get("id")) + (f"  ·  {c['tipo']}" if c.get("tipo") else "")
                self.create_text(x, cy + 10, text=sub, anchor="w", fill=MUTED, font=F_PICCOLO)
                self.create_text(w - 16, cy, text="×", fill=ROSSO, font=("Segoe UI", 14, "bold"))
                self.create_line(0, y0 + self.RIGA - 1, w, y0 + self.RIGA - 1, fill=BORDER)
            self.configure(scrollregion=(0, 0, w, max(h, len(self._canali) * self.RIGA)))

        def _clic(self, e):
            i = int(self.canvasy(e.y) // self.RIGA)
            if not (0 <= i < len(self._canali)):
                return
            c = self._canali[i]
            w = max(self.winfo_width(), int(self["width"]))
            if e.x >= w - 34:
                self._on_remove(c)
            else:
                self._on_toggle(c, not c.get("attivo"))
