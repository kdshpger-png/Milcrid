const { app, BrowserWindow, ipcMain, Menu, MenuItem, shell, dialog, Notification } = require('electron');
const path = require('path');
const os = require('os');
const fs = require('fs');
const { spawn, execSync, execFile, execFileSync } = require('child_process');
const { promisify } = require('util');
const execFileAsync = promisify(execFile);

// DBUS_SESSION_BUS_ADDRESS kommt hier automatisch von der systemd-Login-
// Session mit (auch wenn .xinitrc sie nirgends setzt) und zeigt auf den
// echten systemd-Nutzer-Bus (/run/user/1000/bus). Fatal fuer gestartete
// Linux-Programme: gio/Snap-Programme wie Firefox versuchen dann, darueber
// z.B. eine Accessibility-Bus-Verbindung aufzubauen, und HAENGEN sich dabei
// auf UNBEGRENZTE Zeit auf (nicht nur langsam - mehrere Minuten getestet,
// nie zurueckgekommen), statt regulaer ihr Fenster zu oeffnen - exakt der
// Grund, warum "Firefox" bisher nur als Taskleisten-Icon ohne Fenster
// erschien. Ohne diese Variable starten dieselben Programme sofort
// (Klaus/Claude 2026-08-19, ausfuehrlich mit Test-Skripten nachvollzogen).
// Frueh entfernen (vor jedem execFile/spawn weiter unten), damit KEIN von
// main.js gestartetes Programm sie je erbt.
delete process.env.DBUS_SESSION_BUS_ADDRESS;

// Sicherheitsnetz: ohne das beendet Node bei JEDER unbehandelten Exception
// sofort den kompletten Prozess ("A JavaScript error occurred in the main
// process" - fuer einen Kiosk, der einfach immer laufen soll, das
// schlechteste denkbare Verhalten, siehe LibreOffice-Absturz am 2026-08-19).
// Nur protokollieren und weiterlaufen, statt zu sterben.
process.on('uncaughtException', (fehler) => {
  linuxAppLogZeile(`UNBEHANDELTE EXCEPTION (App laeuft trotzdem weiter): ${fehler && fehler.stack ? fehler.stack : fehler}`);
});
process.on('unhandledRejection', (fehler) => {
  linuxAppLogZeile(`UNBEHANDELTE PROMISE-ABLEHNUNG (App laeuft trotzdem weiter): ${fehler && fehler.stack ? fehler.stack : fehler}`);
});

