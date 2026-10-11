"""
chiavi.py - aggiunge / sostituisce / toglie le chiavi API in bots.env (pensato per Termux, cartella The-Trust).

Metti questo file nella stessa cartella di bots.env (di solito ~/The-Trust). Se bots.env non c'è lo crea.

USO
  python chiavi.py                      menù interattivo (consigliato)
  python chiavi.py --mostra             elenca le chiavi presenti (mascherate)
  python chiavi.py NOME=valore ...      imposta direttamente, es.:
        python chiavi.py GRAVES_R34_KEY=abc123 GRAVES_R34_USER=marquise
  python chiavi.py --rimuovi NOME ...   toglie una o più variabili
  python chiavi.py --file /percorso/bots.env ...   usa un altro file

COSA FA E COSA NON TOCCA
- Cambia SOLO le variabili indicate: commenti, righe vuote, ordine e tutte le altre variabili restano come sono.
- Se una variabile compare più volte (l'ultima vince, per Branch/bot_manager) la sostituisce nella prima riga
  e toglie le altre, così non resta un duplicato che ti sovrascrive il nuovo valore.
- Riconosce anche le righe con "export NOME=..." e mantiene il tipo di fine riga (LF/CRLF).
- Prima di scrivere salva una copia in bots.env.bak; la scrittura è atomica; il file diventa leggibile
  solo da te (chmod 600), perché contiene chiavi.
- I valori sono scritti senza virgolette quando possibile (vanno bene sia per i bot sia per
  "set -a; . ./bots.env; set +a"); con caratteri speciali vengono messi tra apici singoli.
- Nel sito rule34.xxx/Gelbooru le credenziali sono mostrate come  &api_key=XXXX&user_id=123 :
  se incolli quella stringa al posto della chiave, estraggo chiave e user_id da sola.

Dopo la modifica RIAVVIA i bot: leggono le variabili solo all'avvio (Graves le rilegge a ogni ricerca,
ma solo da quelle che il processo ha ricevuto all'avvio).
"""
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

# (variabile, descrizione, valore suggerito se manca)
SITI = {
    "rule34.xxx": [("GRAVES_R34_USER", "user_id", "marquise"), ("GRAVES_R34_KEY", "api_key", "")],
    "Gelbooru": [("GRAVES_GELBOORU_USER", "user_id", "marquise"), ("GRAVES_GELBOORU_KEY", "api_key", "")],
    "Danbooru (facoltativo)": [("GRAVES_DANBOORU_USER", "utente", ""), ("GRAVES_DANBOORU_KEY", "api key", "")],
    "e621 (facoltativo)": [("GRAVES_E621_USER", "utente", ""), ("GRAVES_E621_KEY", "api key", "")],
    "Ricerca Google: Serper": [("GRAVES_SERPER_KEY", "chiave", "")],
    "Ricerca Google: SerpApi": [("GRAVES_SERPAPI_KEY", "chiave", "")],
}
SEGRETE = ("KEY", "TOKEN", "HASH")      # variabili mascherate quando vengono mostrate

