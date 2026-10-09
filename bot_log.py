"""
bot_log.py - log su file con rotazione, condiviso da telegram_bot.py, discord_bot.py e org_bot.py.

Avviati con pythonw (nessuna console) sys.stdout e sys.stderr sono None: print() e i traceback
andrebbero persi. attiva_log_su_file() li gira su  <script>.log  accanto allo script, con
rotazione automatica (2 MB per file, ultime 2 copie: <script>.log.1 e <script>.log.2).
Con una console normale (o se stdout esiste già, ad esempio org_bot caricato da discord_bot)
non fa niente.
"""
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path


class _FlussoSuLogger:
    """Oggetto simile a un file: ogni riga completa scritta qui finisce nel logger."""
    encoding = "utf-8"
    errors = "replace"

    def __init__(self, logger: logging.Logger):
        self._logger = logger
        self._buf = ""

    def write(self, s) -> int:
        s = s if isinstance(s, str) else str(s)
        self._buf += s
        while "\n" in self._buf:
            riga, self._buf = self._buf.split("\n", 1)
            riga = riga.rstrip("\r")
            if riga.strip():
                self._logger.info(riga)
        return len(s)

    def flush(self):
        pass

    def isatty(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def reconfigure(self, **kw):   # telegram_bot.py lo chiama per la console di Windows
        pass


def attiva_log_su_file(max_bytes: int = 2_000_000, copie: int = 2) -> None:
    forzato = os.environ.get("BOT_LOG_FILE") == "1"   # lo imposta bot_manager: stdout è /dev/null (Linux/Android)
    if sys.stdout is not None and sys.stderr is not None and not forzato:
        return
    percorso = Path(sys.argv[0] or __file__).resolve().with_suffix(".log")
    handler = RotatingFileHandler(percorso, maxBytes=max_bytes, backupCount=copie, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))   # le righe hanno già l'orario (vedi log())
    logger = logging.getLogger(f"bot_file_log.{percorso.stem}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:      # già attivato (es. org_bot caricato da discord_bot)
        return
    logger.addHandler(handler)
    logger.info(f"\n=== Avvio {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    flusso = _FlussoSuLogger(logger)
    if sys.stdout is None or forzato:
        sys.stdout = flusso
    if sys.stderr is None or forzato:
        sys.stderr = flusso
