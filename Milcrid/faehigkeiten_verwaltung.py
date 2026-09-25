# faehigkeiten_verwaltung.py
# Lokale KI > Faehigkeiten: An/Aus-Schalter, die WIRKLICH steuern, ob die KI
# ein bestimmtes Werkzeug ueberhaupt im Kontext angeboten bekommt - anders als
# die entfernten "Eigenen Tools" (siehe toolbox_verwaltung.py) ist der
# Schalter hier selbst der Wirkmechanismus, keine Anzeige. Ist eine Faehigkeit
# ausgeschaltet, taucht ihr Werkzeug in kontext_fuer_eingabe() unten NIE auf -
# die KI erfaehrt gar nichts von ihrer Existenz.
#
# Erste Faehigkeit (Klaus-Wunsch 2026-08-25): "Themen Manager öffnen" - die KI
# kann per Chat ein einzelnes oder alle vorhandenen Themen (vormals
# "Schreibtische") als Fenster im Portal öffnen lassen. Das eigentliche
# Werkzeug (open_theme) steht in bridge.py - hier nur Schalter-Zustand +
# Text/Stichwoerter, damit main.py entscheiden kann, ob es der KI gerade
# angeboten wird.

import json
import os

BASIS_ORDNER = os.path.dirname(os.path.abspath(__file__))
DATEN_PFAD = os.path.join(BASIS_ORDNER, "faehigkeiten.json")

