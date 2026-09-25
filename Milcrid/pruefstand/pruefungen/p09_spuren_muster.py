"""
Millok-Spuren: Erkennen von Unsicherheit, Bestaetigung, Ablehnung

spuren_verwaltung.py entscheidet anhand von Textmustern, ob aus einem
Gespraechsmoment ein Trainingsdatensatz wird. Zwei Fehlerarten sind moeglich,
und sie sind NICHT gleich schlimm:

  - etwas verpassen        -> ein Fall geht verloren, sonst nichts
  - etwas falsch erkennen  -> FALSCHE Trainingsdaten, die das Modell
                              spaeter in die falsche Richtung ziehen

Deshalb steht im Modul selbst: "lieber einen echten Fall verpassen als einen
falschen Trainingsdatensatz erzeugen". Diese Pruefung testet genau das mit
echten deutschen Formulierungen - inklusive der Faelle, an denen ein
frueherer Entwurf laut Kommentar schon einmal gescheitert ist
(Fuellwoerter dazwischen, Verb am Satzende).
"""
import importlib.util

# (Text, soll_erkannt_werden)
UNSICHER = [
    # Klaus' echter "Uhr"-Fall und Varianten davon
    ("Ich habe die Uhr geschlossen. Bin mir aber nicht sicher, ob das richtig war.", True),
    ("Bin mir nicht sicher, ob du das gemeint hast.", True),
    ("Ich bin nicht ganz sicher.", True),
    ("Ich bin unsicher, welches Fenster du meinst.", True),
    ("War das so richtig?", True),
    ("Habe ich das richtig verstanden?", True),
    ("Falls das falsch war, sag Bescheid.", True),
    ("Ich weiß nicht, ob das stimmt.", True),
    ("Korrigiere mich, wenn ich falsch liege.", True),
    ("Mir ist nicht ganz klar, ob du den Rechner meinst.", True),
    # Das Gegenteil - darf NICHT als Unsicherheit gelten
    ("Ich habe die Uhr geschlossen.", False),
    ("Erledigt.", False),
    ("Ich habe alles richtig verstanden und erledigt.", False),
    ("Das Fenster ist jetzt zu.", False),
    ("Die Datei wurde korrekt gespeichert.", False),
]

BESTAETIGUNG = [
    ("ja", True), ("Ja, genau", True), ("genau", True), ("stimmt", True),
    ("Richtig", True), ("passt", True), ("Ja, aber die Uhr auch noch", True),
    ("nein", False), ("Nein, das meinte ich nicht", False),
    ("mach mal das Fenster zu", False), ("", False),
]

ABLEHNUNG = [
    ("nein", True), ("Nein, das meinte ich nicht", True),
    ("falsch", True), ("Doch nicht, lass es", True),
    ("ja", False), ("genau", False), ("mach weiter", False), ("", False),
]

