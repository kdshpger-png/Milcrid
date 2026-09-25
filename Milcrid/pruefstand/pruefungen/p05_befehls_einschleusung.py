"""
Befehls-Einschleusung in main.js (Electron-Hauptprozess)

execSync/exec bauen eine SHELL-Befehlszeile zusammen. Steckt darin ein
${...}-Platzhalter mit Daten, die nicht aus dem eigenen Code stammen, kann
ein Semikolon oder ein Backtick darin einen zweiten Befehl anhaengen:

    execSync(`nmcli device wifi connect ${ssid}`)
    ssid = 'Cafe; rm -rf ~'      ->  zwei Befehle statt einem

Der Hauptprozess laeuft OHNE Sandkasten und mit den Rechten von Klaus - was
hier ausgefuehrt wird, darf alles, was Klaus darf.

Gefahrlos ist dagegen execFile/execFileSync/spawn MIT Argument-Array: dort
geht jedes Argument einzeln an das Programm, ganz ohne Shell dazwischen.
Genau diese Unterscheidung steht auch schon als Kommentar in main.js
("WICHTIG: execFileSync statt execSync - execSync fuehrt den Befehl ueber
die Shell aus").

Bewertet wird nach der HERKUNFT der eingesetzten Daten:
  - aus dem Portal / aus dem Netz / von fremden Geraeten  -> FEHLER
  - aus einer eigenen festen Liste im Code                -> ok
  - aus einer Systemabfrage (z.B. Geraetename von nmcli)  -> Hinweis
"""
import re

# Namen, die eindeutig von aussen kommen (Portal-Eingaben, Funknamen, ...)
VON_AUSSEN = {
    "ssid", "passwort", "password", "mac", "host", "port", "url", "pfad", "path",
    "name", "titel", "text", "wert", "eingabe", "suchbegriff", "adresse",
    "autoconfigUrl", "einstellungen", "relativerPfad", "exec", "id",
}
# Namen, die aus einer Systemabfrage stammen (weniger scharf, aber nicht "eigen")
AUS_SYSTEM = {"geraet", "ausgang", "device", "schema", "sink"}


def pruefe(ctx):
    quelle = ctx.main_js
    befunde = []
    zeilen = quelle.splitlines()

    # execSync(`...${x}...`)  /  exec(`...${x}...`)  - nur Template-Strings
    muster = re.compile(r"\b(execSync|exec)\(\s*`([^`]*)`")
    for m in muster.finditer(quelle):
        befehl = m.group(2)
        platzhalter = re.findall(r"\$\{([^}]*)\}", befehl)
        if not platzhalter:
            continue  # feste Zeichenkette, keine Einschleusung moeglich
        zeile_nr = quelle[: m.start()].count("\n") + 1
        zeile_txt = zeilen[zeile_nr - 1].strip() if zeile_nr <= len(zeilen) else ""

        for p in platzhalter:
            # ternaere Ausdruecke mit festen Zeichenketten sind harmlos:
            #   ${an ? 'connect' : 'disconnect'}
            if re.fullmatch(r"[^?]*\?\s*'[^']*'\s*:\s*'[^']*'", p.strip()):
                continue
            # Number(...) / String(Number(...)) sind entschaerft
            if p.strip().startswith("Number("):
                continue

            grundname = re.split(r"[.\[(]", p.strip())[0]
            if grundname in VON_AUSSEN:
                befunde.append(ctx.fehler(
                    f"main.js Zeile {zeile_nr}: execSync mit Fremd-Daten '${{{p}}}'",
                    f"Ein Semikolon in '{grundname}' haengt einen zweiten Shell-Befehl an. "
                    f"Loesung: execFileSync mit Argument-Array.\n      {zeile_txt[:110]}",
                ))
            elif grundname in AUS_SYSTEM:
                befunde.append(ctx.hinweis(
                    f"main.js Zeile {zeile_nr}: execSync mit Systemwert '${{{p}}}'",
                    f"Geringes Risiko (Wert kommt vom System, nicht vom Nutzer), aber "
                    f"execFileSync waere sauberer.\n      {zeile_txt[:110]}",
                ))
            else:
                befunde.append(ctx.hinweis(
                    f"main.js Zeile {zeile_nr}: execSync mit Platzhalter '${{{p}}}'",
                    f"Herkunft von '{grundname}' pruefen.\n      {zeile_txt[:110]}",
                ))

    # spawn(...) mit Shell-Option waere ebenfalls gefaehrlich
    for m in re.finditer(r"spawn\([^;]*shell\s*:\s*true", quelle):
        zeile_nr = quelle[: m.start()].count("\n") + 1
        befunde.append(ctx.fehler(
            f"main.js Zeile {zeile_nr}: spawn(..., {{shell: true}})",
            "Mit shell:true gilt dieselbe Gefahr wie bei execSync.",
        ))

    gesamt = len(muster.findall(quelle))
    ctx.zaehle("execSync-Aufrufe mit Template-String", gefunden=gesamt)
    return befunde
