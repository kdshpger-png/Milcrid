#!/bin/bash
# Einmalig mit Klaus' Passwort ausfuehren:   sudo bash ~/Milcrid/system/ollama_update_freigeben.sh
#
# Richtet den Knopf "Ollama aktualisieren" im Milcrid-Portal (Update > KI) ein:
#   1. kopiert das Update-Skript root-eigen nach /usr/local/sbin/milcrid-ollama-update
#   2. erlaubt Milcrid, GENAU dieses Skript ohne Passwort zu starten (/etc/sudoers.d/milcrid-ollama)
# Die Regel wird vorher mit visudo geprueft - eine fehlerhafte Datei wird nie aktiv.
# (Opus fuer Klaus, 14.09.2026)
set -euo pipefail
if [ "$(id -u)" != 0 ]; then echo "Bitte mit sudo starten: sudo bash $0"; exit 1; fi
HIER="$(cd "$(dirname "$0")" && pwd)"
NUTZER="${SUDO_USER:-miluh}"

install -o root -g root -m 755 "$HIER/milcrid-ollama-update" /usr/local/sbin/milcrid-ollama-update

REGEL=$(mktemp)
echo "$NUTZER ALL=(root) NOPASSWD: /usr/local/sbin/milcrid-ollama-update" > "$REGEL"
if visudo -cf "$REGEL"; then
  install -o root -g root -m 440 "$REGEL" /etc/sudoers.d/milcrid-ollama
  rm -f "$REGEL"
  echo "Fertig: Ollama laesst sich jetzt im Milcrid-Portal unter Update > KI aktualisieren."
else
  rm -f "$REGEL"
  echo "FEHLER: Regel ungueltig - nichts geaendert."; exit 1
fi