const MILCRID_DIR = path.join(os.homedir(), 'Milcrid');
const PORTAL_HTML = path.join(MILCRID_DIR, 'milcrid_portal.html');
const ICON_PATH = path.join(__dirname, 'icon-256.png');
const PRELOAD_PATH = path.join(__dirname, 'preload.js');
// Welche Programm-Kacheln in Apps liegen (aus "Apps hinzufuegen" verknuepft) -
// liegt bewusst in ~/Milcrid (nicht ~/Milcrid-App), so kann Milcrid selbst spaeter
// ueber ihre normalen Datei-Werkzeuge mitlesen/mitschreiben, unabhaengig
// davon ob der Portal-Server/Ollama gerade laeuft.
const APPS_LISTE_PATH = path.join(MILCRID_DIR, 'apps.json');
// Gleicher Grund wie bei apps.json: in ~/Milcrid, nicht ~/Milcrid-App.
// Schreibtisch (Klaus-Wunsch 2026-08-21): eigene, benannte Icon-Sammlungen,
// mehrere gleichzeitig als eigenes Fenster offenbar (wie Datei Manager) -
// bewusst eine eigene Datei statt in apps.json mit reinzupacken, damit die
// schon recht komplexe apps.json (Seiten-Buttons, Milcrid-Apps, Reihenfolgen)
// nicht noch mehr Struktur traegt.
const SCHREIBTISCHE_PATH = path.join(MILCRID_DIR, 'schreibtische.json');
// Jeder Schreibtisch bekommt einen ECHTEN Ordner hier drunter, benannt nach
// seinem Titel (Klaus-Wunsch 2026-08-21: "in dem Ordner speichern können,
// also den angelegten über Schreibtisch") - LibreOffice & Co. koennen dann
// per normalem Speichern-Dialog direkt dort hineinspeichern, nicht nur per
// Ziehen aus dem Datei Manager. Deshalb ein auffindbarer Name statt einer
// internen id als Ordnername.
const SCHREIBTISCH_ORDNER_BASIS = path.join(MILCRID_DIR, 'Schreibtisch Ablagen');
function schreibtischOrdnerName(titel){
  // Zeichen raus, die im Dateisystem Probleme machen wuerden - leerer Rest
  // (z.B. Titel bestand nur aus solchen Zeichen) faellt auf einen festen
  // Namen zurueck statt einen leeren/seltsamen Ordner anzulegen.
  const sicher = String(titel || '').replace(/[\/\\:*?"<>|]/g, '').trim();
  return sicher || 'Schreibtisch';
}
// Jede Milcrid-App liegt in einem eigenen Unterordner hier drin, z.B.
// "Milcrid Apps/kalender/kalender.html" + "kalender.js" - sowohl fest
// mitgelieferte als auch spaeter aus dem echten Milcrid App Store
// heruntergeladene (siehe milcridAppInstallieren weiter unten).
const MILCRID_APPS_DIR = path.join(__dirname, 'Milcrid Apps');

// Programme, die ueber "Vom PC (Linux)" gestartet wurden und noch laufen
// (fuer die Taskleiste unten links im Portal) - Map exec -> {name, icon, exec,
// timer}, damit ein neu geoeffnetes Portalfenster (Reload) sofort den
// aktuellen Stand kennt, ohne dass main.js selbst Name/Icon nachschlagen muss
// (die Portal-Seite kennt beides schon aus der Kachel). "timer" wird beim
// Versand rausgefiltert (siehe sendeLaufendeProgrammeAnAlleFenster), sonst
// laesst sich das nicht ueber IPC verschicken.
const laufendePrograme = new Map();
// Protokoll fuer die Linux-App-Start-Diagnose (Firefox-Mehrfachfenster-
// Untersuchung und die spaeteren Fokus-Probleme) - ein Log, gemeinsam von
// _appNachVorneHolen und dem linux-app-starten-Handler benutzt.
const linuxAppLogPfad = path.join(MILCRID_DIR, 'linux-app-start.log');
function linuxAppLogZeile(zeile) {
  try { fs.appendFileSync(linuxAppLogPfad, new Date().toISOString() + ' ' + zeile + '\n', 'utf-8'); } catch (e) {}
}
// Liefert die Fenster-Kennung (WM_CLASS), unter der ein Programm seine
// Fenster beim Fenstermanager anmeldet - Grundlage fuer die wmctrl-Aufrufe
// unten (ActivateApp/GetWindowCount, frueher ueber eine eigene GNOME-Shell-
// Erweiterung geloest, siehe Begruendung dort). Bevorzugt "StartupWMClass"
// aus der Desktop-Datei selbst (der vom Programm SELBST angegebene Wert,
// z.B. bei Firefox "firefox_firefox" - exakt geprueft, passt); ist der nicht
// gesetzt, als Rueckfall der Desktop-Datei-Name ohne ".desktop" (trifft bei
// vielen Programmen zufaellig genauso zu, ist aber nur eine Vermutung).
function _wmClassFuerDesktopDatei(pfad) {
  try {
    const werte = desktopDateiLesen(fs.readFileSync(pfad, 'utf-8'));
    if (werte.StartupWMClass) return werte.StartupWMClass;
  } catch (e) {}
  return path.basename(pfad, '.desktop');
}
// Liefert die WM_CLASS, MIT der ein Terminal=true-Programm OHNE eigene
// StartupWMClass selbst gestartet werden muss (siehe _appStarten) - sonst
// null (dann ganz normal ueber "gio launch").
//
// WARUM (Klaus, 2026-08-23: htop 8x, nvtop 4x offen gewesen, obwohl jeweils
// nur einmal geklickt - dasselbe Grundproblem wie vorher schon bei Zutty,
// nur dort ueber einen anderen Umweg sichtbar): "gio launch" wrappt
// Terminal=true selbst ueber den System-Standard-Terminal
// (x-terminal-emulator), OHNE dass wir dessen WM_CLASS beeinflussen koennen.
// kitty meldet dabei IMMER "kitty.kitty", egal welches Programm darin
// laeuft - der Rueckfall in _wmClassFuerDesktopDatei (Dateiname, z.B.
// "nvtop") passt darum NIE zum echten Fenster. Die Fenster-Pruefung
// (_fensterAnzahlUeberErweiterung) sieht dadurch DAUERHAFT 0 Fenster, obwohl
// eins offen ist - das Erststart-Fokus-Sicherheitsnetz (_appNachVorneHolen)
// haelt das faelschlich fuer "noch kein Fenster da" und schiebt JEDES MAL
// einen zweiten Start nach, und nach ein paar weiteren Pruefungen wird das
// (laengst offene) Icon sogar wieder entfernt.
// Fix: den Terminal-Start selbst uebernehmen, mit einer WM_CLASS, die EXAKT
// der Rueckfall-Kennung entspricht (Dateiname ohne ".desktop") - dann passt
// die Fenster-Pruefung wieder von selbst, ohne jede Terminal-Desktop-Datei
// einzeln von Hand anfassen zu muessen. Gilt automatisch fuer jedes
// kuenftige Terminal-Programm mit dazu.
function _terminalWmClassFuerDesktopDatei(pfad) {
  try {
    const werte = desktopDateiLesen(fs.readFileSync(pfad, 'utf-8'));
    if (werte.Terminal === 'true' && !werte.StartupWMClass) return path.basename(pfad, '.desktop');
  } catch (e) {}
  return null;
}
// Aufloesung des GERADE aktiven Standard-Terminals - nicht fest verdrahtet
// (z.B. auf "kitty"), damit ein spaeterer Terminal-Wechsel (wie der von
// Zutty auf kitty, 2026-08-22) hier nichts erneut kaputt macht.
function _standardTerminalPfad() {
  try { return fs.realpathSync('/etc/alternatives/x-terminal-emulator'); }
  catch (e) { return 'kitty'; }
}
// Startet ein Programm entweder ueber unseren eigenen Terminal-Wrapper
// (siehe _terminalWmClassFuerDesktopDatei) oder ganz normal ueber
// "gio launch <Desktop-Datei>" - EIN Ort fuer diese Entscheidung, damit
// sowohl der erste Start (ipcMain "linux-app-starten") als auch der
// Rueckfall-Neustart in _appNachVorneHolen (nochmalStarten) denselben Weg
// nehmen; sonst wuerde ein Rueckfall-Neustart fuer ein Terminal-Programm
// wieder auf "gio launch" zurueckfallen und in dieselbe WM_CLASS-Falle
// laufen.
/* Eine Adresse im Browser oeffnen - BEWUSST anders als _appStarten.
 *
 * Klaus-Fund 2026-09-04 ("firefox hat den link nicht bekommen also leere ff
 * seite"), auf Milcrid nachgemessen:
 *
 *   gio launch firefox.desktop <url>   bei schon laufendem Firefox
 *     -> startet einen ZWEITEN Prozess (pids 158807 + 161280),
 *        der am Profil des ersten scheitert:
 *        "Firefox is already running, but is not responding",
 *        die Adresse geht dabei verloren.
 *
 *   /snap/bin/firefox <url>            mit DBUS_SESSION_BUS_ADDRESS
 *     -> KEIN neuer Prozess (dieselbe PID 163375), die Seite erscheint
 *        als neuer Tab im vorhandenen Fenster. Genau richtig.
 *
 * Der Unterschied: der zweite Weg spricht Firefox' eigene Fernsteuerung an,
 * und die braucht DBUS_SESSION_BUS_ADDRESS. Die wird ganz oben in dieser
 * Datei absichtlich aus der Umgebung geloescht (sonst haengen sich Snap-
 * Programme beim ERSTEN Start auf) - hier also gezielt fuer dieses eine
 * Kind wieder hineinreichen, wie beim Flatpak-Fall weiter oben.
 */
function _adresseOeffnen(pfad, url, laeuftSchon) {
  let werte;
  try { werte = desktopDateiLesen(fs.readFileSync(pfad, 'utf-8')); }
  catch (e) { werte = {}; }
  const exec = (werte.Exec || '').replace(/%[a-zA-Z]/g, '').trim();
  const teile = exec.split(' ').filter(Boolean);
  if (!teile.length) {
    linuxAppLogZeile(`Adresse: keine Exec-Zeile in ${pfad} - fallback auf gio launch`);
    _appStarten(pfad, 'Adresse (Rueckfall)', url);
    return;
  }
  const umgebung = process.env.XDG_RUNTIME_DIR
    ? { ...process.env, DBUS_SESSION_BUS_ADDRESS: `unix:path=${process.env.XDG_RUNTIME_DIR}/bus` }
    : process.env;
  // Geerbte "Capabilities" abwerfen - genau wie beim Flatpak-Start weiter
  // oben. Der Elektron-Hauptprozess erbt vom Kiosk-Start Rechte, die ein
  // eingesperrtes Programm (Snap wie Flatpak) durcheinanderbringen. Genau
  // deshalb klappte derselbe Befehl von Hand per SSH, aber nicht aus
  // Milcrid heraus - dieselbe Beobachtung wie damals bei bwrap.
  const roh = [...teile.slice(1), url];
  const befehlsTeile = fs.existsSync('/usr/bin/setpriv')
    ? ['/usr/bin/setpriv', '--ambient-caps=-all', '--inh-caps=-all', '--', teile[0], ...roh]
    : [teile[0], ...roh];
  linuxAppLogZeile(`Adresse direkt: ${befehlsTeile.join(' ')} (laeuftSchon=${laeuftSchon})`);
  const kind = spawn(befehlsTeile[0], befehlsTeile.slice(1),
                     { detached: true, stdio: 'ignore', env: umgebung });
  kind.on('error', (fehler) => {
    linuxAppLogZeile(`Adresse FEHLGESCHLAGEN: ${fehler.message} - fallback auf gio launch`);
    _appStarten(pfad, 'Adresse (Rueckfall nach Fehler)', url);
  });
  kind.unref();
}

function _appStarten(pfad, kontext, url) {
  const terminalKlasse = _terminalWmClassFuerDesktopDatei(pfad);
  if (terminalKlasse) {
    let werte;
    try { werte = desktopDateiLesen(fs.readFileSync(pfad, 'utf-8')); } catch (e) { werte = {}; }
    const exec = (werte.Exec || '').replace(/%[a-zA-Z]/g, '').trim();
    const teile = exec.split(' ').filter(Boolean);
    if (!teile.length) return;
    const terminalPfad = _standardTerminalPfad();
    linuxAppLogZeile(`Terminal-Start selbst uebernommen (${kontext}): pfad="${pfad}" class="${terminalKlasse}" exec="${exec}"`);
    const kindprozess = spawn(terminalPfad, ['--class', terminalKlasse, '-e', ...teile], { detached: true, stdio: 'ignore' });
    kindprozess.on('error', (fehler) => {
      linuxAppLogZeile(`Terminal-Start FEHLGESCHLAGEN (${kontext}): pfad="${pfad}" fehler="${fehler.message}"`);
    });
    kindprozess.unref();
    return;
  }
  let werte;
  try { werte = desktopDateiLesen(fs.readFileSync(pfad, 'utf-8')); } catch (e) { werte = {}; }
  // Flatpak-Programme (X-Flatpak in der Desktop-Datei, also alles, was ueber
  // den Milcrid App Store von Flathub kommt) NICHT ueber "gio launch"
  // starten, sondern ihre Exec-Zeile direkt selbst ausfuehren.
  //
  // WARUM (Klaus, 2026-08-23, ueber Stunden eingegrenzt: erst "System
  // Monitoring Center", dann zur Gegenprobe VLC - beide gingen ueber einen
  // Portal-Klick NIE auf, Icon erschien kurz und verschwand wieder):
  // Ausschlussverfahren hat es auf genau eine Kombination eingegrenzt.
  //   - derselbe "gio launch"-Befehl von Hand per SSH: Fenster kommt sofort
  //   - derselbe Befehl per Node execFile aus einem NORMALEN node-Prozess
  //     (Testskript auf demselben Rechner/Nutzer/Display): Fenster kommt
  //   - derselbe Befehl per Node execFile aus dem ELECTRON-Hauptprozess:
  //     nichts passiert, oft startet nicht mal ein Prozess
  // Node, execFile und gio sind damit alle entlastet - es liegt an etwas im
  // Electron-Hauptprozess (Chromium veraendert u.a. Signalmasken und
  // Datei-Handles seiner Kindprozesse). Statt dem weiter nachzujagen: den
  // Umweg ueber gio hier einfach weglassen. spawn(..., detached) aus
  // demselben Electron-Prozess funktioniert nachweislich - genau so laeuft
  // seit demselben Tag schon der Terminal-Zweig oben (nvtop/htop), und ein
  // direkt gestartetes "flatpak run ..." wurde vor diesem Fix live
  // gegengeprueft (VLC-Fenster kam sofort).
  //
  // Nur fuer Flatpak umgestellt, nicht generell: Snap-/apt-Programme
  // (Firefox, Thunderbird, LibreOffice) laufen ueber "gio launch"
  // einwandfrei, und dessen Zusatznutzen (bringt eine schon laufende
  // Einzelinstanz von selbst nach vorne) soll ihnen erhalten bleiben.
  if (werte['X-Flatpak']) {
    // Exec-Zeile in Einzelteile zerlegen und die Platzhalter entfernen, die
    // nur fuer "mit Datei/URL geoeffnet" gedacht sind:
    //   %U/%f/... - Desktop-Datei-Platzhalter (wie ueberall sonst auch)
    //   @@u/@@    - Flatpaks eigene Datei-Weiterreich-Markierungen, die
    //               IMMER paarweise um solche Platzhalter stehen
    //   --file-forwarding - schaltet genau diese Markierungen ein und
    //               ergibt ohne sie keinen Sinn mehr
    // Beispiel VLC: "flatpak run --branch=stable --arch=x86_64
    //   --command=/app/bin/vlc --file-forwarding org.videolan.VLC
    //   --started-from-file @@u %U @@" wird zu "flatpak run --branch=stable
    //   --arch=x86_64 --command=/app/bin/vlc org.videolan.VLC
    //   --started-from-file" (genau so vorab von Hand getestet, Fenster kam).
    const teile = (werte.Exec || '').split(/\s+/).filter(Boolean).filter(t =>
      !/^%[a-zA-Z]$/.test(t) && !/^@@[uUfF]?$/.test(t) && t !== '--file-forwarding');
    if (!teile.length) return;
    if (url) teile.push(url);
    // DBUS_SESSION_BUS_ADDRESS wird ganz oben in dieser Datei ABSICHTLICH aus
    // der gesamten main.js-Umgebung entfernt (siehe Kommentar dort), weil
    // Snap-Programme wie Firefox sich sonst beim Start ewig aufhaengen.
    // Flatpak braucht sie aber fuer seinen Sandbox-/Portal-Mechanismus -
    // darum hier gezielt nur fuer dieses eine Kind wiederherstellen.
    const umgebung = process.env.XDG_RUNTIME_DIR
      ? { ...process.env, DBUS_SESSION_BUS_ADDRESS: `unix:path=${process.env.XDG_RUNTIME_DIR}/bus` }
      : process.env;
    // Vor dem eigentlichen Start die geerbten "Capabilities" abwerfen.
    //
    // WARUM (Klaus/Claude, 2026-08-23, nach stundenlanger Eingrenzung - das
    // war die eigentliche Ursache, warum ueber den Milcrid App Store
    // installierte Flathub-Programme NIE aufgingen, weder "System Monitoring
    // Center" noch VLC): Flatpak baut seine Sandbox mit "bwrap" auf, und
    // bwrap bricht mit
    //     "bwrap: Unexpected capabilities but not setuid, old file caps config?"
    //     "Fehler: Abgleich mit Dbus-Proxy ist fehlgeschlagen"
    // sofort ab, wenn der aufrufende Prozess ueberhaupt irgendwelche
    // Capabilities besitzt, ohne setuid zu sein - das ist eine
    // Sicherheitspruefung von bwrap selbst, kein Konfigurationsfehler.
    //
    // Genau das ist hier der Fall: der Kiosk-Dienst (milcrid-kiosk.service,
    // startet ueber "PAMName=login") bekommt CAP_WAKE_ALARM als "ambiente"
    // Capability mitgegeben, und ambiente Capabilities vererben sich an
    // JEDEN Kindprozess weiter - also auch an flatpak/bwrap. Nachgemessen:
    //     Electron  CapAmb: 0000000800000000   (Bit 35 = CAP_WAKE_ALARM)
    //     SSH-Shell CapAmb: 0000000000000000
    // Deshalb lief exakt derselbe Befehl von Hand per SSH immer sauber
    // durch, ueber einen Klick im Portal aber nie - dieselbe Datei, dieselbe
    // Umgebung, derselbe Nutzer, nur eben mit geerbter Capability.
    //
    // "setpriv" (util-linux, gehoert zum Grundsystem) wirft sie fuer genau
    // dieses eine Kind ab; die Kiosk-Sitzung selbst bleibt unveraendert.
    // Faellt setpriv wider Erwarten aus, lieber ohne starten als gar nicht.
    const befehlsTeile = fs.existsSync('/usr/bin/setpriv')
      ? ['/usr/bin/setpriv', '--ambient-caps=-all', '--inh-caps=-all', '--', ...teile]
      : teile;
    linuxAppLogZeile(`Flatpak-Start selbst uebernommen (${kontext}): pfad="${pfad}" DISPLAY="${umgebung.DISPLAY}" befehl="${befehlsTeile.join(' ')}"`);
    // Ausgabe NICHT wegwerfen, sondern in eine eigene Datei schreiben:
    // Flatpak meldet den Grund fuers Nicht-Starten (fehlender X11-Socket,
    // Sandbox-Problem, ...) ausschliesslich auf stderr, und mit "ignore" war
    // dieser Grund bisher nicht nachvollziehbar. Eine Datei statt einer Pipe,
    // damit der Kindprozess unabhaengig weiterlaufen kann (eine Pipe, die
    // niemand ausliest, wuerde ihn blockieren, sobald sie voll ist).
    let ausgabeZiel = 'ignore';
    try { ausgabeZiel = fs.openSync(path.join(MILCRID_DIR, 'flatpak-start.log'), 'a'); } catch (e) {}
    const kindprozess = spawn(befehlsTeile[0], befehlsTeile.slice(1), {
      detached: true,
      stdio: ausgabeZiel === 'ignore' ? 'ignore' : ['ignore', ausgabeZiel, ausgabeZiel],
      env: umgebung,
    });
    kindprozess.on('error', (fehler) => {
      linuxAppLogZeile(`Flatpak-Start FEHLGESCHLAGEN (${kontext}): pfad="${pfad}" fehler="${fehler.message}"`);
    });
    kindprozess.unref();
    return;
  }
  const argumente = url ? ['launch', pfad, url] : ['launch', pfad];
  linuxAppLogZeile(`gio launch (${kontext}): pfad="${pfad}" url="${url || ''}"`);
  // DBUS_SESSION_BUS_ADDRESS auch hier setzen - NICHT nur bei Flatpak.
  //
  // Klaus-Fund 2026-09-04, eingegrenzt durch einen Vergleichsversuch: Ein
  // Link aus dem Ergebnis-Fenster landete in einem leeren Firefox. Erst der
  // Vergleich zeigte, woran es liegt:
  //   Firefox von Hand (SSH) gestartet  -> Link wird sauber uebernommen,
  //                                        gleiche PID, neuer Tab
  //   Firefox von Milcrid gestartet     -> zweiter Prozess, "Firefox is
  //                                        already running but not responding"
  // Es lag also nicht am Oeffnen des Links, sondern am STARTEN von Firefox.
  // Ohne die Bus-Adresse kann Firefox seine eigene Fernsteuerung nicht
  // anmelden - ein spaeterer Aufruf findet es dann nicht und macht einen
  // zweiten Prozess auf, der am Profil des ersten scheitert.
  //
  // Die Variable wird ganz oben in dieser Datei absichtlich geloescht, weil
  // die von systemd geerbte Adresse ins Leere zeigte und Snap-Programme
  // daran ewig haengen blieben (2026-08-19). Hier wird sie NICHT geerbt,
  // sondern auf den echten, funktionierenden Bus gesetzt - genau den Wert,
  // mit dem der SSH-Start nachweislich funktioniert.
  const gioUmgebung = process.env.XDG_RUNTIME_DIR
    ? { ...process.env, DBUS_SESSION_BUS_ADDRESS: `unix:path=${process.env.XDG_RUNTIME_DIR}/bus` }
    : process.env;
  execFile('gio', argumente, { env: gioUmgebung }, (fehler, stdout, stderr) => {
    if (fehler) linuxAppLogZeile(`gio launch FEHLER (${kontext}): ${fehler.message} stderr="${(stderr || '').trim()}"`);
  });
}
// Versucht, das Fenster einer laufenden App ueber wmctrl (normales X11-
// Werkzeug, funktioniert mit jedem EWMH-Fenstermanager wie unserem Openbox -
// frueher stand hier ein Aufruf in eine eigene GNOME-Shell-Erweiterung
// hinein, die brauchte aber gnome-shell selbst als laufenden Fenstermanager,
// was wiederum GNOMEs eigene Oberflaeche sichtbar gemacht haette; wmctrl
// braucht dagegen gar kein GNOME) nach vorne zu holen (entminimieren + fokussieren -
// dasselbe wie ein Klick auf ein Dock-Icon). Hat die App noch GAR KEIN
// Fenster (z.B. D-Bus-aktivierbare Programme wie GNOME Settings, die beim
// ersten "gio launch" nur als Hintergrunddienst hochfahren, ohne ihr
// Hauptfenster zu oeffnen - siehe Klaus' 2026-08-11-Beobachtung: Icon
// erscheint, Fenster nicht, verschwindet nach ein paar Sekunden von selbst
// wieder), findet ActivateApp kein Fenster (erfolg=false) - dann als
// Rueckfall NOCH EINMAL "gio launch" schicken, exakt der Weg der beim
// manuellen Klick auf das Taskleisten-Icon nachweislich hilft (der zweite
// Activate-Aufruf bringt bei diesen Programmen tatsaechlich ein Fenster,
// der erste offenbar nicht zuverlaessig).
// darfNeuStarten: NUR bei einem echten Klick von Klaus true.
//
// WARUM DIESER SCHALTER (Klaus 2026-08-11: "mach ich die App klein, geht sie
// direkt wieder von alleine auf"): der gio-launch-Rueckfall unten startet die
// App NEU, wenn ActivateApp kein Fenster aktivieren konnte. Bei einem
// automatischen Aufruf (Erststart-Fokus aus dem 4-Sekunden-Takt) hiess das:
// Klaus minimiert das Fenster, im Hintergrund laeuft eine Pruefung, und die
// App wird ungefragt neu gestartet und steht wieder gross auf dem Schirm.
// Ein automatischer Aufruf darf ab jetzt nur noch ein VORHANDENES Fenster
// nach vorne holen - nie von sich aus etwas neu starten.
// optionen.aktivieren: darf ein VORHANDENES Fenster nach vorne geholt werden?
//   Nur bei einem echten Klick von Klaus. Ein automatischer Aufruf darf das
//   NIE - sonst holt er ein Fenster zurueck, das Klaus gerade absichtlich
//   klein gemacht hat (Klaus 2026-08-13: "mache ich es klein, geht es direkt
//   wieder auf" - der Erststart-Fokus lief noch und hat es entminimiert).
// optionen.neustarten: darf notfalls ein zweiter "gio launch" nachgeschoben
//   werden? Gebraucht fuer D-Bus-Apps wie GNOME Settings, bei denen der erste
//   Start nur den Hintergrunddienst hochfaehrt, ohne Fenster.
function _appNachVorneHolen(pfad, kontext, optionen){
  const desktopId = path.basename(pfad);
  const darfAktivieren = !!(optionen && optionen.aktivieren);
  const darfNeuStarten = !!(optionen && optionen.neustarten);
  const nochmalStarten = () => {
    linuxAppLogZeile(`Rueckfall-Neustart (${kontext}): pfad="${pfad}"`);
    _appStarten(pfad, `Rueckfall-${kontext}`);
  };
  // ZUERST fragen, ob die App ueberhaupt schon ein Fenster hat - das
  // entscheidet, was hier ueberhaupt richtig ist. Vorher wurde blind
  // ActivateApp geschickt und erst an dessen Fehlschlag erkannt, dass kein
  // Fenster da ist; ein vorhandenes (minimiertes) Fenster wurde dabei immer
  // mit hochgeholt, auch ungefragt.
  _fensterAnzahlUeberErweiterung(pfad, (fensterAnzahl, fensterMinimiert) => {
    if (!darfAktivieren) {
      // Automatischer Aufruf (Erststart-Fokus). Ein vorhandenes Fenster wird
      // NICHT angefasst - egal ob es gerade sichtbar oder minimiert ist.
      // Nur wenn nachweislich GAR KEIN Fenster existiert, ist der zweite
      // "gio launch" faellig (der Fall, den GNOME Settings & Co. brauchen).
      if (fensterAnzahl === 0 && darfNeuStarten) {
        linuxAppLogZeile(`Erststart ohne Fenster (${kontext}): desktopId="${desktopId}" - schiebe zweiten Start nach`);
        nochmalStarten();
      } else {
        linuxAppLogZeile(`kein Eingriff (${kontext}): desktopId="${desktopId}" fensterAnzahl=${fensterAnzahl} - automatischer Aufruf fasst vorhandene Fenster nicht an`);
      }
      return;
    }
    // Echter Klick von Klaus: vorhandenes Fenster nach vorne holen; gibt es
    // keins, notfalls neu starten.
    execFile('wmctrl', ['-xa', _wmClassFuerDesktopDatei(pfad)],
      (fehler, stdout, stderr) => {
        const erfolg = !fehler;
        linuxAppLogZeile(`ActivateApp (${kontext}): desktopId="${desktopId}" fensterAnzahl=${fensterAnzahl} erfolg=${erfolg} neustartErlaubt=${darfNeuStarten} stdout="${(stdout || '').trim()}" fehler="${fehler ? fehler.message : ''}"`);
        if (erfolg) return;
        if (!darfNeuStarten) {
          linuxAppLogZeile(`kein Fenster aktivierbar (${kontext}) - KEIN Neustart (wurde gerade schon gestartet).`);
          return;
        }
        nochmalStarten();
      });
  });
}
function sendeLaufendeProgrammeAnAlleFenster() {
  const liste = [...laufendePrograme.values()].map(({ name, icon, exec, pfad, anzahl, minimiert }) => ({ name, icon, exec, pfad, anzahl, minimiert: minimiert || 0 }));
  BrowserWindow.getAllWindows().forEach(w => w.webContents.send('laufende-programme', liste));
}
// Zaehlt per pgrep, wie viele Prozesse zum Suchbegriff laufen - nicht ob der
// urspruenglich gestartete Prozess noch existiert. Wichtig bei
// Einzelinstanz-Programmen wie Firefox: laeuft Firefox schon, meldet sich der
// neu gestartete Prozess nur kurz beim bestehenden Fenster und beendet sich
// selbst gleich wieder - der urspruengliche Prozess waere also laengst weg,
// obwohl das Programm (in einem ANDEREN, laenger laufenden Prozess) weiter offen ist.
// Die Anzahl wird fuer die blauen Punkte unter dem Taskleisten-Icon gebraucht
// (wie bei Ubuntus eigenem Dock) - normalerweise bleibt sie bei 1, auch wenn
// das Programm mehrere Fenster hat (ein Prozess, mehrere Fenster). Zeigt sie
// mehr als 1, laufen tatsaechlich mehrere GETRENNTE Prozesse.
function _anzahlLaufend(suchbegriff, callback) {
  // Erst genauer Name-Treffer (-x): findet z.B. bei Firefox NUR den echten
  // Browser-Hauptprozess ("firefox"), nicht dessen Begleitprozesse wie
  // "crashhelper" - die haben "firefox" zwar im Pfad, aber einen eigenen
  // Prozessnamen, und blieben sonst faelschlich mitgezaehlt.
  // Findet -x nichts (z.B. bei Programmen, deren echter Prozess anders heisst
  // als der Startbefehl, etwa LibreOffice -> soffice.bin), zur Sicherheit
  // noch der breitere Pfad-Treffer (-f) als Rueckfall.
  // Prozessnamen sind im Linux-Kern auf 15 Zeichen begrenzt - "pgrep -x"
  // meldet bei laengeren Suchbegriffen darum GRUNDSAETZLICH nichts (mit einem
  // eigenen Hinweistext auf der Fehlerausgabe). Betrifft genau die Faelle, die
  // Klaus am 13.08.2026 gemeldet hat: "google-chrome-stable" (20) und
  // "gnome-control-center" (20). Den zum Scheitern verurteilten Aufruf gar
  // nicht erst machen, sondern direkt den breiteren -f-Weg nehmen.
  if (suchbegriff.length > 15) {
    execFile('pgrep', ['-f', suchbegriff], (fehler0, stdout0) => {
      const treffer0 = (stdout0 || '').split('\n').map(z => z.trim()).filter(Boolean);
      callback(treffer0.length, treffer0, false);
    });
    return;
  }
  execFile('pgrep', ['-x', suchbegriff], (fehler, stdout) => {
    const treffer = (stdout || '').split('\n').map(z => z.trim()).filter(Boolean);
    // genau=true: exakter Prozessname-Treffer, die Zahl ist verlaesslich.
    if (treffer.length) { callback(treffer.length, treffer, true); return; }
    execFile('pgrep', ['-f', suchbegriff], (fehler2, stdout2) => {
      const treffer2 = (stdout2 || '').split('\n').map(z => z.trim()).filter(Boolean);
      // genau=false: -f sucht den Namen als Textschnipsel in der GESAMTEN
      // Befehlszeile IRGENDEINES Prozesses. Bei kurzen/generischen Namen ist
      // das grob falsch. Nachgemessen am 11.08.2026: "resources" traf vier
      // Claude-Desktop-Prozesse, weil in deren Befehlszeile der Pfad
      // ".../claude-desktop/resources/app.asar" steht - der wirklich
      // gestartete Prozess war nicht mal dabei. Ergebnis waren vier blaue
      // Punkte fuer eine App, die so gar nicht offen war.
      // Diese Zahl taugt daher NUR fuer "laeuft ueberhaupt noch etwas?",
      // NICHT zum Zaehlen der Fenster-Punkte (siehe Aufrufer).
      callback(treffer2.length, treffer2, false);
    });
  });
}
// Genauere Fenster-Anzahl (statt Prozess-Anzahl) fuer die blauen Punkte, ueber
// wmctrl (siehe _wmClassFuerDesktopDatei) - zaehlt bei Einzelinstanz-
// Programmen wie Firefox auch dann richtig 2 oder 3, wenn das technisch nur
// EIN Prozess mit mehreren Fenstern ist (siehe Kommentar bei _anzahlLaufend
// oben). callback(null) wenn wmctrl fehlschlaegt (z.B. nicht installiert) -
// Aufrufer faellt dann auf die Prozess-Anzahl zurueck.
function _fensterAnzahlUeberErweiterung(pfad, callback) {
  const wmClass = _wmClassFuerDesktopDatei(pfad).toLowerCase();
  execFile('wmctrl', ['-lx'], (fehler, stdout) => {
    if (fehler) { callback(null); return; }
    let anzahl = 0;
    const fensterIds = [];
    for (const zeile of (stdout || '').split('\n')) {
      const spalten = zeile.trim().split(/\s+/);
      // wmctrl -x zeigt WM_CLASS als "Instanz.Klasse" (zwei getrennte X11-
      // Eigenschaften, hier nur zur Anzeige mit einem Punkt verbunden).
      // Vorher wurde nur die KLASSE (Suffix nach dem Punkt) und nur GENAU so
      // gross-/kleingeschrieben verglichen wie in der Desktop-Datei - das
      // reicht nicht: Tkinter-Programme (z.B. das per Flatpak installierte
      // "System Monitoring Center") setzen die Instanz exakt wie angegeben
      // ("smc_window"), machen aus der KLASSE aber automatisch einen
      // Grossbuchstaben-Anfang ("Smc_window") - X11-ueblich, aber nicht das,
      // was in StartupWMClass steht. Ergebnis war dasselbe Bild wie beim
      // alten Zutty-Bug: die Fenster-Pruefung sah dauerhaft 0 Fenster, obwohl
      // eins offen war, das Icon verschwand nach ein paar Sekunden von
      // selbst wieder (Klaus, 2026-08-23). Fix: gross-/kleinschreibungs-
      // unabhaengig vergleichen, UND sowohl gegen die Instanz als auch
      // gegen die Klasse einzeln pruefen, nicht nur gegen den Klassen-Teil.
      const klasse = (spalten[2] || '').toLowerCase();
      const punkt = klasse.indexOf('.');
      const instanz = punkt === -1 ? klasse : klasse.slice(0, punkt);
      const klasseTeil = punkt === -1 ? klasse : klasse.slice(punkt + 1);
      if (klasse === wmClass || instanz === wmClass || klasseTeil === wmClass) {
        anzahl++;
        if (spalten[0]) fensterIds.push(spalten[0]);
      }
    }
    // Zweiter Wert: wie viele dieser Fenster sind WEGGEKLAPPT (minimiert)?
    // Gebraucht seit Klaus' Entscheidung (b) vom 23.09.2026: das Icon-Fenster
    // ist ein Ablagefach fuer Weggeklapptes, kein Anzeiger fuer alles Laufende.
    // Erkennungsmerkmal ist _NET_WM_STATE_HIDDEN - das setzt der Fenster-
    // manager genau dann, wenn ein Fenster minimiert ist.
    // Die Fenster-Kennung kommt aus der wmctrl-Ausgabe und wird als eigenes
    // Argument uebergeben (kein Shell-Aufruf) - nichts, was sich einschleusen
    // liesse.
    if (!fensterIds.length) { callback(anzahl, 0); return; }
    let offeneAbfragen = fensterIds.length;
    let minimiert = 0;
    fensterIds.forEach((id) => {
      execFile('xprop', ['-id', id, '_NET_WM_STATE'], (f2, aus2) => {
        if (!f2 && /_NET_WM_STATE_HIDDEN/.test(aus2 || '')) minimiert++;
        if (--offeneAbfragen === 0) callback(anzahl, minimiert);
      });
    });
  });
}

// System > Alle Schalter: liest WIRKLICH ALLE echten an/aus-Schalter (nicht
// nur eine kuratierte Auswahl) direkt vom System - deshalb "automatisch neu
// scannen", falls nach einem Ubuntu-Update welche dazukommen oder wegfallen.
// Technik: gsettings kennt hunderte Schluessel, viele davon fuer einzelne
// Programme oder rein interne Sachen - deshalb nur Schemas durchsuchen, die
// hier als "echte Desktop-Einstellung" gelistet sind (Sicherheits-Whitelist
// auf Schema-Ebene), und davon nur die, deren aktueller Wert wortwoertlich
// true/false ist (also wirklich ein Schalter, keine Zahl/Text/Liste).
// Auf genau diese eine Kategorie eingedampft (Klaus-Wunsch 2026-08-21,
// nach einer Bestandsaufnahme, was auf DIESEM System - Ubuntu Server +
// Openbox, kein GNOME-Desktop - ueberhaupt noch etwas bewirkt): alle
// anderen Kategorien haengen an einem GNOME-Dienst, der hier nicht laeuft
// (gnome-shell, gnome-settings-daemon, mutter - siehe Prozessliste, keiner
// davon aktiv, obwohl die Pakete noch installiert sind). Ein Schalter dort
// liess sich zwar anklicken und der Wert wurde auch wirklich gespeichert,
// aber niemand hat je zugehoert und ihn umgesetzt - reine Attrappen.
// org.gnome.desktop.interface ist die Ausnahme: das liest jedes GTK-
// Programm (Firefox, LibreOffice) direkt beim eigenen Start ueber GTKs
// eigenen Einstellungs-Mechanismus, unabhaengig von jedem Sitzungsdienst -
// bleibt darum drin. Ein paar einzelne Schluessel darin sind selbst noch
// GNOME-Shell-spezifisch (z.B. die Uhr-Anzeige im oberen Panel, das es hier
// nicht gibt) und damit ebenfalls wirkungslos - die einzeln rauszufiltern
// wuerde aber genau der Absicht dieser Liste widersprechen (Schema-Ebene,
// nicht Schluessel-Ebene, siehe Kommentar oben an SCHALTER_KATEGORIEN
// selbst) und muesste nach jedem Ubuntu-Update von Hand nachgepflegt
// werden. Harmlos: ein wirkungsloser Klick dort veraendert nur einen Wert,
// den niemand liest.
//
// Was frueher hier stand und warum es raus ist:
//   org.gnome.settings-daemon.plugins.color/.power - braucht gsd-color/
//     gsd-power (nicht aktiv)
//   org.gnome.desktop.sound - braucht einen Sound-Event-Dienst (nicht aktiv)
//   org.gnome.desktop.peripherals.* - wird normalerweise live von
//     gsd-mouse/-keyboard angewendet UND xinput muesste installiert sein,
//     um es ueberhaupt selbst nachzubauen - ist es nicht (2026-08-21 geprueft)
//   org.gnome.desktop.a11y* - braucht denselben fehlenden Dienst
//   org.gnome.desktop.screensaver - Bildschirm-An/Aus laeuft laengst direkt
//     ueber "xset"/DPMS in .xinitrc, unabhaengig von diesem Schalter
//   org.gnome.desktop.notifications - kein Benachrichtigungsdienst installiert
//   org.gnome.desktop.media-handling - der USB-Automount-Wächter
//     (gvfs-udisks2-volume-monitor) laeuft nicht, geprueft 2026-08-21
//   org.gnome.desktop.screen-time-limits/.break-reminders/.remote-desktop -
//     hatten schon vorher 0 Treffer (Schema gar nicht installiert)
//   org.gnome.desktop.lockdown - wird von GNOME-eigenen Programmen
//     abgefragt (Dateien/Terminal/Drucken sperren), die hier nicht laufen
//   org.gnome.desktop.wm.preferences/org.gnome.mutter/org.gnome.shell -
//     komplett wirkungslos: der Fenstermanager hier ist Openbox, das seine
//     eigene, getrennte Konfigurationsdatei (~/.config/openbox/rc.xml)
//     benutzt und gsettings nie anschaut; gnome-shell/mutter laufen gar
//     nicht erst
const SCHALTER_KATEGORIEN = [
  { praefix: 'org.gnome.desktop.interface', kategorie: 'Anzeige & Oberfläche' },
];
function schemaZuKategorie(schema) {
  // Erweiterungs-Schemas (dash-to-dock, Desktop-Icons, ...) bewusst raus -
  // das sind Einstellungen einzelner, optionaler Shell-Erweiterungen, keine
  // Kern-Systemschalter, und die jeweilige Erweiterung hat eh ihre eigenen
  // Einstellungen (ueber "Erweiterungen"/"Tweaks").
  if (schema.includes('.extensions.')) return null;
  const treffer = SCHALTER_KATEGORIEN.find(k => schema === k.praefix || schema.startsWith(k.praefix + '.'));
  return treffer ? treffer.kategorie : null;
}
function schluesselHuebschMachen(key) {
  return key.split('-').map(wort => wort.charAt(0).toUpperCase() + wort.slice(1)).join(' ');
}
// Echte deutsche Beschriftungen ueber ein kleines Python-Skript (liest die
// uebersetzte GLib-Schema-"summary", siehe schluessel_namen.py) - ein
// einziger Aufruf fuer den kompletten Scan statt einem pro Schluessel.
// Schlaegt das fehl (z.B. kein python3/PyGObject), faellt der Aufrufer auf
// schluesselHuebschMachen() zurueck.
async function schluesselNamenLesen(paare) {
  if (paare.length === 0) return {};
  try {
    const skriptPfad = path.join(__dirname, 'schluessel_namen.py');
    // Ueber den Desktop-Starter (Icon/Menue statt Terminal) fehlt Electron oft
    // LANG - ohne das liefert Python/GLib nur die unuebersetzte Original-
    // beschriftung. Deshalb hier fest Deutsch setzen, statt uns auf das zu
    // verlassen, was die App zufaellig geerbt hat.
    const umgebung = { ...process.env, LANG: 'de_DE.UTF-8', LC_ALL: 'de_DE.UTF-8' };
    const { stdout } = await execFileAsync('/usr/bin/python3', [skriptPfad, JSON.stringify(paare)], { maxBuffer: 10 * 1024 * 1024, env: umgebung });
    return JSON.parse(stdout);
  } catch (e) {
    console.error('[Milcrid] Deutsche Schalter-Namen konnten nicht gelesen werden, Rueckfall auf Roh-Namen:', e.message);
    return {};
  }
}
// LAN-Geraet ueber den TYP finden statt den Namen (z.B. "eno1") fest
// einzutragen - auf Milcrid gibt es zwar nur eine Kabel-Karte, aber der
// Name haengt vom Mainboard/Udev ab und sollte sich nicht in mehreren
// Funktionen wiederholen muessen.
function lanGeraetZeile() {
  const roh = execSync('nmcli -t -f DEVICE,TYPE,STATE device status', { encoding: 'utf-8', timeout: 3000, env: { ...process.env, LC_ALL: 'C' } }).trim();
  return roh.split('\n').find(zeile => zeile.split(':')[1] === 'ethernet');
}
function netzwerkSchalterLesen(id) {
  try {
    if (id === 'wlan') {
      const roh = execSync('nmcli -t -f WIFI radio', { encoding: 'utf-8', timeout: 3000, env: { ...process.env, LC_ALL: 'C' } }).trim();
      return roh === 'enabled';
    }
    if (id === 'lan') {
      const zeile = lanGeraetZeile();
      if (!zeile) return null; // keine Kabel-Netzwerkkarte auf diesem System
      return zeile.split(':')[2] === 'connected';
    }
    if (id === 'bluetooth') {
      const roh = execSync('bluetoothctl show', { encoding: 'utf-8', timeout: 3000, env: { ...process.env, LC_ALL: 'C' } });
      const treffer = /Powered:\s*(yes|no)/.exec(roh);
      return treffer ? treffer[1] === 'yes' : null;
    }
  } catch (e) { return null; }
  return null;
}
async function systemschalterAlleLesen() {
  const liste = [
    { id: 'befehl:lan', kategorie: 'Netzwerk', label: 'LAN', beschreibung: 'Schaltet die Kabel-Netzwerkverbindung ein oder aus.', an: netzwerkSchalterLesen('lan') },
    { id: 'befehl:wlan', kategorie: 'WLAN', label: 'WLAN', beschreibung: 'Schaltet die WLAN-Verbindung ein oder aus.', an: netzwerkSchalterLesen('wlan') },
    { id: 'befehl:bluetooth', kategorie: 'Bluetooth', label: 'Bluetooth', beschreibung: 'Schaltet Bluetooth ein oder aus.', an: netzwerkSchalterLesen('bluetooth') },
  ].filter(eintrag => eintrag.an !== null); // z.B. kein nmcli/bluetoothctl auf diesem System

  let schemas;
  try {
    schemas = execSync('gsettings list-schemas', { encoding: 'utf-8' }).split('\n').map(s => s.trim()).filter(Boolean);
  } catch (e) { schemas = []; }
  const relevanteSchemas = schemas
    .map(schema => ({ schema, kategorie: schemaZuKategorie(schema) }))
    .filter(x => x.kategorie);

  // Einzelne Schluessel, die auf DIESEM System (Openbox statt GNOME Shell,
  // kein gnome-settings-daemon aktiv) nachweislich keine Wirkung mehr haben
  // - geprueft 2026-08-21, siehe die deutschen Erklaerungen im Portal fuer
  // die Begruendung je Schalter. Anders als die schema-weite Auswahl oben
  // (SCHALTER_KATEGORIEN) ist das hier eine Schluessel-Ebene, bewusst kurz
  // gehalten (Klaus-Wunsch 2026-08-21: raus, was zu 100% nichts tut) - die
  // Portal-Seite pflegt ohnehin schon eine Erklaerung pro einzelnem
  // Schluessel (SCHALTER_ERKLAERUNGEN), Schluessel-Ebene ist also kein
  // zusaetzlicher Pflegeaufwand mehr.
  const SCHLUESSEL_OHNE_WIRKUNG = new Set([
    'clock-show-date',        // gehoert zur GNOME-Shell-Panel-Uhr, die es hier nicht gibt
    'clock-show-seconds',     // dito
    'clock-show-weekday',     // dito
    'enable-hot-corners',     // GNOME-Shell-Funktion, Shell laeuft hier nicht
    'show-battery-percentage',// GNOME-Shell-Panel UND kein Akku vorhanden (Desktop-PC)
    'locate-pointer',         // braucht gnome-settings-daemon, laeuft hier nicht
  ]);

  // Werte kommen ueber "list-recursively" (ein Befehl pro Schema statt einem
  // pro Schluessel) - sonst waere das bei ~170+ Schluesseln spuerbar langsam.
  const rohSchalter = [];
  for (const { schema, kategorie } of relevanteSchemas) {
    let zeilen;
    try {
      zeilen = execFileSync('gsettings', ['list-recursively', schema], { encoding: 'utf-8' }).split('\n');
    } catch (e) { continue; }
    for (const zeile of zeilen) {
      const treffer = /^(\S+)\s+(\S+)\s+(true|false)$/.exec(zeile.trim());
      if (!treffer) continue; // nur echte an/aus-Werte, keine Zahlen/Text/Listen
      const [, , schluessel, wert] = treffer;
      if (SCHLUESSEL_OHNE_WIRKUNG.has(schluessel)) continue;
      rohSchalter.push({ schema, kategorie, schluessel, an: wert === 'true' });
    }
  }

  // Beschreibungen (fuer die Erklaerung unter jedem Schalter) parallel statt
  // nacheinander abfragen - sequentiell waeren das bei 150+ Schaltern mehrere
  // Sekunden Wartezeit, parallel sind es unter einer Sekunde. LANG explizit
  // gesetzt aus demselben Grund wie bei schluesselNamenLesen oben.
  const beschreibungsUmgebung = { ...process.env, LANG: 'de_DE.UTF-8', LC_ALL: 'de_DE.UTF-8' };
  const beschreibungen = await Promise.all(rohSchalter.map(({ schema, schluessel }) =>
    execFileAsync('gsettings', ['describe', schema, schluessel], { env: beschreibungsUmgebung }).then(r => r.stdout.trim()).catch(() => '')
  ));
  // Kurze deutsche Titel, ein einziger Aufruf fuer den ganzen Scan.
  const namen = await schluesselNamenLesen(rohSchalter.map(({ schema, schluessel }) => ({ schema, schluessel })));

  rohSchalter.forEach((eintrag, i) => {
    liste.push({
      id: eintrag.schema + '::' + eintrag.schluessel,
      kategorie: eintrag.kategorie,
      label: namen[eintrag.schema + '::' + eintrag.schluessel] || schluesselHuebschMachen(eintrag.schluessel),
      beschreibung: beschreibungen[i],
      an: eintrag.an,
    });
  });
  return liste;
}
function systemschalterSchreiben(id, an) {
  if (id === 'befehl:wlan') { execSync(`nmcli radio wifi ${an ? 'on' : 'off'}`, { timeout: 5000 }); return; }
  if (id === 'befehl:lan') {
    const zeile = lanGeraetZeile();
    if (!zeile) throw new Error('Keine Kabel-Netzwerkkarte gefunden');
    const geraet = zeile.split(':')[0];
    // "connect"/"disconnect" statt radio on/off - LAN hat (anders als WLAN)
    // keinen eigenen Funkschalter, nur die Verbindung selbst laesst sich
    // trennen/aufbauen. Trennt man die Karte, ueber die man gerade selbst
    // verbunden ist (z.B. per SSH), reisst das die Verbindung sofort ab -
    // das ist hier bewusst in Kauf genommen (Milcrid-Testsystem).
    execSync(`nmcli device ${an ? 'connect' : 'disconnect'} ${geraet}`, { timeout: 8000 });
    return;
  }
  if (id === 'befehl:bluetooth') { execSync(`bluetoothctl power ${an ? 'on' : 'off'}`, { timeout: 5000 }); return; }
  const teile = id.split('::');
  if (teile.length !== 2) throw new Error('Ungueltige Schalter-ID: ' + id);
  const [schema, schluessel] = teile;
  if (!schemaZuKategorie(schema)) throw new Error('Schema nicht erlaubt: ' + schema);
  // Zusaetzliche Pruefung, dass der Schluessel wirklich zu diesem Schema
  // gehoert (nicht blind vertrauen, was von der Portal-Seite reinkommt).
  //
  // execFileSync statt execSync (Opus-Pruefstand 2026-09-03, nachgewiesen):
  // execSync gibt die Zeile an die SHELL, und die Whitelist oben laesst ein
  // Schema durch, das mit "org.gnome.desktop.interface." ANFAENGT - der Rest
  // ist beliebig. Ein Schema wie
  //     org.gnome.desktop.interface.; <befehl>
  // kam damit durch die Whitelist, und der eingeschleuste Befehl lief beim
  // list-keys-Aufruf HIER, also noch bevor die Schluessel-Pruefung eine Zeile
  // weiter unten ihn abweisen konnte. Die Abweisung kam zu spaet - der Befehl
  // war schon gelaufen (im Test mit "touch" bewiesen).
  //
  // Mit execFileSync gibt es keine Shell mehr: jedes Argument geht einzeln an
  // gsettings, ein Semikolon darin ist nur noch ein Zeichen im Schemanamen.
  // Dieselbe Unterscheidung steht schon weiter oben in dieser Datei als
  // Kommentar ("WICHTIG: execFileSync statt execSync - execSync fuehrt den
  // Befehl ueber die Shell aus") - hier war sie nur nicht angewandt.
  let bekannteSchluessel;
  try {
    bekannteSchluessel = execFileSync('gsettings', ['list-keys', schema], { encoding: 'utf-8' }).split('\n').map(s => s.trim());
  } catch (e) { throw new Error('Schema nicht lesbar: ' + schema); }
  if (!bekannteSchluessel.includes(schluessel)) throw new Error('Schluessel nicht gefunden: ' + schluessel);
  execFileSync('gsettings', ['set', schema, schluessel, an ? 'true' : 'false']);
}

// ---- WLAN: Netzwerke suchen/verbinden (Klaus-Wunsch 2026-09-03, "wie
// GNOME das macht"). SSID/Passwort kommen aus der Luft bzw. vom Nutzer -
// execFileSync statt execSync (Argument-Array statt zusammengebauter
// Befehlszeile), sonst koennte ein boesartig benanntes Nachbarnetz (SSID
// mit Shell-Sonderzeichen) eigene Befehle einschleusen - gleiches Prinzip
// wie bei der pgrep-Absicherung weiter oben in dieser Datei. -----------
function wlanGeraetName() {
  const roh = execSync('nmcli -t -f DEVICE,TYPE device status', { encoding: 'utf-8', timeout: 3000, env: { ...process.env, LC_ALL: 'C' } }).trim();
  const zeile = roh.split('\n').find(z => z.split(':')[1] === 'wifi');
  return zeile ? zeile.split(':')[0] : null;
}
function wlanNetzeListen() {
  const geraet = wlanGeraetName();
  if (!geraet) return [];
  try { execFileSync('nmcli', ['device', 'wifi', 'rescan'], { timeout: 8000, stdio: 'ignore' }); } catch (e) { /* z.B. laeuft schon ein Scan - Liste unten trotzdem holen */ }
  const roh = execSync('nmcli -t -f SSID,SIGNAL,SECURITY,IN-USE device wifi list', { encoding: 'utf-8', timeout: 8000, env: { ...process.env, LC_ALL: 'C' } }).trim();
  const gesehen = new Set();
  const ergebnis = [];
  roh.split('\n').forEach(zeile => {
    if (!zeile) return;
    // Terse-Ausgabe escaped ":" INNERHALB eines Feldwerts als "\:" (siehe
    // man nmcli) - darum nicht naiv an jedem ":" splitten (eine SSID kann
    // selbst einen Doppelpunkt enthalten), sondern nur an UNescapten.
    const teile = zeile.split(/(?<!\\):/);
    if (teile.length < 4) return;
    const inUse = teile.pop();
    const security = teile.pop();
    const signal = teile.pop();
    const ssid = teile.join(':').replace(/\\:/g, ':');
    if (!ssid || gesehen.has(ssid)) return; // versteckte SSIDs + Mehrfach-Treffer (mehrere Access Points) ausblenden
    gesehen.add(ssid);
    ergebnis.push({ ssid, signal: Number(signal) || 0, gesichert: security !== '', verbunden: inUse === '*' });
  });
  return ergebnis.sort((a, b) => b.signal - a.signal);
}
function wlanVerbinden(ssid, passwort) {
  const args = ['device', 'wifi', 'connect', ssid];
  if (passwort) args.push('password', passwort);
  execFileSync('nmcli', args, { timeout: 20000, encoding: 'utf-8' });
}
function wlanTrennen() {
  const geraet = wlanGeraetName();
  if (!geraet) throw new Error('Kein WLAN-Empfänger gefunden');
  execFileSync('nmcli', ['device', 'disconnect', geraet], { timeout: 8000 });
}
ipcMain.handle('wlan-netze-listen', () => wlanNetzeListen());
ipcMain.handle('wlan-verbinden', (event, ssid, passwort) => { wlanVerbinden(ssid, passwort); });
ipcMain.handle('wlan-trennen', () => { wlanTrennen(); });

// ---- Proxy: GNOME-System-Proxy ueber gsettings (Klaus-Wunsch 2026-09-03,
// "wie GNOME das macht" - siehe Netzwerk > Netzwerk-Proxy dort). Rein
// gsettings-basiert, kein Root/Paket noetig - anders als LAN/WLAN/Bluetooth
// betrifft das nur GTK-Programme, die diesen Schluessel selbst auslesen
// (die meisten tun das, z.B. Firefox NICHT - der hat einen eigenen,
// unabhaengigen Proxy-Schalter in seinen eigenen Einstellungen). -------
function proxyProtokollLesen(schema) {
  const host = execSync(`gsettings get org.gnome.system.proxy.${schema} host`, { encoding: 'utf-8' }).trim().replace(/^'|'$/g, '');
  const port = Number(execSync(`gsettings get org.gnome.system.proxy.${schema} port`, { encoding: 'utf-8' }).trim());
  return { host, port: Number.isFinite(port) ? port : 0 };
}
function proxyLesen() {
  const modus = execSync('gsettings get org.gnome.system.proxy mode', { encoding: 'utf-8' }).trim().replace(/^'|'$/g, '');
  const autoconfigUrl = execSync('gsettings get org.gnome.system.proxy autoconfig-url', { encoding: 'utf-8' }).trim().replace(/^'|'$/g, '');
  const gemeinsam = execSync('gsettings get org.gnome.system.proxy use-same-proxy', { encoding: 'utf-8' }).trim() === 'true';
  return {
    modus, autoconfigUrl, gemeinsam,
    http: proxyProtokollLesen('http'),
    https: proxyProtokollLesen('https'),
    socks: proxyProtokollLesen('socks'),
  };
}
function proxySchreiben(einstellungen) {
  const modus = ['none', 'manual', 'auto'].includes(einstellungen.modus) ? einstellungen.modus : 'none';
  execFileSync('gsettings', ['set', 'org.gnome.system.proxy', 'mode', modus]);
  if (modus === 'auto') {
    execFileSync('gsettings', ['set', 'org.gnome.system.proxy', 'autoconfig-url', String(einstellungen.autoconfigUrl || '')]);
    return;
  }
  if (modus !== 'manual') return;
  const gemeinsam = !!einstellungen.gemeinsam;
  execFileSync('gsettings', ['set', 'org.gnome.system.proxy', 'use-same-proxy', gemeinsam ? 'true' : 'false']);
  const http = einstellungen.http || {};
  execFileSync('gsettings', ['set', 'org.gnome.system.proxy.http', 'host', String(http.host || '')]);
  execFileSync('gsettings', ['set', 'org.gnome.system.proxy.http', 'port', String(Number(http.port) || 0)]);
  // "use-same-proxy" heisst: GNOME uebernimmt den HTTP-Proxy automatisch
  // fuer https/socks mit - eigene Felder dafuer waeren dann nur verwirrend
  // (aendern sich, werden aber ignoriert) - darum hier nur schreiben, wenn
  // NICHT gemeinsam genutzt wird.
  if (!gemeinsam) {
    const https = einstellungen.https || {};
    const socks = einstellungen.socks || {};
    execFileSync('gsettings', ['set', 'org.gnome.system.proxy.https', 'host', String(https.host || '')]);
    execFileSync('gsettings', ['set', 'org.gnome.system.proxy.https', 'port', String(Number(https.port) || 0)]);
    execFileSync('gsettings', ['set', 'org.gnome.system.proxy.socks', 'host', String(socks.host || '')]);
    execFileSync('gsettings', ['set', 'org.gnome.system.proxy.socks', 'port', String(Number(socks.port) || 0)]);
  }
}
ipcMain.handle('proxy-lesen', () => proxyLesen());
ipcMain.handle('proxy-schreiben', (event, einstellungen) => { proxySchreiben(einstellungen); });

// ---- Bluetooth: Geraete suchen/koppeln (Klaus-Wunsch 2026-09-03) --------
// bluetoothctl unterstuetzt jeden dieser Befehle auch EINZELN (nicht nur
// interaktiv) - genau wie "bluetoothctl power on/off" oben bei
// netzwerkSchalterLesen/systemschalterSchreiben, geprueft 2026-09-03.
function bluetoothGeraeteListen() {
  let roh;
  try { roh = execSync('bluetoothctl devices', { encoding: 'utf-8', timeout: 5000 }); } catch (e) { return []; }
  const gefunden = roh.split('\n')
    .map(z => /^Device\s+(\S+)\s+(.*)$/.exec(z.trim()))
    .filter(Boolean)
    .map(m => ({ mac: m[1], name: m[2] }));
  return gefunden.map(g => {
    let info = '';
    try { info = execFileSync('bluetoothctl', ['info', g.mac], { encoding: 'utf-8', timeout: 5000 }); } catch (e) { /* Geraet inzwischen weg - unten als "nicht verbunden" behandeln */ }
    return {
      mac: g.mac,
      name: g.name,
      verbunden: /Connected:\s*yes/.test(info),
      gekoppelt: /Paired:\s*yes/.test(info),
    };
  });
}
function bluetoothScannen(sekunden) {
  // "--timeout N scan on" laeuft N Sekunden lang aktiv und beendet sich
  // danach von selbst (kein separates "scan off" noetig) - waehrenddessen
  // gefundene Geraete landen automatisch im selben Cache wie
  // "bluetoothctl devices" darunter liest, auch unabhaengig vom
  // Kopplungsstatus.
  try {
    execFileSync('bluetoothctl', ['--timeout', String(sekunden), 'scan', 'on'], { timeout: (sekunden + 5) * 1000, encoding: 'utf-8', stdio: 'ignore' });
  } catch (e) { /* z.B. Bluetooth ist aus - Liste danach einfach unveraendert zurueckgeben */ }
  return bluetoothGeraeteListen();
}
function bluetoothVerbinden(mac) {
  // Klaus-Fund 2026-09-03, zweite Runde: der erste Fix (eine bluetoothctl-
  // Sitzung mit "agent NoInputNoOutput" statt Einzelaufrufen) hat das
  // Haengenbleiben behoben, aber ein neues Problem sichtbar gemacht - direkt
  // nach "connect" per Skript-Zeile kam sofort "quit" hinterher, OHNE auf
  // die (asynchrone) Antwort von connect zu warten: die Fehlermeldung zeigte
  // nur "Attempting to connect ..." gefolgt von "quit", nie ein Erfolg/
  // Misserfolg. In einer echten interaktiven Sitzung wartet man selbst,
  // bevor man den naechsten Befehl tippt - per Pipe zugefuehrte Zeilen
  // werden aber alle sofort nacheinander gelesen, ohne diese Wartezeit.
  // Fix: nicht mehr alles auf einmal per stdin schicken, sondern den
  // Prozess offen halten und wirklich auf die Ausgabe warten, bevor der
  // naechste Befehl geschickt wird (und bevor "quit" kommt).
  return new Promise((resolve, reject) => {
    const proc = spawn('bluetoothctl', [], { stdio: ['pipe', 'pipe', 'pipe'] });
    let ausgabe = '';
    let verbindenGesendet = false;
    let erledigt = false;

    function letzteZeilen(){
      return ausgabe.replace(/\x1b\[[0-9;]*m/g, '').trim().split('\n').filter(Boolean).slice(-4).join(' | ');
    }
    function beenden(fehler){
      if (erledigt) return;
      erledigt = true;
      clearTimeout(zeitlimit);
      clearTimeout(pairFallback);
      try { proc.stdin.write('quit\n'); } catch (e) { /* Prozess evtl. schon weg */ }
      setTimeout(() => { try { proc.kill('SIGKILL'); } catch (e) {} }, 500);
      if (fehler) reject(fehler); else resolve();
    }
    function trustUndConnectSenden(){
      if (verbindenGesendet) return;
      verbindenGesendet = true;
      ausgabe = ''; // ab hier nur noch auf die Antwort von "connect" achten
      proc.stdin.write(`trust ${mac}\n`);
      proc.stdin.write(`connect ${mac}\n`);
    }

    const zeitlimit = setTimeout(() => {
      beenden(new Error('Zeitüberschreitung. Letzte Meldung: ' + (letzteZeilen() || '(keine)')));
    }, 30000);
    // Falls "pair" gar keine erkennbare Antwort gibt (seltener Sonderfall),
    // nach 8s trotzdem mit trust/connect weitermachen statt ewig zu warten.
    const pairFallback = setTimeout(trustUndConnectSenden, 8000);

    proc.stdout.on('data', chunk => {
      ausgabe += chunk.toString();
      const sauber = ausgabe.replace(/\x1b\[[0-9;]*m/g, '');
      // "[DEL] Device <mac> ..." heisst: Bluez hat das (noch nie gekoppelte)
      // Geraet aus seiner eigenen Liste entfernt, meist weil die Kopplung
      // gerade fehlgeschlagen ist - z.B. weil der Kopplungsmodus am Geraet
      // selbst inzwischen wieder aus ist. Ohne diese Pruefung liefen
      // trust/connect danach gegen ein bereits verschwundenes Geraet und
      // die Fehlermeldung zeigte nur noch verwirrende Folgefehler
      // ("UnknownObject") statt der eigentlichen Ursache (Klaus-Fund
      // 2026-09-03, dritte Runde).
      if (new RegExp('\\[DEL\\] Device ' + mac, 'i').test(sauber)) {
        beenden(new Error('Kopplung abgebrochen - das Gerät ist währenddessen verschwunden. Meist bedeutet das: der Kopplungsmodus am Gerät selbst ist schon wieder aus. Am Gerät neu aktivieren und sofort danach hier verbinden.'));
        return;
      }
      if (!verbindenGesendet) {
        // "Pairing successful" bei neuer Kopplung, "AlreadyExists" wenn
        // schon vorher gekoppelt - beides bedeutet: weiter zu trust/connect.
        // Ein echter Kopplungsfehler (z.B. Nutzer lehnt am Geraet ab) zeigt
        // sich dann eh gleich danach beim eigentlichen "connect".
        if (/Pairing successful|AlreadyExists|org\.bluez\.Error/i.test(sauber)) trustUndConnectSenden();
        return;
      }
      if (/Connection successful|Connected:\s*yes/i.test(sauber)) beenden(null);
      else if (/Failed to connect|org\.bluez\.Error/i.test(sauber)) beenden(new Error(letzteZeilen()));
    });
    proc.on('error', e => beenden(e));
    proc.on('exit', () => { if (!erledigt) beenden(new Error('bluetoothctl beendet ohne Rückmeldung: ' + (letzteZeilen() || '(keine)'))); });

    proc.stdin.write('agent NoInputNoOutput\n');
    proc.stdin.write('default-agent\n');
    proc.stdin.write(`pair ${mac}\n`);
  });
}
function bluetoothTrennen(mac) {
  execFileSync('bluetoothctl', ['disconnect', mac], { timeout: 8000, encoding: 'utf-8' });
}
function bluetoothEntfernen(mac) {
  execFileSync('bluetoothctl', ['remove', mac], { timeout: 8000, encoding: 'utf-8' });
}
ipcMain.handle('bluetooth-geraete-listen', () => bluetoothGeraeteListen());
ipcMain.handle('bluetooth-scannen', (event, sekunden) => bluetoothScannen(sekunden || 8));
ipcMain.handle('bluetooth-verbinden', (event, mac) => bluetoothVerbinden(mac));
ipcMain.handle('bluetooth-trennen', (event, mac) => { bluetoothTrennen(mac); });
ipcMain.handle('bluetooth-entfernen', (event, mac) => { bluetoothEntfernen(mac); });

// Standard-Orte fuer Programm-Eintraege (.desktop-Dateien) unter Linux.
// $XDG_DATA_DIRS deckt die meisten Faelle ab, aber Snap- und Flatpak-Pakete
// (z.B. Firefox als Snap) registrieren sich oft an Stellen, die dort nicht
// zuverlaessig drinstehen - deshalb zusaetzlich fest mit reinnehmen.
function xdgDatenOrdner() {
  const ausUmgebung = (process.env.XDG_DATA_DIRS || '')
    .split(':').filter(Boolean).map(dir => path.join(dir, 'applications'));
  // Reihenfolge nach XDG-Spezifikation: Benutzerordner haben Vorrang vor den
  // Systemordnern, damit eine eigene Datei mit gleichem "Name" (z.B. eine
  // gezielte Korrektur wie bei nvtop.desktop) die System-Datei tatsaechlich
  // ueberschreiben kann - vorher stand /usr/share/applications zuerst, eine
  // Datei im Benutzerordner mit demselben Name-Feld wurde dadurch nie
  // erreicht (_alleDesktopEintraege nimmt beim Namen den ERSTEN Treffer).
  return [...new Set([
    ...ausUmgebung,
    path.join(os.homedir(), '.local/share/applications'),
    path.join(os.homedir(), '.local/share/flatpak/exports/share/applications'),
    '/usr/local/share/applications',
    '/usr/share/applications',
    '/var/lib/snapd/desktop/applications',
    '/var/lib/flatpak/exports/share/applications',
  ])];
}
const DESKTOP_ORDNER = xdgDatenOrdner();
// Icon-Themes: erst das gerade aktive Theme (z.B. "Yaru-blue" bei Ubuntu),
// dann "Yaru" als Ubuntu-Standard-Basis, dann die generischen Fallbacks.
// Ohne das aktive Theme mit reinzunehmen findet man auf Ubuntu kaum ein
// Icon, weil viele Programme (Rechner, Dateien, Kalender usw.) ihr Bild nur
// im gerade eingestellten Yaru-Farbton hinterlegt haben, nicht in hicolor.
function aktivesIconThemaErmitteln() {
  try {
    return execSync('gsettings get org.gnome.desktop.interface icon-theme', { encoding: 'utf-8' })
      .trim().replace(/^'|'$/g, '');
  } catch (e) {
    return null;
  }
}
const ICON_THEMEN = [...new Set([aktivesIconThemaErmitteln(), 'Yaru', 'hicolor', 'Adwaita'].filter(Boolean))];
// Klaus-Fund 2026-08-25: nach dem Installieren zeigten mehrere Programme das
// Standard-Icon statt ihres eigenen (VLC, nvtop, vermutlich auch kitty) -
// drei unabhaengige Luecken in dieser Liste, keine davon war vorher drin:
//   - Flatpak-Programme (z.B. VLC) legen ihre Icons unter
//     ~/.local/share/flatpak/exports/share/icons/... ab, System-weite
//     Flatpaks unter /var/lib/flatpak/exports/share/icons/... - beide
//     Wurzeln fehlten komplett.
//   - "scalable" (fuer aufloesungsunabhaengige SVGs, z.B. kitty.svg unter
//     hicolor/scalable/apps) fehlte in der Groessen-Liste - dort standen
//     bisher nur feste Pixelgroessen.
//   - nvtop.svg liegt direkt unter /usr/share/icons/ (ohne Theme-
//     Unterordner) - eine unuebliche, aber reale Ablage, die die reine
//     Theme-Suche nie erreicht.
const ICON_GROESSEN = ['256x256', '128x128', '64x64', '48x48', '32x32', 'scalable'];
const ICON_WURZELN = [
  '/usr/share/icons',
  '/var/lib/flatpak/exports/share/icons',
  path.join(os.homedir(), '.local/share/flatpak/exports/share/icons'),
];
const ICON_ORDNER = [
  ...ICON_WURZELN.flatMap(wurzel =>
    ICON_THEMEN.flatMap(thema =>
      ICON_GROESSEN.map(groesse => path.join(wurzel, thema, groesse, 'apps')))),
  '/usr/share/icons', // Rueckfall fuer flach abgelegte Icons wie nvtop.svg
  '/usr/share/pixmaps',
];

const ZOOM_MIN = 0.7;
const ZOOM_MAX = 1.6;
const ZOOM_SCHRITT = 0.1;

let pythonProzess = null;
let habenWirGestartet = false;

// Laeuft der Portal-Server schon? Gefragt wird das, was wirklich zaehlt: hoert
// jemand auf dem Portal-Port? Frueher wurde stattdessen nach dem TEXT
// "main.py --portal" in irgendeiner Befehlszeile auf dem System gesucht - und
// jeder beliebige andere Prozess, der diesen Text zufaellig enthaelt (z.B. ein
// Terminal-Befehl, der nach genau diesem Prozess sucht), galt als "der Server
// laeuft schon". Die App startete dann keinen - Ergebnis: Portal offen,
// Milcrid dauerhaft offline, ohne erkennbaren Grund. Genau so passiert am
// 13.08.2026 waehrend einer Fehlersuche.
//
// Ein belegter Port ist der harte Beweis: nur ein wirklich laufender Server
// kann ihn halten. Bleibt die Pruefung unmoeglich (kein "ss" vorhanden),
// lieber den alten Namensweg als gar nichts.
function laeuftSchonPortalServer() {
  try {
    const zeilen = execFileSync('ss', ['-ltn'], { encoding: 'utf-8' });
    return zeilen.split('\n').some(z => /[\s:]8765\s/.test(z) && /LISTEN/.test(z));
  } catch (e) {
    try {
      // WICHTIG: execFileSync statt execSync - execSync fuehrt den Befehl ueber
      // eine Shell aus ("/bin/sh -c '...'"), und diese Shell traegt den
      // gesuchten Text dann selbst als eigenes Argument in ihrer Befehlszeile.
      execFileSync('pgrep', ['-f', 'main.py --portal'], { stdio: 'ignore' });
      return true;
    } catch (e2) {
      return false;
    }
  }
}

function starteBackendFallsNoetig() {
  if (laeuftSchonPortalServer()) {
    console.log('[Milcrid-App] Portal-Server laeuft bereits - wird weiterbenutzt.');
    habenWirGestartet = false;
    return;
  }
  console.log('[Milcrid-App] Starte Portal-Server...');
  pythonProzess = spawn('python3', ['main.py', '--portal'], {
    cwd: MILCRID_DIR,
    stdio: 'inherit',
  });
  habenWirGestartet = true;
}

function beendeBackendFallsWirGestartetHaben() {
  return new Promise((resolve) => {
    if (!habenWirGestartet || !pythonProzess || pythonProzess.killed) {
      resolve();
      return;
    }
    console.log('[Milcrid-App] Beende Portal-Server (sichert dabei automatisch)...');
    let fertig = false;
    pythonProzess.once('exit', () => {
      fertig = true;
      resolve();
    });
    pythonProzess.kill('SIGINT');
    // Sicherheitsnetz: falls das Speichern ungewoehnlich lange braucht,
    // trotzdem irgendwann weitermachen statt die App ewig offen zu halten.
    // Zusaetzlich SIGKILL hinterher, falls SIGINT den Prozess nicht beendet
    // hat (z.B. haengt an einer laufenden Ollama-Antwort) - sonst bleibt der
    // Prozess als Zombie haengen und der naechste Portal-Start findet ihn per
    // pgrep faelschlich als "laeuft schon", obwohl er kaputt ist.
    setTimeout(() => {
      if (!fertig && pythonProzess && !pythonProzess.killed) pythonProzess.kill('SIGKILL');
      resolve();
    }, 8000);
  });
}

function erstelleFenster() {
  // --kiosk auf der Kommandozeile (siehe ~/.xinitrc auf Milcrid) schaltet
  // echtes Vollbild ohne Fensterrahmen ein - beim normalen Entwickeln auf
  // einem GNOME-Desktop (ohne dieses Flag) bleibt die App ein normales
  // Fenster wie bisher.
  const kioskModus = process.argv.includes('--kiosk');
  const win = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 720,
    minHeight: 560,
    icon: ICON_PATH,
    title: 'Milcrid',
    autoHideMenuBar: true,
    kiosk: kioskModus,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: PRELOAD_PATH,
    },
  });
  win.setMenuBarVisibility(false);
  // ---- Fehler AUS DEM PORTAL mitschreiben (Opus 2026-09-07) -------------
  // Bisher gab es dafuer keinen Weg: Bricht im Portal-Skript etwas ab, sieht
  // man am Bildschirm nur, dass "nichts passiert" - die Meldung landet in
  // einer Konsole, die im Kiosk niemand sieht. Genau daran sind heute zwei
  // Fehlersuchen haengen geblieben (der Datei Manager, der sich nicht oeffnet,
  // und ein splashSchliessen-Aufruf, der die ganze Nachrichtenverarbeitung
  // lahmlegte, ohne dass sich der Grund ermitteln liess).
  // Nur Fehler und Warnungen, mit Deckel gegen unbegrenztes Wachstum -
  // dieselbe Lehre wie bei portal-monitor.log, das ohne Begrenzung auf 68 MB
  // angewachsen war.
  const PORTAL_FEHLER_LOG = path.join(__dirname, 'portal-fehler.log');
  win.webContents.on('console-message', (event, stufe, text, zeile, quelle) => {
    if (stufe < 2) return;   // 0=log, 1=info, 2=warning, 3=error
    try {
      if (fs.existsSync(PORTAL_FEHLER_LOG) && fs.statSync(PORTAL_FEHLER_LOG).size > 1024 * 1024) {
        fs.renameSync(PORTAL_FEHLER_LOG, PORTAL_FEHLER_LOG + '.alt');
      }
      const art = stufe === 3 ? 'FEHLER ' : 'WARNUNG';
      const ort = quelle ? ` (${path.basename(quelle)}:${zeile})` : '';
      fs.appendFileSync(PORTAL_FEHLER_LOG,
        // Ortszeit, nicht UTC: toISOString() lieferte zwei Stunden Rueckstand,
        // und beim ersten echten Einsatz hielt ich frische Fehler deshalb
        // faelschlich fuer alte (2026-09-08).
        `${new Date().toLocaleString('sv-SE').slice(0, 19)} ${art} ${text}${ort}\n`);
    } catch (e) { /* Mitschreiben darf das Portal nie stoeren */ }
  });

  win.loadFile(PORTAL_HTML);

  // Links mit target="_blank" (z.B. Chat-Links, der Milcrid-App-Store-Link)
  // sollen im normalen System-Browser aufgehen statt in einem neuen,
  // menue- und adresslosen Electron-Fenster.
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  // Rechtsklick-Menue: die App hat keine eigene Menueleiste, also gibt es
  // ohne das hier auch kein Kopieren/Einfuegen per Rechtsklick wie in einem
  // normalen Browser.
  win.webContents.on('context-menu', (event, params) => {
    const menu = new Menu();
    if (params.isEditable) {
      menu.append(new MenuItem({ role: 'cut', enabled: params.editFlags.canCut }));
      menu.append(new MenuItem({ role: 'copy', enabled: params.editFlags.canCopy }));
      menu.append(new MenuItem({ role: 'paste', enabled: params.editFlags.canPaste }));
    } else if (params.selectionText) {
      menu.append(new MenuItem({ role: 'copy' }));
    }
    if (menu.items.length > 0) menu.popup();
  });
}

function aendereZoom(event, delta) {
  const win = BrowserWindow.fromWebContents(event.sender);
  if (!win) return;
  const aktuell = win.webContents.getZoomFactor();
  const neu = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, aktuell + delta));
  win.webContents.setZoomFactor(neu);
}

