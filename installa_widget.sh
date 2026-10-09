#!/data/data/com.termux/files/usr/bin/bash
# installa_widget.sh - crea gli script per Termux:Widget in ~/.shortcuts/tasks
#
# Uso (in Termux, nella cartella del repo):   bash installa_widget.sh
# Si può rilanciare quando vuoi: sovrascrive gli script. Se sposti la cartella del repo, rilancialo.
# Serve: app Termux:Widget (F-Droid) e, per le notifiche, Termux:API (pkg install termux-api).
#
# Widget creati (gli script girano in background, senza aprire il terminale, e rispondono con un toast):
#   Bot-Avvia       aggiorna da GitHub e accende i bot che non girano
#   Bot-Ferma       spegne i bot
#   Bot-Stato       mostra quali bot girano
#   Bot-Aggiorna    controlla GitHub e aggiorna ora (riavvia solo i bot interessati)
#   Cookie-Aggiorna importa i cookie copiati negli appunti (aggiorna_cookies.py --clipboard)
#   Bot-Log         mostra in una notifica le ultime righe dei log

set -e
REPO="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.shortcuts/tasks"
mkdir -p "$DEST"

scrivi() {   # $1 = nome del widget; il corpo arriva da stdin
    {
        echo '#!/data/data/com.termux/files/usr/bin/bash'
        echo "cd \"$REPO\" || { termux-toast \"Cartella non trovata: $REPO\"; exit 1; }"
        cat
    } > "$DEST/$1"
    chmod +x "$DEST/$1"
    echo "  creato: $1"
}

scrivi Bot-Avvia <<'EOF'
termux-wake-lock
OUT=$(python avvia_bots.py avvia 2>&1 | tail -n 2)
termux-toast -g middle "$OUT"
EOF

scrivi Bot-Ferma <<'EOF'
OUT=$(python avvia_bots.py stop 2>&1 | tail -n 2)
termux-wake-unlock
termux-toast -g middle "$OUT"
EOF

scrivi Bot-Stato <<'EOF'
OUT=$(python avvia_bots.py stato 2>&1 | tail -n 2)
termux-toast -g middle "$OUT"
EOF

scrivi Bot-Aggiorna <<'EOF'
OUT=$(python avvia_bots.py update 2>&1 | tail -n 3)
termux-toast -g middle "$OUT"
EOF

scrivi Cookie-Aggiorna <<'EOF'
# l'ultima riga di aggiorna_cookies.py è il riepilogo di una riga fatto per il toast
OUT=$(python aggiorna_cookies.py --clipboard 2>&1 | tail -n 1)
termux-toast -g middle "$OUT"
EOF

scrivi Bot-Log <<'EOF'
OUT=""
for f in telegram_bot.log discord_bot.log; do
    if [ -f "$f" ]; then
        OUT="$OUT[$f]
$(tail -n 5 "$f" | cut -c1-110)
"
    fi
done
[ -z "$OUT" ] && OUT="Nessun log ancora: avvia prima i bot."
termux-notification --id bot-log --title "Log dei bot" --content "$OUT"
EOF

echo
echo "Fatto. Ora, sulla schermata Home di Android:"
echo "  tieni premuto -> Widget -> Termux:Widget -> trascina il widget, poi apri la cartella 'tasks'."
