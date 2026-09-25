#!/bin/bash
# milcrid-install.sh - richtet Milcrid auf einem frischen Ubuntu 24.04 (Server) ein.
#
# Aufruf als der kuenftige Milcrid-Benutzer (braucht sudo), aus dem entpackten Paket heraus:
#   bash milcrid-install.sh
# Das Paket enthaelt nur Programm: Milcrid/ und Milcrid-App/ - kein Gedaechtnis, keine
# Profile, keine Tests, keine Protokolle. Alles Benutzerbezogene kommt aus $NUTZER/$HOME.
#
# Jeder Schritt darf mehrfach laufen. Ausgaben landen zusaetzlich in ~/milcrid-install.log.
# Nie "apt autoremove" - das nimmt den NVIDIA-Treiber mit.
#
# Voraussetzung: eigener Rechner NUR fuer Milcrid, Ubuntu 24.04, NVIDIA-Karte (16 GB
# empfohlen) mit eingerichtetem Treiber. Milcrid ist ein Web-OS, keine App: es
# uebernimmt den Start des Rechners und darf Programme, Fenster und Neustart steuern.
# (Opus fuer Klaus, 16.09.2026 - erster Versuch auf dem eAcer; 26.09.2026 fuer GitHub)

set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

NUTZER="$(id -un)"
PAKET="$(cd "$(dirname "$0")" && pwd)"
LOG="$HOME/milcrid-install.log"
NODE_VERSION="22.23.2"
MODELLE="${MILCRID_MODELLE:-qwen3.5:9b qwen3.5:4b}"
AKTIVES_MODELL="${MILCRID_AKTIV:-qwen3.5:9b}"

exec > >(tee -a "$LOG") 2>&1
schritt() { echo; echo "=== $(date '+%H:%M:%S') $*"; }

[ "$NUTZER" = root ] && { echo "Bitte als normaler Benutzer starten, nicht als root."; exit 1; }
[ -d "$PAKET/Milcrid" ] && [ -d "$PAKET/Milcrid-App" ] || { echo "Milcrid/ oder Milcrid-App/ fehlt neben dem Skript."; exit 1; }

schritt "1 Pakete (ohne Empfehlungen, damit kein GNOME/gdm3 mitkommt)"
sudo apt-get update -qq
sudo apt-get install -y -qq --no-install-recommends \
  xserver-xorg xinit openbox unclutter x11-xserver-utils wmctrl xdotool scrot dbus-x11 \
  xdg-desktop-portal xdg-desktop-portal-gtk libgtk-3-0t64 libnss3 libgbm1 libasound2t64 \
  libxss1 libxtst6 libatk-bridge2.0-0t64 libcups2t64 \
  pipewire pipewire-pulse wireplumber \
  python3-venv python3-pip python3-tk espeak-ng \
  flatpak fonts-noto-color-emoji fonts-dejavu-core \
  libreoffice-writer libreoffice-calc libreoffice-impress libreoffice-draw libreoffice-math libreoffice-base \
  libreoffice-gtk3 kitty git curl ca-certificates nvtop zstd
if dpkg -l gdm3 2>/dev/null | grep -q ^ii; then echo "WARNUNG: gdm3 ist installiert - der uebernimmt sonst den Start."; fi

# Der Server-Installer laesst die Zeitzone auf UTC - Milcrid zeigte Uhr und Termine 2 h falsch.
sudo timedatectl set-timezone "${MILCRID_ZEITZONE:-Europe/Berlin}"

schritt "2 Snap-Programme (Firefox, Thunderbird)"
for s in firefox thunderbird; do snap list "$s" >/dev/null 2>&1 || sudo snap install "$s"; done

schritt "3 Flathub fuer den Benutzer (Apps aus dem Portal installieren)"
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

schritt "4 Ollama"
if ! command -v ollama >/dev/null; then curl -fsSL https://ollama.com/install.sh | sh; fi
sudo systemctl enable --now ollama
for _ in $(seq 30); do curl -sf http://127.0.0.1:11434/api/version >/dev/null && break; sleep 1; done
ollama --version

schritt "5 Programm nach $HOME kopieren"
# Programm immer erneuern, Einstellungen (*.json) nur anlegen, wenn sie fehlen -
# ein erneuter Lauf darf nichts zuruecksetzen, was der Nutzer im Portal eingestellt hat.
for d in Milcrid Milcrid-App; do
  rsync -a --exclude="*.json" "$PAKET/$d/" "$HOME/$d/"
  rsync -a --ignore-existing --include="*/" --include="*.json" --exclude="*" "$PAKET/$d/" "$HOME/$d/"
done
# Nur beim ersten Lauf setzen - ein erneuter Lauf darf die Modellwahl des Nutzers nicht zuruecksetzen.
[ -f "$HOME/Milcrid/.installiert" ] || echo "{\"modell\": \"$AKTIVES_MODELL\"}" > "$HOME/Milcrid/aktives_modell.json"
# Das Paket kennt den Heimordner nicht - Platzhalter @HOME@ (Bilder der Milcrid-Apps)
# beim ersten Einrichten durch den echten Ordner ersetzen.
[ -f "$HOME/Milcrid/.installiert" ] || sed -i "s#@HOME@#$HOME#g" "$HOME/Milcrid/apps.json"
touch "$HOME/Milcrid/.installiert"
mkdir -p "$HOME/Documents" "$HOME/Downloads"