ipcMain.on('zoom-in',    e => aendereZoom(e, ZOOM_SCHRITT));
ipcMain.on('zoom-out',   e => aendereZoom(e, -ZOOM_SCHRITT));
ipcMain.on('zoom-reset', e => {
  const win = BrowserWindow.fromWebContents(e.sender);
  if (win) win.webContents.setZoomFactor(1);
});
// Absolute Stufe statt relativ +/- (Klaus-Wunsch 2026-08-14, Milcrid >
// Portal > Groesse - ersetzt die alte "-⊙+"-Leiste ueber der Uhr mit einer
// festen 5-Stufen-Auswahl).
ipcMain.on('zoom-set', (e, faktor) => {
  const win = BrowserWindow.fromWebContents(e.sender);
  if (!win) return;
  const neu = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, faktor));
  win.webContents.setZoomFactor(neu);
});

// Gespeicherte Bildpfade koennen veralten: Ubuntus Symbol-Paket "Yaru" ist
// auf dem KI-PC nicht mehr installiert, LibreOffice Writer/Draw/Math zeigten
// darum nur noch das Ersatzbild (Klaus-Fund 2026-09-22). Beim Lesen jeden
// fehlenden Pfad einmal neu suchen (gleicher Name, alle Symbol-Pakete) - das
// Portal speichert den berichtigten Stand beim naechsten Aendern mit.
function _veraltetesIconErneuern(app) {
  if (!app || app.typ === 'milcrid' || !app.icon || !path.isAbsolute(app.icon)) return;
  if (fs.existsSync(app.icon)) return;
  const neu = iconPfadAufloesen(path.basename(app.icon).replace(/\.(png|svg|xpm)$/i, ''));
  if (neu) app.icon = neu;
}
ipcMain.handle('apps-lesen', () => {
  let daten;
  try {
    daten = JSON.parse(fs.readFileSync(APPS_LISTE_PATH, 'utf-8'));
  } catch (e) {
    return []; // Datei gibt's noch nicht oder ist kaputt - leer starten
  }
  const liste = Array.isArray(daten) ? daten : (daten.linuxApps || []);
  liste.forEach(_veraltetesIconErneuern);
  if (!Array.isArray(daten) && daten.seitenButtons) Object.values(daten.seitenButtons).forEach(_veraltetesIconErneuern);
  return daten;
});
ipcMain.handle('apps-speichern', (event, liste) => {
  fs.writeFileSync(APPS_LISTE_PATH, JSON.stringify(liste, null, 2), 'utf-8');
});