# "Chat speichern" - der Wunsch, der main.py abfaengt, BEVOR das Modell die
# Eingabe sieht. Falsch-negativ heisst hier NICHT nur "ein Fall geht
# verloren": die Eingabe geht dann ans Modell, und das griff nachweislich zum
# naechstbesten Werkzeug aus dem Prompt (systemcheck, write_file). Deshalb
# stehen alle fuenf echten Fehlschlaege vom 08.09. als Pflichtfaelle drin.
# Falsch-positiv ist trotzdem schlimmer: dann wird mitten im Gespraech
# gespeichert UND der Verlauf geleert.
CHAT_SPEICHERN = [
    # ZUSAMMENGESCHRIEBEN - so kam es am 09.09. um 00:40 wirklich an, und
    # genau daran ist die erste Fassung gescheitert: EIN Wort, also kein
    # "speicher" am Anfang und kein "chat" darin. Das Modell legte danach
    # eine test.txt an, weil es den Beispielwert von write_file abschrieb.
    ("Schatzspeichern", True),
    ("Chatspeichern", True),
    ("speicherchat", True),
    # ... und die Nachbarn, die dabei NICHT durchkommen duerfen. Die ersten
    # beiden sind echt: so hat Whisper Klaus in derselben Minute verstanden.
    ("Schweisserscheid", False),
    ("schmerzschatten", False),
    ("Schattenseite", False),
    ("Schatzkiste", False),
    ("Speicherplatz", False),
    ("speicherkarte", False),
    # die fuenf echten Verhoerer vom 08.09. (Whisper aus "Chat")
    ("Schatt speichern", True),
    ("Schatz, Speichern", True),
    ("Shut, Speichern", True),
    ("Speicher, Shut", True),
    ("speichere den Shad", True),
    # was getippt schon immer ging - darf nicht kaputtgehen
    ("speicher den chat", True),
    ("speichere den chat", True),
    ("speicher chat", True),
    ("Chat speichern", True),
    ("speicher bitte mal den chat", True),
    ("computer speicher den chat", True),
    ("speicher das gespräch", True),
    # Gegenprobe - muss draussen bleiben
    ("speichere den systemcheck als textdatei txt in deiner sandbox", False),
    ("speicher die datei", False),
    ("wie speichere ich den chat?", False),
    ("kannst du den chat speichern oder nicht?", False),
    ("schließe das schattenfenster", False),
    ("speicher den chat in downloads als pdf", False),
    ("schatz", False),
    ("speichern", False),
    ("öffne den chat", False),
    ("wie viel speicherplatz ist noch frei", False),
    ("", False),
]


def pruefe(ctx):
    quelle = ctx.milcrid / "spuren_verwaltung.py"
    if not quelle.exists():
        return [ctx.hinweis("spuren_verwaltung.py nicht gefunden", "")]

    spec = importlib.util.spec_from_file_location("spuren_test", quelle)
    sv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sv)

    befunde = []
    geprueft = 0

    for text, soll in UNSICHER:
        geprueft += 1
        ist = sv.unsicherheit(text) is not None
        if ist == soll:
            continue
        if soll:
            befunde.append(ctx.hinweis(
                f"Unsicherheit NICHT erkannt: \"{text}\"",
                "Dieser Moment wuerde nicht als Trainingsdatensatz festgehalten "
                "(Verlust, kein Schaden).",
            ))
        else:
            befunde.append(ctx.fehler(
                f"Unsicherheit FAELSCHLICH erkannt: \"{text}\"",
                "Eine selbstbewusste Antwort wird als Zoegern gewertet - daraus "
                "entstehen falsche Trainingsdaten. Das Modul will ausdruecklich "
                "lieber etwas verpassen als etwas Falsches aufzeichnen.",
            ))

    for text, soll in BESTAETIGUNG:
        geprueft += 1
        ist = sv.ist_bestaetigung(text)
        if ist != soll:
            art = ctx.fehler if not soll else ctx.hinweis
            befunde.append(art(
                f"ist_bestaetigung(\"{text}\") = {ist}, erwartet {soll}",
                "Falsch-positiv erzeugt einen falschen Trainingsdatensatz."
                if not soll else "Ein echter Fall geht verloren.",
            ))

    for text, soll in ABLEHNUNG:
        geprueft += 1
        ist = sv.ist_ablehnung(text)
        if ist != soll:
            art = ctx.fehler if not soll else ctx.hinweis
            befunde.append(art(
                f"ist_ablehnung(\"{text}\") = {ist}, erwartet {soll}", ""))

    for text, soll in CHAT_SPEICHERN:
        geprueft += 1
        ist = sv.ist_chat_speichern(text)
        if ist != soll:
            befunde.append(ctx.fehler(
                f"ist_chat_speichern(\"{text}\") = {ist}, erwartet {soll}",
                "Nicht erkannt: die Eingabe geht ans Modell, das dann zum "
                "naechstbesten Werkzeug greift (belegt: systemcheck, write_file)."
                if soll else
                "Faelschlich erkannt: es wird mitten im Gespraech gespeichert "
                "UND der Verlauf geleert.",
            ))

    ctx.zaehle("Spuren-Muster", geprueft=geprueft)
    return befunde