schritt "6 Python-Umgebung"
[ -x "$HOME/Milcrid/venv/bin/python" ] || python3 -m venv "$HOME/Milcrid/venv"
"$HOME/Milcrid/venv/bin/pip" install -q --upgrade pip
"$HOME/Milcrid/venv/bin/pip" install -q -r "$HOME/Milcrid/requirements.txt"

schritt "7 Node $NODE_VERSION + Electron"
export NVM_DIR="$HOME/.nvm"
if [ ! -s "$NVM_DIR/nvm.sh" ]; then
  git clone -q --depth 1 https://github.com/nvm-sh/nvm.git "$NVM_DIR"
fi
set +u; . "$NVM_DIR/nvm.sh"; nvm install "$NODE_VERSION" >/dev/null; nvm alias default "$NODE_VERSION" >/dev/null; set -u
(cd "$HOME/Milcrid-App" && npm ci --no-audit --no-fund && node node_modules/electron/install.js)
for _ in $(seq 60); do [ -f "$HOME/Milcrid-App/node_modules/electron/dist/chrome-sandbox" ] && break; sleep 1; done
# Ohne root-eigenes SUID-Sandbox-Programm bricht Electron sofort mit SIGTRAP ab
# (Ubuntu 24.04 sperrt die Alternative, unprivilegierte User-Namespaces, per AppArmor).
sudo chown root:root "$HOME/Milcrid-App/node_modules/electron/dist/chrome-sandbox"
sudo chmod 4755 "$HOME/Milcrid-App/node_modules/electron/dist/chrome-sandbox"
ldd "$HOME/Milcrid-App/node_modules/electron/dist/electron" | grep "not found" && { echo "Electron: Bibliotheken fehlen"; exit 1; } || echo "Electron: Bibliotheken vollstaendig"

schritt "8 KI-Modelle laden: $MODELLE"
for m in $MODELLE; do ollama pull "$m"; done

schritt "9 Spracherkennung (faster-whisper large-v3) vorab laden"
"$HOME/Milcrid/venv/bin/python" -c "from faster_whisper.utils import download_model; print(download_model('large-v3'))"

schritt "10 Kiosk-Start einrichten"
cat > "$HOME/.xinitrc" <<'XINIT'
#!/bin/bash
xset -dpms
export GDK_SCALE=1
export GDK_DPI_SCALE=1.6
echo "Xft.dpi: 153" | xrdb -merge
export XDG_CURRENT_DESKTOP=GNOME
xset s off
xset s noblank
unclutter &
openbox &
# xdg-desktop-portal startet ohne volle Desktop-Sitzung nicht von selbst -
# ohne ihn oeffnen Flatpak-Programme nie ein Fenster.
/usr/libexec/xdg-desktop-portal-gtk &
/usr/libexec/xdg-desktop-portal &
sleep 1
# Ein main.py aus einer frueheren Sitzung haengt an der Anmeldesitzung, nicht am
# Kiosk-Dienst, und ueberlebt dessen Neustart - samt Grafikspeicher und altem Code.
# Erst beenden (hat bis zu 15 s zum Speichern), dann frisch starten.
pkill -TERM -u "$USER" -f "^python3 -u main.py --portal" && for _ in $(seq 15); do pgrep -u "$USER" -f "^python3 -u main.py --portal" >/dev/null || break; sleep 1; done
pkill -KILL -u "$USER" -f "^python3 -u main.py --portal"
cd ~/Milcrid && source venv/bin/activate && python3 -u main.py --portal &
sleep 2
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
nvm use default > /dev/null
cd ~/Milcrid-App && node_modules/.bin/electron . --kiosk --force-device-scale-factor=1.6
# Electron beendet -> ganze X-Sitzung beenden, damit systemd neu startet.
pkill -9 -f "Xorg :0" 2>/dev/null
XINIT
chmod +x "$HOME/.xinitrc"

sudo tee /etc/systemd/system/milcrid-kiosk.service >/dev/null <<UNIT
[Unit]
Description=Milcrid Kiosk Portal
After=systemd-user-sessions.service getty@tty1.service ollama.service
Conflicts=getty@tty1.service

[Service]
Type=simple
User=$NUTZER
PAMName=login
WorkingDirectory=$HOME
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
TTYVTDisallocate=yes
StandardInput=tty
StandardOutput=journal
StandardError=journal
UtmpIdentifier=tty1
UtmpMode=user
ExecStart=/usr/bin/startx $HOME/.xinitrc -- vt1
Restart=always
RestartSec=3
TimeoutStopSec=20
# PAMName=login legt alles ab startx in eine eigene Anmeldesitzung - systemds SIGTERM
# erreicht darum nur startx (ein sh-Skript, das ihn nicht weitergibt). Ohne diese
# Zeilen wird startx nach der Wartezeit hart beendet und X, Electron und main.py
# bleiben verwaist zurueck (X-Sperrdatei bleibt liegen -> naechster Start auf :1).
# xinit beendet auf SIGTERM X und Sitzung sauber; main.py bekommt es danach selbst.
ExecStop=-/usr/bin/pkill -TERM -u $NUTZER -f "^xinit $HOME/.xinitrc"
ExecStopPost=-/usr/bin/pkill -TERM -u $NUTZER -f "^python3 -u main.py --portal"