ipcMain.handle('schreibtische-lesen', () => {
  try {
    return JSON.parse(fs.readFileSync(SCHREIBTISCHE_PATH, 'utf-8'));
  } catch (e) {
    return []; // Datei gibt's noch nicht oder ist kaputt - leer starten
  }
});
ipcMain.handle('schreibtische-speichern', (event, liste) => {
  fs.writeFileSync(SCHREIBTISCHE_PATH, JSON.stringify(liste, null, 2), 'utf-8');
});

// Legt den echten Ordner eines Schreibtischs an (falls noch nicht vorhanden)
// und liefert den absoluten Pfad zurueck - wird bei jedem Oeffnen/Aktualisieren
// des Fensters aufgerufen (billig dank recursive:true, das bei einem schon
// vorhandenen Ordner einfach nichts tut), nicht nur einmal beim Erstellen,
// damit ein von Hand geloeschter Ordner beim naechsten Ablegen automatisch
// wieder da ist.
ipcMain.handle('schreibtisch-ordner-sicherstellen', (event, titel) => {
  const ordner = path.join(SCHREIBTISCH_ORDNER_BASIS, schreibtischOrdnerName(titel));
  fs.mkdirSync(ordner, { recursive: true });
  return ordner;
});
// Listet den echten Ordner-Inhalt (Klaus-Wunsch: was jemand direkt in
// LibreOffice dort hineinspeichert, soll im Schreibtisch auftauchen, ohne
// dass Milcrid selbst davon "weiss" - deshalb bei jedem Neuzeichnen frisch
// vom Dateisystem gelesen statt in schreibtische.json mitgefuehrt).
ipcMain.handle('schreibtisch-ordner-lesen', (event, ordner) => {
  try {
    return fs.readdirSync(ordner, { withFileTypes: true }).map(eintrag => {
      const voll = path.join(ordner, eintrag.name);
      let groesse = 0, geaendert = '';
      try {
        const stat = fs.statSync(voll);
        groesse = stat.size;
        geaendert = stat.mtime.toISOString().slice(0, 10);
      } catch (e) { /* zwischen readdir und stat verschwunden - egal */ }
      return { name: eintrag.name, ordner: eintrag.isDirectory(), groesse, geaendert, pfad: voll };
    });
  } catch (e) {
    return []; // Ordner (noch) nicht da oder nicht lesbar
  }
});
// Kopiert eine Datei zwischen Datei Manager und Schreibtisch, in BEIDE
// Richtungen (Klaus-Wunsch 2026-08-21: "zurueck ziehen geht nicht" +
// Kopieren/Einfuegen als Alternative zum Ziehen) - echte Kopie, kein
// Verweis, genau wie das Ablegen einer Datei auf dem Windows-Desktop.
// quellRelativerPfad/zielOrdner duerfen JEWEILS home-relativ (Datei Manager,
// z.B. "Dokumente/Brief.pdf" bzw. "Dokumente") ODER absolut sein (aus einem
// Schreibtisch, dessen Ordner schon als absoluter Pfad vorliegt) -
// path.resolve(homedir, x) behandelt beides gleich richtig: bei einem
// absoluten x wird homedir schlicht ignoriert. Quelle wird gegen das
// Home-Verzeichnis abgesichert, exakt dieselbe Pruefung wie
// dateimanager_verwaltung.py's ROOT_DIR-Grenze in Python, damit ein
// manipuliertes Datenpaket nicht irgendeine Systemdatei kopieren kann -
// dasselbe fuers Ziel, auch wenn es in der Praxis immer innerhalb des
// Home-Verzeichnisses liegt. Namenskollision haengt "(2)", "(3)", ... an,
// statt stillschweigend zu ueberschreiben.
ipcMain.handle('schreibtisch-datei-kopieren', (event, { quellRelativerPfad, zielOrdner }) => {
  // Seit 24.09.2026 auch von/auf ein Laufwerk ("@laufwerke/..."), sonst unveraendert
  // nur im Home - _dmBereichErlaubt prueft den ECHTEN (aufgeloesten) Pfad.
  const quelle = fs.realpathSync(_dateiPfadAufloesen(quellRelativerPfad));
  if (!_dmBereichErlaubt(quelle)) {
    throw new Error('Ungültiger Quellpfad');
  }
  const zielOrdnerAbsolut = _dateiPfadAufloesen(zielOrdner);
  if (!_dmBereichErlaubt(zielOrdnerAbsolut)) {
    throw new Error('Ungültiger Zielordner');
  }
  fs.mkdirSync(zielOrdnerAbsolut, { recursive: true });
  const ext = path.extname(quelle);
  const basis = path.basename(quelle, ext);
  let name = path.basename(quelle);
  let ziel = path.join(zielOrdnerAbsolut, name);
  let n = 1;
  while (fs.existsSync(ziel)) {
    n++;
    name = `${basis} (${n})${ext}`;
    ziel = path.join(zielOrdnerAbsolut, name);
  }
  fs.copyFileSync(quelle, ziel);
  return { name };
});
// Nimmt eine Datei wieder von einem Schreibtisch runter - bei einer echten
// Datei (anders als bei einem nur verknuepften Milcrid-Icon) heisst das
// wirklich LOESCHEN, nicht nur Trennen. Gleiche Absicherung wie beim
// Kopieren, damit ueber diesen Weg nichts ausserhalb der Schreibtisch-Ordner
// geloescht werden kann.
ipcMain.handle('schreibtisch-datei-loeschen', (event, pfad) => {
  const basis = fs.realpathSync(SCHREIBTISCH_ORDNER_BASIS);
  const ziel = fs.realpathSync(pfad);
  if (ziel !== basis && !ziel.startsWith(basis + path.sep)) {
    throw new Error('Ungültiger Zielpfad');
  }
  fs.rmSync(ziel, { recursive: true, force: true });
});
// Oeffnet eine Datei mit dem vom System zugeordneten Standardprogramm
// (Klaus-Wunsch: PDF/Text/Bilder z.B. in LibreOffice) - wie ein Doppelklick
// im normalen Dateimanager, technisch ueber xdg-open.
ipcMain.handle('datei-oeffnen', async (event, pfad) => {
  return await shell.openPath(pfad); // leerer String = ok, sonst Fehlertext
});

// Milcrid Editor (Klaus-Wunsch 2026-09-24): beliebige TEXT-Dateien lesen und
// schreiben. Grenzen, damit ein Fehlgriff harmlos bleibt: hoechstens 5 MB, und
// nichts mit Null-Bytes (Bild, PDF, Programm) - das waere im Textfeld nur
// Zeichensalat und beim Speichern kaputt. Geschrieben wird ueber eine
// Zwischendatei + Umbenennen: bricht es mittendrin ab, bleibt die alte Datei
// heil. Die Rechte der alten Datei bleiben erhalten (ausfuehrbare .sh).
const EDITOR_MAX_BYTES = 5 * 1024 * 1024;

// Wohin wirklich geschrieben wird (Systemcheck 24.09.2026, B-1). Vorher wurde die
// Zwischendatei auf den Pfad umbenannt: war er eine Verknuepfung, ersetzte das
// den LINK durch eine Kopie und das Original blieb alt - und Umbenennen ging
// auch ueber einen Schreibschutz hinweg. Jetzt: Verknuepfung -> ins Original
// schreiben (wie jeder Editor), schreibgeschuetzt -> ehrlich ablehnen.
function _schreibZiel(voll) {
  let ziel = voll;
  try { ziel = fs.realpathSync(voll); } catch (e) { return voll; }   // neue Datei
  try { fs.accessSync(ziel, fs.constants.W_OK); }
  catch (e) { throw new Error('Die Datei ist schreibgeschützt. Mit „Speichern unter“ als neue Datei ablegen.'); }
  return ziel;
}
ipcMain.handle('editor-datei-lesen', (event, pfad) => {
  try {
    const voll = path.resolve(String(pfad || ''));
    const info = fs.statSync(voll);
    if (!info.isFile()) return { erfolg: false, fehler: 'Das ist keine Datei.' };
    if (info.size > EDITOR_MAX_BYTES) {
      return { erfolg: false, fehler: `Zu groß für den Editor (${(info.size / 1048576).toFixed(1)} MB, höchstens 5 MB).` };
    }
    const roh = fs.readFileSync(voll);
    if (roh.includes(0)) return { erfolg: false, fehler: 'Keine Textdatei (z. B. Bild, PDF oder Programm).' };
    return { erfolg: true, pfad: voll, inhalt: roh.toString('utf-8') };
  } catch (e) {
    return { erfolg: false, fehler: e.code === 'ENOENT' ? 'Datei nicht gefunden.' : e.message };
  }
});
ipcMain.handle('editor-datei-schreiben', (event, pfad, inhalt) => {
  const voll = path.resolve(String(pfad || ''));
  let zwischen = null;
  try {
    const ziel = _schreibZiel(voll);
    zwischen = ziel + '.milcrid-speichern';
    fs.writeFileSync(zwischen, String(inhalt ?? ''), 'utf-8');
    try { fs.chmodSync(zwischen, fs.statSync(ziel).mode); } catch (e) { /* neue Datei */ }
    fs.renameSync(zwischen, ziel);
    return { erfolg: true, pfad: voll };
  } catch (e) {
    if (zwischen) try { fs.unlinkSync(zwischen); } catch (e2) {}
    return { erfolg: false, fehler: e.message };
  }
});

