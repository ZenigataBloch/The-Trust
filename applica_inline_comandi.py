"""
applica_inline_comandi.py - rende /ricerca e /booru invocabili via @bot (inline) in gruppi e canali.

Uso (nella cartella dei bot):   python applica_inline_comandi.py
Crea telegram_bot.py.bak, poi modifica telegram_bot.py. Si può rilanciare senza danni.

Come si usa dopo la patch (in qualsiasi gruppo o canale dove il bot è amministratore):
    @nomedelbot ricerca gatti arancioni -n 3
    @nomedelbot booru hatsune_miku solo -n 2 -s gb -r
Sopra la tastiera compare un risultato: toccalo. Il bot cancella il messaggio e:
  - ricerca: pubblica le immagini nella chat;
  - booru:   ti manda le anteprime in PRIVATO con Invia / Altro / Scarta; il file parte
             nella chat d'origine (canale, gruppo o topic) solo se premi Invia.
Nei canali i comandi /xxx scritti a mano non funzionano (i post dei canali non hanno un mittente):
l'inline è l'unico modo, e vale anche per i gruppi. Nei gruppi e in privato /ricerca e /booru
restano utilizzabili come prima.

Cosa cambia in telegram_bot.py:
  1. cmd_ricerca e cmd_booru: il controllo dell'utente resta lì, il resto passa a _ricerca_core
     e _booru_core, che prendono chat, messaggio e argomenti come parametri;
  2. handle_inline: se la query inizia con "ricerca" o "booru" propone il risultato del comando;
  3. nuovo handler handle_comando_inline (group=1) che riceve il messaggio "via @bot", applica le
     stesse regole di handle() su chi può usare il bot e dove, e lancia il corpo del comando.
"""
import shutil
import sys
from pathlib import Path

DEST = Path(sys.argv[1] if len(sys.argv) > 1 else "telegram_bot.py")

# ---------------------------------------------------------------- 1. /ricerca
R1_OLD = '''    if user.id != OWNER:
        log(f"Ignorato /ricerca da {user.id}: non è OWNER_ID")
        return
    kw = {"message_thread_id": msg.message_thread_id} if msg.is_topic_message else {}
'''
R1_NEW = '''    if user.id != OWNER:
        log(f"Ignorato /ricerca da {user.id}: non è OWNER_ID")
        return
    await _ricerca_core(ctx, msg, chat, list(ctx.args or []))


async def _ricerca_core(ctx: ContextTypes.DEFAULT_TYPE, msg, chat, args: list, cancella: bool = False):
    """Corpo di /ricerca: usato da cmd_ricerca e dal comando inline (cancella=True: toglie il messaggio)."""
    kw = {"message_thread_id": msg.message_thread_id} if msg.is_topic_message else {}
'''
R2_OLD = 'query, n = graves.parse_richiesta(" ".join(ctx.args or []))'
R2_NEW = 'query, n = graves.parse_richiesta(" ".join(args))'
R3_OLD = '''    if problems:
        err = "⚠️ " + "\\n⚠️ ".join(problems)
        if chat.type != ChatType.PRIVATE:
'''
R3_NEW = '''    if cancella and not problems:
        try:
            await msg.delete()
        except Exception:
            log("  non riesco a cancellare il messaggio del comando (manca il permesso?)")
    if problems:
        err = "⚠️ " + "\\n⚠️ ".join(problems)
        if chat.type != ChatType.PRIVATE:
'''

# ---------------------------------------------------------------- 2. /booru
B1_OLD = '''    if user.id != OWNER:
        log(f"Ignorato /booru da {user.id}: non è OWNER_ID")
        return
    kw = {"message_thread_id": msg.message_thread_id} if msg.is_topic_message else {}
'''
B1_NEW = '''    if user.id != OWNER:
        log(f"Ignorato /booru da {user.id}: non è OWNER_ID")
        return
    await _booru_core(ctx, msg, chat, list(ctx.args or []))


async def _booru_core(ctx: ContextTypes.DEFAULT_TYPE, msg, chat, args: list):
    """Corpo di /booru: usato da cmd_booru e dal comando inline (anche nei canali)."""
    kw = {"message_thread_id": msg.message_thread_id} if msg.is_topic_message else {}
'''
B2_OLD = 'rich = graves.parse_booru(" ".join(ctx.args or []))'
B2_NEW = 'rich = graves.parse_booru(" ".join(args))'

# ---------------------------------------------------------------- 3. inline
I1_OLD = '''    is_owner = q.from_user.id == OWNER
    urls = URL_RE.findall(q.query or "") if is_owner else []
'''
I1_NEW = '''    is_owner = q.from_user.id == OWNER
    cmd = _inline_comando(q.query) if is_owner else None
    if cmd:                      # "@bot ricerca ..." / "@bot booru ...": vedi _risposta_inline_comando
        await _risposta_inline_comando(q, cmd)
        return
    urls = URL_RE.findall(q.query or "") if is_owner else []
'''

