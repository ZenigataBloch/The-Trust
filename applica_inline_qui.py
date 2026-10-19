"""
applica_inline_qui.py - /url e /ricerca via @bot anche in chat dove il bot NON c'è.

Va applicata DOPO applica_inline_comandi.py.
Uso (nella cartella dei bot):   python applica_inline_qui.py
Crea telegram_bot.py.bak, poi modifica telegram_bot.py. Si può rilanciare senza danni.

PASSO OBBLIGATORIO su @BotFather:  /setinlinefeedback -> scegli il bot -> Enabled (100%).
Senza, il bot non viene avvisato di quale risultato hai toccato e il segnaposto resta com'è.

Come funziona
-------------
Un bot che non è nella chat non può scrivere né modificare niente lì. Può però modificare i
messaggi inviati con la sua inline mode: il risultato inline è un segnaposto (immagine grigia
con il pulsante «Scarico…»); quando lo tocchi il messaggio parte da te, il bot scarica e poi
SOSTITUISCE il segnaposto col file vero (editMessageMedia). Per farlo Telegram vuole un file_id:
il bot carica il file nella tua chat privata, ne prende il file_id, modifica il messaggio e
cancella la copia privata.

    @nomedelbot https://link            -> 2 risultati: «Scarica e pubblica» (serve il bot nella chat)
                                           e «Scarica qui» (funziona ovunque)
    @nomedelbot ricerca gatti           -> idem, «Cerca qui»

Limiti di Telegram, non aggirabili:
  - un messaggio inline contiene UN solo file: se il link ne ha di più parte il primo (il resto
    è segnalato in privato). Per /ricerca parte la prima immagine che si scarica (-n è ignorato);
  - immagini oltre 10 MB non possono essere sostituite al segnaposto; i video oltre 50 MB sono
    compressi come al solito;
  - il messaggio resta "via @bot" e, finché scarica, si vede il segnaposto grigio;
  - se qualcosa va storto, il segnaposto diventa «⚠️ Non riuscito» (lo cancelli tu) e il motivo
    arriva in privato;
  - /booru NON è incluso: ha il flusso anteprima + scelta in privato, che qui non ha senso.

Alla prima accensione il bot manda UNA volta alla tua chat privata l'immagine grigia del
segnaposto (e la cancella); il suo file_id resta in inline_segnaposto.json accanto allo script.
Serve aver premuto Start sul bot in privato.
"""
import shutil
import sys
from pathlib import Path

DEST = Path(sys.argv[1] if len(sys.argv) > 1 else "telegram_bot.py")

# ---------------------------------------------------------------- 1. risultato /url
U_OLD = '''        input_message_content=InputTextMessageContent(text),
    )
    await q.answer([result], cache_time=0, is_personal=True)
'''
U_NEW = '''        input_message_content=InputTextMessageContent(text),
    )
    risultati = [result]
    qui = _risultato_qui("dl", "📎 Scarica qui (il bot non serve nella chat)", urls[0][:80])
    if qui:
        risultati.append(qui)
    await q.answer(risultati, cache_time=0, is_personal=True)
'''

# ---------------------------------------------------------------- 2. risultato /ricerca
C_OLD = '''        input_message_content=InputTextMessageContent(f"{nome} {args}"),
    )
    await q.answer([result], cache_time=0, is_personal=True)
'''
C_NEW = '''        input_message_content=InputTextMessageContent(f"{nome} {args}"),
    )
    risultati = [result]
    if nome == "ricerca":
        qui = _risultato_qui("rc", titolo.replace("Cerca immagini", "Cerca qui, senza bot nella chat", 1),
                             "1 immagine · funziona anche dove il bot non c'è")
        if qui:
            risultati.append(qui)
    await q.answer(risultati, cache_time=0, is_personal=True)
'''

# ---------------------------------------------------------------- 3. segnaposto all'avvio
P_OLD = '''    log(f"Bot avviato: @{app.bot.username}. In attesa di link…")
'''
P_NEW = '''    log(f"Bot avviato: @{app.bot.username}. In attesa di link…")
    await prepara_segnaposto(app.bot)
'''

# ---------------------------------------------------------------- 4. registrazione handler
H_OLD = '''        group=1,
    )
'''
H_NEW = '''        group=1,
    )
    app.add_handler(ChosenInlineResultHandler(on_inline_scelto))
    app.add_handler(CallbackQueryHandler(on_segnaposto, pattern=r"^ph$"))
'''