// Terminplaner: Datei(en) fuer einen Termin auswaehlen (Klaus-Brainstorm
// 2026-09-14). Nur der Pfad wird gemerkt, die Datei bleibt, wo sie ist.
// (Die frueheren kalender-lesen/-speichern sind weg: der Kalender liest seit
// dem Planer aus planer_verwaltung.py.)
ipcMain.handle('datei-auswaehlen', async (event) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  const ergebnis = await dialog.showOpenDialog(win, { properties: ['openFile', 'multiSelections'] });
  return ergebnis.canceled ? [] : ergebnis.filePaths;
});
// Eine Erinnerung meldet sich - liegt ein anderes Programm vor dem Portal,
// saehe man die Karte sonst nicht.
ipcMain.handle('portal-nach-vorne', (event) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  if (!win) return;
  if (win.isMinimized()) win.restore();
  win.show();
  win.moveTop();
  win.focus();
});

// ---- Milcrid App Store: Installieren-Klick auf der Store-Webseite laedt
// eine Milcrid-App (Kalender, Taschenrechner, ...) direkt in dieses Portal ----
//
// Der Store (https://miluh.de/apps/) laeuft als ganz normale, oeffentliche
// Webseite in Klaus' System-Browser, komplett getrennt von diesem Electron-
// Programm. Damit ein Klick auf "Installieren" trotzdem etwas in DIESEM,
// schon laufenden Portal ausloesen kann, hoert dieses Programm im Hintergrund
// auf einem lokalen Port mit (nur 127.0.0.1 - von aussen/aus dem Internet
// nicht erreichbar). Die Store-Seite schickt dorthin per fetch() eine
// Installieren-Anfrage; hier wird die App-Datei dann selbst aus dem
// oeffentlichen Store nachgeladen und als Kachel im Portal eingebaut -
// exakt das gleiche Prinzip wie beim alten, fest eingebauten Kalender
// (siehe appDateiLesen weiter oben), nur jetzt aus dem Netz statt von der
// Festplatte und fuer beliebige zukuenftige Milcrid-Apps statt nur Kalender.
const http = require('http');
const MILCRID_INSTALL_PORT = 51823;
const MILCRID_STORE_URSPRUNG = 'https://miluh.de';

// Nur Adressen unter https://miluh.de/apps/ werden nachgeladen - sonst koennte
// diese Schnittstelle missbraucht werden, um beliebige Internet-Adressen auf
// die Festplatte zu laden.
function istErlaubteStoreUrl(url) {
  try {
    const u = new URL(url);
    return u.origin === MILCRID_STORE_URSPRUNG && u.pathname.startsWith('/apps/');
  } catch (e) {
    return false;
  }
}

function milcridZustandLesen() {
  try {
    const geladen = JSON.parse(fs.readFileSync(APPS_LISTE_PATH, 'utf-8'));
    if (Array.isArray(geladen)) return { linuxApps: geladen, seitenButtons: {}, milcridApps: [] };
    if (!Array.isArray(geladen.milcridApps)) geladen.milcridApps = [];
    return geladen;
  } catch (e) {
    return { linuxApps: [], seitenButtons: {}, milcridApps: [] };
  }
}

async function milcridAppInstallieren(id, name, htmlUrl, jsUrl, iconUrl) {
  const zielOrdner = path.join(MILCRID_APPS_DIR, id);
  fs.mkdirSync(zielOrdner, { recursive: true });
  const htmlAntwort = await fetch(htmlUrl);
  // .ok pruefen, nicht nur ob fetch selbst geklappt hat - sonst wuerde z.B.
  // eine veraltete Store-Seite (verweist auf eine inzwischen umbenannte/
  // geloeschte Datei) eine 404-Fehlerseite als vermeintlich gueltigen
  // App-Inhalt abspeichern, statt sauber mit einem Fehler abzubrechen.
  if (!htmlAntwort.ok) throw new Error(`HTML nicht erreichbar (${htmlAntwort.status})`);
  fs.writeFileSync(path.join(zielOrdner, `${id}.html`), await htmlAntwort.text(), 'utf-8');
  if (jsUrl) {
    const jsAntwort = await fetch(jsUrl);
    if (!jsAntwort.ok) throw new Error(`JS nicht erreichbar (${jsAntwort.status})`);
    fs.writeFileSync(path.join(zielOrdner, `${id}.js`), await jsAntwort.text(), 'utf-8');
  }
  let iconPfad = null;
  if (iconUrl) {
    const iconAntwort = await fetch(iconUrl);
    if (iconAntwort.ok) {
      const endung = path.extname(new URL(iconUrl).pathname) || '.svg';
      iconPfad = path.join(zielOrdner, `${id}-icon${endung}`);
      fs.writeFileSync(iconPfad, Buffer.from(await iconAntwort.arrayBuffer()));
    }
  }

  const zustand = milcridZustandLesen();
  const eintrag = { id, name, iconPfad };
  zustand.milcridApps = zustand.milcridApps.filter(a => a.id !== id);
  zustand.milcridApps.push(eintrag);
  fs.writeFileSync(APPS_LISTE_PATH, JSON.stringify(zustand, null, 2), 'utf-8');

  BrowserWindow.getAllWindows().forEach(w => w.webContents.send('milcrid-app-installiert', eintrag));
  return eintrag;
}

ipcMain.handle('milcrid-app-entfernen', (event, id) => {
  const zustand = milcridZustandLesen();
  zustand.milcridApps = zustand.milcridApps.filter(a => a.id !== id);
  fs.writeFileSync(APPS_LISTE_PATH, JSON.stringify(zustand, null, 2), 'utf-8');
  fs.rmSync(path.join(MILCRID_APPS_DIR, id), { recursive: true, force: true });
});

// Vom Neustart-Hinweis im Portal aus aufgerufen ("Jetzt neu anmelden").
// --logout statt --reboot: neu installierte Flatpak-Programme brauchen nur
// eine neue Anmelde-Sitzung, keinen kompletten PC-Neustart. Ohne --no-prompt,
// damit Ubuntus eigener Abmelden-Dialog nochmal fragt/einen Countdown mit
// Abbrechen zeigt - niemand soll unerwartet mitten aus der Arbeit fliegen.
ipcMain.handle('gnome-neu-anmelden', () => {
  spawn('gnome-session-quit', ['--logout']);
});

function milcridInstallServerStarten() {
  // Zusaetzlich in eine Datei protokollieren (nicht nur console.log) - eine
  // aus dem Dock/Menue gestartete Electron-App hat oft kein sichtbares
  // Terminal, console.log-Ausgaben gehen dann ins Leere und ein Fehler beim
  // Starten dieses Servers waere sonst nicht nachvollziehbar.
  const installLogPfad = path.join(MILCRID_DIR, 'milcrid-install-server.log');
  function installProtokoll(zeile) {
    console.log('[Milcrid-App] ' + zeile);
    try { fs.appendFileSync(installLogPfad, new Date().toISOString() + ' ' + zeile + '\n', 'utf-8'); } catch (e) {}
  }

  // ---- Echtes Linux-Programm per Flatpak installieren (z.B. Firefox, VLC) ----
  // Anders als milcridAppInstallieren() oben (die nur Dateien herunterlaedt)
  // fuehrt das hier einen echten Systembefehl aus - deshalb vorher IMMER ein
  // sichtbares Ja/Nein-Fenster, und der Nutzer sieht/entscheidet, was passiert.
  async function flatpakInstallAnfragen(id, name) {
    const antwort = await dialog.showMessageBox({
      type: 'question',
      buttons: ['Installieren', 'Abbrechen'],
      defaultId: 0,
      cancelId: 1,
      title: 'Milcrid App Store',
      message: `"${name}" installieren?`,
      detail: `Wird per Flatpak von Flathub installiert (${id}). Laeuft im Hintergrund weiter.`,
    });
    if (antwort.response !== 0) return 'abgebrochen';

    const proc = spawn('flatpak', ['install', 'flathub', id, '-y'], { stdio: 'ignore' });
    proc.on('error', err => {
      installProtokoll(`Flatpak-Installation FEHLER (${name}/${id}): ${err.message}`);
    });
    proc.on('exit', code => {
      const erfolgreich = code === 0;
      installProtokoll(erfolgreich
        ? `Flatpak-Installation erfolgreich: ${name} (${id})`
        : `Flatpak-Installation fehlgeschlagen (Code ${code}): ${name} (${id})`);
      if (Notification.isSupported()) {
        new Notification({
          title: 'Milcrid App Store',
          body: erfolgreich ? `"${name}" wurde installiert.` : `"${name}" konnte nicht installiert werden (Fehlercode ${code}).`,
        }).show();
      }
      // Zusaetzlich ans Portal-Fenster (falls offen) - dort erscheint bei
      // Erfolg ein Hinweisfenster mit "Jetzt neu anmelden"/"Spaeter", das
      // stehen bleibt statt wie eine System-Benachrichtigung zu verschwinden.
      BrowserWindow.getAllWindows().forEach(w => w.webContents.send('flatpak-installation-fertig', { id, name, erfolgreich }));
    });
    return 'gestartet';
  }

  const server = http.createServer((req, res) => {
    let url;
    try { url = new URL(req.url, `http://127.0.0.1:${MILCRID_INSTALL_PORT}`); }
    catch (e) { res.writeHead(400); res.end(); return; }
    res.setHeader('Access-Control-Allow-Origin', MILCRID_STORE_URSPRUNG);

    if (req.method === 'GET' && url.pathname === '/install') {
      const id = url.searchParams.get('id');
      const name = url.searchParams.get('name');
      const htmlUrl = url.searchParams.get('html');
      const jsUrl = url.searchParams.get('js');
      const iconUrl = url.searchParams.get('icon');
      // id nur Buchstaben/Ziffern/Bindestrich - wird als Ordner-/Dateiname
      // benutzt, verhindert Pfad-Ausbrueche wie "../../".
      const gueltigeId = id && /^[a-z0-9-]+$/.test(id);
      if (!gueltigeId || !name || !htmlUrl || !istErlaubteStoreUrl(htmlUrl)
          || (jsUrl && !istErlaubteStoreUrl(jsUrl)) || (iconUrl && !istErlaubteStoreUrl(iconUrl))) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: false, error: 'ungueltige Anfrage' }));
        return;
      }
      milcridAppInstallieren(id, name, htmlUrl, jsUrl, iconUrl)
        .then(() => {
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ ok: true }));
        })
        .catch(err => {
          res.writeHead(500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ ok: false, error: String(err) }));
        });
      return;
    }

    if (req.method === 'GET' && url.pathname === '/flatpak-install') {
      // Nur Anfragen von der echten Store-Seite akzeptieren - ohne diese
      // Pruefung koennte jede beliebige Webseite, die der Nutzer besucht,
      // im Hintergrund eine echte Systeminstallation anstossen (das
      // Ja/Nein-Fenster faengt das zwar zusaetzlich ab, aber so kommt die
      // Anfrage erst gar nicht bis dahin).
      const ursprung = req.headers['referer'] || req.headers['origin'] || '';
      if (!ursprung.startsWith(MILCRID_STORE_URSPRUNG)) {
        res.writeHead(403, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: false, error: 'nicht erlaubter Ursprung' }));
        return;
      }
      const id = url.searchParams.get('id');
      const name = url.searchParams.get('name');
      // Flatpak-IDs sehen aus wie umgekehrte Domainnamen (org.videolan.VLC) -
      // wird unten direkt als Kommandozeilen-Argument benutzt, das verhindert
      // z.B. dass da sowas wie "--irgendwas" hineinrutscht.
      const gueltigeId = id && /^[A-Za-z][A-Za-z0-9]*(\.[A-Za-z][A-Za-z0-9_-]*)+$/.test(id);
      if (!gueltigeId || !name) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: false, error: 'ungueltige Anfrage' }));
        return;
      }
      flatpakInstallAnfragen(id, name)
        .then(status => {
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ ok: true, status }));
        })
        .catch(err => {
          res.writeHead(500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ ok: false, error: String(err) }));
        });
      return;
    }

    res.writeHead(404); res.end();
  });
  server.on('error', err => installProtokoll('Milcrid-Install-Server FEHLER: ' + err.message + ' (' + err.code + ')'));
  server.listen(MILCRID_INSTALL_PORT, '127.0.0.1', () => {
    installProtokoll('Milcrid-Install-Server gestartet auf 127.0.0.1:' + MILCRID_INSTALL_PORT);
  });
}

ipcMain.handle('app-datei-lesen', (event, relativerPfad) => {
  const vollerPfad = path.join(MILCRID_APPS_DIR, relativerPfad);
  // Verhindert, dass ein relativer Pfad mit "../.." aus dem Apps-Ordner
  // rausfuehrt und beliebige Dateien auf der Platte gelesen werden koennten.
  if (!vollerPfad.startsWith(MILCRID_APPS_DIR + path.sep)) {
    throw new Error('Ungueltiger App-Pfad: ' + relativerPfad);
  }
  return fs.readFileSync(vollerPfad, 'utf-8');
});

// ---- Installierte Linux-Programme finden (fuer Apps > Apps hinzufuegen) ----
// ---- Dateien oeffnen: Standardprogramme und "Oeffnen mit" (Klaus 24.09.2026) ----
// Das Portal entscheidet, WELCHES Programm (Tabelle in oeffnen_mit.json,
// Einstellungen > Standardprogramme); hier wird nur gestartet, gelesen und
// gespeichert. Gestartet wird ueber die beiden erprobten Wege weiter oben:
// Firefox ueber _adresseOeffnen (gio launch verliert bei laufendem Firefox
// das Argument, Fund 04.09.), alles andere ueber _appStarten (Flatpak-,
// Snap- und Terminal-Sonderfaelle).
const OEFFNEN_MIT_PFAD = path.join(MILCRID_DIR, 'oeffnen_mit.json');

// Home-relative Pfade (Datei Manager) und absolute (Themen, Milcrid) gleich behandeln.
function _dateiPfadAufloesen(pfad) {
  const roh = String(pfad || '');
  // Datei Manager auf einem Laufwerk (24.09.2026): "@laufwerke/<Name>/..." ->
  // /media/<nutzer>/<Name>/... (oder /run/media/...). Nie aus dem Laufwerk heraus.
  const lw = /^@laufwerke\/([^/]+)(?:\/(.*))?$/.exec(roh);
  if (lw) {
    for (const wurzel of _laufwerkWurzeln()) {
      if (path.basename(wurzel) !== lw[1] || !fs.existsSync(wurzel)) continue;
      const voll = path.resolve(wurzel, lw[2] || '');
      if (voll === wurzel || voll.startsWith(wurzel + path.sep)) return voll;
    }
    return path.join('/laufwerk-nicht-eingesteckt', lw[1]);
  }
  return path.isAbsolute(roh) ? path.resolve(roh) : path.resolve(os.homedir(), roh);
}
function _laufwerkWurzeln() {
  const u = os.userInfo().username, wurzeln = [];
  for (const basis of [`/media/${u}`, `/run/media/${u}`]) {
    try { for (const n of fs.readdirSync(basis)) wurzeln.push(path.join(basis, n)); } catch (e) {}
  }
  return wurzeln;
}
// Home oder ein eingestecktes Laufwerk - wohin der Datei Manager darf.
function _dmBereichErlaubt(abs) {
  const heim = fs.realpathSync(os.homedir());
  if (abs === heim || abs.startsWith(heim + path.sep)) return true;
  return _laufwerkWurzeln().some(w => abs === w || abs.startsWith(w + path.sep));
}

ipcMain.handle('oeffnen-mit-lesen', () => {
  try { return JSON.parse(fs.readFileSync(OEFFNEN_MIT_PFAD, 'utf-8')); }
  catch (e) { return {}; }
});
ipcMain.handle('oeffnen-mit-speichern', (event, daten) => {
  try {
    fs.writeFileSync(OEFFNEN_MIT_PFAD, JSON.stringify(daten || {}, null, 2), 'utf-8');
    return { erfolg: true };
  } catch (e) { return { erfolg: false, fehler: e.message }; }
});

ipcMain.handle('datei-pfad-pruefen', (event, pfad) => {
  const voll = _dateiPfadAufloesen(pfad);
  try {
    const info = fs.statSync(voll);
    return { gibt_es: true, pfad: voll, ordner: info.isDirectory(), groesse: info.size };
  } catch (e) { return { gibt_es: false, pfad: voll }; }
});

// Alle sichtbaren Programme mit ihren Dateiarten (MimeType) - fuer "Oeffnen
// mit" und die Einstellungen. Dieselben Ordner wie die App-Liste
// (DESKTOP_ORDNER); gleiche Datei in mehreren Ordnern zaehlt nur einmal.
ipcMain.handle('programme-mit-dateiarten', () => {
  const gesehen = new Set();
  const liste = [];
  for (const ordner of DESKTOP_ORDNER) {
    let dateien = [];
    try { dateien = fs.readdirSync(ordner).filter(n => n.endsWith('.desktop')); } catch (e) { continue; }
    for (const name of dateien) {
      if (gesehen.has(name)) continue;
      const voll = path.join(ordner, name);
      let werte;
      try { werte = desktopDateiLesen(fs.readFileSync(voll, 'utf-8')); } catch (e) { continue; }
      if (werte.NoDisplay === 'true' || werte.Hidden === 'true' || !werte.MimeType) continue;
      gesehen.add(name);
      liste.push({ id: name, desktop: voll, name: werte['Name[de]'] || werte.Name || name,
                   mime: werte.MimeType.split(';').filter(Boolean) });
    }
  }
  return liste;
});

ipcMain.handle('datei-mit-programm-oeffnen', (event, pfad, desktopPfad) => {
  const voll = _dateiPfadAufloesen(pfad);
  if (!fs.existsSync(voll)) return { erfolg: false, fehler: 'Die Datei gibt es nicht (mehr).' };
  if (!desktopPfad || !fs.existsSync(desktopPfad)) return { erfolg: false, fehler: 'Das Programm ist nicht (mehr) installiert.' };
  linuxAppLogZeile(`Oeffnen mit: "${voll}" -> ${desktopPfad}`);
  try {
    if (/firefox/i.test(path.basename(desktopPfad))) _adresseOeffnen(desktopPfad, voll, true);
    else _appStarten(desktopPfad, 'Oeffnen mit', voll);
    return { erfolg: true };
  } catch (e) { return { erfolg: false, fehler: e.message }; }
});

// Standard-Weg des Systems (Linux entscheidet) - mit Rueckmeldung statt still.
ipcMain.handle('datei-system-oeffnen', async (event, pfad) => {
  const voll = _dateiPfadAufloesen(pfad);
  const fehler = await shell.openPath(voll);
  return fehler ? { erfolg: false, fehler } : { erfolg: true };
});

// Nachbarn im selben Ordner fuer Bild- und Videobetrachter (vor/zurueck).
ipcMain.handle('ordner-dateien-mit-endung', (event, pfad, endungen) => {
  const voll = _dateiPfadAufloesen(pfad);
  const ordner = fs.existsSync(voll) && fs.statSync(voll).isDirectory() ? voll : path.dirname(voll);
  const erlaubt = new Set((endungen || []).map(e => String(e).toLowerCase()));
  try {
    return fs.readdirSync(ordner)
      .filter(n => !n.startsWith('.') && erlaubt.has(path.extname(n).slice(1).toLowerCase()))
      .sort((a, b) => a.localeCompare(b, 'de', { numeric: true, sensitivity: 'base' }))
      .map(n => path.join(ordner, n));
  } catch (e) { return []; }
});

// Bildbetrachter: gedrehtes/umgewandeltes Bild schreiben (data:-URL vom Canvas).
function _dataUrlZuPuffer(dataUrl) {
  const treffer = /^data:image\/[a-z+]+;base64,(.+)$/i.exec(String(dataUrl || ''));
  if (!treffer) throw new Error('Kein Bild erhalten.');
  return Buffer.from(treffer[1], 'base64');
}
ipcMain.handle('bild-speichern', (event, pfad, dataUrl) => {
  const voll = _dateiPfadAufloesen(pfad);
  let zwischen = null;
  try {
    const ziel = _schreibZiel(voll);
    zwischen = ziel + '.milcrid-speichern';
    fs.writeFileSync(zwischen, _dataUrlZuPuffer(dataUrl));
    fs.renameSync(zwischen, ziel);
    return { erfolg: true, pfad: voll };
  } catch (e) {
    if (zwischen) try { fs.unlinkSync(zwischen); } catch (e2) {}
    return { erfolg: false, fehler: e.message };
  }
});
ipcMain.handle('bild-speichern-unter', async (event, vorschlag, dataUrl) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  const start = path.isAbsolute(String(vorschlag || '')) ? vorschlag
    : path.join(app.getPath('pictures'), vorschlag || 'bild.png');
  let ergebnis;
  // Nur das Format anbieten, das im Inhalt steckt (Systemcheck 24.09.2026, B-2):
  // der Inhalt entsteht VOR dem Dialog - vorher konnte man dort JPG waehlen und
  // bekam PNG-Daten in einer .jpg-Datei.
  const art = (/^data:image\/([a-z+]+);/i.exec(String(dataUrl || '')) || [])[1] || 'png';
  const FORMATE = { png: { name: 'PNG-Bild', extensions: ['png'] },
                    jpeg: { name: 'JPG-Bild', extensions: ['jpg', 'jpeg'] },
                    webp: { name: 'WEBP-Bild', extensions: ['webp'] } };
  try {
    ergebnis = await dialog.showSaveDialog(win, { defaultPath: start, filters: [FORMATE[art.toLowerCase()] || FORMATE.png] });
  } catch (e) { return { erfolg: false, fehler: e.message }; }
  if (ergebnis.canceled || !ergebnis.filePath) return { erfolg: false, abgebrochen: true };
  // Von Hand eine andere Endung getippt ("bild.jpg" bei PNG-Inhalt)? Der Linux-Dialog
  // laesst das trotz Filter zu - dann die passende Endung setzen, damit Name und Inhalt stimmen.
  let ziel = ergebnis.filePath;
  const passend = (FORMATE[art.toLowerCase()] || FORMATE.png).extensions;
  const endung = path.extname(ziel).slice(1).toLowerCase();
  if (!passend.includes(endung)) ziel = (endung ? ziel.slice(0, -(endung.length + 1)) : ziel) + '.' + passend[0];
  try {
    fs.writeFileSync(ziel, _dataUrlZuPuffer(dataUrl));
    return { erfolg: true, pfad: ziel };
  } catch (e) { return { erfolg: false, fehler: e.message }; }
});

// Datei-Auswahl mit Filter (Bild-/Videobetrachter), startet im passenden Ordner.
ipcMain.handle('datei-auswaehlen-art', async (event, art) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  const ARTEN = {
    bild: { ordner: 'pictures', name: 'Bilder', ext: ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'avif', 'ico'] },
    video: { ordner: 'videos', name: 'Videos und Musik', ext: ['mp4', 'webm', 'mkv', 'mov', 'm4v', 'ogv', 'mp3', 'ogg', 'oga', 'wav', 'flac', 'm4a', 'opus', 'aac'] },
  };
  const a = ARTEN[art];
  const optionen = { properties: ['openFile', 'multiSelections'] };
  if (a) {
    try { optionen.defaultPath = app.getPath(a.ordner); } catch (e) {}
    optionen.filters = [{ name: a.name, extensions: a.ext }, { name: 'Alle Dateien', extensions: ['*'] }];
  }
  const ergebnis = await dialog.showOpenDialog(win, optionen);
  return ergebnis.canceled ? [] : ergebnis.filePaths;
});

