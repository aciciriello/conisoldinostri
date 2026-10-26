#!/bin/bash
# Installa (o rimuove) l'aggiornamento settimanale automatico su macOS.
#   bash scripts/programma_settimanale.sh            installa: ogni lunedì alle 7:30
#   bash scripts/programma_settimanale.sh rimuovi    disinstalla
# Su un server Linux usare invece cron, per esempio:
#   30 7 * * 1 cd /percorso/CruscottoSpesaStato && .venv/bin/python scripts/aggiorna.py
set -euo pipefail

PROGETTO="$(cd "$(dirname "$0")/.." && pwd)"
ETICHETTA="it.conisoldinostri.aggiorna"
PLIST="$HOME/Library/LaunchAgents/$ETICHETTA.plist"

if [[ "${1:-}" == "rimuovi" ]]; then
  launchctl bootout "gui/$(id -u)/$ETICHETTA" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Aggiornamento settimanale rimosso."
  exit 0
fi

[[ -x "$PROGETTO/.venv/bin/python" ]] || { python3 -m venv "$PROGETTO/.venv"; "$PROGETTO/.venv/bin/pip" install -q -r "$PROGETTO/requirements.txt"; }
mkdir -p "$PROGETTO/scripts/rapporti" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$ETICHETTA</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PROGETTO/.venv/bin/python</string>
    <string>$PROGETTO/scripts/aggiorna.py</string>
  </array>
  <key>WorkingDirectory</key><string>$PROGETTO</string>
  <key>StartCalendarInterval</key>
  <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardOutPath</key><string>$PROGETTO/scripts/rapporti/launchd.log</string>
  <key>StandardErrorPath</key><string>$PROGETTO/scripts/rapporti/launchd.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$ETICHETTA" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Aggiornamento settimanale installato: ogni lunedì alle 7:30."
echo "Per provarlo subito:  launchctl kickstart gui/$(id -u)/$ETICHETTA"
echo "Rapporto:             $PROGETTO/scripts/rapporti/ultimo.md"
