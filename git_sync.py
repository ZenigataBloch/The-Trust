"""
git pull a prova di conflitti sui file .json di stato (autoupdate.json, graves_redgifs_token.json, ...).

Quei file cambiano da soli mentre il bot gira: se sono tracciati da git, il pull si blocca con
«unmerged files» / «local changes would be overwritten». Questo modulo, prima del pull:
  1. chiude un merge/stash rimasto a metà e azzera i conflitti (git merge --abort; git reset),
  2. fa una COPIA dei .json modificati/cancellati/in conflitto (il tuo token e i contatori non si perdono),
  3. scarta le modifiche locali a quei file, così il pull passa,
  4. fa git pull --ff-only,
  5. rimette al loro posto le copie (anche se il repository, nel frattempo, ha smesso di tracciarli).
Altri file in conflitto NON vengono toccati: in quel caso si ferma e lo dice.

Uso:   python git_sync.py [cartella]         oppure     from git_sync import git_pull_sicuro
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _git(cartella: Path, *args: str, ok_errore: bool = False) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *args], cwd=cartella, capture_output=True, text=True)
    if r.returncode and not ok_errore:
        raise RuntimeError(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()}")
    return r


def _file_json_sporchi(cartella: Path) -> tuple[list[str], list[str]]:
    """(json da salvare e scartare, altri file con modifiche/conflitti)."""
    out = _git(cartella, "status", "--porcelain", "-z").stdout
    voci = [v for v in out.split("\0") if v]
    json_, altri = [], []
    i = 0
    while i < len(voci):
        v = voci[i]
        stato, nome = v[:2], v[3:]
        if stato[0] in "RC":                  # rinomina: la voce successiva è il vecchio nome
            i += 1
        i += 1
        if stato == "??":
            continue                          # file non tracciati: non bloccano il pull
        (json_ if nome.lower().endswith(".json") else altri).append(nome)
    return json_, altri


def git_pull_sicuro(cartella=".", log=print) -> str:
    """Esegue il pull. Restituisce l'output di git; solleva RuntimeError se non riesce."""
    cartella = Path(cartella).resolve()
    _git(cartella, "merge", "--abort", ok_errore=True)    # niente da annullare = errore ignorato
    _git(cartella, "reset", "-q", ok_errore=True)         # toglie i conflitti dall'indice, lascia i file
    sporchi, altri = _file_json_sporchi(cartella)
    copie = Path(tempfile.mkdtemp(prefix="git_sync_"))
    salvati = []
    try:
        for nome in sporchi:
            sorgente = cartella / nome
            if sorgente.exists():
                (copie / nome).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sorgente, copie / nome)
                salvati.append(nome)
            _git(cartella, "checkout", "--", nome, ok_errore=True)    # scarta la modifica locale
        if sporchi:
            log(f"git: file di stato messi da parte prima del pull: {', '.join(sporchi)}")
        altri = _file_json_sporchi(cartella)[1]
        if altri:
            raise RuntimeError("ci sono altri file modificati o in conflitto che non tocco: " + ", ".join(altri)
                               + "  (risolvili a mano con git status)")
        esito = _git(cartella, "pull", "--ff-only")
        return (esito.stdout or esito.stderr).strip()
    finally:
        for nome in salvati:                               # rimetto i miei dati, comunque sia andato il pull
            destinazione = cartella / nome
            destinazione.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(copie / nome, destinazione)
        shutil.rmtree(copie, ignore_errors=True)


if __name__ == "__main__":
    try:
        print(git_pull_sicuro(sys.argv[1] if len(sys.argv) > 1 else "."))
    except Exception as e:
        print(f"⚠ git pull non riuscito: {e}")
        sys.exit(1)
