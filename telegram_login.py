"""
telegram_login.py - collega il tuo account Telegram PERSONALE, una volta sola.

Serve per i link dei canali privati (t.me/c/...). Il bot (BOT_TOKEN) resta separato e non usa mai questo account:
telegram_bot.py lo usa solo per LEGGERE i post di cui sei già membro.

Prima:  pip install telethon
        TG_API_ID e TG_API_HASH in bots.env  (li crei su https://my.telegram.org -> API development tools)
Poi:    python telegram_login.py     (chiede numero, codice ricevuto su Telegram ed eventuale password 2FA)

Crea  utente.session  accanto agli script: equivale a una sessione aperta sul tuo account.
NON metterlo su GitHub (aggiungi  *.session  al .gitignore) e non condividerlo.
Per scollegarlo: Telegram > Impostazioni > Dispositivi > termina la sessione, e cancella utente.session.
"""
import asyncio
import os
from pathlib import Path

import bot_manager as BM

env = BM.carica_env()
API_ID = int(env.get("TG_API_ID") or 0)
API_HASH = env.get("TG_API_HASH", "")
SESSION = env.get("TG_SESSION") or str(Path(__file__).resolve().with_name("utente"))


async def main():
    from telethon import TelegramClient
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()                      # interattivo: telefono, codice, password 2FA
    me = await client.get_me()
    print(f"Collegato come {me.first_name} (@{me.username or 'senza username'}). Sessione: {SESSION}.session")
    await client.disconnect()
    try:
        os.chmod(SESSION + ".session", 0o600)
    except OSError:
        pass


if __name__ == "__main__":
    if not (API_ID and API_HASH):
        raise SystemExit("Metti TG_API_ID e TG_API_HASH in bots.env (da https://my.telegram.org).")
    asyncio.run(main())