# name -> {titel (Portal-Anzeige), beschreibung+aufruf (fuer die KI),
# stichwoerter (wann ueberhaupt dazuladen, wie bei toolbox_verwaltung)}
FAEHIGKEITEN = {
    "themen_oeffnen": {
        "titel": "Themen Manager öffnen",
        "beschreibung": (
            'open_theme: öffnet ein oder alle vorhandenen Themen (Themen '
            "Manager) als Fenster im Portal. Bei name steht der Titel des "
            'gewünschten Themas; name="alle" öffnet ALLE vorhandenen Themen. Gibt '
            "es kein Thema mit dem genannten Namen, meldet das Werkzeug die "
            "tatsächlich vorhandenen Namen zurück - dann nachfragen statt "
            "zu raten. Wichtig: 'Portal' und 'Milcrid' sind KEINE Themen, "
            "sondern die Oberfläche selbst bzw. du selbst - dafür gibt es "
            "kein Fenster zum Öffnen. Meldet dieses Werkzeug 'nicht "
            "gefunden', NIEMALS als Ausweg die Websuche oder ein anderes "
            "Programm probieren - stattdessen Klaus direkt sagen, dass es "
            "das nicht gibt. Sagt Klaus \"Fenster X\", meint er meistens "
            "einen Portal-Bereich (open_section), NICHT dieses Werkzeug hier. "
            # Gemessen 23./24.09.2026 (Stufentest, Stufe "leicht"): "öffne Thema
            # Klaus" ging 9 von 10 Mal an open_section statt hierher - das Thema
            # existiert, open_theme haette funktioniert. Grund war der Satz davor:
            # er stand ganz am ENDE dieser Beschreibung, und beim kleinen Modell
            # bleibt das Letzte am staerksten haengen. Es las also zuletzt "nimm
            # lieber open_section". Gemeint war der Satz nur fuer "Fenster X".
            # Nach der Lehre "Wortlaut statt Regel" steht der Fall jetzt woertlich
            # da, mit fertigem Aufruf - und als LETZTER Satz, damit die richtige
            # Anweisung die ist, die haengen bleibt.
            'ABER: Sagt Klaus ausdrücklich das Wort "Thema" - zum Beispiel '
            '"öffne Thema Klaus", "mach Thema Opus auf", "Thema Gemini bitte" -, '
            "dann ist IMMER dieses Werkzeug gemeint und niemals open_section. "
            'Dann rufe open_theme(name="Klaus") auf, also genau den Namen, den '
            "Klaus hinter dem Wort Thema gesagt hat."
        ),
        "aufruf": 'open_theme(name="<Titel des Themas>")',
        "stichwoerter": ["thema", "themen", "schreibtisch"],
        "beispiel": "öffne Thema Klaus",
    },
    "apps_oeffnen": {
        "titel": "Apps öffnen",
        "beschreibung": (
            'open_app: öffnet ein installiertes Linux-Programm ODER eine '
            "der Milcrid-eigenen kleinen Anwendungen (Uhr, Rechner, "
            "Kalender, Termine, Notizen) - BEIDE Arten ueber DASSELBE "
            "Werkzeug, es gibt kein "
            'eigenes open_calculator/open_clock/open_calendar. Beispiele: '
            'name="Firefox", name="Thunderbird Mail", name="Milcrid '
            'Rechner", name="Milcrid Uhr", name="Milcrid Kalender", '
            'name="Milcrid Termine", name="Milcrid Notizen". Termine '
            'und Kalender sind ZWEI verschiedene Apps. Sagt '
            'Klaus nur "Rechner"/"Uhr"/"Kalender"/"Termine"/"Terminplaner"/"Notizen" ohne "Milcrid" davor, ist '
            "trotzdem die jeweilige Milcrid-App gemeint - einfach so "
            "aufrufen, nicht extra nachfragen. Auch gängige Oberbegriffe "
            "wie \"Browser\" oder \"Mail\" funktionieren. "
            "Ein MINIMIERTES Fenster wieder zeigen (\"zeig die Uhr wieder\", "
            "\"hol den Rechner zurück\") geht ebenfalls mit open_app und "
            "demselben Namen. "
            "Passen mehrere Programme zum Namen, fragt das Werkzeug nach statt "
            "eins zu raten - dann beim Namen genauer werden. Wichtig: "
            "'Portal', 'Milcrid' allein und 'Meine Apps' sind KEINE Programme, "
            "sondern Teile der Oberfläche - \"Meine Apps\" ist der "
            "Portal-Bereich, IN dem die Programme stehen, und wird mit "
            "open_section geöffnet, nicht hiermit. Allgemein: steht der "
            "genannte Name in der Bereichsliste von open_section, ist immer "
            "open_section gemeint. Meldet dieses Werkzeug 'nicht "
            "gefunden', NIEMALS als Ausweg die Websuche, ein anderes "
            "Programm oder einen erfundenen Werkzeugnamen probieren - "
            "stattdessen Klaus direkt sagen, dass es das nicht gibt. Sagt "
            "Klaus \"Fenster X\", meint er meistens "
            "einen Portal-Bereich (open_section), NICHT dieses Werkzeug hier."
        ),
        "aufruf": 'open_app(name="<Name des Programms>")',
        # "zeig"/"hol" (Opus 2026-09-13): "zeig den Rechner wieder" bekam nur
        # show_result angeboten (Stichwort "zeig") und nie open_app.
        "stichwoerter": [
            "öffne", "starte", "app", "programm", "browser", "firefox",
            "mail", "libreoffice", "terminal", "vlc", "zeig", "hol ",
        ],
        "beispiel": "öffne den Browser",
    },
    # ---- Fremdes Fenster vorlesen (Klaus-Wunsch 2026-09-20) ----
    # Gemessen: das Modell liest einen Dialog fehlerfrei vor, kann aber nicht
    # einschaetzen, ob er im Weg ist - darum steht hier NUR "vorlesen und
    # fragen", und der Vorschlag kommt aus dialog_verwaltung.py.
    "fenster_vorlesen": {
        "titel": "Fremdes Fenster vorlesen",
        "beschreibung": (
            'fenster_vorlesen: liest vor, was in einem FREMDEN Fenster steht - also in einem '
            'Programm oder seinem Dialog ("Dokument speichern?", "Update", "alte Sitzung '
            'wiederherstellen"), NICHT in einem Portal-Fenster. name = der Titel aus der Lage-Zeile; '
            'ohne name wird das zuletzt geoeffnete genommen. Benutze es, wenn Klaus fragt, was in '
            'einem Fenster steht, und immer dann, wenn in der Lage ein fremdes Fenster steht und du '
            'deshalb nicht weiterkommst. Das Ergebnis enthaelt den Wortlaut - gib ihn Klaus weiter '
            'und frage ihn, was er tun will. Du klickst NIE selbst etwas an. '
            'dialog_abbrechen(name="<Titel>") drueckt Abbrechen - aber erst, nachdem Klaus '
            'ausdruecklich zugestimmt hat; vorher wird es abgelehnt.'
        ),
        "aufruf": 'fenster_vorlesen(name="<Titel des Fensters>")',
        "stichwoerter": ["vorlesen", "lies vor", "lies mir", "was steht", "dialog",
                         "fenster lesen", "meldung", "steht da", "im weg", "abfrage",
                         "hinweis", "was will"],
        "beispiel": "was steht in dem Fenster",
    },
    "dateien_oeffnen": {
        "titel": "Dateien öffnen",
        "beschreibung": (
            'open_file: öffnet eine Datei mit dem vom System zugeordneten '
            "Standardprogramm (wie ein Doppelklick im Datei Manager) - "
            "funktioniert mit JEDEM Dateityp, den das System kennt (PDF, "
            "TXT, PY, Bilder, ...), nicht nur bestimmten. name ist das Wort, "
            "das Klaus sagt - gib es einfach so weiter, AUCH OHNE ENDUNG: "
            '"öffne demo" -> open_file(name="demo") findet demo.txt selbst. '
            "Rate nie eine Endung dazu und rate nie einen Pfad. Gesucht wird "
            "im ganzen Milcrid-Ordner samt Unterordnern; ist ein Thema-Fenster "
            "offen, gewinnt eine Datei aus diesem Thema. Passen mehrere Dateien, "
            "fragt das Werkzeug nach - gib die Frage an Klaus weiter, statt eine "
            "auszuwählen. Wichtig: 'Portal' und 'Milcrid' sind KEINE Dateien, "
            "sondern die Oberfläche selbst bzw. du selbst. Meldet dieses "
            "Werkzeug 'existiert nicht', NIEMALS als Ausweg die Websuche "
            "oder ein anderes Programm probieren - stattdessen Klaus direkt "
            "sagen, dass es das nicht gibt. Sagt Klaus \"Fenster X\", meint "
            "er meistens einen Portal-Bereich (open_section), NICHT dieses "
            "Werkzeug hier."
        ),
        "aufruf": 'open_file(name="<Dateiname>")',
        "stichwoerter": ["öffne", "datei", "dokument", "pdf", "öffnen", "zeig mir", "mach auf", "lies"],
        "beispiel": "öffne die Datei main.py",
    },
    "bereiche_oeffnen": {
        "titel": "Portal-Bereiche öffnen",
        "beschreibung": (
            'open_section: öffnet einen Bereich/eine Kachel IM PORTAL SELBST '
            '(z.B. name="Einstellungen", name="Farben", name="Lokale KI") - eine '
            "Navigations-Kachel der Oberfläche, KEINE Datei, KEIN Programm, "
            "KEIN Thema. Uhr, Rechner und Kalender sind KEINE Bereiche, sondern "
            "Programme - dafür open_app(name=\"Milcrid Kalender\") usw. "
            "Starkes Erkennungszeichen: sagt Klaus \"Fenster X\" "
            '(z.B. "Fenster Lokale KI", "Fenster Farben"), ist damit fast '
            "immer DIESES Werkzeug hier gemeint, nicht open_app/open_file/"
            "open_theme. AUSNAHME 2 (2026-09-04): \"Suchfenster\", "
            "\"Ergebnisfenster\" und \"Suchergebnis\" sind KEINE Bereiche - "
            "gemeint ist das Fenster mit einem Suchergebnis, das gerade offen "
            "ist. Soll daraus ein LINK geöffnet werden, ist open_url "
            "zuständig; die vollständigen Adressen stehen in der Liste, die "
            "dir das Such-Werkzeug zurückgegeben hat. NIEMALS dafür \"Portal "
            "Durchsuchen\" öffnen - das ist die Suchfunktion des Portals und "
            "etwas völlig anderes. "
            "AUSNAHME (2026-09-03): Soll das Fenster GROSS, "
            "KLEIN oder angeordnet werden (\"mach das Fenster X groß\", "
            "\"mach X klein\"), geht es um ein SCHON OFFENES Fenster - dann "
            "sind maximize_window / minimize_window / arrange_windows "
            "zustaendig. Dieses Werkzeug hier OEFFNET nur. "
            "Klickt fuer Klaus dieselbe Kachel, die er sonst "
            "selbst anklicken wuerde - ein Unterbereich (z.B. Farben) "
            "oeffnet automatisch auch seinen Oberbereich (z.B. Einstellungen) mit. "
            "Gibt es keinen Bereich mit dem genannten Namen, meldet das "
            "Werkzeug die tatsaechlich vorhandenen Namen zurueck - dann "
            "nachfragen statt zu raten, NIE die Websuche oder ein anderes "
            "Werkzeug als Ausweg probieren. "
            # Gemessen 23./24.09.2026: "oeffne Thema Klaus" landete 9 von 10 Mal
            # HIER statt bei open_theme. Erster Versuch war, nur die Themen-
            # Beschreibung zu schaerfen - das half (open_theme 0 -> 4 von 10),
            # reichte aber nicht: der falsche Griff passiert hier, also muss die
            # Absage auch hier stehen. Und zwar am ENDE, das bleibt haengen.
            'LETZTE REGEL, WICHTIG: Sagt Klaus das Wort "Thema" - zum Beispiel '
            '"oeffne Thema Klaus", "mach Thema Opus auf" -, dann ist dieses '
            "Werkzeug NICHT zustaendig. Dann gehoert der Befehl zu "
            'open_theme(name="Klaus"). Ein Thema ist niemals ein Bereich.'
        ),
        "aufruf": 'open_section(name="<Name des Bereichs>")',
        "stichwoerter": [],  # wird unten aus PORTAL_BEREICHE befuellt, siehe dort
        "beispiel": "öffne meine Apps",
    },
    "apps_schliessen": {
        "titel": "Apps schließen",
        "beschreibung": (
            'close_app: schließt ein ECHTES Linux-Programm (z.B. Firefox, '
            'LibreOffice, Thunderbird Mail), das über "Meine Apps" läuft - '
            "das Gegenstück zu open_app, gleiche Namen/Oberbegriffe wie "
            'dort (z.B. name="Browser"). Für ein Fenster IM PORTAL SELBST '
            "(Thema, Datei-Manager, Bereich) ist stattdessen close_window "
            "zuständig, NICHT dieses Werkzeug."
        ),
        "aufruf": 'close_app(name="<Name des Programms>")',
        # Wortstaemme statt "schließe" (Opus 2026-09-10, KI-Pruefstand):
        # "schließ mal den Browser" traf keins der Stichwoerter - angeboten
        # wurde nur open_app (wegen "Browser"), und Milcrid OEFFNETE den
        # Browser, 4 von 4 Mal. Gleiche Lehre wie bei "minimier"/"klein".
        "stichwoerter": ["schließ", "schliess", "beende", "beenden"],
        "beispiel": "schließe den Browser",
    },
    "fenster_schliessen": {
        "titel": "Fenster schließen",
        "beschreibung": (
            'close_window: schließt ein offenes Fenster IM PORTAL SELBST '
            "(ein Thema, ein Datei-Manager-Fenster, ein Bereichs-Fenster) "
            "anhand seines sichtbaren Titels. "
            'name="alle" schließt alle offenen Portal-Fenster auf einmal; '
            "weggeklappte (minimierte) Fenster im Icon Fenster bleiben dabei. "
            # Klaus 23.09./25.09.2026 - Wortlaut mit fertigem Aufruf, siehe unten.
            'Sagt Klaus "schließe alle Fenster und Icon Fenster", dann rufe '
            'close_window(name="alle und Icon Fenster") auf - das schließt auch '
            "die weggeklappten. "
            "Für ein ECHTES Linux-Programm wie Firefox (per open_app "
            "geöffnet) ist stattdessen close_app zuständig, NICHT dieses "
            "Werkzeug. AUSNAHME: das CHATFENSTER (diese Unterhaltung hier) "
            "ist KEIN Portal-Fenster im Sinne dieses Werkzeugs - dafür ist "
            "set_chat_window zuständig. Ob ein Fenster mit dem genannten "
            "Namen wirklich offen ist, weiß erst das Portal selbst - dieses "
            "Werkzeug kann das vorher nicht prüfen. "
            # Klaus 2026-09-23: "schliesse Icon Fenster" griff zu show_result
            # statt close_window. Das Werkzeug WAR angeboten (Stichwort
            # "schliess" trifft) - das Modell hat sich nur falsch entschieden.
            # Nach der Lehre "Wortlaut statt Regel" steht der Fall jetzt
            # woertlich da, mitsamt fertigem Aufruf.
            'DAS ICON FENSTER: sagt Klaus "schließe das Icon Fenster" oder '
            '"mach die Icon Leiste zu", dann rufe close_window(name="Icon Fenster") '
            "auf - das ist das kleine Fenster mit den Bildchen der offenen "
            'Programme. Es wird von name="alle" ABSICHTLICH nicht mit '
            "geschlossen; nur wenn Klaus es ausdrücklich nennt."
        ),
        "aufruf": 'close_window(name="<Titel des Fensters>")',
        # Wortstaemme - Begruendung siehe apps_schliessen direkt darueber.
        "stichwoerter": ["schließ", "schliess", "zumachen", "beenden", "icon fenster", "icon leiste"],
        "beispiel": "schließe alle Fenster",
    },
    # Klaus-Wunsch 2026-09-05: das Chatfenster selbst (wo diese Unterhaltung
    # steht) ist WEDER ein Portal-Fenster (close_window) NOCH ein Bereich
    # (open_section) - es ist eine feste Leiste, immer da, nur ein- oder
    # ausgeblendet. Braucht deshalb ein eigenes, kleines Werkzeug statt sich
    # in eines der beiden anderen zu quetschen.
    "chat_fenster_stellen": {
        "titel": "Chatfenster ein-/ausblenden/maximieren",
        "beschreibung": (
            'set_chat_window: stellt das Chatfenster (diese Unterhaltung '
            'hier) ein. zustand="auf" oeffnet es in normaler Groesse, '
            'zustand="gross" MAXIMIERT es auf Vollbild (das ist gemeint, '
            'wenn Klaus "maximiere/vergroessere das Chatfenster" sagt - '
            "NICHT maximize_window, das ist NUR fuer Portal-Fenster/Themen/"
            'Bereiche zustaendig), zustand="zu" blendet es aus - der Chat '
            "selbst laeuft im Hintergrund normal weiter, nur sichtbar ist "
            "er nicht mehr. Kein Name noetig, es gibt nur dieses eine "
            "Chatfenster."
        ),
        "aufruf": 'set_chat_window(zustand="gross")',
        # Die verhoerten Fassungen MUESSEN hier stehen (Klaus-Fund 2026-09-10).
        # Whisper macht aus "Chatfenster" verlaesslich "Schattenfenster",
        # "Schattfenster" oder "Schatzfenster" - keins davon traf ein Stichwort,
        # also bekam das Modell set_chat_window gar nicht erst angeboten.
        # Es las dann in der close_window-Beschreibung "fuers Chatfenster ist
        # set_chat_window zustaendig", hatte dieses Werkzeug aber nicht - und
        # antwortete deshalb immer wieder "das Portal kennt keinen Bereich
        # namens Schattenfenster", statt es einfach zu schliessen.
        # Dieselbe Klangfamilie ist in bridge._CHATFENSTER_NAMEN schon seit
        # dem 07.09. hinterlegt - dort wirkt sie aber erst, wenn das Werkzeug
        # schon aufgerufen WURDE. Hier entscheidet sich, ob es das ueberhaupt
        # gibt.
        "stichwoerter": [
            "chatfenster", "chat-fenster", "unterhaltung",
            "schattenfenster", "schattfenster", "schatzfenster", "schatfenster",
            "tschatfenster", "chatleiste", "chatbereich",
        ],
        "beispiel": "schließe das Chatfenster",
    },
    "fenster_minimieren": {
        "titel": "Fenster minimieren",
        "beschreibung": (
            'minimize_window: macht ein offenes Portal-Fenster klein (wie '
            "ein Klick auf das Minimieren-Symbol) - der Inhalt bleibt "
            "erhalten, ein Klick auf das zugehörige Taskleisten-Icon holt "
            "es unverändert zurück. name ist der sichtbare Titel des "
            "Fensters. AUSNAHME: das CHATFENSTER (diese Unterhaltung hier) "
            "ist KEIN Portal-Fenster im Sinne dieses Werkzeugs - dafür ist "
            "set_chat_window(zustand=\"zu\") zuständig, NICHT dieses Werkzeug."
        ),
        "aufruf": 'minimize_window(name="<Titel des Fensters>")',
        # "klein machen" als ganze Wendung traf "mach die Uhr KLEIN" NICHT -
        # im Deutschen wandert der zweite Teil ans Satzende (Verbklammer).
        # Genau daran ist der Befehl bis 2026-09-03 gescheitert: nicht das
        # Werkzeug fehlte, es wurde dem Modell nur nie gezeigt. Deshalb
        # Wortstaemme statt Wendungen.
        "stichwoerter": ["minimier", "verkleiner", "klein"],
        "beispiel": "minimiere das Fenster Farben",
    },
    # ---- Neu 2026-09-03: aus Milcrids eigenen Fehlversuchen abgeleitet.
    # Im Langzeitgedaechtnis standen 42 Aufrufe von Werkzeugen, die es nicht
    # gab - jedes Mal mit einem sinnvollen Namen. Das war kein Trainings-,
    # sondern ein Ausstattungsproblem.
    "fenster_maximieren": {
        "titel": "Fenster groß machen",
        "beschreibung": (
            'maximize_window: macht ein BEREITS OFFENES Portal-Fenster GROSS '
            "(Vollbild) - dasselbe wie ein Klick auf das ⤢-Symbol oben "
            'rechts im Fenster. Mit zurueck="ja" wird es wieder auf normale '
            "Größe gebracht. name ist der sichtbare Titel des Fensters. "
            "WICHTIG zur Abgrenzung: Bei \"mach das Fenster X groß\" ist "
            "IMMER dieses Werkzeug gemeint, NICHT open_section - Klaus will "
            "ein vorhandenes Fenster vergrößern, nicht einen Bereich neu "
            "öffnen. open_section ist nur zuständig, wenn er etwas ÖFFNEN "
            "will, das noch nicht offen ist. AUSNAHME: das CHATFENSTER "
            "(diese Unterhaltung hier) ist KEIN Portal-Fenster im Sinne "
            "dieses Werkzeugs - dafür ist set_chat_window(zustand=\"gross\") "
            "zuständig, NICHT dieses Werkzeug."
        ),
        "aufruf": 'maximize_window(name="<Titel des Fensters>")',
        # Wortstaemme - siehe Begruendung bei fenster_minimieren.
        # "größer" enthaelt NICHT "groß" (ö statt o) - beide Formen noetig.
        # Vom Pruefstand gefunden, nachdem der erste Fix schon drin war.
        # "normal"/"normalgroß" (Opus 2026-09-13): "mach den Rechner wieder normal"
        # blendete gar kein Werkzeug ein - es klappte nur, wenn maximize_window
        # kurz davor schon gezeigt worden war.
        "stichwoerter": ["maximier", "vergrößer", "vergroesser", "vollbild",
                         "groß", "gross", "größ", "groess", "normal"],
        "beispiel": "mach das Fenster Farben groß",
    },
    "url_oeffnen": {
        "titel": "Internetseite öffnen",
        "beschreibung": (
            "open_url: öffnet eine oder MEHRERE Internetadressen im "
            "Browser. Mehrere mit Komma trennen. Nur http:// und https:// - "
            "eine Adresse ohne Vorsatz (z.B. miluh.de) wird automatisch zu "
            "https:// ergänzt. WICHTIG: Will Klaus einen Link aus einem "
            "Suchergebnis oder Fenster öffnen, ist IMMER dieses Werkzeug "
            "gemeint - die vollständige Adresse steht in der Liste, die dir "
            "das Such-Werkzeug zurückgegeben hat. NIEMALS stattdessen "
            "open_app(name=\"Firefox\") nehmen: das öffnet nur einen leeren "
            "Browser ohne die Seite. open_app ist nur für ein Programm OHNE "
            "bestimmte Adresse."
        ),
        "aufruf": 'open_url(url="<Internetadresse>")',
        # "link"/"links" fehlte - deshalb wurde open_url bei "oeffne alle
        # Links aus dem Suchfenster" gar nicht erst angeboten, und Milcrid
        # griff sechsmal hintereinander zu open_app (Klaus-Fund 2026-09-04).
        # ".de", "www" usw. (Opus 2026-09-13, Prompt-Test): "öffne spiegel.de"
        # traf keins der Woerter oben - open_url wurde nie gezeigt, das Modell
        # nahm web_search oder read_url.
        "stichwoerter": ["link", "seite", "webseite", "internetseite", "url",
                         "adresse", "im browser", "aufrufen",
                         ".de", ".com", ".org", ".net", ".eu", "www", "http"],
        "beispiel": "öffne den Link aus dem Suchfenster",
    },
    "lautstaerke_stellen": {
        "titel": "Lautstärke stellen",
        "beschreibung": (
            "set_volume: stellt die Lautstärke des Systems. Drei Formen: "
            'prozent="30" setzt sie fest auf 30%, aendern="10" macht 10% '
            'LAUTER, aendern="-10" macht 10% leiser, stumm="ja" schaltet '
            'stumm (stumm="nein" hebt es auf). Beim Lauterstellen wird eine '
            "bestehende Stummschaltung automatisch aufgehoben."
        ),
        "aufruf": 'set_volume(aendern="10")',
        "stichwoerter": ["lauter", "leiser", "lautstärke", "lautstaerke",
                         "stumm", "ton aus", "ton an", "leise", "laut"],
        "beispiel": "mach die Lautstärke 10% lauter",
    },
    "farbe_stellen": {
        "titel": "Portal-Farbe stellen",
        "beschreibung": (
            "set_theme: stellt die Farbe des Portals. Entweder mit einem "
            'Farbnamen (farbe="grün", "blau", "rot", "lila", "orange", '
            '"türkis", "rosa", "gelb", "braun", "grau", "schwarz") oder mit '
            'einem genauen Farbton (hue="140", geht von 0 bis 360 wie der '
            "Regler unter Einstellungen > Farben). Wirkt sofort und bleibt auch "
            "nach einem Neustart erhalten."
        ),
        "aufruf": 'set_theme(farbe="grün")',
        # Die Farbnamen selbst gehoeren dazu: "stell das Portal auf gruen"
        # enthaelt das Wort "Farbe" gar nicht.
        "stichwoerter": ["farbe", "farbton", "hintergrund", "thema", "theme",
                         "bunt", "umfärb", "umfaerb",
                         "blau", "grün", "gruen", "rot", "gelb", "orange",
                         "lila", "violett", "rosa", "pink", "türkis", "tuerkis",
                         "braun", "grau", "schwarz"],
        "beispiel": "stell das Portal auf grün",
    },
    "ergebnis_fenster": {
        "titel": "Ergebnis im Fenster zeigen",
        "beschreibung": (
            "show_result: zeigt einen LANGEN Text in einem eigenen "
            "Portal-Fenster statt im Chat - aber NUR, wenn Klaus das so "
            "wollte. titel ist die Fensterueberschrift, text der "
            "vollstaendige Inhalt. Im Fenster kann Klaus Links anklicken "
            "(gehen im Browser auf), den Text kopieren und als Datei "
            "speichern. WICHTIG: Nach dem Aufruf den Text im Chat NICHT "
            "nochmal wiederholen - nur kurz sagen, dass er im Fenster "
            "steht. "
            "Den Text UNVERAENDERT uebergeben - mit allen Zeilenumbruechen "
            "und Adressen genau so, wie er aus dem anderen Werkzeug kam. "
            "Nicht zusammenfassen, nicht umformatieren, nichts weglassen. "
            "WICHTIG (Klaus-Fund 2026-09-10): fuer ein SUCHERGEBNIS (von "
            "web_search) rufst du dieses Werkzeug NICHT von dir aus auf, "
            "nur weil der Text lang ist - web_search gibt den Text absichtlich "
            "direkt in deine Antwort, das ist der Normalfall. Nur wenn "
            "Klaus ausdruecklich ein (extra/eigenes) Fenster verlangt, nimm "
            "STATTDESSEN web_search(query=\"...\", ins_fenster=\"ja\") - "
            "nicht zusaetzlich noch show_result mit demselben Text "
            "hinterher, sonst steht es doppelt. show_result ist fuer "
            "andere lange Texte gedacht, die du schon hast (z.B. ein "
            "Dateiinhalt, eine lange Liste) und bei denen Klaus ausdruecklich "
            "ein Fenster wollte."
        ),
        "aufruf": 'show_result(titel="<Überschrift>", text="<der ganze Text>")',
        "stichwoerter": ["zeig", "zeige", "fenster", "extra fenster",
                         "eigenem fenster", "suche", "such ", "liste",
                         "ergebnis", "anzeigen"],
        "beispiel": "suche nach Wetter und zeig das Ergebnis im Fenster",
    },
    "fenster_anordnen": {
        "titel": "Fenster anordnen",
        "beschreibung": (
            'arrange_windows: ordnet offene Portal-Fenster neu an - '
            'art="nebeneinander", art="untereinander" oder art="gestaffelt" '
            '(Kaskade). Wirkt normalerweise auf ALLE offenen Fenster '
            "gleichzeitig, es gibt dafür keinen einzelnen Fenster-Namen. "
            'AUSNAHME (Klaus-Wunsch 2026-09-09): Sagt Klaus ausdrücklich, es '
            'gehe um die THEMEN ("staffle die Themen", "Themen nebeneinander"), '
            'dann zusätzlich nur="themen" mitgeben - dann bleiben Portal, Uhr '
            "und alles andere stehen, wo sie sind. Ohne diesen Zusatz kommt "
            "alles mit, und das ist bei \"ordne alle Fenster an\" auch richtig. "
            "Braucht mindestens zwei passende Fenster, sonst passiert nichts."
        ),
        "aufruf": 'arrange_windows(art="nebeneinander")',
        "stichwoerter": [
            "anordnen", "nebeneinander", "untereinander", "gestaffelt", "kaskade",
            "staffle", "staffeln",
        ],
        "beispiel": "ordne die Fenster nebeneinander an",
    },
    "zurueck_gehen": {
        "titel": "Zurück gehen",
        "beschreibung": (
            "go_back: geht im gerade offenen Portal-Fenster eine Ebene "
            "zurück - genau das, was der Zurück-Knopf oben im Fenster tut. "
            "Gemeint ist das, wenn Klaus \"zurück\", \"geh zurück\" oder "
            "\"eine Ebene zurück\" sagt. Braucht keinen Namen. Ist keine "
            "Unteransicht offen, passiert nichts."
        ),
        "aufruf": "go_back()",
        "stichwoerter": ["zurück", "zurueck", "eine ebene"],
        "beispiel": "geh zurück",
    },
    # Die einzige Faehigkeit, die den Rechner selbst betrifft. Sie fuehrt
    # bewusst NICHTS aus, sondern oeffnet nur dieselbe Sicherheitsfrage, die
    # auch die beiden Punkte unten am Bildschirmrand oeffnen - bestaetigen
    # muss Klaus von Hand. Der Befehl waere technisch harmlos (passwortloses
    # systemctl liegt vor); das Risiko ist, dass die KI ihn ausloest, weil
    # ueber Neustarts GEREDET wird statt einen zu wollen. Mit der Rueckfrage
    # kann sie schlimmstenfalls ein Fenster oeffnen (Klaus-Wunsch 2026-09-01).
    "pc_steuern": {
        "titel": "PC neu starten / ausschalten",
        "beschreibung": (
            "Drei Werkzeuge, ZWEI Schritte. Schritt 1 - die Frage stellen. "
            "Achte genau darauf, WELCHE der beiden gemeint ist, das wird "
            "leicht verwechselt: "
            "\"neu starten\", \"Neustart\", \"reboot\", \"starte neu\" "
            "-> restart_pc(). "
            "\"ausschalten\", \"aus\", \"abschalten\", \"runterfahren\", "
            "\"herunterfahren\" -> shutdown_pc(). "
            "Diese beiden starten und beenden NICHTS, sie oeffnen nur die "
            "Sicherheitsfrage - du darfst sie deshalb ohne Zoegern aufrufen. "
            "WICHTIG: Schreib NIEMALS die Sicherheitsfrage nur mit eigenen "
            "Worten hin (z.B. \"Moechtest du den Computer neu starten?\") - "
            "ohne den echten Aufruf [TOOL_CALL: restart_pc()] bzw. "
            "[TOOL_CALL: shutdown_pc()] bleibt die Frage technisch NICHT "
            "offen, und ein spaeteres \"ja\" laeuft ins Leere. IMMER erst "
            "der Aufruf, DANN erst der Satz aus dem Werkzeug-Ergebnis. "
            "Schritt 2 - confirm_pc: fuehrt den offenen Vorgang WIRKLICH aus. "
            "Sagt Klaus danach \"ich bestaetige\", \"ja\", \"mach das\" "
            "oder wiederholt er den Wunsch, dann rufe confirm_pc() auf - NICHT "
            "noch einmal restart_pc/shutdown_pc, sonst fragst du ewig weiter. "
            "confirm_pc braucht keinen Namen, es weiss selbst, worum es geht. "
            "Rufe NICHTS davon auf, wenn ueber Neustarts nur geredet wird "
            "(\"wie startet man den PC neu?\") - dann antworte nur. "
            "AUSNAHME, sehr wichtig: steht \"Rechner\" allein im Satz, OHNE "
            "eines der Woerter oben (\"neu starten\"/\"ausschalten\"/"
            "\"runterfahren\"/...), ist damit so gut wie immer die App "
            "\"Milcrid Rechner\" (Taschenrechner) gemeint, NICHT der PC - "
            "Beispiel \"öffne Rechner\", \"starte den Rechner\". Dann NICHTS "
            "von hier nehmen, sondern open_app(name=\"Milcrid Rechner\")."
        ),
        "aufruf": "restart_pc()",
        # Bewusst auch das blosse Wort "pc": die Stichwoerter werden als
        # Textstueck gesucht, und "starte den PC neu" enthaelt weder "neu
        # starten" noch "neustart" - die Wortstellung ist im Deutschen frei.
        # Ohne Treffer sieht die KI die Beschreibung nie und RAET dann den
        # Werkzeugnamen ("restart_computer", 2026-09-01 beobachtet). Lieber
        # die Beschreibung einmal zu oft mitgeben.
        # "rechner" bewusst NICHT mehr hier (bis 2026-09-04 drin): "öffne
        # Rechner" (die App) zeigte dadurch IMMER auch diese Beschreibung an,
        # und das kleine Modell hat sich trotz AUSNAHME-Satz oben wiederholt
        # fuer restart_pc() statt open_app entschieden - ein Text-Hinweis
        # reichte nicht, das Stichwort musste ganz raus (Klaus-Fund
        # 2026-09-04, live nachgestellt: "öffne Rechner" fragte staendig nach
        # PC-Neustart). "starte den Rechner neu" findet die KI seither ueber
        # "pc" nicht mehr - Abwaegung bewusst so, weil "öffne Rechner" die
        # sehr viel haeufigere Formulierung ist.
        "stichwoerter": ["pc", "neu starten", "neustart", "ausschalten",
                         "runterfahren", "herunterfahren", "abschalten", "reboot",
                         "fahr", "schalt", "bestätig", "bestaetig"],
        "beispiel": "starte den PC neu",
    },
    # ---- Terminplaner, Notizen, Wecker, Timer (Klaus-Brainstorm 2026-09-14) ----
    # Werkzeuge in bridge.py, Logik in planer_verwaltung.py. Die Beschreibungen
    # sagen dem Modell ausdruecklich, Klaus' Worte fuer Datum/Uhrzeit NUR
    # weiterzureichen - gerechnet wird in Python (Modelltest 13.09.: "welcher
    # Tag ist heute" 1 von 5). Beispielwerte stehen nur als <Platzhalter> da,
    # echte Werte schreiben kleine Modelle ab (Lehre C4).
    "termine_eintragen": {
        "titel": "Termine eintragen",
        "beschreibung": (
            'add_appointment: trägt einen Termin in Milcrid Termine ein. '
            'datum und uhrzeit GENAU mit Klaus\' Worten übergeben ("morgen", "Freitag", "20.10.", '
            '"halb 11") - NICHT selbst umrechnen, Milcrid rechnet das. uhrzeit leer lassen, wenn keine '
            'genannt wurde (dann ganztägig). titel = worum es geht, kurz. Optional: ort, details, '
            'erinnerung ("2 Stunden", "1 Tag", "1 Woche", "keine"; ohne Angabe 1 Stunde vorher), '
            'wiederholung ("jede Woche", "jeden Monat", "jedes Jahr"), datei (Dateiname aus Milcrids '
            'Ordner). Sagt Klaus "erinnere mich am/um … an …", ist das ein Termin mit '
            'erinnerung="zum Termin". "erinnere mich IN 20 Minuten" ist dagegen ein Timer '
            '(start_timer). Das Werkzeug meldet zurück, was wirklich gespeichert wurde - genau das '
            'weitersagen. Meldet es "NICHT eingetragen", das so sagen und nichts anderes behaupten.'
        ),
        "aufruf": 'add_appointment(datum="<Datum>", uhrzeit="<Uhrzeit>", titel="<Titel>")',
        "stichwoerter": ["termin", "trag", "eintrag", "erinner", "geburtstag", "verabredung",
                         "kalender", "planer"],
        "beispiel": "trag morgen um 10 Uhr einen Termin ein",
    },
    "termine_zeigen": {
        "titel": "Termine zeigen und vorbereiten",
        "beschreibung": (
            'list_appointments: nennt Klaus seine Termine und öffnet Milcrid Termine. zeitraum = '
            '"heute", "morgen", "woche", "nächste woche", "monat", "alle" oder ein Datum mit Klaus\' '
            'Worten. Nur die Termine nennen, die das Werkzeug liefert - niemals welche erfinden. '
            'prepare_appointment(titel="<Stichwort>"): "zeig mir den Termin X nochmal", "bereite '
            'X vor" - öffnet den Termin in Milcrid Termine, öffnet seine Dateien und liefert Details und '
            'Notizen dazu. Meldet es eine Datei als NICHT GEFUNDEN, das Klaus deutlich sagen.'
        ),
        "aufruf": 'list_appointments(zeitraum="<Zeitraum>")',
        # Wortstaemme statt Wendungen: "was steht morgen an" enthaelt "was steht
        # an" nie am Stueck (Verbklammer, siehe Pruefstand p11).
        "stichwoerter": ["termin", "vorbereit", "bereite", "was steht", "was habe", "was hab", "vorhab",
                         "kalender", "planer"],
        "beispiel": "welche Termine habe ich morgen",
    },
    "online_ki_fragen": {
        "titel": "Online-KI fragen",
        "beschreibung": (
            'frage_online_ki: gibt Klaus\' Frage an die grosse Online-KI weiter (Gemini und andere, '
            'ueber seinen eigenen API-Schluessel) und holt ihre Antwort. Nimm das, wenn Klaus '
            'ausdruecklich die Online-KI/Gemini/ChatGPT fragen will, oder wenn er etwas will, das '
            'nur eine grosse KI kann (lange Texte schreiben, Code entwerfen, tagesaktuelle '
            'Einschaetzungen). auftrag = die Frage in Klaus\' Worten, vollstaendig und fuer sich '
            'verstaendlich - die Online-KI kennt euer Gespraech nicht. Sagt Klaus, wie LANG die '
            'Antwort sein soll ("kurz", "in einem Satz", "ausfuehrlich", "mindestens 20 Saetze"), '
            'dann schreibe genau das mit in den auftrag - sonst antwortet die Online-KI, wie sie will. '
            'ins_fenster="ja" NUR, wenn Klaus ausdruecklich ein Fenster will oder etwas Langes '
            '(Text, Code, Liste, Erklaerung, "ausfuehrlich"). Bei "kurz", "in einem Satz", '
            '"nur die Zahl", "ja oder nein" NIE ins_fenster - die Antwort gehoert in den Chat. Das ist NICHT die Internetsuche: web_search '
            'liefert Fundstellen aus dem Netz, frage_online_ki liefert die Antwort einer anderen KI. '
            'Kommt die Antwort KURZ und direkt zurueck, gib Klaus ihren Inhalt im Chat wieder - sage dann '
            'NICHT, sie stehe in einem Fenster. Nur wenn das Werkzeug ausdruecklich meldet, dass der Text im '
            'Fenster steht, sagst du genau das (und wiederholst ihn nicht). '
            'Die Antwort steht danach auch im Fenster Online KI - dort kann Klaus weiterfragen. '
            'Geht nur, wenn Klaus dort den Schalter Verbindung eingeschaltet hat; ist er aus, sage '
            'ihm genau das. '
            'Nennt Klaus eine DATEI, die mit soll ("schick demo.txt an Gemini", "lass die Online-KI '
            'rechnung.pdf zusammenfassen"), dann dateien="<Dateiname>" (mehrere mit Komma). Will er die '
            'Antwort als Datei ("Ergebnis in zusammenfassung.txt"), dann speichern_als="<Dateiname>". '
            'Beides nur, wenn Klaus es sagt.'
        ),
        # Zusatzfelder bewusst NICHT im Aufruf-Beispiel: das kleine Modell
        # schreibt Beispielwerte ab (test.txt, 09.09.) - sie stehen nur oben.
        "aufruf": 'frage_online_ki(auftrag="<Klaus\' Frage>")',
        "stichwoerter": ["online ki", "online-ki", "onlineki", "gemini", "chatgpt", "chat gpt",
                         "api ki", "grosse ki", "große ki", "andere ki"],
        "beispiel": "frag die Online KI nach den neuesten Nachrichten zu KI",
    },
    "notizen_speichern": {
        "titel": "Notizen speichern",
        "beschreibung": (
            'save_note: speichert eine Notiz in Milcrid Notizen. text = der Inhalt, wörtlich wie '
            'Klaus ihn sagt. Optional: titel, datum (Klaus\' Worte, dann erscheint sie im '
            'Termine an dem Tag), termin (Stichwort eines vorhandenen Termins, zu dem die Notiz '
            'gehört). Das Werkzeug meldet zurück, was wirklich gespeichert wurde - genau das '
            'weitersagen.'
        ),
        "aufruf": 'save_note(text="<Text der Notiz>")',
        # "schreib" auch allein: "schreib dir auf: ..." hat "auf" am Satzende.
        "stichwoerter": ["notiz", "notier", "schreib", "merkzettel"],
        "beispiel": "notiere dir bitte etwas",
    },
    "wecker_timer": {
        "titel": "Wecker und Timer",
        "beschreibung": (
            'set_alarm: stellt einen Wecker in der Milcrid Uhr. uhrzeit mit Klaus\' Worten ("7 Uhr", '
            '"halb 7"), optional bezeichnung, wiederholung ("jeden Tag", "werktags", ohne Angabe '
            'einmal). start_timer(dauer="<Dauer>"): startet einen Timer ("5 Minuten", "1 Stunde 30 '
            'Minuten"), optional bezeichnung - auch für "erinnere mich in X Minuten an Y" '
            '(bezeichnung=Y). stop_alarm(): macht aus, was gerade klingelt ("Wecker aus", "stopp", '
            '"ist gut"). Das Werkzeug meldet zurück, was wirklich gestellt wurde - genau das '
            'weitersagen.'
        ),
        "aufruf": 'set_alarm(uhrzeit="<Uhrzeit>")',
        "stichwoerter": ["wecker", "weck", "timer", "klingel", "alarm", "eieruhr", "countdown",
                         "erinner", "minuten", "stopp"],
        "beispiel": "stell einen Timer auf ein paar Minuten",
    },
}