function desktopDateiLesen(inhalt) {
  const werte = {};
  let imEintrag = false;
  for (const zeile of inhalt.split('\n')) {
    const getrimmt = zeile.trim();
    if (getrimmt === '[Desktop Entry]') { imEintrag = true; continue; }
    if (getrimmt.startsWith('[')) { if (imEintrag) break; else continue; }
    if (!imEintrag) continue;
    const gleich = getrimmt.indexOf('=');
    if (gleich === -1) continue;
    const schluessel = getrimmt.slice(0, gleich).trim();
    // Erster Treffer gewinnt - ueberspringt Locale-Varianten wie "Name[de]"
    if (!(schluessel in werte)) werte[schluessel] = getrimmt.slice(gleich + 1).trim();
  }
  return werte;
}

function iconPfadAufloesen(icon) {
  if (!icon) return null;
  if (path.isAbsolute(icon)) return fs.existsSync(icon) ? icon : null;
  for (const ordner of ICON_ORDNER) {
    for (const endung of ['png', 'svg', 'xpm']) {
      const kandidat = path.join(ordner, `${icon}.${endung}`);
      if (fs.existsSync(kandidat)) return kandidat;
    }
  }
  return null;
}

// Liest alle .desktop-Eintraege einmal ein (Name -> {name, exec, pfad, icon}).
// Eigene Funktion, damit sowohl die "Vom PC (Linux)"-Liste als auch der
// Nachschlage-Fallback in linux-app-starten (fuer Kacheln, die noch aus der
// Zeit VOR dem pfad-Feld stammen, siehe dort) dieselbe Quelle benutzen.
function _alleDesktopEintraege() {
  const gefunden = new Map(); // Name -> Eintrag, gegen Duplikate ueber mehrere Ordner
  for (const ordner of DESKTOP_ORDNER) {
    let dateien;
    try { dateien = fs.readdirSync(ordner); } catch (e) { continue; }
    for (const datei of dateien) {
      if (!datei.endsWith('.desktop')) continue;
      const pfad = path.join(ordner, datei);
      let werte;
      try { werte = desktopDateiLesen(fs.readFileSync(pfad, 'utf-8')); }
      catch (e) { continue; }
      if (werte.Type !== 'Application') continue;
      if (werte.NoDisplay === 'true' || werte.Hidden === 'true') continue;
      if (!werte.Name || !werte.Exec) continue;
      if (gefunden.has(werte.Name)) continue;
      // Exec kann Platzhalter wie %u/%f/%U/%F enthalten - fuers Starten unnoetig
      const exec = werte.Exec.replace(/%[a-zA-Z]/g, '').trim();
      gefunden.set(werte.Name, { name: werte.Name, exec, pfad, icon: iconPfadAufloesen(werte.Icon) });
    }
  }
  return gefunden;
}

ipcMain.handle('linux-apps-liste', () => {
  const gefunden = _alleDesktopEintraege();
  return [...gefunden.values()].sort((a, b) => a.name.localeCompare(b.name, 'de'));
});

// Wie oft neu geprueft wird, ob ein verfolgtes Programm noch laeuft.
//
// War mal 4, dann 8 Sekunden (Klaus 2026-08-11, "GPU geht immer rauf und
// runter, obwohl ich nichts mache") - jede Pruefung startet pro offener App
// bis zu zwei pgrep-Prozesse UND einen gdbus-Aufruf in die GNOME-Shell
// hinein, und die Shell ist der Fensterverwalter, der auf der Grafikkarte
// laeuft, daher der Verdacht auf Polling als Ursache. Auf 3 Sekunden
// zurueckgesetzt (Klaus 2026-08-15, "Icon bleibt zu lange nach dem
// Schliessen stehen"): er vermutet inzwischen, das GPU-Auf-und-Ab von
// damals kam eher von einem Linux-Update, das zufaellig gleichzeitig lief,
// nicht vom Polling selbst - falls das GPU-Verhalten zurueckkommt, ist
// dieser Wert der erste Verdaechtige.
const LAUFEND_PRUEF_ABSTAND_MS = 3000;

// Wie lange nach dem Start darf das Fenster automatisch nach vorne geholt
// werden? Danach nie wieder ungefragt (siehe Erststart-Fokus weiter unten).
const ERSTSTART_FOKUS_FENSTER_MS = 20000;

// Klaus-Fund 2026-09-03, zweite Runde: ein fester Zeitabstand (erst
// probiert: 2,5s) reicht NICHT als Doppelklick-Schutz - "laufendePrograme"
// traegt einen neu gestarteten Befehl schon optimistisch als "laeuft" ein,
// BEVOR ueberhaupt ein Fenster bestaetigt ist (siehe "anzahl: 1" beim
// set() weiter unten), aber Firefox braucht auf diesem PC (NVIDIA-Treiber,
// Snap-Sandbox) manchmal mehrere Sekunden laenger als das, bis sein
// Einzelinstanz-Mechanismus wirklich bereit ist. Jeder Klick VOR diesem
// Zeitpunkt startet einen weiteren echten Firefox-Prozess, der sich mit
// den anderen um die Profil-Sperre streitet - Klaus beobachtete das als
// sieben gestapelte Firefox-Symbole in der Taskleiste nach mehrfachem
// Klicken. Fix: nicht mehr nach fester Zeit, sondern nach ECHTER
// Bestaetigung (erstes gesehenes Fenster, "bestaetigt" unten) - bis dahin
// ignoriert ein erneuter Klick auf dieselbe Kachel/denselben Seiten-Knopf
// den Start, mit einer Notbremse bei 25s falls nie ein Fenster kommt
// (sonst waere ein wirklich haengengebliebenes Programm fuer immer
// blockiert). Ein Klick von der TASKLEISTE (ausTaskleiste) will ohnehin
// nur das vorhandene Fenster zurueckholen, nicht neu starten - der greift
// weiter unten in einen anderen Zweig und ist von dieser Sperre nicht
// betroffen.
const START_UNBESTAETIGT_NOTBREMSE_MS = 25000;

ipcMain.on('linux-app-starten', (event, eintrag) => {
  // Rueckwaerts-kompatibel: frueher wurde nur der reine exec-String
  // geschickt, jetzt {exec, name, icon} fuer die Taskleiste.
  const info = (typeof eintrag === 'string') ? { exec: eintrag, name: eintrag, icon: null } : (eintrag || {});
  const teile = (info.exec || '').split(' ').filter(Boolean);
  if (!teile.length) return;
  const laeuftSchon = laufendePrograme.has(info.exec);
  // Die Mehrfachklick-Sperre gilt NICHT, wenn eine Adresse mitkommt.
  //
  // Klaus-Fund 2026-09-04: "öffne alle Links" uebergab korrekt fuenf
  // Adressen, geoeffnet wurde aber nur die erste. Im Protokoll stand
  // viermal "Start ignoriert" mit derselben Millisekunde - die Sperre, die
  // ich morgens gegen die sieben gleichzeitigen Firefox-Instanzen gebaut
  // hatte, hielt die vier weiteren fuer Doppelklicks.
  //
  // Sie hat recht, solange es um "starte das Programm" geht: zweimal
  // dasselbe ohne Adresse ist wirklich ein Versehen. Fuenf verschiedene
  // Adressen sind aber fuenf verschiedene Auftraege, auch wenn sie in
  // derselben Millisekunde kommen. Dieselbe Unterscheidung wie weiter
  // unten beim Oeffnen selbst.
  if (laeuftSchon && !info.ausTaskleiste && !info.url) {
    const bestehenderEintrag = laufendePrograme.get(info.exec);
    const nochUnbestaetigt = !bestehenderEintrag.bestaetigt
      && (Date.now() - (bestehenderEintrag.gestartetUm || 0)) < START_UNBESTAETIGT_NOTBREMSE_MS;
    if (nochUnbestaetigt) {
      linuxAppLogZeile(`Start ignoriert (voriger Start von "${info.exec}" hat noch kein Fenster bestätigt): exec="${info.exec}"`);
      return;
    }
  }
  // Kacheln, die schon VOR dem pfad-Feld auf den Portal-Seiten-Button gezogen
  // wurden (per Drag&Drop in apps.json gespeichert), kennen ihren
  // Desktop-Datei-Pfad noch nicht - hier per Exec-Abgleich nachschlagen,
  // damit auch schon vorhandene Kacheln (z.B. das bestehende Firefox-Icon)
  // ohne erneutes Hinzufuegen den zuverlaessigeren gio-launch-Weg bekommen.
  if (!info.pfad) {
    for (const eintrag of _alleDesktopEintraege().values()) {
      if (eintrag.exec === info.exec) { info.pfad = eintrag.pfad; break; }
    }
  }
  // Bevorzugt ueber "gio launch <Desktop-Datei>" starten statt die Exec-Zeile
  // blind selbst zu spawnen: das ist derselbe Weg, den auch GNOME beim Klick
  // im App-Raster benutzt, und holt ein bereits laufendes Einzelinstanz-
  // Programm (z.B. Firefox, per Klick auf sein Taskleisten-Icon nach dem
  // Minimieren) zuverlaessiger wieder nach vorne, statt ein weiteres Fenster/
  // eine weitere Instanz zu oeffnen. Nur falls kein Desktop-Datei-Pfad bekannt
  // ist (z.B. rueckwaerts-kompatibler reiner exec-String), auf den alten,
  // rohen Spawn zurueckfallen.
  // Klaus-Fund 2026-09-03, vierte Runde: "ausTaskleiste" unterschied bisher
  // den Klick auf das Taskleisten-Icon (holt das VORHANDENE Fenster zurueck,
  // ueber _appNachVorneHolen) vom Klick auf die Portal-Kachel/Seiten-Button
  // (rief bislang bewusst NOCHMAL "gio launch" auf, in der Annahme, das
  // oeffne bei einem schon laufenden Einzelinstanz-Programm nur ein
  // weiteres Fenster IM SELBEN Prozess). Log-Beweis vom echten Test 2026-
  // 09-03: bei Firefox (Snap) stimmt diese Annahme nicht - jeder erneute
  // "gio launch" auf ein schon laufendes Firefox startete einen VOELLIG
  // EIGENEN, neuen Firefox-Prozess (neue PID), der sich dann mit den
  // anderen um die Profil-Sperre stritt - mal klappte die interne
  // Uebergabe zwischen den Prozessen (Fenster kam zurueck), mal nicht
  // (genau die "is already running"-Fehlermeldung).
  //
  // Versuch (spaeter wieder verworfen): Firefox' eigene "new-window"-
  // Desktop-Aktion (--new-window) statt gio launch aufrufen. Klang richtig
  // (Firefox' eigener Fernsteuerungs-Mechanismus), war es aber nicht -
  // mehrfacher echter Test zeigte, dass auch DAS bei Snap-Firefox
  // unzuverlaessig ist (mal Uebergabe an die laufende Instanz, mal ein
  // weiterer eigener Prozess, auch mit korrekt gesetztem
  // DBUS_SESSION_BUS_ADDRESS/DISPLAY/XAUTHORITY) - liegt tiefer in der
  // Snap-Isolierung, nicht in main.js loesbar. Darum jetzt einheitlich: ein
  // schon bestaetigt laufendes Programm wird IMMER nur nach vorne geholt,
  // nie erneut gestartet - das ist die einzige Variante, die im Test
  // wirklich zuverlaessig war (kein Fehler, kein doppelter Prozess).
  // WICHTIG: "mit einer Adresse oeffnen" ist etwas ANDERES als "zeig mir das
  // Programm". Deshalb steht info.url hier VOR der Schon-offen-Pruefung.
  //
  // Klaus-Fund 2026-09-04: Ein Klick auf einen Link im Ergebnis-Fenster
  // brachte nur ein leeres Firefox nach vorne. Ursache war meine eigene
  // Reparatur vom selben Tag - gegen die sieben gleichzeitigen Firefox-
  // Instanzen wurde ein schon laufendes Programm nur noch nach vorne geholt,
  // nie wieder gestartet. Fuer den Klick auf die Kachel ist das genau
  // richtig; fuer einen Link ist es falsch, denn dabei faellt die Adresse
  // ersatzlos weg. Bei mir fiel es nicht auf, weil Firefox beim Test
  // geschlossen war - dann laeuft es in den Zweig darunter, wo die Adresse
  // korrekt mitgeht. Ein Fehler, der nur auftritt, wenn das Programm schon
  // laeuft.
  const mitAdresse = !!(info.url && info.pfad && fs.existsSync(info.pfad));
  if (mitAdresse) {
    linuxAppLogZeile(`Adresse oeffnen: url="${info.url}" pfad="${info.pfad}" laeuftSchon=${laeuftSchon}`);
    _adresseOeffnen(info.pfad, info.url, laeuftSchon);
    // Laeuft der Browser schon, uebergibt er die Adresse an sein
    // vorhandenes Fenster - das kommt dabei aber nicht von selbst nach
    // vorne. Deshalb zusaetzlich anstupsen (bestes Bemuehen, ohne auf
    // Erfolg zu warten), sonst oeffnet sich der Tab unsichtbar im
    // Hintergrund.
    // KEIN vorzeitiges return hier: war der Browser noch NICHT offen, muss
    // er weiter unten ganz normal in die Taskleiste aufgenommen werden -
    // sonst startet er ohne Icon und ohne Ueberwachung (beim ersten Entwurf
    // dieser Zeilen genau so eingebaut und beim Nachlesen gefunden).
    if (laeuftSchon) _appNachVorneHolen(info.pfad, 'nach Adresse', { aktivieren: true, neustarten: false });
  } else if (laeuftSchon && info.pfad) {
    _appNachVorneHolen(info.pfad, info.ausTaskleiste ? 'Taskleisten-Klick' : 'Portal-Klick (schon laufend)', { aktivieren: true, neustarten: true });
  } else if (info.pfad && fs.existsSync(info.pfad)) {
    // info.url (optional): z.B. der Milcrid-App-Store-Link, der Firefox samt
    // dieser Adresse oeffnen soll statt nur blank - "gio launch" akzeptiert
    // dafuer eine zusaetzliche URI hinter dem Desktop-Datei-Pfad.
    // laeuftSchon ist hier immer false (der Fall "laeuftSchon && info.pfad"
    // wird schon vom Zweig oben abgefangen) - dieser Pfad ist also immer ein
    // wirklich ERSTER Start.
    linuxAppLogZeile(`Start: exec="${info.exec}" pfad="${info.pfad}" url="${info.url || ''}"`);
    _appStarten(info.pfad, 'Portal-Klick', info.url);
  } else {
    linuxAppLogZeile(`roher Spawn (kein pfad): exec="${info.exec}" laeuftSchon=${laeuftSchon}`);
    const kindprozess = spawn(teile[0], teile.slice(1), { detached: true, stdio: 'ignore' });
    // Ohne diesen Handler crasht ein fehlendes/falsch geschriebenes Programm
    // (ENOENT) die GESAMTE App ("A JavaScript error occurred in the main
    // process") - Node wirft das 'error'-Ereignis sonst als unbehandelte
    // Exception (Klaus/Claude 2026-08-19, beobachtet bei LibreOffice waehrend
    // es kurzzeitig deinstalliert war).
    kindprozess.on('error', (fehler) => {
      linuxAppLogZeile(`roher Spawn FEHLGESCHLAGEN: exec="${info.exec}" fehler="${fehler.message}"`);
    });
    kindprozess.unref();
  }
  if (laeuftSchon) {
    // Programm ist laut unserer Liste schon offen - wurde oben bereits per
    // _appNachVorneHolen nach vorne geholt (statt neu gestartet), darum hier
    // nur raus: der bestehende Tracking-Eintrag samt Poll-Intervall (weiter
    // unten aufgebaut) existiert fuer dieses Programm schon.
    return;
  }
  // Ob das Programm noch laeuft (und wie oft), wird per pgrep auf den
  // Programmnamen geprueft (nicht ob GENAU dieser gestartete Prozess noch
  // existiert - siehe _anzahlLaufend weiter oben). basename greift bei
  // Pfaden wie "/snap/bin/firefox" genauso wie bei einem blossen
  // Befehlsnamen wie "firefox" oder "libreoffice".
  const suchbegriff = path.basename(teile[0]);
  // Nur fuer WIRKLICH D-Bus-aktivierbare Programme (siehe Erststart-Fokus
  // weiter unten) darf der automatische Zweitversuch ueberhaupt einen
  // zweiten Prozess nachschieben - fuer alles andere waere das ein
  // ungefragter doppelter Start (siehe dortige Begruendung, Klaus
  // 2026-08-23: Flatpak-Programm "System Monitoring Center").
  let istDBusAktivierbar = false;
  if (info.pfad) {
    try { istDBusAktivierbar = desktopDateiLesen(fs.readFileSync(info.pfad, 'utf-8')).DBusActivatable === 'true'; }
    catch (e) {}
  }
  // Manche Apps starten zwar sauber (Prozess laeuft, Taskleisten-Icon
  // erscheint schon optimistisch weiter unten), ihr Fenster kommt aber nicht
  // von selbst nach vorne - Klaus' Beobachtung 2026-08-11: bei "Settings"
  // erscheint nur das Icon, das Fenster nicht, und verschwindet nach ein
  // paar Sekunden von selbst wieder; klickt man vorher auf das Icon, geht es
  // doch noch auf. Konkret nachvollzogen: "Settings" (org.gnome.Settings)
  // ist D-Bus-aktivierbar (DBusActivatable=true) - der erste "gio launch"
  // startet dabei nur den Hintergrunddienst, ohne zuverlaessig ein Fenster
  // zu oeffnen; der Dienst beendet sich nach ein paar Sekunden Untaetigkeit
  // von selbst wieder, wenn nie eines aufging. Fix: sobald der Prozess zum
  // ERSTEN Mal bestaetigt laeuft (und damit noch bevor er wieder verschwindet),
  // einmalig _appNachVorneHolen nachschieben - das versucht zuerst
  // ActivateApp, und wenn die App noch gar kein Fenster hat (wie bei
  // "Settings"), faellt es automatisch auf einen zweiten "gio launch" zurueck,
  // genau der Weg der beim manuellen Klick auf das Taskleisten-Icon
  // nachweislich hilft. Nur einmal pro Start (fokusVersucht), damit spaetere
  // Pruef-Durchlaeufe nicht wiederholt den Fokus stehlen, waehrend Klaus
  // laengst in einem anderen Fenster arbeitet.
  let fokusVersucht = false;
  // Zeitpunkt des echten Starts - Grundlage fuer die Erststart-Fokus-Frist
  // weiter unten (siehe ausfuehrliche Begruendung dort).
  const startZeitpunkt = Date.now();
  let letzteGemeldeteAnzahl = null;
  // Bei "Settings" konkret beobachtet (Klaus, 2026-08-11): der D-Bus-
  // aktivierte Hintergrunddienst braucht manchmal laenger als die erste
  // Pruefung (4s) nach dem "gio launch", um ueberhaupt als Prozess zu
  // erscheinen - die allererste Pruefung sah dann faelschlich anzahl=0 und
  // hat das Icon sofort wieder entfernt, BEVOR die eigentliche
  // Erststart-Fokus-Logik (siehe _appNachVorneHolen oben) je eine Chance
  // hatte zu greifen. Fix: bevor ein Programm ueberhaupt einmal als
  // laufend bestaetigt wurde (jeSchonGelaufen), bei anzahl=0 nicht sofort
  // aufgeben, sondern noch ein paar Pruefungen Gnadenfrist geben. Ist das
  // Programm schon mal bestaetigt gelaufen und schliesst dann WIRKLICH,
  // gilt weiter die alte, sofortige Reaktion - kein Verzoegern beim
  // normalen Schliessen.
  let jeSchonGelaufen = false;
  let startGnadenfristUebrig = 3;
  // Zusaetzliche Absicherung gegen falsch-positive pgrep-Treffer (Klaus,
  // 2026-08-11, "Resources"): der -f-Rueckfall in _anzahlLaufend sucht nach
  // dem Programmnamen als Textschnipsel in der GESAMTEN Befehlszeile
  // irgendeines Prozesses auf dem System - bei kurzen/generischen Namen wie
  // "resources" kann das zufaellig auf ein voellig anderes Programm
  // anspringen (hier: Claude Desktop, das selbst einen "resources"-Ordner im
  // Pfad hat). Ergebnis: das Taskleisten-Icon blieb fuer immer haengen, mit
  // einer falschen (und je nachdem, was gerade sonst so laeuft, sogar
  // schwankenden) Punktzahl, obwohl "Resources" nie wirklich offen war. Die
  // miluh-window-activator-Erweiterung kennt (ueber Shell.AppSystem) die
  // WIRKLICHE Fensteranzahl der App, unabhaengig vom pgrep-Treffer - bleibt
  // die trotz "laeuft laut pgrep" dauerhaft bei 0, ist das ein starkes
  // Indiz fuer genau diesen Fall. Erst aufgeben, wenn das mehrfach
  // hintereinander so bleibt (nicht sofort beim ersten Mal - ein echtes,
  // gerade erst gestartetes Programm braucht selbst mit dem
  // Erststart-Fokus-Fix oben ein paar Sekunden, bis sein Fenster existiert).
  // Auf 8 angehoben (Klaus, 2026-08-23, Flatpak-App "System Monitoring
  // Center"): mit dem Ende des automatischen Zweitversuchs fuer
  // NICHT-D-Bus-Programme (siehe istDBusAktivierbar/Erststart-Fokus oben)
  // ist der einzige verbleibende Schutz vor einem langsamen, aber echten
  // Programmstart diese Zaehl-Frist - 4 Pruefungen (12s) reichten fuer ein
  // Sandbox-Programm (bwrap + D-Bus-Proxy + GTK/Tk, gemessen ca. 5-6s ab
  // Prozessstart, plus die 3s bis zur ERSTEN Pruefung) zu knapp aus.
  let keinFensterTrotzLaufendUebrig = 8;
  const timer = setInterval(() => {
    _anzahlLaufend(suchbegriff, (anzahl, pids, genau) => {
      // Fensterzahl JETZT schon holen (nicht erst weiter unten fuer die
      // Punkte): sie entscheidet mit darueber, ob das Programm ueberhaupt
      // noch laeuft.
      //
      // WARUM (Klaus 2026-08-13: "das Chrome-Icon geht weg, Chrome ist aber
      // noch offen"): der pgrep-Weg sucht nach dem Befehlsnamen aus der
      // Desktop-Datei - bei Chrome "google-chrome-stable". Das ist doppelt
      // zum Scheitern verurteilt: "pgrep -x" kann Prozessnamen ueber 15
      // Zeichen grundsaetzlich nicht finden, und der laufende Prozess heisst
      // in Wahrheit "chrome" (/opt/google/chrome/chrome), enthaelt den
      // gesuchten Text also auch in seiner Befehlszeile nicht. pgrep meldete
      // dadurch dauerhaft 0, das Icon verschwand nach der Gnadenfrist -
      // waehrend die Fenster-Erweiterung die ganze Zeit sauber "1 Fenster"
      // meldete. Ein sichtbares Fenster ist der verlaesslichere Beweis, dass
      // ein Programm laeuft, als ein Namensvergleich.
      // Zweiter Wert seit 23.09.2026 (Klaus' Regel (b)): wie viele Fenster dieses
      // Programms WEGGEKLAPPT sind. Beim ersten Anlauf hatte ich nur die andere
      // Aufrufstelle (_appNachVorneHolen) umgestellt und diese hier uebersehen -
      // die Abfrageschleife reichte den Wert dadurch nicht durch, er war immer
      // undefined, und Linux-Programme bekamen GAR KEIN Bildchen mehr.
      const weiterPruefen = (fensterAnzahl, fensterMinimiert) => {
      // Vorruebergehend: jede Pruefung mit den echten PIDs protokollieren,
      // um zu sehen ob wirklich mehrere GETRENNTE Prozesse gleichzeitig
      // laufen (echtes Mehrfachfenster-Problem) oder ob sich nur einer
      // abwechselnd verabschiedet/neu meldet (Erkennungs-Wackler). Kann
      // wieder raus, sobald das Problem gefunden ist.
      // Nur noch protokollieren, wenn sich WIRKLICH etwas geaendert hat -
      // vorher schrieb jede App alle 4 Sekunden eine Zeile, die Datei war
      // dadurch nach einem Tag 36 KB gross und die echten Ereignisse gingen
      // zwischen tausenden identischen "anzahl=1"-Zeilen unter.
      if (anzahl !== letzteGemeldeteAnzahl) {
        letzteGemeldeteAnzahl = anzahl;
        linuxAppLogZeile(`Pruefung ${suchbegriff}: anzahl=${anzahl} genau=${genau} pids=[${(pids || []).join(',')}]`);
      }
      const laeuftLautFenster = fensterAnzahl !== null && fensterAnzahl > 0;
      if (anzahl <= 0 && !laeuftLautFenster) {
        if (!jeSchonGelaufen && startGnadenfristUebrig > 0) {
          startGnadenfristUebrig--;
          linuxAppLogZeile(`${suchbegriff} noch nicht erkannt, Gnadenfrist (${startGnadenfristUebrig} weitere Pruefungen)`);
          return;
        }
        clearInterval(timer);
        laufendePrograme.delete(info.exec);
        sendeLaufendeProgrammeAnAlleFenster();
        return;
      }
      if (anzahl <= 0 && laeuftLautFenster && !jeSchonGelaufen) {
        linuxAppLogZeile(`${suchbegriff}: pgrep findet nichts, Erweiterung meldet aber ${fensterAnzahl} Fenster - Icon bleibt (Name aus der Desktop-Datei passt nicht zum echten Prozessnamen).`);
      }
      jeSchonGelaufen = true;
      // Erststart-Fokus NUR in den ersten Sekunden nach dem echten Start.
      //
      // WARUM DIE ZEITGRENZE (Klaus 2026-08-11): die pgrep-Erkennung wackelt
      // bei snap-Programmen. Im Log steht schwarz auf weiss, wie Firefox
      // zwischen anzahl=1 und anzahl=0 springt, obwohl es die ganze Zeit
      // offen war. Bei jedem "0" wird der Eintrag verworfen, beim naechsten
      // Start ein NEUER Zaehler mit fokusVersucht=false angelegt - und der
      // holte dann wieder das Fenster nach vorne, das Klaus laengst
      // minimiert hatte. Nach dieser Frist wird nie wieder ungefragt
      // fokussiert; wer sein Fenster zurueck will, klickt aufs Icon.
      const seitStart = Date.now() - startZeitpunkt;
      if (!fokusVersucht && info.pfad && istDBusAktivierbar && seitStart <= ERSTSTART_FOKUS_FENSTER_MS) {
        fokusVersucht = true;
        // Automatisch: fasst ein vorhandenes Fenster NIE an, schiebt aber bei
        // "gar kein Fenster" den zweiten Start nach - NUR bei
        // DBusActivatable=true (z.B. GNOME Settings): deren erster Aufruf
        // faehrt nachweislich nur einen Hintergrunddienst hoch, OHNE je ein
        // Fenster zu oeffnen, ein zweiter Aufruf hilft dort wirklich (siehe
        // _appNachVorneHolen).
        //
        // Fuer JEDES ANDERE Programm (Klaus, 2026-08-23: das per Flatpak
        // installierte "System Monitoring Center" ging nie auf - der
        // automatische Zweitversuch hat schon nach 3s eine ZWEITE, ebenso
        // schwere Sandbox-Instanz nachgestartet, WAEHREND die erste noch am
        // Hochfahren war (bwrap + D-Bus-Proxy + GTK/Tk brauchen laut Test
        // von Hand ca. 5-6s) - beide haben sich dadurch gegenseitig
        // ausgebremst, keine kam je so weit, ihr Fenster zu zeigen): kein
        // Neustart, nur laenger warten (siehe keinFensterTrotzLaufendUebrig
        // unten) - ein normales, bloss etwas langsames Programm braucht
        // manchmal ein paar Sekunden mehr, keinen zweiten Versuch.
        _appNachVorneHolen(info.pfad, 'Erststart-Fokus', { aktivieren: false, neustarten: true });
      } else if (!fokusVersucht && (!istDBusAktivierbar || seitStart > ERSTSTART_FOKUS_FENSTER_MS)) {
        fokusVersucht = true;  // Frist abgelaufen (oder gar nicht D-Bus-aktivierbar) - nicht nachholen
        if (istDBusAktivierbar) linuxAppLogZeile(`${suchbegriff}: Erststart-Fokus-Frist abgelaufen (${Math.round(seitStart / 1000)}s) - Fenster wird NICHT nach vorne geholt.`);
      }
      const eintrag = laufendePrograme.get(info.exec);
      if (!eintrag) return;
      const anzahlUebernehmen = (finaleAnzahl, echteBestaetigung) => {
        // Erste ECHTE Bestaetigung (wirklich ein Fenster/ein exakter
        // Prozess-Treffer gesehen, nicht der weiter unten beschriebene
        // Sicherheits-Blindwert "1") - schaltet die Mehrfachklick-Sperre
        // oben wieder frei. Ohne die eigene "echteBestaetigung"-Unter-
        // scheidung wuerde der Blindwert-Aufruf (siehe unten) die Sperre
        // faelschlich schon nach der ersten Pruefung freischalten, obwohl
        // noch gar kein Fenster bestaetigt war (Klaus-Fund 2026-09-03,
        // dritte Runde: schnelles Mehrfachklicken oeffnete trotz Sperre
        // wieder mehrere Firefox-Instanzen, sobald diese erste Pruefung -
        // rund 3s nach dem Start - einmal gelaufen war).
        if (echteBestaetigung) eintrag.bestaetigt = true;
        if (eintrag.anzahl !== finaleAnzahl) {
          eintrag.anzahl = finaleAnzahl;
          sendeLaufendeProgrammeAnAlleFenster();
        }
      };
      // Die echte Fenster-Anzahl der Erweiterung ist genauer als die
      // Prozess-Anzahl (Einzelinstanz-Programme haben mehrere Fenster in
      // EINEM Prozess). Liefert die Erweiterung nichts Brauchbares (inaktiv,
      // oder 0 obwohl der Prozess laeuft), bei der Prozess-Anzahl bleiben
      // statt faelschlich auf 0 zu springen.
      if (fensterAnzahl && fensterAnzahl > 0) {
        // Ab jetzt kuerzere Frist (2 statt 8 Pruefungen): der grosse Wert
        // oben ist reine GEDULD BEIM START - ein noch hochfahrendes Programm
        // hat sein Fenster oft erst nach einigen Sekunden. Sobald aber schon
        // einmal ein echtes Fenster da war, ist "kein Fenster mehr" ein
        // verlaessliches Signal fuers Zugemachtworden, und es gibt keinen
        // Grund, noch 24 Sekunden zu warten (Klaus, 2026-08-23: "dauert
        // lange bis Icon weg wenn man auf X geht"). Warum ueberhaupt noch
        // eine Frist und nicht sofort: 2 Pruefungen in Folge ohne Fenster
        // (also rund 6 Sekunden) sind ein Sicherheitsabstand gegen einen
        // kurzen Aussetzer, z.B. wenn ein Programm sein Fenster neu aufbaut.
        //
        // Warum das ueberhaupt noetig ist: bei Flatpak-Programmen taugt die
        // Prozess-Suche zum Erkennen des Endes gar nicht - gesucht wird nach
        // dem Namen aus der Exec-Zeile ("flatpak"), und der trifft dauerhaft
        // den flatpak-session-helper, einen Hintergrunddienst, der nach dem
        // ersten Start einfach weiterlaeuft. Nach dem Schliessen "laeuft"
        // damit fuer immer scheinbar noch etwas; allein die Fensterzahl sagt
        // die Wahrheit.
        keinFensterTrotzLaufendUebrig = 2;
        // Wie viele davon weggeklappt sind, entscheidet ueber das Icon im
        // Icon-Fenster (Klaus' Regel (b), 23.09.2026). Eigener Vergleich,
        // damit auch eine reine Zustandsaenderung (Fenster minimiert, Anzahl
        // gleich geblieben) das Portal erreicht.
        if (eintrag.minimiert !== fensterMinimiert) {
          eintrag.minimiert = fensterMinimiert;
          sendeLaufendeProgrammeAnAlleFenster();
        }
        anzahlUebernehmen(fensterAnzahl, true);
        return;
      }
      // fensterAnzahl === 0 heisst: Erweiterung aktiv UND hat sauber
      // geantwortet (kein Fehler/inaktiv, sonst waere es null) - also ein
      // ECHTES "kein Fenster", nicht bloss "konnte nicht nachschauen".
      // Erst zaehlen, wenn der Erststart-Fokus-Versuch schon gelaufen
      // ist (fokusVersucht) - vorher haette ein neu gestartetes Programm
      // noch gar keine faire Chance auf ein Fenster gehabt.
      if (fensterAnzahl === 0 && fokusVersucht) {
        keinFensterTrotzLaufendUebrig--;
        linuxAppLogZeile(`${suchbegriff}: laut pgrep "laeuft", Erweiterung sieht aber 0 Fenster (${keinFensterTrotzLaufendUebrig} Pruefungen bis Abbruch)`);
        if (keinFensterTrotzLaufendUebrig <= 0) {
          linuxAppLogZeile(`${suchbegriff}: vermutlich falscher pgrep-Treffer (nie ein echtes Fenster) - Icon wird entfernt`);
          clearInterval(timer);
          laufendePrograme.delete(info.exec);
          sendeLaufendeProgrammeAnAlleFenster();
          return;
        }
      }
      // Punkte: kann die Erweiterung nicht antworten, nur eine EXAKTE
      // Prozesszahl (genau=true) nehmen - ein unsicherer -f-Treffer wird auf
      // 1 begrenzt, statt vier Punkte fuer eine App zu zeigen, die gar nicht
      // mehrfach offen ist.
        anzahlUebernehmen(genau && anzahl > 0 ? anzahl : 1, genau && anzahl > 0);
      };
      // Fensterzahl besorgen, dann oben weiter (ohne Desktop-Datei-Pfad gibt
      // es keine - dann entscheidet allein pgrep, wie bisher).
      if (info.pfad) _fensterAnzahlUeberErweiterung(info.pfad, weiterPruefen);
      else weiterPruefen(null, 0);
    });
  }, LAUFEND_PRUEF_ABSTAND_MS);
  // "bestaetigt"/"gestartetUm" von einem eventuell schon vorhandenen
  // Eintrag UEBERNEHMEN statt zurueckzusetzen - sonst wuerde jeder weitere
  // legitime Klick (bewusst ein zusaetzliches Fenster oeffnen, siehe oben)
  // die Mehrfachklick-Sperre erneut fuer 25s scharfschalten, obwohl das
  // Programm laengst bestaetigt laeuft.
  const vorherigerEintrag = laufendePrograme.get(info.exec);
  laufendePrograme.set(info.exec, {
    name: info.name || info.exec, icon: info.icon || null, exec: info.exec, pfad: info.pfad || null,
    anzahl: 1,
    bestaetigt: vorherigerEintrag ? vorherigerEintrag.bestaetigt : false,
    gestartetUm: vorherigerEintrag ? vorherigerEintrag.gestartetUm : Date.now(),
    timer,
  });
  sendeLaufendeProgrammeAnAlleFenster();
});
ipcMain.handle('laufende-programme-liste', () =>
  [...laufendePrograme.values()].map(({ name, icon, exec, pfad, anzahl, minimiert }) => ({ name, icon, exec, pfad, anzahl, minimiert: minimiert || 0 })));