[Install]
WantedBy=multi-user.target
UNIT
# Nach einem Absturz bleibt sonst /tmp/.X0-lock liegen und X landet auf :1.
echo 'r! /tmp/.X[0-9]*-lock' | sudo tee /etc/tmpfiles.d/milcrid-x11-lock.conf >/dev/null

schritt "11 Sudo-Freigaben (nur diese Befehle ohne Passwort)"
regel() {  # regel <datei> <inhalt> - erst pruefen, dann aktivieren
  local t; t=$(mktemp); echo "$2" > "$t"
  if sudo visudo -cf "$t" >/dev/null; then sudo install -o root -g root -m 440 "$t" "/etc/sudoers.d/$1"; echo "ok: $1"; else echo "FEHLER in Regel $1"; fi
  rm -f "$t"
}
regel milcrid-power "$NUTZER ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff, /usr/bin/systemctl reboot"
regel milcrid-paketverwaltung "$NUTZER ALL=(root) NOPASSWD: /usr/bin/apt, /usr/bin/apt-get, /usr/bin/update-alternatives, /usr/bin/snap"
sudo bash "$HOME/Milcrid/system/ollama_update_freigeben.sh"

schritt "12 Startmenue, falls Windows daneben liegt"
if sudo os-prober 2>/dev/null | grep -qi windows; then
  # Menue 10 s zeigen und das zuletzt gewaehlte System merken - sonst landet ein
  # Windows-Neustart (z. B. fuer Updates) jedes Mal in Milcrid.
  sudo sed -i -e "s/^GRUB_DEFAULT=.*/GRUB_DEFAULT=saved/" -e "s/^GRUB_TIMEOUT_STYLE=.*/GRUB_TIMEOUT_STYLE=menu/" \
              -e "s/^GRUB_TIMEOUT=.*/GRUB_TIMEOUT=10/" /etc/default/grub
  for z in "GRUB_SAVEDEFAULT=true" "GRUB_DISABLE_OS_PROBER=false"; do
    grep -q "^${z%%=*}=" /etc/default/grub || echo "$z" | sudo tee -a /etc/default/grub >/dev/null
  done
  # Nach einem Neustart AUS Milcrid kein Menue: ein Dienst merkt sich beim Neustart (nicht beim Ausschalten)
  # "milcrid_neustart=1" in grubenv, GRUB loescht den Merker und startet ohne Wartezeit.
  # Muss NACH 30_os-prober liegen - der setzt bei einem zweiten System die Wartezeit wieder auf 10 s.
  printf '%s\n' '#!/bin/sh' "cat <<'EOF'" \
    'if [ "${milcrid_neustart}" = "1" ]; then' '  set milcrid_neustart=' '  save_env milcrid_neustart' \
    '  set timeout_style=hidden' '  set timeout=0' 'fi' 'EOF' | sudo tee /etc/grub.d/45_milcrid_neustart >/dev/null
  sudo chmod 755 /etc/grub.d/45_milcrid_neustart
  printf '%s\n' '[Unit]' 'Description=Milcrid: Neustart merken (kein Startmenue beim naechsten Start)' \
    'DefaultDependencies=no' 'After=local-fs.target' 'Before=shutdown.target' 'Conflicts=shutdown.target' '' \
    '[Service]' 'Type=oneshot' 'RemainAfterExit=yes' 'ExecStart=/bin/true' \
    'ExecStop=/bin/sh -c '"'"'if systemctl list-jobs | grep -Eq "reboot.target +start"; then grub-editenv /boot/grub/grubenv set milcrid_neustart=1; fi'"'" \
    '' '[Install]' 'WantedBy=multi-user.target' | sudo tee /etc/systemd/system/milcrid-neustart-merker.service >/dev/null
  sudo systemctl daemon-reload
  sudo systemctl enable --now milcrid-neustart-merker.service
  sudo update-grub
  echo "Hinweis: Manche BIOS (z. B. Medion) stellen Windows fest an die erste Stelle - dort Ubuntu nach vorn stellen."
  echo "Hinweis: In Windows RealTimeIsUniversal=1 setzen, sonst geht die Windows-Uhr falsch."
else
  echo "Kein Windows gefunden - nichts zu tun."
fi

schritt "13 Kiosk einschalten"
sudo systemctl daemon-reload
sudo systemd-tmpfiles --create /etc/tmpfiles.d/milcrid-x11-lock.conf || true
sudo systemctl enable milcrid-kiosk.service

schritt "Fertig. Nach einem Neustart startet Milcrid von selbst."