# Katalog aller echten Portal-Bereiche fuer open_section (bridge.py) - name:
# (Anzeigename, Eltern-Kennung oder None). Mechanisch aus milcrid_portal.html
# extrahiert (jedes "hub-zeile"-Element mit seiner id/data-hub-id und dem
# sichtbaren hub-name-Text), NICHT von Hand getippt - Klaus-Wunsch 2026-08-25
# ("öffne Farben"). Bei neuen Kacheln im Portal hier nachziehen, sonst kennt
# open_section sie nicht.
PORTAL_BEREICHE = {
    # "milcrid" ist die Startuebersicht selbst (seit 2026-09-05 "Portal"
    # genannt), erreichbar ueber den festen Seiten-Knopf statt eine
    # Hub-Kachel - deshalb bisher der einzige Bereich, den die KI ueberhaupt
    # nicht kannte. Klaus-Fund 2026-09-05: "öffne Portal" öffnete immer
    # irgendwas anderes, weil das Werkzeug den Namen gar nicht fand und
    # riet. Kennung "milcrid" bleibt intern gleich (nur die ANZEIGE
    # aendert sich), siehe PANEL_NAMEN im Portal-Skript.
    "milcrid": ("Portal", None),
    "apps": ("Meine Apps", None),
    "einstellungen": ("Einstellungen", None),  # Klaus-Wunsch 2026-09-05: hiess vorher "Portal"
    "profilmanager": ("Profil Manager", None),
    "lokaleki": ("Lokale KI", None),
    "apiki": ("API KI", None),
    "linuxpython": ("Linux Python", None),
    "cloud": ("Cloud", None),
    "system": ("Betriebssystem", None),
    "update": ("Update", None),
    "dateimanager": ("Datei Manager", None),
    "schreibtisch": ("Themen Manager", None),
    "extras": ("Extras", None),
    # C26SO (Klaus-Wunsch 2026-09-08) - eigenes System neben Milcrid, im
    # Portal zunaechst nur zum Ansehen. Die vier Module als Unterkacheln,
    # damit die KI sie auch einzeln oeffnen kann ("oeffne Sicherheit").
    "c26so": ("C26SO", None),
    "c26Agenten": ("Agenten", "c26so"),
    "c26Sicherheit": ("Sicherheit", "c26so"),
    "c26Sprache": ("Werkzeugverwaltung", "c26so"),
    "c26Allgemein": ("Werkzeuge Allgemein", "c26so"),
    "c26Beschreibung": ("C26SO Beschreibung", "c26so"),
    "lautstaerkeBtn": ("Lautstärke", "system"),
    "mikrofonBtn": ("Mikrofon", "system"),  # Klaus-Wunsch 2026-09-06
    "aufloesungBtn": ("Bildschirm", "system"),  # Auflösung + Bildwiederholrate (2026-09-20)
    "alleSchalterBtn": ("Alle Schalter", "system"),
    "farbeBtn": ("Farben", "einstellungen"),
    "schriftBtn": ("Schrift", "einstellungen"),
    "buttonsBtn": ("Buttons", "einstellungen"),
    "groesseBtn": ("Größe", "einstellungen"),
    "portalSuchenBtn": ("Portal Durchsuchen", "einstellungen"),
    "hintergrundBtn": ("Hintergrund", "einstellungen"),
    "profilNutzerBtn": ("Nutzer Profil", "profilmanager"),
    "profilAlleBtn": ("Alle Profile", "profilmanager"),
    "profilKiBtn": ("KI Profil", "profilmanager"),
    "profilSelbstBtn": ("Selbst", "profilmanager"),
    "profilTagebuchBtn": ("Tagebuch", "profilmanager"),
    "profilErfahrungslogBtn": ("Erfahrungs-Log", "profilmanager"),
    "gedaechtnisBtn": ("Gedächtnis", "profilmanager"),
    "profilSandboxBtn": ("Sandbox", "profilmanager"),
    "profilErstellenBtn": ("Profil erstellen", "profilmanager"),
    "promptCharakterBtn": ("Charakter Prompt", "lokaleki"),
    "systemPromptBtn": ("System Prompt", "lokaleki"),
    "toolboxSystemBtn": ("System Tools", "lokaleki"),
    "sandboxBtn": ("KI Sandbox", "lokaleki"),
    "kiTestBtn": ("KI Test", "lokaleki"),
    "faehigkeitenBtn": ("Fähigkeiten", "lokaleki"),
    # Nachgetragen 2026-09-20 (Klaus-Wunsch "geh mal alle Portal-Fenster
    # durch, ob die KI sie kennt"): diese zehn Kacheln gab es im Portal,
    # aber open_section kannte sie nicht - "oeffne Langzeitgedaechtnis"
    # oder "oeffne System Test" landete deshalb bei irgendetwas anderem.
    "systemtest": ("System Test", None),
    "modelleBtn": ("Models", "lokaleki"),
    "kurzzeitBtn": ("Kurzzeitgedächtnis", "profilmanager"),
    "langzeitBtn": ("Langzeitgedächtnis", "profilmanager"),
    "updHinweiseBtn": ("Update-Hinweise", "update"),
    "updMilcridBtn": ("Milcrid Update", "update"),
    "updLinuxBtn": ("Linux System", "update"),
    "updProgrammeBtn": ("Programme", "update"),
    "updKiBtn": ("KI-Dienst Ollama", "update"),
    "updTreiberBtn": ("Treiber & Kernel", "update"),
}