// Rechtsklick auf ein Taskleisten-Icon -> "Schliessen": normal beenden
// (SIGTERM, nicht -9), damit das Programm z.B. noch "Speichern?" fragen kann.
// pkill statt eines gemerkten PIDs, aus demselben Grund wie bei _laeuftNoch:
// der urspruenglich gestartete Prozess ist bei Einzelinstanz-Programmen wie
// Firefox oft laengst weg, der eigentliche (laenger laufende) Prozess wurde
// nie von uns gestartet.
//
// pkill allein reicht bei snap-Programmen (z.B. Firefox) NICHT: die laufen in
// einer eigenen systemd-Scope mit AppArmor-Schutz, der Signale von
// "fremden" Prozessen blockt - pkill scheitert dort mit "Keine Berechtigung",
// obwohl derselbe Nutzer beide Prozesse besitzt. Deshalb zuerst versuchen,
// die passende "snap.<name>...scope" ueber /proc/<pid>/cgroup zu finden und
// per systemctl (die darf das, da sie selbst zur Scope gehoert) zu stoppen -
// nur wenn das nicht klappt (kein Snap, keine Scope gefunden), auf normales
// pkill zurueckfallen.
function _snapScopeVonPid(pid, callback) {
  fs.readFile(`/proc/${pid}/cgroup`, 'utf-8', (fehler, inhalt) => {
    if (fehler) { callback(null); return; }
    const treffer = inhalt.match(/(snap\.[^\/\s]+\.scope)/);
    callback(treffer ? treffer[1] : null);
  });
}
// Startbefehle, deren erstes Wort NICHT die App benennt, sondern nur der
// Starter ist. Klaus-Fund 2026-09-06: "schliesse IP-Waechter" suchte nach
// "python3", weil die App als "python3 .../ip_waechter.py" eingetragen ist -
// und darauf passt Milcrids EIGENES Backend (main.py laeuft ebenfalls als
// python3) genauso wie die gemeinte App. Der Befehl haette also Milcrid
// selbst abgeschossen. Dasselbe Muster bei flatpak (VLC), snap, sh/bash und
// env. In diesen Faellen wird das erste Wort genommen, das wirklich das Ziel
// benennt: die Skriptdatei bzw. die Anwendungskennung.
const APP_STARTER = new Set(['python', 'python3', 'flatpak', 'snap', 'sh',
                             'bash', 'env', 'node', 'perl', 'ruby', 'java']);

function _appSuchbegriff(exec) {
  const teile = (exec || '').split(' ').filter(Boolean);
  if (!teile.length) return null;
  let begriff = path.basename(teile[0]);
  if (!APP_STARTER.has(begriff)) return { begriff, exakt: true };
  // Erstes Wort ueberspringen und das erste nehmen, das nicht wie ein
  // Schalter (-x, --foo) oder ein Platzhalter (@@, %U) aussieht.
  for (const roh of teile.slice(1)) {
    if (roh.startsWith('-') || roh.startsWith('@') || roh.startsWith('%')) continue;
    if (roh === 'run') continue;                 // "flatpak run <id>"
    const kandidat = path.basename(roh);
    if (!kandidat || APP_STARTER.has(kandidat)) continue;
    // Hier bewusst KEINE exakte Namenssuche: gesucht wird nach dem Skript
    // bzw. der Kennung in der vollen Befehlszeile, denn der Prozessname
    // ist ja der Starter.
    return { begriff: kandidat, exakt: false };
  }
  return null;  // nichts Eindeutiges gefunden - dann lieber gar nichts tun
}

// ---- Fenster echter Linux-Programme steuern (Klaus-Fund 2026-09-06) -------
// Minimieren und Maximieren liefen bisher NUR ueber mwFensterNachTitelAusfuehren
// im Portal, und das kennt ausschliesslich Milcrids EIGENE Fenster. "Computer,
// minimiere Firefox" wurde deshalb sauber erkannt, ausgefuehrt und meldete
// Vollzug - passiert ist nichts. Fuers Schliessen gab es laengst einen zweiten
// Weg (linux-app-schliessen), fuers Minimieren nicht.
//
// Gesucht wird ueber wmctrl anhand von Fenstertitel UND WM_CLASS, beides
// gross-/kleinschreibungsunabhaengig - dieselbe doppelte Pruefung wie bei
// _fensterAnzahlUeberErweiterung, aus demselben Grund (X11 schreibt die Klasse
// oft anders als die Desktop-Datei).
//
// Der Rueckgabewert sagt, wie viele Fenster wirklich betroffen waren. Damit
// kann der Aufrufer ehrlich antworten statt Vollzug zu behaupten - genau der
// Punkt aus dem Ideenpapier "KI kontrollieren".
function _fensterSuchen(name, callback) {
  const gesucht = (name || '').trim().toLowerCase();
  if (!gesucht) { callback([]); return; }
  execFile('wmctrl', ['-lx'], (fehler, stdout) => {
    if (fehler) { callback([]); return; }
    const treffer = [];
    for (const zeile of (stdout || '').split('\n')) {
      if (!zeile.trim()) continue;
      const spalten = zeile.trim().split(/\s+/);
      const id = spalten[0];
      const klasse = (spalten[2] || '').toLowerCase();
      // Alles ab der vierten Spalte ist der Fenstertitel (kann Leerzeichen
      // enthalten), die dritte ist der Rechnername.
      const titel = spalten.slice(4).join(' ').toLowerCase();
      // Das Kiosk-Fenster selbst ist tabu. Ohne das wuerde ein "minimiere
      // Milcrid", das unter Milcrids eigenen Fenstern nichts findet, das
      // Portal wegklappen und den Bildschirm leeren - derselbe Fehlertyp wie
      // beim Schliessen, wo "python3" das eigene Backend traf.
      if (klasse.includes('milcrid-app')) continue;
      if (klasse.includes(gesucht) || titel.includes(gesucht)) treffer.push(id);
    }
    callback(treffer);
  });
}

ipcMain.handle('fenster-aktion-extern', (event, name, aktion) => {
  return new Promise(aufloesen => {
    _fensterSuchen(name, ids => {
      if (!ids.length) { aufloesen(0); return; }
      let offen = ids.length;
      const fertig = () => { if (--offen <= 0) aufloesen(ids.length); };
      ids.forEach(id => {
        if (aktion === 'minimieren') {
          // xdotool statt wmctrl: "-b add,hidden" wird von vielen
          // Fenstermanagern ignoriert, windowminimize wirkt zuverlaessig.
          execFile('xdotool', ['windowminimize', id], () => fertig());
        } else if (aktion === 'maximieren') {
          // Erst aktivieren, dann maximieren: ein MINIMIERTES Fenster nimmt
          // "add,maximized" gar nicht an - der Befehl verpufft, sichtbar
          // passiert nichts (Klaus-Fund 2026-09-07: "ist ff ein Icon und ich
          // sage maximiere ff, passiert nichts; sage ich oeffne ff, kommt es
          // gross"). "wmctrl -a" holt es zurueck, genau wie der Oeffnen-Weg
          // es tut. Dasselbe Muster wie bei Milcrids eigenen Fenstern, wo
          // das Maximieren ebenfalls erst aus dem minimierten Zustand
          // zurueckholen muss.
          execFile('wmctrl', ['-i', '-a', id], () => {
            execFile('wmctrl', ['-i', '-r', id, '-b', 'add,maximized_vert,maximized_horz'], () => fertig());
          });
        } else if (aktion === 'normalgroesse') {
          execFile('wmctrl', ['-i', '-r', id, '-b', 'remove,maximized_vert,maximized_horz'], () => fertig());
        } else if (aktion === 'schliessen') {
          execFile('wmctrl', ['-i', '-c', id], () => fertig());
        } else fertig();
      });
    });
  });
});

// Flatpak-Apps laufen NICHT unter ihrem Startbefehl. VLC wird gestartet als
// "flatpak run ... org.videolan.VLC ...", der laufende Prozess heisst dann
// aber "bwrap --args 115 -- /app/bin/vlc" - in dessen Befehlszeile kommt die
// Kennung "org.videolan.VLC" nirgends vor. Ein pgrep darauf findet also
// nichts, und das Schliessen lief ins Leere, waehrend das Fenster offen
// dastand (Klaus-Test 2026-09-09: "den vlc player kann man gar nicht mehr zu
// machen"). Flatpak hat dafuer einen eigenen Befehl, der die Kennung kennt.
function _flatpakKennung(exec) {
  const teile = (exec || '').split(' ').filter(Boolean);
  if (!teile.some(t => path.basename(t) === 'flatpak')) return null;
  // Die Kennung ist der erste Teil in Punktschreibweise, der kein Schalter
  // und kein Pfad ist - z.B. org.videolan.VLC.
  for (const roh of teile) {
    if (roh.startsWith('-') || roh.startsWith('@') || roh.startsWith('%')) continue;
    if (roh.includes('/')) continue;
    if (/^[A-Za-z][\w-]*(\.[A-Za-z][\w-]*){2,}$/.test(roh)) return roh;
  }
  return null;
}

// Wie lange ein Programm nach dem sanften Schliessen Zeit bekommt, bevor
// nachgesehen wird (siehe linux-app-schliessen). Firefox braucht mit vielen
// Tabs ein paar Sekunden, um seine Sitzung zu speichern.
const SANFT_SCHLIESSEN_MS = 10000;

// Die X-Fenster, die zu diesen Prozessen gehoeren (_NET_WM_PID, "wmctrl -lp"),
// als [{id, pid}]. Das Kiosk-Fenster selbst ist tabu - gleiche Regel wie in
// _fensterSuchen.
function _fensterVonPids(pids, callback) {
  const gesucht = new Set(pids.map(String));
  execFile('wmctrl', ['-lpx'], (fehler, stdout) => {
    if (fehler) { callback([]); return; }
    const treffer = [];
    for (const zeile of (stdout || '').split('\n')) {
      const spalten = zeile.trim().split(/\s+/);
      if (spalten.length < 4) continue;
      if ((spalten[3] || '').toLowerCase().includes('milcrid-app')) continue;
      if (gesucht.has(spalten[2])) treffer.push({ id: spalten[0], pid: spalten[2] });
    }
    callback(treffer);
  });
}