# ---------------------------------------------------------------- 5. nuovo codice (prima di on_error)
ANCORA_ERR = "async def on_error(update, ctx: ContextTypes.DEFAULT_TYPE):"
NUOVO_CODICE = '''# ---------- /url e /ricerca via @bot anche dove il bot NON è nella chat ----------
# Il risultato inline è un segnaposto (immagine grigia + pulsante) che, una volta toccato, il bot
# sostituisce col file vero con editMessageMedia. Richiede /setinlinefeedback = Enabled su @BotFather.
import struct
import zlib

from telegram import InlineQueryResultCachedPhoto, InputMediaAnimation
from telegram.ext import ChosenInlineResultHandler

_PLACEHOLDER_ID = None   # file_id dell'immagine grigia (None = funzione non disponibile)
_SEGNAPOSTO_FILE = Path(__file__).resolve().with_name("inline_segnaposto.json")


def _png_grigio(w: int = 480, h: int = 270, rgb=(28, 28, 28)) -> bytes:
    """PNG a tinta unita, senza librerie esterne."""
    def blocco(tipo: bytes, dati: bytes) -> bytes:
        return struct.pack(">I", len(dati)) + tipo + dati + struct.pack(">I", zlib.crc32(tipo + dati) & 0xFFFFFFFF)
    raw = (b"\\x00" + bytes(rgb) * w) * h
    return (b"\\x89PNG\\r\\n\\x1a\\n" + blocco(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + blocco(b"IDAT", zlib.compress(raw, 9)) + blocco(b"IEND", b""))


async def prepara_segnaposto(bot):
    """Ricava (e ricorda) il file_id dell'immagine grigia: la manda una volta sola a OWNER e la cancella."""
    global _PLACEHOLDER_ID
    try:
        d = json.loads(_SEGNAPOSTO_FILE.read_text(encoding="utf-8"))
        if d.get("bot") == bot.id and d.get("file_id"):
            _PLACEHOLDER_ID = d["file_id"]
            log("Inline «qui»: segnaposto pronto (ricordati di /setinlinefeedback su @BotFather)")
            return
    except Exception:
        pass
    try:
        m = await bot.send_photo(OWNER, _png_grigio(), caption="Segnaposto per l'inline (si cancella da solo).")
        _PLACEHOLDER_ID = m.photo[-1].file_id
        _SEGNAPOSTO_FILE.write_text(json.dumps({"bot": bot.id, "file_id": _PLACEHOLDER_ID}), encoding="utf-8")
        try:
            await m.delete()
        except Exception:
            pass
        log("Inline «qui»: segnaposto creato (ricordati di /setinlinefeedback su @BotFather)")
    except Exception as e:
        log(f"Inline «qui» NON attivo: non riesco a creare il segnaposto ({e}). Apri il bot in privato e premi Start.")


def _risultato_qui(tipo: str, titolo: str, descrizione: str):
    """Risultato inline modificabile (segnaposto + pulsante), o None se il segnaposto non c'è."""
    if not _PLACEHOLDER_ID:
        return None
    return InlineQueryResultCachedPhoto(
        id=f"{tipo}:{uuid.uuid4().hex[:12]}",
        photo_file_id=_PLACEHOLDER_ID,
        title=titolo[:100],
        description=descrizione[:100],
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏳ Scarico…", callback_data="ph")]]),
    )


async def on_segnaposto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q:
        await q.answer("Sto scaricando…")


async def _media_inline(bot, path: Path):
    """Carica il file nella chat privata per ottenere un file_id e restituisce (InputMedia, messaggio privato).
    Un messaggio inline può essere modificato solo con un file_id (o un URL), non con un upload."""
    ext, size = path.suffix.lower(), path.stat().st_size
    gif = ext in ANIM_EXT
    if gif and size > MAX_FILE:
        nuovo = await asyncio.to_thread(gif_to_mp4, path, int(MAX_FILE * 0.9))
        if nuovo == path:
            raise ValueError(f"{path.name} supera i 50 MB")
        path, ext, size = nuovo, nuovo.suffix.lower(), nuovo.stat().st_size
    if ext in VIDEO_EXT and size > MAX_FILE:
        path = await asyncio.to_thread(compress_video, path, limite_bytes=MAX_FILE)
        ext, size = path.suffix.lower(), path.stat().st_size
        if size > MAX_FILE:
            raise ValueError(f"{path.name} è ancora sopra i 50 MB")
    log(f"    inline: preparo {path.name} ({mb(size)})")
    with open(path, "rb") as f:
        if gif:
            m = await bot.send_animation(OWNER, f)
            fid = (m.animation or m.document).file_id
            return InputMediaAnimation(media=fid), m
        if ext in VIDEO_EXT:
            m = await bot.send_video(OWNER, f, supports_streaming=True)
            if m.video:
                return InputMediaVideo(media=m.video.file_id, supports_streaming=True), m
            return InputMediaAnimation(media=m.animation.file_id), m
        if ext in IMAGE_EXT and size <= MAX_PHOTO:
            m = await bot.send_photo(OWNER, f)
            return InputMediaPhoto(media=m.photo[-1].file_id), m
    raise ValueError(f"{path.name}: formato o dimensione non adatti a un messaggio inline (immagini max 10 MB)")


async def on_inline_scelto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Hai toccato «Scarica qui» / «Cerca qui»: scarico e sostituisco il segnaposto col file."""
    r = update.chosen_inline_result
    if not r or r.from_user.id != OWNER or not r.inline_message_id:
        return
    tipo = r.result_id.split(":")[0]
    if tipo not in ("dl", "rc"):
        return
    iid = r.inline_message_id
    t0 = time.time()
    url, extra, privato = "", 0, None
    try:
        with tempfile.TemporaryDirectory() as d:
            if tipo == "dl":
                urls = URL_RE.findall(r.query or "")
                if not urls:
                    raise ValueError("nessun link nella richiesta")
                url = urls[0]
                log(f"Inline «qui»: {url}")
                files = await asyncio.to_thread(download, url, d)
                if not files:
                    raise ValueError("niente da scaricare")
                files = [await rendi_riproducibile(p) for p in files]
                extra = (len(files) - 1) + (len(urls) - 1)
            else:
                cmd = _inline_comando(r.query or "")
                if graves is None or not cmd:
                    raise ValueError("Graves non è caricato: manca graves.py accanto a telegram_bot.py")
                query, _ = graves.parse_richiesta(cmd[1])
                log("Inline «qui»: ricerca immagini")
                files = await asyncio.to_thread(graves.cerca_e_scarica, query, d, 1)
            media, privato = await _media_inline(ctx.bot, files[0])
            await ctx.bot.edit_message_media(media=media, inline_message_id=iid)
            log(f"  segnaposto sostituito in {time.time() - t0:.0f}s")
        if extra:
            await ctx.bot.send_message(OWNER, f"ℹ️ Un messaggio inline contiene un solo file: ne ho inviato 1, "
                                              f"gli altri {extra} non sono partiti.")
    except Exception as e:
        log(f"  ERRORE inline «qui»: {e}")
        try:
            await ctx.bot.edit_message_caption(inline_message_id=iid, caption="⚠️ Non riuscito (dettagli in privato)")
        except Exception as e2:
            log(f"  segnaposto non aggiornato: {e2}")
        testo = f"🍪 {e}" if isinstance(e, CookieError) else f"⚠️ {e}"
        try:
            await ctx.bot.send_message(OWNER, (testo + (f"\\n{url}" if url else ""))[:4000])
        except Exception as e3:
            log(f"  non riesco a scrivere in privato: {e3}")
    finally:
        if privato is not None:   # la copia privata serviva solo per il file_id
            try:
                await privato.delete()
            except Exception:
                pass
    for avviso in prendi_avvisi():
        try:
            await ctx.bot.send_message(OWNER, "⚠️ " + avviso)
        except Exception:
            pass


'''