# bereiche_oeffnen bekommt ALLE echten Bereichsnamen automatisch als
# Stichwoerter (statt eine kleine handverlesene Liste, siehe Kommentar bei
# FAEHIGKEITEN oben) - Klaus-Fund 2026-08-25: "öffne Lokale KI" fand das
# Werkzeug frueher gar nicht, weil "lokale ki" auf keiner Liste stand, die KI
# sah es also nie und riet stattdessen (Dateiname erfunden). "fenster" extra
# dazu als starkes, unzweideutiges Signalwort (Klaus-Vorschlag, "Fenster
# Lokale KI" statt "öffne Lokale KI" - trennt es klar von den drei anderen
# Werkzeugen, die alle auch auf "öffne" reagieren).
# Portal-Fenster (Klaus-Wunsch 22.09.2026): "Milcrid Direkt Aufgaben" und
# "Milcrid Dialog-Regeln" sind seit dem 21.09. eigene Fenster mit eigener
# Kachel, entstehen aber erst zur LAUFZEIT (portalfensterAnmelden im Portal).
# Sie stehen deshalb weder in apps.json noch in PORTAL_BEREICHE - fuer die KI
# gab es sie schlicht nicht. Diese Liste fuellt das Portal selbst ueber
# portalkarte_uebernehmen(), sie ist beim Start absichtlich leer.
PORTAL_FENSTER = {}   # kennung -> Anzeigename