// Vor Neustart/Ausschalten (Klaus-Wunsch 2026-09-22): ALLE Programmfenster
// sanft schliessen, wie ein Klick aufs X - LibreOffice & Co. fragen dann
// selbst "Speichern?". Vorher wurde einfach ausgeschaltet und Ungespeichertes
// war weg. Beendet NICHTS hart: was offen bleibt, meldet es dem Portal, und
// Klaus entscheidet (antworten, nochmal pruefen oder trotzdem).
// Taucht ein NEUES Fenster auf (meist die Speichern-Frage), wird sofort
// gemeldet statt die vollen SANFT_SCHLIESSEN_MS zu warten.
function _programmFenster(callback) {
  execFile('wmctrl', ['-lpx'], (fehler, stdout) => {
    if (fehler) { callback(null); return; }
    const fenster = [];
    for (const zeile of (stdout || '').split('\n')) {
      const t = zeile.trim().split(/\s+/);
      if (t.length < 4) continue;
      if ((t[3] || '').toLowerCase().includes('milcrid-app')) continue;  // das Kiosk-Fenster selbst
      if (t[1] === '-1') continue;  // Leisten/Schreibtisch, keine Programme
      fenster.push({ id: t[0], klasse: t[3], titel: t.slice(5).join(' ') });
    }
    callback(fenster);
  });
}
// Nur nachsehen, NICHT schliessen - fuers Weitermachen, sobald Klaus die
// Speichern-Frage beantwortet hat (22.09.). Ein erneutes "schliessen" wuerde
// die offene Frage selbst wegklicken. null = Liste nicht lesbar (dann warten).
ipcMain.handle('programm-fenster-liste', () => new Promise(resolve =>
  _programmFenster(f => resolve(f ? f.map(x => ({ titel: x.titel, klasse: x.klasse })) : null))));
ipcMain.handle('fenster-sanft-schliessen-alle', () => new Promise(resolve => {
  _programmFenster(anfang => {
    if (!anfang) { resolve({ erfolg: false, fehler: 'Die Fensterliste war nicht lesbar.', offen: [] }); return; }
    if (!anfang.length) { resolve({ erfolg: true, geschlossen: 0, offen: [] }); return; }
    linuxAppLogZeile(`Vor Neustart/Ausschalten: schliesse sanft ${anfang.length} Fenster: ${anfang.map(f => f.titel).join(' | ')}`);
    anfang.forEach(f => execFile('wmctrl', ['-i', '-c', f.id], () => {}));
    const alteIds = new Set(anfang.map(f => f.id));
    const beginn = Date.now();
    const pruefen = () => _programmFenster(jetzt => {
      jetzt = jetzt || [];
      const vergangen = Date.now() - beginn;
      const neue = jetzt.filter(f => !alteIds.has(f.id));
      if (!jetzt.length || vergangen >= SANFT_SCHLIESSEN_MS || (neue.length && vergangen >= 1500)) {
        if (jetzt.length) linuxAppLogZeile(`Vor Neustart/Ausschalten: bleibt offen: ${jetzt.map(f => f.titel).join(' | ')}`);
        resolve({ erfolg: true, geschlossen: anfang.filter(f => !jetzt.some(j => j.id === f.id)).length,
                  offen: jetzt.map(f => ({ titel: f.titel, klasse: f.klasse })) });
        return;
      }
      setTimeout(pruefen, 500);
    });
    setTimeout(pruefen, 500);
  });
}));

ipcMain.on('linux-app-schliessen', (event, exec) => {
  const flatpak = _flatpakKennung(exec);
  if (flatpak) {
    execFile('flatpak', ['kill', flatpak], (fehler) => {
      if (fehler) console.log('[Milcrid-App] flatpak kill fehlgeschlagen:', flatpak, fehler.message);
    });
    return;
  }
  const ziel = _appSuchbegriff(exec);
  if (!ziel) return;
  // Sicherheitsnetz, unabhaengig vom Suchbegriff: der eigene Prozess und
  // Milcrids Backend werden NIE beendet, auch wenn ein Suchmuster auf sie
  // passt. Ohne das kann ein einziger falsch eingetragener Startbefehl das
  // ganze System abschiessen.
  const tabu = new Set([String(process.pid), String(process.ppid)]);
  const hartBeenden = (pids) => {
    pids.filter(pid => !tabu.has(pid)).forEach(pid => {
      execFile('ps', ['-o', 'args=', '-p', pid], (f2, args) => {
        if ((args || '').includes('main.py')) return;  // Milcrids Backend
        _snapScopeVonPid(pid, scope => {
          if (scope) execFile('systemctl', ['--user', 'stop', scope], () => {});
          else execFile('kill', [pid], () => {});
        });
      });
    });
  };
  // Erst SANFT: die Fenster des Programms normal schliessen, wie ein Klick
  // aufs X (Opus 2026-09-19, Wiki Symptom 19). Das harte Beenden oben schoss
  // Firefox samt allen Teilprozessen gleichzeitig ab - fuer Firefox ein
  // "Absturz beim Start", nach ein paar Mal bot es an, sich zurueckzusetzen
  // (Old Firefox Data auf dem Schreibtisch, danach Englisch + Neustart).
  // LibreOffice machte eine Notsicherung statt "Speichern?" zu fragen und
  // zeigte beim naechsten Start die Dokumentwiederherstellung.
  // Fragt das Programm nach dem Schliessen noch etwas (Speichern ja/nein),
  // bleibt es OFFEN - das entscheidet Klaus, nicht Milcrid. Hart beendet wird
  // nur noch, was ohne jedes Fenster haengen bleibt oder gar keins hatte.
  //
  // Nach dem Schliessen werden NUR die Prozesse weiter beachtet, denen ein
  // Fenster gehoerte. pgrep -f trifft jeden Prozess, in dessen Befehlszeile der
  // Name vorkommt - beim ersten Test (19.09.) eine Shell mit dem Pfad
  // ~/.config/libreoffice darin. Die hatte nie ein Fenster, "hing" also nach
  // der Regel unten und wurde hart beendet. Wer kein Fenster hatte, ist nicht
  // das Programm, das Klaus zumachen wollte.
  const beenden = (pids) => {
    pids = pids.filter(pid => !tabu.has(pid));
    if (!pids.length) return;
    _fensterVonPids(pids, fenster => {
      if (!fenster.length) { hartBeenden(pids); return; }
      const mitFenster = [...new Set(fenster.map(f => f.pid))];
      linuxAppLogZeile(`Sanft schliessen: exec="${exec}" fenster=${fenster.length} prozesse=${mitFenster.join(',')}`);
      fenster.forEach(f => execFile('wmctrl', ['-i', '-c', f.id], () => {}));
      setTimeout(() => {
        const nochDa = mitFenster.filter(pid => fs.existsSync(`/proc/${pid}`));
        if (!nochDa.length) {
          linuxAppLogZeile(`Sanft geschlossen: exec="${exec}"`);
          return;
        }
        _fensterVonPids(nochDa, offen => {
          if (offen.length) {
            linuxAppLogZeile(`Bleibt offen (fragt noch nach, z.B. Speichern): exec="${exec}" fenster=${offen.length}`);
            return;
          }
          linuxAppLogZeile(`Ohne Fenster haengen geblieben, beende hart: exec="${exec}"`);
          hartBeenden(nochDa);
        });
      }, SANFT_SCHLIESSEN_MS);
    });
  };
  if (ziel.exakt) {
    execFile('pgrep', ['-x', ziel.begriff], (fehler, stdout) => {
      const pids = (stdout || '').split('\n').map(z => z.trim()).filter(Boolean);
      if (!pids.length) {
        execFile('pgrep', ['-f', ziel.begriff], (f2, out2) => {
          beenden((out2 || '').split('\n').map(z => z.trim()).filter(Boolean));
        });
        return;
      }
      beenden(pids);
    });
  } else {
    execFile('pgrep', ['-f', ziel.begriff], (fehler, stdout) => {
      beenden((stdout || '').split('\n').map(z => z.trim()).filter(Boolean));
    });
  }
});

// Echter nativer "Speichern unter"-Dialog (Klaus-Wunsch 2026-08-15, Portal >
// Gedaechtnis > Kurzzeitgedaechtnis > Speichern) - bisher gab es das nirgends
// im Portal, jede Speichern-Aktion schrieb bisher direkt an einen festen Ort
// zurueck. Reiner Datei-Export: schreibt den mitgeschickten Text an die vom
// Nutzer gewaehlte Stelle, laesst die eigentliche Quelldatei unangetastet.
ipcMain.handle('datei-speichern-dialog', async (event, daten) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  const { vorschlagName, inhalt } = daten || {};
  let ergebnis;
  try {
    // Ein blosser Dateiname landete im Arbeitsordner des Programms - also in
    // Milcrid-App zwischen main.js und den Sicherungen (gesehen 24.09.2026
    // beim Milcrid Editor). Ohne Ordner darum in "Dokumente" anfangen.
    const vorschlag = vorschlagName || 'export.txt';
    const startPfad = path.isAbsolute(vorschlag) ? vorschlag : path.join(app.getPath('documents'), vorschlag);
    ergebnis = await dialog.showSaveDialog(win, { defaultPath: startPfad });
  } catch (e) {
    return { erfolg: false, fehler: e.message };
  }
  if (ergebnis.canceled || !ergebnis.filePath) return { erfolg: false, abgebrochen: true };
  try {
    fs.writeFileSync(ergebnis.filePath, inhalt || '', 'utf-8');
    return { erfolg: true, pfad: ergebnis.filePath };
  } catch (e) {
    return { erfolg: false, fehler: e.message };
  }
});

ipcMain.handle('systemschalter-lesen', () => systemschalterAlleLesen());
ipcMain.handle('systemschalter-umschalten', (event, id, neuerWert) => {
  systemschalterSchreiben(id, neuerWert);
});

// ---- Lautstaerke (Klaus-Wunsch 2026-08-21) -------------------------------
// Ueber PipeWire/wpctl statt eines GNOME-Schalters - laeuft auf diesem
// System unabhaengig von jeder Desktop-Umgebung (geprueft: PipeWire aktiv,
// PulseAudio nicht - "wpctl status" zeigt die echten Audiogeraete).
function lautstaerkeLesen() {
  try {
    const roh = execSync('wpctl get-volume @DEFAULT_AUDIO_SINK@', { encoding: 'utf-8', timeout: 3000 }).trim();
    const treffer = /Volume:\s*([\d.]+)(\s*\[MUTED\])?/.exec(roh);
    if (!treffer) return null;
    return { prozent: Math.round(parseFloat(treffer[1]) * 100), stumm: !!treffer[2] };
  } catch (e) { return null; }
}
function lautstaerkeSetzen(prozent) {
  const sicher = Math.max(0, Math.min(100, Math.round(prozent)));
  execSync(`wpctl set-volume @DEFAULT_AUDIO_SINK@ ${sicher}%`, { timeout: 3000 });
}
function lautstaerkeStummSchalten(stumm) {
  execSync(`wpctl set-mute @DEFAULT_AUDIO_SINK@ ${stumm ? '1' : '0'}`, { timeout: 3000 });
}
ipcMain.handle('lautstaerke-lesen', () => lautstaerkeLesen());
ipcMain.handle('lautstaerke-setzen', (event, prozent) => { lautstaerkeSetzen(prozent); });
ipcMain.handle('lautstaerke-stummschalten', (event, stumm) => { lautstaerkeStummSchalten(stumm); });

// ---- Mikrofon / Eingabegeraet (Klaus-Wunsch 2026-09-06) ------------------
// Gegenstueck zur Lautstaerke, nur fuer die EINGABE: @DEFAULT_AUDIO_SOURCE@
// statt @DEFAULT_AUDIO_SINK@. Sonst identischer Weg ueber PipeWire/wpctl.
// Anders als bei der Ausgabe sind hier bewusst mehr als 100% erlaubt (bis
// 150%): wpctl kann die Eingangsverstaerkung ueber den Normalwert anheben,
// und genau das ist der Sinn eines Empfindlichkeitsreglers - ein zu leises
// Mikrofon laesst sich nicht durch Herunterregeln retten.
const MIKROFON_MAX_PROZENT = 150;
function mikrofonLesen() {
  try {
    const roh = execSync('wpctl get-volume @DEFAULT_AUDIO_SOURCE@', { encoding: 'utf-8', timeout: 3000 }).trim();
    const treffer = /Volume:\s*([\d.]+)(\s*\[MUTED\])?/.exec(roh);
    if (!treffer) return null;
    let name = null;
    try {
      // Die Standard-Quelle ist in "wpctl status" mit einem * markiert.
      const status = execSync('wpctl status', { encoding: 'utf-8', timeout: 3000 });
      const m = /\*\s*\d+\.\s+(.+?)\s+\[vol:/.exec(status.slice(status.indexOf('Sources:')));
      if (m) name = m[1].trim();
    } catch (e) { /* Name ist nur schmueckend - ohne ihn geht der Regler trotzdem */ }
    return { prozent: Math.round(parseFloat(treffer[1]) * 100), stumm: !!treffer[2], name };
  } catch (e) { return null; }
}
function mikrofonSetzen(prozent) {
  const sicher = Math.max(0, Math.min(MIKROFON_MAX_PROZENT, Math.round(prozent)));
  execSync(`wpctl set-volume @DEFAULT_AUDIO_SOURCE@ ${sicher}%`, { timeout: 3000 });
}
function mikrofonStummSchalten(stumm) {
  execSync(`wpctl set-mute @DEFAULT_AUDIO_SOURCE@ ${stumm ? '1' : '0'}`, { timeout: 3000 });
}
ipcMain.handle('mikrofon-lesen', () => mikrofonLesen());
ipcMain.handle('mikrofon-setzen', (event, prozent) => { mikrofonSetzen(prozent); });
ipcMain.handle('mikrofon-stummschalten', (event, stumm) => { mikrofonStummSchalten(stumm); });

// ---- Bildschirm: Aufloesung + Bildwiederholrate (Klaus-Wunsch 2026-08-21,
// Hz ergaenzt 2026-09-20) ------------------------------------------------
// Ueber xrandr - reines X11-Werkzeug, unabhaengig von jeder Desktop-
// Umgebung, im Gegensatz zu den GNOME-Aufloesungs-Einstellungen (die
// gnome-control-center brauchen wuerden, hier nicht installiert).
//
// Warum die Hz dazukamen (Klaus-Fund 2026-09-20): der Bildschirm lief auf
// 60 Hz, obwohl er 180 Hz kann - auf den dunklen Lila-Flaechen des Portals
// war ein Flimmern zu sehen. Gemessen: das Bild selbst aendert sich ueber
// 30 Aufnahmen um KEIN einziges Pixel, das Flimmern entsteht also erst auf
// dem Weg Grafikkarte -> Monitor. Genau dagegen hilft eine hoehere Rate.
const BILDSCHIRM_PFAD = path.join(os.homedir(), 'Milcrid', 'bildschirm.json');

function xrandrAusgangLesen() {
  const zeilen = execSync('xrandr --query', { encoding: 'utf-8', timeout: 3000 }).split('\n');
  for (const zeile of zeilen) {
    const treffer = /^(\S+) connected/.exec(zeile);
    if (treffer) return treffer[1]; // ersten verbundenen Ausgang nehmen
  }
  return null;
}

// Eine Modus-Zeile von xrandr sieht so aus:
//     2560x1440     60.00 +  180.00*  165.00   144.00   120.00
// Das "*" markiert die laufende Rate, das "+" die vom Bildschirm bevorzugte.
// Beide koennen am selben Wert kleben ("60.00*+"), darum werden sie einzeln
// abgeschnitten statt die Zeile nur nach "*" zu durchsuchen.
function hzAusZeile(rest) {
  const hzListe = [];
  let hzAktiv = null;
  for (const teil of rest.trim().split(/\s+/)) {
    const m = /^([\d.]+)([*+]*)$/.exec(teil);
    if (!m) continue;
    const wert = Math.round(parseFloat(m[1]));
    // 119.93 und 119.88 sind fuer uns beide "120 Hz" - doppelte Eintraege
    // wuerden im Portal zwei gleich beschriftete Knoepfe ergeben.
    if (!hzListe.includes(wert)) hzListe.push(wert);
    if (m[2].includes('*')) hzAktiv = wert;
  }
  hzListe.sort((a, b) => b - a); // hoechste zuerst - die ist die ruhigste
  return { hzListe, hzAktiv };
}

function aufloesungenLesen() {
  try {
    const zeilen = execSync('xrandr --query', { encoding: 'utf-8', timeout: 3000 }).split('\n');
    const ergebnis = [];
    const gesehen = new Map();
    for (const zeile of zeilen) {
      const kopf = /^\s+(\d+)x(\d+)\s+(.*)$/.exec(zeile);
      if (!kopf) continue;
      const [, breite, hoehe, rest] = kopf;
      const label = `${breite}x${hoehe}`;
      const { hzListe, hzAktiv } = hzAusZeile(rest);
      if (gesehen.has(label)) {
        // Dieselbe Aufloesung kann mehrfach auftauchen (einmal vom Bildschirm
        // gemeldet, einmal selbst hinzugefuegt). Dann die Raten zusammenlegen,
        // statt die zweite Zeile wegzuwerfen - sonst fehlen Hz in der Liste.
        const vorhanden = gesehen.get(label);
        for (const hz of hzListe) if (!vorhanden.hzListe.includes(hz)) vorhanden.hzListe.push(hz);
        vorhanden.hzListe.sort((a, b) => b - a);
        if (hzAktiv !== null) { vorhanden.hzAktiv = hzAktiv; vorhanden.aktiv = true; }
        continue;
      }
      const eintrag = {
        breite: Number(breite), hoehe: Number(hoehe),
        hz: hzAktiv !== null ? hzAktiv : (hzListe[0] || null),
        hzListe, hzAktiv,
        aktiv: hzAktiv !== null,
      };
      gesehen.set(label, eintrag);
      ergebnis.push(eintrag);
    }
    return ergebnis;
  } catch (e) { return []; }
}

// Damit die Wahl einen Neustart ueberlebt: ~/.xinitrc liest diese Datei beim
// Hochfahren und stellt den Bildschirm wieder so ein. Ohne das waere die
// Einstellung nach jedem Kiosk-Start wieder weg (X faellt auf die vom
// Bildschirm bevorzugte Rate zurueck, und das sind hier 60 Hz).
function bildschirmMerken(ausgang, breite, hoehe, hz) {
  try {
    fs.writeFileSync(BILDSCHIRM_PFAD, JSON.stringify({
      ausgang, breite: Number(breite), hoehe: Number(hoehe), hz: hz ? Number(hz) : null,
      gespeichert: new Date().toISOString(),
    }, null, 2), 'utf-8');
  } catch (e) { /* Merken ist Beiwerk - die Umstellung selbst hat schon geklappt */ }
}

function aufloesungSetzen(breite, hoehe, hz) {
  const ausgang = xrandrAusgangLesen();
  if (!ausgang) throw new Error('Kein verbundener Bildschirmausgang gefunden.');
  const modus = `${Number(breite)}x${Number(hoehe)}`;
  let rate = hz ? Number(hz) : null;
  if (!rate) {
    // Ohne ausdrueckliche Rate die hoechste nehmen, die diese Aufloesung kann.
    // Vorher liess der Aufruf die Rate weg, und X nahm die vom Bildschirm
    // bevorzugte - bei Klaus' Monitor 60 Hz, obwohl 180 gehen.
    const treffer = aufloesungenLesen().find(e => e.breite === Number(breite) && e.hoehe === Number(hoehe));
    rate = treffer && treffer.hzListe.length ? treffer.hzListe[0] : null;
  }
  // Der Aufruf steht bewusst ausgeschrieben da und wird nicht vorher in einer
  // Variablen zusammengebaut: der Pruefstand sucht Systemwerte DIREKT im
  // execSync und wuerde die Stelle sonst gar nicht mehr sehen (beim ersten
  // Bauen am 2026-09-20 genau so passiert - die Zahl fiel still von 10 auf 9).
  const rateTeil = rate ? ` --rate ${Number(rate)}` : '';
  execSync(`xrandr --output ${ausgang} --mode ${modus}${rateTeil}`, { timeout: 5000 });
  bildschirmMerken(ausgang, breite, hoehe, rate);
}

ipcMain.handle('aufloesungen-lesen', () => aufloesungenLesen());
ipcMain.handle('aufloesung-setzen', (event, breite, hoehe, hz) => { aufloesungSetzen(breite, hoehe, hz); });

// Liste der auf diesem Linux tatsaechlich installierten Schriftarten (fuer
// die Schriftart-Auswahl im Portal, Einstellungen > Schrift) - "fc-list" ist
// das Standard-Fontconfig-Werkzeug, auf so gut wie jedem Linux vorhanden.
// "--format=%{family[0]}\n" liefert nur den ersten/primaeren Familiennamen
// pro Schriftdatei (nicht Stil/Gewicht) - trotzdem taucht jede Familie mehrmals
// auf (eine Zeile je installierter Schnittart wie Regular/Bold/Italic), daher
// hier dedupliziert und deutsch sortiert.
// Klaus-Wunsch (2026-08-08): die volle Liste (~230 Schriften auf diesem
// System) war zu unuebersichtlich und viele davon sind fuer die Auswahl
// nicht hilfreich (z.B. "D050000L", technische PostScript-Kernschriften
// ohne erkennbaren Namen) - daher auf die ersten 15 (nach dem Ausschluss
// von D050000L) begrenzt statt alles anzuzeigen.
const SCHRIFT_AUSSCHLIESSEN = ['D050000L'];
ipcMain.handle('schriftarten-liste', async () => {
  try {
    const { stdout } = await execFileAsync('fc-list', ['--format=%{family[0]}\\n']);
    const namen = [...new Set(stdout.split('\n').map(s => s.trim()).filter(Boolean))];
    namen.sort((a, b) => a.localeCompare(b, 'de'));
    return namen.filter(name => !SCHRIFT_AUSSCHLIESSEN.includes(name)).slice(0, 15);
  } catch (e) {
    return []; // z.B. kein fontconfig auf diesem System - Portal zeigt dann nur die Standard-Liste
  }
});

app.whenReady().then(() => {
  starteBackendFallsNoetig();
  milcridInstallServerStarten();
  // Kurze Pause fuers Hochfahren - die Portal-Seite verbindet sich sowieso
  // automatisch neu, falls der Server noch nicht ganz so weit ist.
  setTimeout(erstelleFenster, 500);

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) erstelleFenster();
  });
});

app.on('window-all-closed', async () => {
  await beendeBackendFallsWirGestartetHaben();
  app.quit();
});

// Goldener "Exit"-Punkt im Portal (Klaus-Wunsch 2026-08-14) - schliesst
// einfach das Fenster, den Rest (Backend sauber per SIGINT beenden -
// main.py speichert dabei selbst noch schnell den Chat, siehe dortiges
// KeyboardInterrupt - danach app.quit()) erledigt bereits window-all-closed
// oben, keine eigene Logik hier noetig.
ipcMain.on('app-schliessen', () => {
  BrowserWindow.getAllWindows().forEach(w => w.close());
});

// Goldene Punkte "Exit"/"Neustart" im Portal (Klaus-Wunsch 2026-08-19) -
// schalten/starten den ganzen PC, nicht nur das Portal (das Portal wird
// vorher schon separat per appSchliessen() sauber zu, siehe dortige
// Verdrahtung im Portal-Skript). Braucht auf dem PC selbst eine einmalige
// Sudo-Freigabe fuer genau diese beiden Befehle (siehe /etc/sudoers.d/ -
// Klaus richtet das per Hand ein, das aendert Claude nie selbst). Ohne die
// Freigabe fragt sudo hier nach einem Passwort, das execFile nie eingeben
// kann - der Befehl haengt dann bis zum Timeout, statt sofort zu wirken.
ipcMain.on('pc-ausschalten', () => {
  execFile('sudo', ['systemctl', 'poweroff']);
});
ipcMain.on('pc-neustarten', () => {
  execFile('sudo', ['systemctl', 'reboot']);
});