RE_RIGA = re.compile(r"^(\s*(?:export\s+)?)([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
SICURO = re.compile(r"^[\w.@:/+,=-]*$")


def trova_file(argomento: str | None) -> Path:
    if argomento:
        return Path(argomento).expanduser()
    qui = Path(__file__).resolve().parent / "bots.env"
    if qui.exists():
        return qui
    alt = Path.home() / "The-Trust" / "bots.env"
    return alt if alt.exists() else qui


def pulisci_valore(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def formatta(v: str) -> str:
    if SICURO.match(v):
        return v
    return "'" + v.replace("'", "'\\''") + "'"


class EnvFile:
    def __init__(self, path: Path):
        self.path = path
        try:
            grezzo = path.read_bytes().decode("utf-8-sig")
        except FileNotFoundError:
            grezzo = ""
        self.eol = "\r\n" if "\r\n" in grezzo else "\n"
        self.righe = grezzo.replace("\r\n", "\n").split("\n")
        if self.righe and self.righe[-1] == "":
            self.righe.pop()
        self.modificato = False

    def posizioni(self, nome: str) -> list[int]:
        out = []
        for i, r in enumerate(self.righe):
            m = RE_RIGA.match(r)
            if m and m.group(2) == nome and not r.lstrip().startswith("#"):
                out.append(i)
        return out

    def leggi(self, nome: str) -> str | None:
        pos = self.posizioni(nome)
        if not pos:
            return None
        return pulisci_valore(RE_RIGA.match(self.righe[pos[-1]]).group(3))   # l'ultima vince

    def imposta(self, nome: str, valore: str):
        riga_nuova = None
        pos = self.posizioni(nome)
        if pos:
            prefisso = RE_RIGA.match(self.righe[pos[0]]).group(1)
            riga_nuova = f"{prefisso}{nome}={formatta(valore)}"
            self.righe[pos[0]] = riga_nuova
            for i in reversed(pos[1:]):          # duplicati: via
                del self.righe[i]
        else:
            self.righe.append(f"{nome}={formatta(valore)}")
        self.modificato = True

    def rimuovi(self, nome: str) -> bool:
        pos = self.posizioni(nome)
        for i in reversed(pos):
            del self.righe[i]
        if pos:
            self.modificato = True
        return bool(pos)

    def salva(self):
        if not self.modificato:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            shutil.copy2(self.path, self.path.with_name(self.path.name + ".bak"))
        testo = self.eol.join(self.righe) + (self.eol if self.righe else "")
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".bots.env.")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(testo.encode("utf-8"))
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        self.modificato = False
        return True


def maschera(nome: str, v: str | None) -> str:
    if v is None:
        return "(non impostata)"
    if v == "":
        return "(vuota)"
    if any(s in nome for s in SEGRETE):
        return "••••" + v[-4:] if len(v) > 8 else "••••"
    return v


def estrai_credenziali(testo: str) -> dict:
    """Da '&api_key=XXXX&user_id=123' ricava {'key': 'XXXX', 'user': '123'}."""
    out = {}
    mk = re.search(r"api_key=([^&\s\"']+)", testo)
    mu = re.search(r"user_id=([^&\s\"']+)", testo)
    if mk:
        out["key"] = mk.group(1)
    if mu:
        out["user"] = mu.group(1)
    return out


def mostra(env: EnvFile):
    print(f"\nFile: {env.path}")
    for sito, voci in SITI.items():
        print(f"\n{sito}")
        for nome, desc, _ in voci:
            print(f"  {nome:<24} {maschera(nome, env.leggi(nome))}")
    note = sorted({RE_RIGA.match(r).group(2) for r in env.righe if RE_RIGA.match(r)}
                  - {n for v in SITI.values() for n, _, _ in v})
    if note:
        print("\nAltre variabili nel file: " + ", ".join(note))
    print()


def menu_sito(env: EnvFile, sito: str):
    voci = SITI[sito]
    print(f"\n== {sito} ==  (Invio = lascia com'è, - = togli la variabile; per chiave e user_id "
          "puoi incollare la stringa &api_key=...&user_id=...)")
    for nome, desc, suggerito in voci:
        attuale = env.leggi(nome)
        predefinito = f" [{suggerito}]" if attuale is None and suggerito else ""
        risposta = input(f"{nome} - {desc}, ora: {maschera(nome, attuale)}{predefinito}\n> ").strip()
        cred = estrai_credenziali(risposta)
        if cred:
            for n, d, _ in voci:
                if n.endswith("_KEY") and "key" in cred:
                    env.imposta(n, cred["key"])
                    print(f"  {n} impostata dalla stringa incollata")
                if n.endswith("_USER") and "user" in cred:
                    env.imposta(n, cred["user"])
                    print(f"  {n} impostato dalla stringa incollata")
            continue
        if risposta == "":
            if attuale is None and suggerito:
                env.imposta(nome, suggerito)
                print(f"  {nome}={suggerito} (valore suggerito)")
            continue
        if risposta == "-":
            print(f"  {nome} tolta" if env.rimuovi(nome) else f"  {nome} non c'era")
            continue
        env.imposta(nome, pulisci_valore(risposta))
        print(f"  {nome} impostata")


def interattivo(env: EnvFile):
    nomi = list(SITI)
    while True:
        print(f"\nFile: {env.path}" + ("   (modifiche non salvate)" if env.modificato else ""))
        for i, s in enumerate(nomi, 1):
            stato = " / ".join("ok" if env.leggi(n) else "manca" for n, _, _ in SITI[s])
            print(f"  {i}) {s:<26} [{stato}]")
        print("  m) mostra tutto   s) salva ed esci   q) esci senza salvare")
        scelta = input("> ").strip().lower()
        if scelta == "m":
            mostra(env)
        elif scelta == "s":
            if env.salva():
                print(f"Salvato in {env.path} (copia precedente: {env.path.name}.bak). Riavvia i bot.")
            else:
                print("Niente da salvare.")
            return
        elif scelta == "q":
            if env.modificato and input("Ci sono modifiche non salvate: uscire lo stesso? [s/N] ").lower() != "s":
                continue
            return
        elif scelta.isdigit() and 1 <= int(scelta) <= len(nomi):
            menu_sito(env, nomi[int(scelta) - 1])
        else:
            print("Scelta non valida.")


def main(argv: list[str]):
    percorso = None
    if "--file" in argv:
        i = argv.index("--file")
        if i + 1 >= len(argv):
            sys.exit("--file vuole un percorso")
        percorso = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return
    env = EnvFile(trova_file(percorso))

    if "--mostra" in argv:
        mostra(env)
        return
    if not argv:
        interattivo(env)
        return

    rimuovi = False
    for a in argv:
        if a == "--rimuovi":
            rimuovi = True
            continue
        if rimuovi:
            print(f"{a}: " + ("tolta" if env.rimuovi(a) else "non c'era"))
            continue
        if "=" not in a:
            sys.exit(f"Non capisco «{a}»: usa NOME=valore")
        nome, valore = a.split("=", 1)
        nome = nome.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", nome):
            sys.exit(f"Nome di variabile non valido: {nome}")
        cred = estrai_credenziali(valore)
        if cred and nome.endswith("_KEY"):
            if "key" in cred:
                env.imposta(nome, cred["key"])
            if "user" in cred:
                env.imposta(nome[:-4] + "_USER", cred["user"])
            print(f"{nome}: chiave (e user_id) ricavate dalla stringa incollata")
        else:
            env.imposta(nome, pulisci_valore(valore))
            print(f"{nome} impostata")
    if env.salva():
        print(f"Salvato in {env.path}. Riavvia i bot.")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (KeyboardInterrupt, EOFError):
        print("\nInterrotto: niente è stato salvato.")