def _namensformen(name):
    """Alle Schreibweisen, unter denen ein Name als Stichwort treffen kann.

    Der Vorfilter in kontext_fuer_eingabe prueft schlicht "Stichwort steckt im
    Satz". Klaus sagt denselben Namen aber mal getrennt, mal zusammen, und
    Whisper schreibt ihn entsprechend ("Direkt Aufgaben" / "Direktaufgaben") -
    ohne beide Formen faellt genau die andere durch (derselbe Grund wie bei
    _eng() in bridge.open_section, Klaus-Fund 07.09. "Datei Manager"). Der
    Name OHNE das Wort "Milcrid" kommt dazu, weil Klaus das Praefix im
    Sprechen fast immer weglaesst."""
    formen = set()
    for n in (name, name[8:] if name.lower().startswith("milcrid ") else ""):
        n = (n or "").strip().lower()
        if not n:
            continue
        formen.add(n)
        formen.add(n.replace(" ", ""))
        formen.add(n.replace("-", " "))
        # Auch ganz ohne Trennung: "Dialog-Regeln" spricht Klaus als
        # "Dialogregeln" aus, und genau diese Form fehlte im ersten Anlauf -
        # das Werkzeug wurde deshalb gar nicht erst eingeblendet (gemessen
        # im Lauf 22:56).
        formen.add(n.replace("-", "").replace(" ", ""))
        # Dazu jedes markante EINZELWORT des Namens. Grund: Klaus beugt im
        # Sprechen ("oeffne direkTE Aufgaben" - seine erste Formulierung am
        # 22.09.), und dann steckt keine der ganzen Formen mehr im Satz. Das
        # Einzelwort "aufgaben" ueberlebt jede Beugung.
        # Erst ab 7 Buchstaben, damit haeufige kurze Woerter ("meine",
        # "alle", "profil") das Werkzeug nicht dauernd einblenden - jede
        # eingeblendete Beschreibung ist fuer das kleine Modell eine
        # Einladung, sie auch zu benutzen (siehe main.py).
        # Gemessen an den 107 echten Eingaben der Mitschrift vom 22.09.:
        # bereiche_oeffnen wird dadurch bei 20 % statt 16 % eingeblendet, und
        # die vier zusaetzlichen sind genau Klaus' vier Fehlversuche - kein
        # einziger Fehlalarm.
        for w in n.replace("-", " ").split():
            if len(w) >= 7 and w != "milcrid":
                formen.add(w)
    return {f for f in formen if len(f) > 2}


