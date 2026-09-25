"""
IPC-Abgleich: Portal  ->  preload.js  ->  main.js

Die Electron-Bruecke hat DREI Stationen, und jede kann einzeln kaputtgehen,
ohne dass irgendwo ein Fehler auffaellt:

    Portal ruft   window.milcrid.wlanNetzeListen()
    preload.js    wlanNetzeListen: () => ipcRenderer.invoke('wlan-netze-listen')
    main.js       ipcMain.handle('wlan-netze-listen', ...)

Faellt ein Glied aus, gibt es KEINEN Syntaxfehler und KEINE Meldung - die
Funktion tut einfach nichts (oder wirft erst beim Klick). Genau die Sorte
Fehler, die der ID-Pruefer nicht findet (es fehlt kein Element, es fehlt ein
Empfaenger) - vgl. Fund M-2 im Opus-Check vom 2026-08-27, wo ein geloeschter
WebSocket-Empfaenger dieselbe Bauart hatte.

Geprueft wird in beide Richtungen:
  1. Portal ruft etwas, das preload nicht anbietet          -> tote Funktion
  2. preload bietet etwas an, das main.js nicht behandelt   -> Aufruf laeuft ins Leere
  3. main.js behandelt etwas, das preload nicht anbietet    -> unerreichbar (Leiche)
  4. preload bietet etwas an, das das Portal nie ruft       -> Leiche (nur Hinweis)
  5. send/invoke-Verwechslung (ipcMain.on vs ipcMain.handle) -> haengt oder wirft
"""
import re
from pathlib import Path


