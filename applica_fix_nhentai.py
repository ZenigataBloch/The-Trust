"""
applica_fix_nhentai.py - corregge telegram_bot.py per l'errore
  [nhentai][error] HttpError: SSLError: CERTIFICATE_VERIFY_FAILED ... self signed certificate

Uso (nella cartella dei bot):   python applica_fix_nhentai.py
Crea telegram_bot.py.bak, poi modifica due punti di telegram_bot.py. Si può rilanciare senza danni.

Cosa cambia: se gallery-dl fallisce per il certificato, SOLO per i siti elencati in
SSL_SENZA_VERIFICA (default: nhentai.net) riprova una volta senza controllare il certificato.
Per disattivare la cosa:  set SSL_SENZA_VERIFICA=   (vuoto).  Per altri siti: set SSL_SENZA_VERIFICA=nhentai.net,altro.it
"""
import shutil
import sys
from pathlib import Path

DEST = Path(sys.argv[1] if len(sys.argv) > 1 else "telegram_bot.py")

VECCHIA_FIRMA = '''def download_gallerydl(url: str, folder: str, sorgente: tuple[str, str] | None = None) -> list[Path]:
    cmd = [_python_console(), "-m", "gallery_dl", "-d", folder]
'''
NUOVA_FIRMA = '''def download_gallerydl(url: str, folder: str, sorgente: tuple[str, str] | None = None,
                       verifica_ssl: bool = True) -> list[Path]:
    cmd = [_python_console(), "-m", "gallery_dl", "-d", folder]
    if not verifica_ssl:
        cmd.append("--no-check-certificate")
'''

VECCHIO_BLOCCO = '''    log("  provo con gallery-dl…")
    try:
        return download_gallerydl(url, folder, sorgente)
    except Exception as e:
        raise DownloadError(str(e), dettagli=f"{err_yt}\\n{e}") from None
'''
NUOVO_BLOCCO = '''    log("  provo con gallery-dl…")
    try:
        return download_gallerydl(url, folder, sorgente)
    except Exception as e:
        if _errore_certificato(str(e)) and _ssl_senza_verifica(url):
            host = urlsplit(url).netloc.lower().removeprefix("www.")
            log(f"  gallery-dl: certificato non valido per {host}: riprovo UNA volta senza verifica SSL")
            try:
                return download_gallerydl(url, folder, sorgente, verifica_ssl=False)
            except Exception as e2:
                extra = ""
                if _errore_certificato(str(e2)):
                    extra = (f" Il sito {host} presenta un certificato non valido anche senza verifica: "
                             "di solito è un blocco del provider o la scansione HTTPS dell'antivirus. "
                             "Prova a cambiare DNS (es. 1.1.1.1), una VPN, o a disattivare la scansione HTTPS.")
                raise DownloadError(str(e2) + extra, dettagli=f"{err_yt}\\n{e2}") from None
        raise DownloadError(str(e), dettagli=f"{err_yt}\\n{e}") from None
'''

HELPER = '''# ---------- certificati SSL non validi (es. nhentai) ----------
# Se gallery-dl fallisce con CERTIFICATE_VERIFY_FAILED, per i siti elencati qui si riprova UNA volta
# senza verifica del certificato. Variabile SSL_SENZA_VERIFICA: host separati da virgola
# (default nhentai.net; vuota = mai). Vale anche per i sottodomini (i.nhentai.net, ...).
SSL_SENZA_VERIFICA = tuple(x.strip().lower() for x in
                           os.environ.get("SSL_SENZA_VERIFICA", "nhentai.net").split(",") if x.strip())


def _errore_certificato(testo: str) -> bool:
    t = testo.lower()
    return "certificate_verify_failed" in t or "certificate verify failed" in t


def _ssl_senza_verifica(url: str) -> bool:
    host = urlsplit(url.strip()).netloc.lower().removeprefix("www.")
    return any(host == h or host.endswith("." + h) for h in SSL_SENZA_VERIFICA)


'''
ANCORA_HELPER = "def _scarica(url: str, folder: str, sorgente: tuple[str, str] | None) -> list[Path]:"


def main():
    if not DEST.is_file():
        sys.exit(f"{DEST} non trovato: lancia lo script nella cartella dei bot.")
    grezzo = DEST.read_bytes().decode("utf-8")
    crlf = "\r\n" in grezzo
    s = grezzo.replace("\r\n", "\n")

    if "_ssl_senza_verifica" in s:
        print("Già applicato: niente da fare.")
        return
    for nome, pezzo in (("download_gallerydl", VECCHIA_FIRMA), ("_scarica", VECCHIO_BLOCCO),
                        ("_scarica (firma)", ANCORA_HELPER)):
        if s.count(pezzo) != 1:
            sys.exit(f"Non trovo il punto da modificare in {nome} (il file è diverso da quello atteso). "
                     "Nessuna modifica fatta.")

    s = s.replace(VECCHIA_FIRMA, NUOVA_FIRMA)
    s = s.replace(ANCORA_HELPER, HELPER + ANCORA_HELPER)
    s = s.replace(VECCHIO_BLOCCO, NUOVO_BLOCCO)
    if crlf:
        s = s.replace("\n", "\r\n")
    shutil.copy2(DEST, DEST.with_name(DEST.name + ".bak"))
    DEST.write_bytes(s.encode("utf-8"))
    print(f"Fatto: {DEST} aggiornato (copia in {DEST.name}.bak). Riavvia i bot.")


if __name__ == "__main__":
    main()