def _stichwoerter_berechnen():
    """bereiche_oeffnen bekommt ALLE echten Bereichs- und Fensternamen
    automatisch als Stichwoerter (statt einer handverlesenen Liste, siehe
    Kommentar bei FAEHIGKEITEN oben) - Klaus-Fund 2026-08-25: "öffne Lokale
    KI" fand das Werkzeug frueher gar nicht, weil "lokale ki" auf keiner
    Liste stand, die KI sah es also nie und riet stattdessen (Dateiname
    erfunden). "fenster" extra dazu als starkes, unzweideutiges Signalwort
    (Klaus-Vorschlag, "Fenster Lokale KI" statt "öffne Lokale KI" - trennt es
    klar von den drei anderen Werkzeugen, die alle auch auf "öffne" reagieren).

    Seit 22.09. eine Funktion statt einer einmaligen Zuweisung: die Namen
    koennen sich zur Laufzeit aendern, wenn das Portal seine Karte meldet."""
    woerter = {"fenster", "portal", "bereich", "kachel"}
    for anzeige, _eltern in PORTAL_BEREICHE.values():
        woerter |= _namensformen(anzeige)
    for anzeige in PORTAL_FENSTER.values():
        woerter |= _namensformen(anzeige)
    FAEHIGKEITEN["bereiche_oeffnen"]["stichwoerter"] = sorted(woerter)


