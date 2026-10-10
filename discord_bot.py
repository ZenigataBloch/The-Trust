"""
Bot Discord personale (app installabile dall'utente): comando slash /url.

Uso:
  Scrivi  /url link:<url>  in qualsiasi DM, gruppo privato o server.
  Il bot scarica video/immagini e li posta come risposta al comando, quindi
  l'altra persona li vede subito come allegati (niente attesa dell'embed).

Funziona anche nei DM dove il bot NON è presente, perché è installato sul tuo
account (User Install), non su un server.

Dipendenze:  pip install -U discord.py yt-dlp gallery-dl python-telegram-bot
(python-telegram-bot serve solo perché riusiamo le funzioni di telegram_bot.py)
Serve anche ffmpeg nel PATH.

Setup su https://discord.com/developers/applications :
  1. New Application -> scheda Bot -> Reset Token (è il DISCORD_TOKEN)
  2. Scheda Installation -> abilita "User Install"
  3. Apri il link di installazione e scegli "Add to my apps"
  4. Su Discord: Impostazioni -> Avanzate -> Modalità sviluppatore, poi tasto
     destro sul tuo profilo -> Copia ID utente (è il DISCORD_OWNER_ID)

Variabili d'ambiente:
  DISCORD_TOKEN      token del bot Discord
  DISCORD_OWNER_ID   il TUO ID utente Discord (solo tu puoi usare il comando)
  COOKIES_BROWSER    (opzionale) browser da cui leggere i cookie, es. "firefox,chrome" (in ordine)
  COOKIES_FILE       (opzionale) cookies.txt, provato per ultimo
  DISCORD_MAX_MB     (opzionale) limite upload, default 20
  DISCORD_CACHE_DIR  (opzionale) cartella della cache, default ~/.cache/discord_bot
  DISCORD_CACHE_MAX_MB (opzionale) tetto della cache, default 500

Cache: i file già scaricati/compressi restano su disco e, se rimandi lo stesso link
(anche a un'altra persona), vengono inviati subito senza riscaricare. Per forzare un
nuovo download usa  /url link:<url> ricarica:True

Perché OWNER: il bot scarica col TUO PC e con i cookie del TUO browser. Chiunque
installasse l'app potrebbe usarli, quindi il comando risponde solo a te.
"""
import sys
from pathlib import Path

# Senza console (pythonw) stdout/stderr sono None: li giro su un file .log con rotazione.
from bot_log import attiva_log_su_file
attiva_log_su_file()

import asyncio
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import weakref
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

print(f"[{time.strftime('%H:%M:%S')}] Avvio discord_bot.py: carico le librerie…", flush=True)

try:
    import discord
    from discord import app_commands
except ImportError:
    sys.exit("Manca discord.py: esegui  pip install -U discord.py")

# riuso le funzioni di telegram_bot.py (download, compressione, log)
try:
    from telegram_bot import (URL_RE, VIDEO_EXT, CookieError, compress_video, descrivi_cookie,
                     download, gif_to_mp4, log, log_versioni, mb, normalizza_url, prendi_avvisi,
                     rendi_riproducibile)
except Exception as e:
    sys.exit(f"Non riesco a importare telegram_bot.py (deve stare nella stessa cartella): {e!r}")

TOKEN = os.environ.get("DISCORD_TOKEN", "")
OWNER = int(os.environ.get("DISCORD_OWNER_ID") or 0)
if not TOKEN or not OWNER:
    sys.exit("Imposta DISCORD_TOKEN e DISCORD_OWNER_ID (vedi avvia_bot.bat).")

# limite upload senza Nitro (20 MB dall'agosto 2026); regolalo se lo verifichi diverso
MAX_UPLOAD = int(float(os.environ.get("DISCORD_MAX_MB", "20")) * 1024 * 1024)
TARGET = int(MAX_UPLOAD * 0.9)   # bersaglio della compressione, con un po' di margine
MAX_FILES_PER_MSG = 10
LIMITE_SEC = 13 * 60   # il token di una risposta slash dura 15 minuti: mi fermo prima

# cache su disco dei file già pronti (separata da tmp: non viene svuotata dalla pulizia)
CACHE_DIR = Path(os.environ.get("DISCORD_CACHE_DIR") or Path.home() / ".cache" / "discord_bot")
CACHE_MAX = int(float(os.environ.get("DISCORD_CACHE_MAX_MB", "500")) * 1024 * 1024)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
for _t in CACHE_DIR.glob("*.tmp"):          # resti di salvataggi interrotti
    shutil.rmtree(_t, ignore_errors=True)

log(f"Librerie caricate (discord.py {discord.__version__}). "
    f"Limite upload {mb(MAX_UPLOAD)}, compressione a {mb(TARGET)}.")