MODIFICHE = (
    ("risultato /url", U_OLD, U_NEW),
    ("risultato /ricerca", C_OLD, C_NEW),
    ("post_init", P_OLD, P_NEW),
    ("registrazione handler", H_OLD, H_NEW),
)


def main():
    if not DEST.is_file():
        sys.exit(f"{DEST} non trovato: lancia lo script nella cartella dei bot.")
    grezzo = DEST.read_bytes().decode("utf-8")
    crlf = "\r\n" in grezzo
    s = grezzo.replace("\r\n", "\n")

    if "on_inline_scelto" in s:
        print("Già applicato: niente da fare.")
        return
    if "handle_comando_inline" not in s:
        sys.exit("Prima applica applica_inline_comandi.py (questa patch ci si appoggia). Nessuna modifica fatta.")
    for nome, vecchio, _ in MODIFICHE + (("on_error", ANCORA_ERR, ""),):
        if s.count(vecchio) != 1:
            sys.exit(f"Non trovo il punto da modificare ({nome}): il file è diverso da quello atteso. "
                     "Nessuna modifica fatta.")

    for _, vecchio, nuovo in MODIFICHE:
        s = s.replace(vecchio, nuovo)
    s = s.replace(ANCORA_ERR, NUOVO_CODICE + ANCORA_ERR)
    if crlf:
        s = s.replace("\n", "\r\n")
    shutil.copy2(DEST, DEST.with_name(DEST.name + ".bak"))
    DEST.write_bytes(s.encode("utf-8"))
    print(f"Fatto: {DEST} aggiornato (copia in {DEST.name}.bak).\n"
          "Ora su @BotFather: /setinlinefeedback -> il tuo bot -> Enabled. Poi riavvia il bot Telegram.")


if __name__ == "__main__":
    main()