_stichwoerter_berechnen()


def portalkarte_uebernehmen(karte):
    """Traegt nach, was das Portal ueber sich selbst meldet (siehe
    window.milcridPortalkarte und main.py, typ "portalkarte").

    Nur ERGAENZEN, nie loeschen: kommt eine Karte unvollstaendig an - etwa
    weil das Portal gerade neu aufbaut -, soll die KI nicht kurzzeitig
    weniger koennen als vorher. Gibt (neue Bereiche, neue Fenster) zurueck."""
    neu_b = neu_f = 0
    for e in karte or []:
        if not isinstance(e, dict):
            continue
        art = e.get("art")
        name = str(e.get("name") or "").strip()
        kennung = str(e.get("kennung") or "").strip()
        if not name or not kennung:
            continue
        if art == "bereich":
            if kennung not in PORTAL_BEREICHE:
                PORTAL_BEREICHE[kennung] = (name, e.get("eltern") or None)
                neu_b += 1
        elif art == "portalfenster":
            if kennung not in PORTAL_FENSTER:
                PORTAL_FENSTER[kennung] = name
                neu_f += 1
    if neu_b or neu_f:
        _stichwoerter_berechnen()
    return neu_b, neu_f

# Sicherer Default: AUS, bis Klaus eine Faehigkeit selbst im Portal
# einschaltet - passt zum Grundsatz dieser Nacht (der Schalter muss echt
# etwas steuern, nicht nachtraeglich abgesichert werden muessen).
_STANDARD_AN = False


def _daten_laden():
    try:
        with open(DATEN_PFAD, "r", encoding="utf-8") as f:
            daten = json.load(f)
    except Exception:
        daten = {}
    if not isinstance(daten, dict):
        daten = {}
    return daten


def _daten_speichern(daten):
    with open(DATEN_PFAD, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)


def ist_aktiv(name):
    daten = _daten_laden()
    return bool(daten.get(name, _STANDARD_AN))


def info():
    """Alles, was das Portal fuer die Faehigkeiten-Ansicht braucht."""
    daten = _daten_laden()
    return {
        "faehigkeiten": [
            {"name": n, "titel": f["titel"], "beispiel": f.get("beispiel", ""),
             "an": bool(daten.get(n, _STANDARD_AN))}
            for n, f in FAEHIGKEITEN.items()
        ]
    }


def umschalten(name, an):
    if name not in FAEHIGKEITEN:
        return {"erfolg": False, "fehler": f'Unbekannte Fähigkeit "{name}".'}
    daten = _daten_laden()
    daten[name] = bool(an)
    _daten_speichern(daten)
    return {"erfolg": True}


# Diese drei IMMER neu anbieten, wenn ihr Stichwort trifft, auch wenn
# schon einmal in dieser Sitzung gezeigt - Begruendung siehe Kommentar
# in kontext_fuer_eingabe unten.
_IMMER_NEU_ZEIGEN = {
    "fenster_minimieren", "fenster_maximieren", "fenster_schliessen",
    # Klaus-Fund 2026-09-10, noch am selben Abend: "Neustart" -> Modell
    # stellt die Sicherheitsfrage nur in EIGENEN Worten, OHNE restart_pc()
    # wirklich aufzurufen - die Frage steht dann nie technisch offen. Jedes
    # weitere "Neustart"/"ja" traf pc_steuern danach nicht mehr frisch
    # (schon gezeigt), confirm_pc() fand folgerichtig nichts zum Bestaetigen
    # -> Klaus haengt in einer Schleife fest, der PC startet nie neu. Bei
    # einem sicherheitsrelevanten Zwei-Schritt-Ablauf wiegt das besonders
    # schwer - lieber jedes Mal neu zeigen als einmal in dieser Schleife.
    "pc_steuern",
    # Opus 2026-09-10, am KI-Pruefstand gefunden: das Geschwister der drei
    # Fenster-Werkzeuge fehlte hier. "Schattenfenster schliessen" bekam dann
    # nur close_window angeboten - dessen Beschreibung sagt "fuers
    # Chatfenster ist set_chat_window zustaendig", genau das war aber als
    # "schon gezeigt" unterdrueckt. Folge: Milcrid verweigerte oder schloss
    # ein falsches Fenster (Kalender) - 3 von 4 Durchgaengen.
    "chat_fenster_stellen",
}


# ---- Eine Faehigkeit, zu der gerade eine Frage OFFEN steht ---------------
#
# Klaus-Fund 2026-09-20: Milcrid liest einen Dialog vor und fragt "soll ich
# abbrechen?". Klaus sagt "ja bitte" - und nichts passiert. Ursache ist die
# Stichwort-Pruefung ganz unten: in "ja bitte" steckt keines der Woerter von
# "Fenster vorlesen", also wird die Faehigkeit gar nicht erst mitgeladen. Das
# Modell KANN den Abbruch nicht aufrufen, so willig es auch ist.
#
# _IMMER_NEU_ZEIGEN hilft dagegen NICHT - das hebt nur die Sperre "schon einmal
# gezeigt" auf, die Stichwort-Pruefung laeuft trotzdem. Zwei verschiedene
# Bremsen; im Protokoll vom 20.09. hatte ich sie verwechselt.
#
# Darum hier ein eigener Merker: solange eine Frage technisch offen ist, wird
# ihre Faehigkeit bei JEDER Eingabe angeboten, egal welche Worte Klaus waehlt.
# Bewusst eng: nur der offene Moment, und er endet mit Klaus' Antwort. Wer
# anmeldet, meldet auch wieder ab - siehe bridge._dialog_anfrage_setzen().
_OFFENE_FRAGE = {}


def offene_frage_anmelden(name, hinweis=""):
    """Diese Faehigkeit bei jeder Eingabe zeigen, bis abgemeldet wird.

    *hinweis* ist der Satz fuer genau diesen Moment; er steht dann UNTER der
    Werkzeug-Beschreibung. Die Beschreibung sagt, was das Werkzeug KANN - der
    Hinweis sagt, was JETZT zu tun ist. Live-Fund 20.09.: ohne ihn las das
    Modell auf "ja bitte" das Fenster einfach noch einmal vor und stellte
    dieselbe Frage erneut - eine Schleife, aus der Klaus nicht herauskommt.
    Klaus' Lehre "Wortlaut statt Regel": dem kleinen Modell muss man den Satz
    hinschreiben, eine allgemeine Regel genuegt ihm nicht."""
    if name in FAEHIGKEITEN:
        _OFFENE_FRAGE[name] = hinweis or ""


def offene_frage_abmelden(name):
    """Zurueck zum Normalfall: nur noch bei passenden Stichwoertern."""
    _OFFENE_FRAGE.pop(name, None)


def offene_fragen():
    """Wozu steht gerade eine Frage offen? (Nur zum Nachsehen und Pruefen.)"""
    return set(_OFFENE_FRAGE)