# ---------------------------------------------------------------- 4. nuovo codice (prima di on_error)
ANCORA_ERR = "async def on_error(update, ctx: ContextTypes.DEFAULT_TYPE):"
NUOVO_CODICE = '''# ---------- /ricerca e /booru via @bot (inline): gruppi e canali ----------
# Nei canali i comandi /xxx non arrivano (i post non hanno un mittente): si scrive
#   @nomedelbot ricerca <cosa cercare> [-n 1-10]      @nomedelbot booru <tag> [-n 1-5] [-s sito] [-r]
# handle_inline propone un risultato; toccandolo parte nella chat "ricerca ..." o "booru ..." (senza
# barra, così non lo prende anche CommandHandler) e handle_comando_inline lo esegue.
_INLINE_CMD_RE = re.compile(r"\\s*/?(ricerca|booru)(?:\\s+(.*))?$", re.I | re.S)


def _inline_comando(testo: str):
    """('ricerca'|'booru', argomenti) se il testo è un comando inline, altrimenti None."""
    m = _INLINE_CMD_RE.match(testo or "")
    if not m:
        return None
    return m.group(1).lower(), " ".join((m.group(2) or "").split())


async def _risposta_inline_comando(q, cmd):
    """Risultato inline di un comando; con argomenti non validi non propone niente."""
    nome, args = cmd
    try:
        if graves is None:
            raise RuntimeError("graves.py non caricato")
        if nome == "ricerca":
            query, n = graves.parse_richiesta(args)
            titolo = f"🔎 Cerca immagini: {query[:50]}"
            desc = f"{n} immagini" if n else "numero di immagini di default"
        else:
            rich = graves.parse_booru(args)
            titolo = f"🏷 Booru ({rich.sito}): {' '.join(rich.tags)[:50]}"
            desc = f"{rich.n} risultati" + (" · casuali" if rich.casuale else "") + " · anteprime in privato"
    except Exception as e:
        if args:   # senza argomenti è solo la parola digitata a metà: niente da segnalare
            log(f"Inline /{nome}: non propongo il risultato ({str(e)[:100]})")
        await q.answer([], cache_time=0, is_personal=True)
        return
    result = InlineQueryResultArticle(
        id=uuid.uuid4().hex,
        title=titolo,
        description=desc,
        input_message_content=InputTextMessageContent(f"{nome} {args}"),
    )
    await q.answer([result], cache_time=0, is_personal=True)


async def handle_comando_inline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Messaggio "ricerca ..." / "booru ..." inviato via @bot (inline) in un gruppo, canale o chat privata."""
    msg, chat, user = update.effective_message, update.effective_chat, update.effective_user
    if not msg or not chat or not msg.via_bot or msg.via_bot.id != ctx.bot.id:
        return
    cmd = _inline_comando(msg.text or "")
    if not cmd:
        return
    # stesse regole di handle(): dove e per chi (il risultato inline lo propone comunque solo a OWNER)
    if chat.type == ChatType.CHANNEL:
        if CHANNELS and chat.id not in CHANNELS and chat.id not in AUTO_CHANNELS:
            log(f"Ignorato comando inline nel canale {chat.id}: non è in CHANNEL_ID")
            return
    elif chat.type in (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.PRIVATE):
        if not user or user.id != OWNER:
            log(f"Ignorato comando inline da {user.id if user else '?'}: non è OWNER_ID")
            return
    else:
        return
    nome, args = cmd
    if nome == "ricerca":
        await _ricerca_core(ctx, msg, chat, args.split(), cancella=True)
    else:
        await _booru_core(ctx, msg, chat, args.split())


'''

# ---------------------------------------------------------------- 5. registrazione handler
H_OLD = '''    app.add_handler(CallbackQueryHandler(on_booru_scelta, pattern=r"^bo:"))
'''
H_NEW = '''    app.add_handler(CallbackQueryHandler(on_booru_scelta, pattern=r"^bo:"))
    app.add_handler(   # group=1: gira in aggiunta a handle() (group 0), che ignora questi messaggi senza link
        MessageHandler((filters.UpdateType.MESSAGE | filters.UpdateType.CHANNEL_POST) & filters.TEXT,
                       handle_comando_inline),
        group=1,
    )
'''

MODIFICHE = (
    ("cmd_ricerca (controllo utente)", R1_OLD, R1_NEW),
    ("cmd_ricerca (argomenti)", R2_OLD, R2_NEW),
    ("cmd_ricerca (cancella il messaggio)", R3_OLD, R3_NEW),
    ("cmd_booru (controllo utente)", B1_OLD, B1_NEW),
    ("cmd_booru (argomenti)", B2_OLD, B2_NEW),
    ("handle_inline", I1_OLD, I1_NEW),
    ("registrazione handler", H_OLD, H_NEW),
)


def main():
    if not DEST.is_file():
        sys.exit(f"{DEST} non trovato: lancia lo script nella cartella dei bot.")
    grezzo = DEST.read_bytes().decode("utf-8")
    crlf = "\r\n" in grezzo
    s = grezzo.replace("\r\n", "\n")

    if "handle_comando_inline" in s:
        print("Già applicato: niente da fare.")
        return
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
    print(f"Fatto: {DEST} aggiornato (copia in {DEST.name}.bak). Riavvia il bot Telegram.")


if __name__ == "__main__":
    main()