log(f"Cache: {CACHE_DIR} (max {mb(CACHE_MAX)})")

# segnale "sono pronto" per il pannello: creato in on_ready (comandi registrati + connesso), con il mio PID
PRONTO_FILE = Path(__file__).resolve().parent / "discord_pronto.flag"
HASH_FILE = Path(__file__).resolve().parent / "discord_comandi.hash"
PRONTO_FILE.unlink(missing_ok=True)
log_versioni()
log("Cookie: " + descrivi_cookie())


class DiscordBot(discord.Client):
    def __init__(self):
        # nessuna menzione dal testo: una riga di lista con @everyone/@qualcuno non deve fare ping
        super().__init__(intents=discord.Intents.default(),
                         allowed_mentions=discord.AllowedMentions.none())
        self.tree = app_commands.CommandTree(self)

    def _impronta_comandi(self) -> str:
        """Impronta dei comandi (e del token): se non cambia, non serve richiamare tree.sync()."""
        dati = []
        for c in self.tree.get_commands():
            try:
                dati.append(c.to_dict(self.tree))
            except TypeError:
                dati.append(c.to_dict())
        blob = json.dumps(dati, sort_keys=True, default=str) + "|" + TOKEN
        return hashlib.sha256(blob.encode()).hexdigest()

    async def setup_hook(self):
        # tree.sync() ha un rate limit severo (429): con riavvii ripetuti il bot restava bloccato.
        # Registro i comandi solo se sono cambiati (per forzarlo: cancella discord_comandi.hash).
        try:
            impronta = self._impronta_comandi()
        except Exception as e:
            log(f"impronta comandi non calcolabile ({e!r}): registro comunque")
            impronta = None
        try:
            salvata = HASH_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            salvata = ""
        if impronta and impronta == salvata:
            log("Comandi slash invariati dall'ultimo avvio: registrazione saltata")
            return
        log("Registro i comandi slash su Discord…")
        try:
            cmds = await self.tree.sync()   # registra /url globalmente
        except Exception as e:
            log(f"Registrazione comandi non riuscita ({e!r}): uso quelli già presenti su Discord")
            return
        if impronta:
            try:
                HASH_FILE.write_text(impronta, encoding="utf-8")
            except OSError:
                pass
        log("Comandi registrati: " + (", ".join("/" + c.name for c in cmds) or "nessuno"))


client = DiscordBot()


@client.event
async def on_ready():
    try:
        PRONTO_FILE.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass
    log(f"✅ Bot Discord AVVIATO come {client.user} (id {client.user.id}). "
        f"Usa /url in un DM; solo l'utente {OWNER} è autorizzato.")


# parametri di tracciamento che non cambiano il contenuto del link
_TRACK = {"igsh", "igshid", "_t", "_r", "_d", "is_from_webapp", "sender_device", "sender_web_id",
          "share_app_id", "share_author_id", "share_link_id", "share_item_id", "share_id",
          "si", "feature", "rdt", "context", "ref", "ref_source"}


def chiave(url: str) -> str:
    """Identificativo stabile del link: stesso post condiviso in modi diversi = stessa chiave."""
    u = urlsplit(normalizza_url(url).strip())   # Twitter/X: stesso tweet = stessa chiave
    host = u.netloc.lower().removeprefix("www.")
    q = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
         if k.lower() not in _TRACK and not k.lower().startswith("utm_")]
    norm = urlunsplit(("https", host, u.path.rstrip("/"), urlencode(sorted(q)), ""))
    return hashlib.sha1(norm.encode()).hexdigest()[:16]


# un lock per chiave: se lo stesso link arriva due volte di fila, il secondo aspetta il primo
# e poi lo trova già in cache invece di riscaricarlo
_LOCKS: "weakref.WeakValueDictionary[str, asyncio.Lock]" = weakref.WeakValueDictionary()


def lock_chiave(key: str) -> asyncio.Lock:
    lock = _LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[key] = lock
    return lock   # chi lo usa ne tiene un riferimento finché serve; poi sparisce da solo


def cache_leggi(key: str) -> list[Path]:
    """File pronti in cache per questa chiave (lista vuota se assenti o non più validi)."""
    d = CACHE_DIR / key
    if not d.is_dir():
        return []
    files = sorted(p for p in d.iterdir() if p.is_file())
    if not files or any(p.stat().st_size > MAX_UPLOAD for p in files):
        shutil.rmtree(d, ignore_errors=True)   # vuota o sopra il limite attuale
        return []
    os.utime(d)   # segna come usata di recente
    return files