def kontext_fuer_eingabe(eingabe, schon_gezeigt=None):
    """Gleiches Rueckgabe-Format wie toolbox_verwaltung.kontext_fuer_eingabe
    (main.py behandelt beide identisch) - PLUS die Schalter-Pruefung: eine
    ausgeschaltete Faehigkeit wird hier nie zurueckgegeben, egal welche
    Stichwoerter treffen."""
    schon_gezeigt = schon_gezeigt or set()
    text = (eingabe or "").lower()
    treffer = []
    for name, f in FAEHIGKEITEN.items():
        # Klaus-Fund 2026-09-10: "minimiere Klaus", direkt danach "minimiere
        # Fenster Klaus", "minimiere Thema Klaus" - alle drei nur Text vom
        # Modell ("Fenster Klaus wurde minimiert"), OHNE jeden TOOL_CALL.
        # Nichts wurde wirklich minimiert, Milcrid meldete trotzdem Erfolg.
        # Ursache: einmal gezeigt, nie wieder - das kleine Modell verlaesst
        # sich dann auf die blosse Erinnerung an ein frueher gesehenes
        # Werkzeug statt es erneut aufzurufen, und das gelingt ihm nicht
        # zuverlaessig (siehe wiki Symptom 5, Nachtrag). Bei den drei
        # Fenster-AKTIONS-Werkzeugen ist eine stille Falschmeldung
        # schlimmer als ein paar zusaetzliche Zeilen Beschreibung - darum
        # HIER die Sperre umgehen und bei jedem Stichwort-Treffer erneut
        # zeigen, nicht nur beim ersten Mal.
        # Steht zu dieser Faehigkeit eine Frage offen, zaehlt weder "schon
        # gezeigt" noch das Stichwort - sonst faellt genau die Antwort durch,
        # auf die wir warten ("ja bitte").
        offen = name in _OFFENE_FRAGE
        if name in schon_gezeigt and name not in _IMMER_NEU_ZEIGEN and not offen:
            continue
        # Der Schalter gilt weiter: eine ausgeschaltete Faehigkeit wird auch
        # bei offener Frage nie angeboten.
        if not ist_aktiv(name):
            continue
        if offen or any(wort in text for wort in f["stichwoerter"]):
            treffer.append(name)
    if not treffer:
        return None, []
    # Die Regel-Zeile ist bewusst Teil DIESES Textes und nicht in jede
    # einzelne Beschreibung kopiert - so gilt sie automatisch fuer jedes
    # kuenftige Werkzeug und kann nicht bei einem vergessen werden.
    #
    # Warum es sie gibt (Opus-Pruefung 2026-08-31): die Beispiel-Aufrufe
    # enthielten frueher ECHTE, existierende Werte (u.a. name="Auto", ein
    # tatsaechlich vorhandenes Thema). Kam ein unvollstaendiger Befehl an -
    # per Sprache passiert das oft, z.B. nur "öffne" oder "schlie" -, hatte
    # das Modell nichts zum Anknuepfen und uebernahm einfach den
    # Beispielwert. Ergebnis: Milcrid oeffnete/minimierte staendig "Auto",
    # im Chatprotokoll vom 2026-08-31 dutzendfach belegt. Klaus hat sogar
    # versucht, ihr das im Gespraech abzugewoehnen ("benutze nicht mehr
    # Auto") - das konnte nicht wirken, weil die Ursache hier im
    # Werkzeug-Text stand, nicht im Gespraech.
    teile = [
        "[Zusätzliches Werkzeug für diese Anfrage verfügbar:]",
        "Die Werte in spitzen Klammern (z. B. <Titel des Fensters>) sind "
        "PLATZHALTER, keine echten Namen - niemals wörtlich einsetzen. "
        "Setze den genannten Namen OHNE spitze Klammern ein. "
        "Hat Klaus einen Namen genannt, das Werkzeug damit einfach "
        "AUFRUFEN - auch wenn der Name ungewohnt klingt. Nicht vorher "
        "nachfragen, ob es ihn gibt: das Werkzeug meldet das selbst zurück "
        "und nennt dann die tatsächlich vorhandenen Namen. Nur wenn GAR "
        "KEIN Name genannt wurde oder die Eingabe abgeschnitten wirkt "
        "(z. B. nur \"öffne\", \"schlie\", \"Minimi\" - bei Spracheingabe "
        "häufig), NICHT raten und keinen Namen aus dieser Beschreibung "
        "nehmen, sondern kurz zurückfragen, was gemeint ist.",
        # Kürze-Regel (Klaus-Wunsch 2026-09-01). Sie steht bewusst HIER, im
        # Werkzeug-Kontext, und nicht im allgemeinen Charakter-Prompt: sie
        # soll nur für Befehle gelten. Bittet Klaus ausdrücklich um etwas
        # Ausführliches ("lies mir die Datei vor", "erklär mir das"), ist
        # kein Werkzeug-Kontext im Spiel oder er hat ausdrücklich gefragt -
        # dann darf sie so lang antworten wie nötig.
        # Der Zusatz zum FORMAT ist unverzichtbar: ohne ihn nahm das Modell
        # "kurz" auch fuer den Werkzeug-Aufruf und schrieb nur noch nacktes
        # "restart_pc()" in den Text - ohne die [TOOL_CALL: ...]-Klammer, also
        # ohne dass ueberhaupt etwas ausgefuehrt wurde (2026-09-01 sofort beim
        # ersten Test aufgetreten). Kuerze darf immer nur den ANTWORTTEXT
        # betreffen, nie die Form des Aufrufs.
        "ANTWORTLÄNGE UND REIHENFOLGE: Das hier ist ein Befehl, kein Gespräch. "
        "Deine erste Antwort besteht NUR aus Aufrufen - kein Satz davor "
        "oder danach, denn vor dem [WERKZEUG-ERGEBNIS] ist noch nichts "
        "passiert. Jeder Aufruf steht in seiner EIGENEN Klammer im Format "
        "[TOOL_CALL: ...]. Hat Klaus' Satz mehrere Aufträge (\"X und Y\", "
        "\"öffne X und maximiere es\"), schreibst du alle Aufrufe "
        "hintereinander: [TOOL_CALL: a(...)] [TOOL_CALL: b(...)] - das "
        "System führt sie der Reihe nach aus. Nach dem Ergebnis schreibst "
        "du EINEN Satz, was wirklich passiert ist. "
        "Zähle nichts "
        "auf, was im Werkzeug-Ergebnis stand (Listen von Namen, Programmen, "
        "Bereichen); nenne höchstens die zwei, drei naheliegendsten. Biete "
        "keine Alternativen an, um die niemand gebeten hat. Ausführlich "
        "wird nur, wer ausdrücklich darum gebeten wird.",
        # Beim ersten Test des Bestätigens gemeldet: das Werkzeug antwortete
        # "Kein offener Vorgang", Milcrid schrieb Klaus "Der PC wurde
        # erfolgreich neu gestartet" (2026-09-01). Ein erfundener Erfolg ist
        # schlimmer als ein Fehlschlag - Klaus glaubt dann, etwas sei
        # passiert, und sucht den Fehler an der falschen Stelle.
        "WAHRHEIT: Sage nur das, was im Werkzeug-Ergebnis wirklich steht. "
        "Meldet das Werkzeug, dass etwas NICHT ging oder nichts gefunden "
        "wurde, dann sage genau das - kurz und geradeheraus. Behaupte "
        "niemals einen Erfolg, den das Werkzeug nicht gemeldet hat.",
    ]
    for name in treffer:
        f = FAEHIGKEITEN[name]
        teile.append(f"\n{f['aufruf']}: {f['beschreibung']}")
        # Steht zu dieser Faehigkeit gerade eine Frage offen, zaehlt fuer
        # diesen einen Zug der konkrete Satz mehr als die allgemeine
        # Beschreibung - er steht deshalb direkt darunter.
        if _OFFENE_FRAGE.get(name):
            teile.append(_OFFENE_FRAGE[name])
        if name == "bereiche_oeffnen":
            # Die ECHTEN Bereichsnamen mitgeben. Vorher hing die Erkennung
            # allein am Signalwort "Fenster" ("Fenster Meine Apps") - ohne
            # das wusste die KI nicht, dass "Meine Apps" ein Bereich ist,
            # und probierte es als Programm, das es nicht gibt (Klaus-Fund
            # 2026-09-01: "computer öffne meine apps versteht er nicht").
            # Aus PORTAL_BEREICHE erzeugt, kann also nicht veralten.
            # Seit 22.09. stehen die Portal-FENSTER mit in derselben Liste
            # (Direkt Aufgaben, Dialog-Regeln). Genau daran scheiterte
            # "oeffne Direkt Aufgaben": das Modell sah den Namen hier
            # nirgends und nahm den naechstbesten aus der Liste ("Meine
            # Apps") - dieselbe Fehlerklasse wie das Beispiel-Thema "Auto"
            # am 31.08. Ein Name, den das Modell nicht liest, existiert
            # fuer es nicht, egal wie gut das Werkzeug dahinter ihn findet.
            namen = ", ".join(sorted({a for a, _e in PORTAL_BEREICHE.values()}
                                     | set(PORTAL_FENSTER.values())))
            teile.append(
                "Das sind ALLE vorhandenen Portal-Bereiche und -Fenster: " + namen + ". "
                "Nennt Klaus einen davon, ist dieses Werkzeug gemeint - auch "
                "ohne das Wort \"Fenster\" davor. Nimm den Namen, den KLAUS "
                "gesagt hat, und nie einen anderen aus dieser Liste, nur weil "
                "er dir bekannter vorkommt.")
    return "\n".join(teile), treffer