def pruefe(ctx):
    portal = ctx.portal_js
    preload = ctx.preload_js
    mainjs = ctx.main_js
    befunde = []

    # ---------------------------------------------------------- preload einlesen
    # Zeilen der Form:   name: (args) => ipcRenderer.invoke('kanal', ...)
    #                    name: (args) => ipcRenderer.send('kanal', ...)
    #                    name: (cb)   => ipcRenderer.on('kanal', ...)
    preload_eintraege = {}          # portal-Name -> (art, kanal)
    for m in re.finditer(
        r"(\w+)\s*:\s*\([^)]*\)\s*=>\s*ipcRenderer\.(invoke|send|on)\(\s*['\"]([^'\"]+)['\"]",
        preload,
    ):
        preload_eintraege[m.group(1)] = (m.group(2), m.group(3))

    # ---------------------------------------------------------- main.js einlesen
    main_handle = set(re.findall(r"ipcMain\.handle\(\s*['\"]([^'\"]+)['\"]", mainjs))
    main_on = set(re.findall(r"ipcMain\.on\(\s*['\"]([^'\"]+)['\"]", mainjs))
    # An das Fenster gesendete Kanaele (fuer ipcRenderer.on im preload)
    main_sendet = set(re.findall(r"(?:\.webContents|fenster|win)\.send\(\s*['\"]([^'\"]+)['\"]", mainjs))
    main_sendet |= set(re.findall(r"webContents\.send\(\s*['\"]([^'\"]+)['\"]", mainjs))

    # ---------------------------------------------------------- Portal einlesen
    # window.milcrid.NAME(...)   sowie   milcrid.NAME  in Faehigkeitspruefungen
    portal_nutzt = set(re.findall(r"window\.milcrid\.(\w+)", portal))
    portal_nutzt |= set(re.findall(r"(?<![.\w])milcrid\.(\w+)", portal))
    # 'milcrid' selbst ist kein Funktionsname
    portal_nutzt.discard("milcrid")

    # WICHTIG: nicht nur das Portal zaehlt. Die Milcrid-Apps (Uhr, Rechner,
    # Kalender unter Milcrid-App/"Milcrid Apps"/) werden per innerHTML +
    # eigenem <script> in dieselbe Seite geladen und benutzen dieselbe
    # Bruecke. Ohne sie meldete diese Pruefung kalenderLesen/kalenderSpeichern
    # dauerhaft als "Leiche", obwohl der Kalender sie taeglich benutzt -
    # ein Fehlalarm, der bei jedem Lauf wiedergekommen waere.
    for datei in ctx.app_dateien():
        try:
            inhalt = datei.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        portal_nutzt |= set(re.findall(r"window\.milcrid\.(\w+)", inhalt))

    # ------------------------------------------------ 1. Portal -> preload fehlt
    for name in sorted(portal_nutzt):
        if name not in preload_eintraege:
            zeilen = ctx.portal_zeilen(f"milcrid.{name}")
            befunde.append(ctx.fehler(
                f"Portal ruft window.milcrid.{name}(), preload.js bietet das nicht an",
                f"Aufruf laeuft ins Leere (undefined is not a function). Zeile(n): {zeilen}",
            ))

    # -------------------------------------------- 2. preload -> main.js fehlt
    for name, (art, kanal) in sorted(preload_eintraege.items()):
        if art == "invoke":
            if kanal not in main_handle:
                if kanal in main_on:
                    befunde.append(ctx.fehler(
                        f"preload '{name}' nutzt invoke('{kanal}'), main.js hat aber nur ipcMain.on",
                        "invoke auf einen on-Kanal liefert nie ein Ergebnis - der Aufruf haengt "
                        "bzw. wirft 'No handler registered'.",
                    ))
                else:
                    befunde.append(ctx.fehler(
                        f"preload '{name}' ruft Kanal '{kanal}', main.js behandelt ihn nicht",
                        "Aufruf schlaegt zur Laufzeit fehl ('No handler registered for ...').",
                    ))
        elif art == "send":
            if kanal not in main_on:
                if kanal in main_handle:
                    befunde.append(ctx.fehler(
                        f"preload '{name}' nutzt send('{kanal}'), main.js hat aber ipcMain.handle",
                        "send auf einen handle-Kanal wird still verworfen - die Aktion passiert nie.",
                    ))
                else:
                    befunde.append(ctx.fehler(
                        f"preload '{name}' sendet Kanal '{kanal}', main.js hoert nicht darauf",
                        "Die Aktion passiert nie, ohne jede Meldung.",
                    ))
        elif art == "on":
            if kanal not in main_sendet:
                befunde.append(ctx.hinweis(
                    f"preload '{name}' hoert auf '{kanal}', main.js sendet das nirgends",
                    "Empfaenger wird nie ausgeloest (evtl. Leiche aus einem Rueckbau).",
                ))

    # ------------------------------------- 3. main.js-Kanaele ohne preload-Bruecke
    preload_kanaele = {k for (_, k) in preload_eintraege.values()}
    for kanal in sorted(main_handle | main_on):
        if kanal not in preload_kanaele:
            befunde.append(ctx.hinweis(
                f"main.js behandelt '{kanal}', preload.js bietet dafuer nichts an",
                "Vom Portal aus unerreichbar - entweder Leiche oder die Bruecke fehlt noch.",
            ))

    # Kurznamen wie "const M = window.milcrid || {}" (Editor, Bild, Video,
    # dateiOeffnenZentral im Portal, 24.09.2026): M.dateiPfadPruefen(...) ist
    # genauso ein Aufruf. Zaehlt NUR fuer "wird genutzt" und nur fuer Namen,
    # die preload wirklich anbietet - ein Kurzname wie "m" steht im Portal
    # auch fuer WebSocket-Nachrichten (m.typ), daraus darf kein Fehler werden.
    alias_nutzt = set()
    texte = [portal]
    for datei in ctx.app_dateien():
        try:
            texte.append(datei.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            pass
    for text in texte:
        for alias in set(re.findall(r"(?:const|let|var)\s+(\w+)\s*=\s*window\.milcrid\b", text)):
            alias_nutzt |= {n for n in re.findall(rf"(?<![.\w]){re.escape(alias)}\.(\w+)", text)
                            if n in preload_eintraege}

    # ------------------------------------------- 4. preload-Eintrag nie genutzt
    for name in sorted(preload_eintraege):
        if name not in portal_nutzt and name not in alias_nutzt:
            befunde.append(ctx.hinweis(
                f"preload bietet '{name}' an, das Portal ruft es nirgends",
                "Leiche oder noch nicht angeschlossen.",
            ))

    ctx.zaehle(
        "IPC-Kanaele",
        portal=len(portal_nutzt),
        preload=len(preload_eintraege),
        main_handle=len(main_handle),
        main_on=len(main_on),
    )
    return befunde