def cache_salva(key: str, files: list[Path]) -> list[Path]:
    """Copia i file pronti in cache; restituisce i percorsi in cache (o gli originali se fallisce)."""
    d, tmp = CACHE_DIR / key, CACHE_DIR / f"{key}.tmp"
    try:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(d, ignore_errors=True)
        tmp.mkdir()
        for p in files:
            shutil.copy2(p, tmp / p.name)
        tmp.rename(d)
        pulisci_cache(d)
        return sorted(p for p in d.iterdir() if p.is_file())
    except Exception as e:
        log(f"  cache non salvata: {e}")
        shutil.rmtree(tmp, ignore_errors=True)
        return files


def pulisci_cache(tieni: Path):
    """Se la cache supera il tetto, elimina le voci usate meno di recente."""
    dirs = [x for x in CACHE_DIR.iterdir() if x.is_dir() and not x.name.endswith(".tmp")]
    peso = lambda x: sum(f.stat().st_size for f in x.iterdir() if f.is_file())
    tot = sum(peso(x) for x in dirs)
    for x in sorted(dirs, key=lambda x: x.stat().st_mtime):
        if tot <= CACHE_MAX:
            break
        if x == tieni:
            continue
        tot -= peso(x)
        shutil.rmtree(x, ignore_errors=True)
        log(f"  cache piena: eliminata la voce più vecchia {x.name}")


def _riduci_immagine(path: Path, target: int) -> Path:
    """Ricomprime un'immagine troppo pesante in JPEG (abbassando qualità e dimensioni) finché sta sotto target."""
    try:
        from PIL import Image
    except ImportError:
        raise ValueError(f"{path.name} supera {mb(MAX_UPLOAD)} (per ridurla serve  pip install Pillow)")
    im = Image.open(path)
    im.load()
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        sfondo = Image.new("RGB", im.size, (255, 255, 255))   # il JPEG non ha trasparenza
        sfondo.paste(im, mask=im.getchannel("A"))
        im = sfondo
    else:
        im = im.convert("RGB")
    out = path.with_name(path.stem + "_small.jpg")
    scala, qualita = 1.0, 90
    for _ in range(10):
        img = im if scala >= 1 else im.resize((max(1, int(im.width * scala)), max(1, int(im.height * scala))),
                                              Image.LANCZOS)
        img.save(out, "JPEG", quality=qualita, optimize=True)
        if out.stat().st_size <= target:
            log(f"    {path.name}: ridotta a {mb(out.stat().st_size)} (qualità {qualita}, scala {scala:.2f})")
            return out
        if qualita > 70:
            qualita -= 10
        else:
            scala *= 0.8
    raise ValueError(f"{path.name} è ancora sopra {mb(MAX_UPLOAD)} anche dopo la riduzione")


async def fit(path: Path, riduci: bool = True) -> Path:
    """Restituisce un file che sta nel limite di Discord: comprime i video, converte le GIF e, se `riduci`,
    ricomprime le immagini troppo pesanti (con riduci=False le scarta con un errore)."""
    if path.stat().st_size <= MAX_UPLOAD:
        return path
    if path.suffix.lower() == ".gif":
        # una GIF troppo grande diventa un mp4 muto, molto più leggero
        nuovo = await asyncio.to_thread(gif_to_mp4, path, TARGET)
        if nuovo == path:   # GIF senza animazione: non c'è niente da convertire
            if not riduci:
                raise ValueError(f"{path.name} supera {mb(MAX_UPLOAD)}")
            return await asyncio.to_thread(_riduci_immagine, path, TARGET)
        path = nuovo
        if path.stat().st_size <= MAX_UPLOAD:
            return path
    elif path.suffix.lower() not in VIDEO_EXT:
        if not riduci:
            raise ValueError(f"{path.name} supera {mb(MAX_UPLOAD)}")
        return await asyncio.to_thread(_riduci_immagine, path, TARGET)
    small = await asyncio.to_thread(compress_video, path, TARGET, limite_bytes=MAX_UPLOAD)
    if small.stat().st_size > MAX_UPLOAD:
        raise ValueError(f"{path.name} è ancora sopra {mb(MAX_UPLOAD)}")
    return small


def batches(files: list[Path]):
    """Raggruppa i file in messaggi da max 10 allegati e dimensione totale nel limite."""
    batch, total = [], 0
    for p in files:
        size = p.stat().st_size
        if batch and (len(batch) >= MAX_FILES_PER_MSG or total + size > MAX_UPLOAD):
            yield batch
            batch, total = [], 0
        batch.append(p)
        total += size
    if batch:
        yield batch


