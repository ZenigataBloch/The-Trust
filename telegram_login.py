"""
telegram_login.py - collega il tuo account Telegram PERSONALE (non il bot), una volta sola.

Serve per i link dei canali privati (t.me/c/...). Il bot (BOT_TOKEN) resta separato e non usa mai questo account:
telegram_bot.py lo usa solo per LEGGERE i post di cui sei già membro.

Prima:  pip install telethon
        TG_API_ID e TG_API_HASH in bots.env  (li crei su https://my.telegram.org -> API development tools)
Poi:    python telegram_login.py   -> chiede il TUO NUMERO DI TELEFONO, il codice arrivato su Telegram ed
        eventualmente la password 2FA. Il token del bot NON va inserito qui.

Crea  utente.session  accanto agli script: equivale a una sessione aperta sul tuo account.
NON metterlo su GitHub (aggiungi  *.session  al .gitignore) e non condividerlo.
Per scollegarlo: Telegram > Impostazioni > Dispositivi > termina la sessione, e cancella utente.session.
"""
import asyncio
import os
import re
from pathlib import Path

import bot_manager as BM

env = BM.carica_env()
API_ID = int(env.get("TG_API_ID") or 0)
API_HASH = env.get("TG_API_HASH", "")
SESSION = env.get("TG_SESSION") or str(Path(__file__).resolve().with_name("utente"))
FILE_SESSIONE = Path(SESSION + ".session")


def chiedi_telefono() -> str:
    while True:
        v = input("Il TUO numero di telefono, con prefisso (es. +393331234567): ").strip().replace(" ", "")
        if re.fullmatch(r"\+?\d{7,15}", v):
            return v if v.startswith("+") else "+" + v
        print("Non sembra un numero di telefono (il token del bot non va bene qui). Riprova.")


async def main():
    from telethon import TelegramClient

    if FILE_SESSIONE.exists():                       # sessione già presente: è di una persona o di un bot?
        c = TelegramClient(SESSION, API_ID, API_HASH)
        await c.connect()
        me = await c.get_me() if await c.is_user_authorized() else None
        await c.disconnect()
        if me is not None and not me.bot:
            print(f"Già collegato come {me.first_name} (@{me.username or 'senza username'}). Niente da fare.")
            return
        print("La sessione esistente è di un BOT o non è valida: la cancello e la rifaccio.")
        FILE_SESSIONE.unlink()

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start(phone=chiedi_telefono)        # codice e password 2FA vengono chiesti nel terminale
    me = await client.get_me()
    await client.disconnect()
    if me.bot:
        FILE_SESSIONE.unlink(missing_ok=True)
        raise SystemExit("Hai collegato un bot, non un account personale: riprova col numero di telefono.")
    print(f"Collegato come {me.first_name} (@{me.username or 'senza username'}). Sessione: {FILE_SESSIONE}")
    try:
        os.chmod(FILE_SESSIONE, 0o600)
    except OSError:
        pass


if __name__ == "__main__":
    if not (API_ID and API_HASH):
        raise SystemExit("Metti TG_API_ID e TG_API_HASH in bots.env (da https://my.telegram.org).")
    asyncio.run(main())