@client.tree.command(name="url", description="Scarica video/immagini da un link e li posta qui")
@app_commands.describe(link="Link da scaricare (anche più di uno)",
                       ricarica="Ignora la cache e riscarica da zero")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def cmd_url(interaction: discord.Interaction, link: str, ricarica: bool = False):
    if interaction.user.id != OWNER:
        log(f"Ignorato /url da {interaction.user.id}: non è DISCORD_OWNER_ID")
        await interaction.response.send_message("Non sei autorizzato.", ephemeral=True)
        return

    urls = URL_RE.findall(link)
    if not urls:
        await interaction.response.send_message("Nessun link http(s) valido.", ephemeral=True)
        return

    # Discord vuole una risposta entro 3 secondi: rispondo subito, poi lavoro
    await interaction.response.defer(thinking=True)

    problems, sent = [], 0
    t_inizio = time.time()
    for n, url in enumerate(urls, 1):
        if time.time() - t_inizio > LIMITE_SEC:
            restanti = urls[n - 1:]
            log(f"  limite dei 15 minuti di Discord: salto {len(restanti)} link")
            problems.append("⏸ Fermato per il limite di 15 minuti di Discord. Rilancia /url con i link "
                            "rimasti (quelli già scaricati partono subito dalla cache):\n" + "\n".join(restanti))
            break
        t0 = time.time()
        log(f"[{n}/{len(urls)}] {url}")
        key = chiave(url)
        async with lock_chiave(key):   # stesso link in parallelo: il secondo aspetta e usa la cache
            ready = [] if ricarica else cache_leggi(key)
            if ready:
                log(f"  CACHE: trovato, rimando {len(ready)} file senza riscaricare")
            with tempfile.TemporaryDirectory() as d:
                if not ready:
                    try:
                        files = await asyncio.to_thread(download, url, d)
                    except Exception as e:
                        log(f"  ERRORE download: {e}")
                        problems.append(f"🍪 {e}\n{url}" if isinstance(e, CookieError) else f"{url}\n{e}")
                        continue
                    if not files:
                        problems.append(f"Niente da scaricare: {url}")
                        continue

                    errori_prima = len(problems)
                    for p in files:
                        try:
                            ready.append(await fit(await rendi_riproducibile(p)))
                        except Exception as e:
                            log(f"  ERRORE {p.name}: {e}")
                            problems.append(f"{p.name}: {e}")
                    if ready and len(problems) == errori_prima:   # salvo solo se è andato tutto bene
                        ready = cache_salva(key, ready)

                for batch in batches(ready):
                    handles = [discord.File(p) for p in batch]
                    try:
                        log(f"  invio {len(batch)} file su Discord…")
                        await interaction.followup.send(files=handles)
                        sent += len(batch)
                    except Exception as e:
                        log(f"  ERRORE invio: {e}")
                        problems.append(f"invio non riuscito: {e}")
                    finally:
                        for h in handles:
                            h.close()
        log(f"  completato in {time.time() - t0:.0f}s")

    problems.extend(prendi_avvisi())   # es. troppi download Instagram: avviso solo a te (ephemeral)
    if problems:
        if sent == 0:
            # tolgo il "sta pensando…" pubblico, così l'altra persona non vede errori
            try:
                await interaction.delete_original_response()
            except Exception:
                pass
        try:
            await interaction.followup.send(("⚠️ " + "\n⚠️ ".join(problems))[:1900], ephemeral=True)
        except Exception as e:   # tipicamente il token di 15 minuti è già scaduto
            log(f"  non riesco a inviare il riepilogo degli errori: {e}")


# --- supplemento facoltativo: liste per persona e comando /invia (file org_bot.py) ---
org_bot = None
try:
    import org_bot
except ModuleNotFoundError as e:
    if e.name == "org_bot":
        log(f"org_bot.py NON trovato in {Path(__file__).resolve().parent}: il comando /invia non è attivo")
    else:
        log(f"org_bot.py non si carica (manca il modulo {e.name}): il bot parte senza /invia")
    org_bot = None
except Exception as e:   # un problema lì non deve fermare il bot
    log(f"org_bot.py non si carica ({e!r}): il bot parte senza /invia")
    org_bot = None
if org_bot:
    try:
        org_bot.registra(client, OWNER, fit, batches)
        log("Supplemento org_bot caricato: comando /invia attivo")
    except Exception as e:   # un problema lì non deve fermare il bot
        log(f"org_bot non caricato ({e!r}): il bot parte senza /invia")


if __name__ == "__main__":
    log("Accesso a Discord in corso…")
    try:
        client.run(TOKEN)
    except discord.LoginFailure:
        sys.exit("Token Discord non valido: ricontrolla DISCORD_TOKEN "
                 "(Developer Portal -> Bot -> Reset Token).")
