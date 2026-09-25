# analyze_url.py
# Werkzeug fuer Milcrid: liest eine URL und ANALYSIERT auch sehr lange Texte
# (AGB, Datenschutz, lange Artikel), die read_url sonst am 12000-Zeichen-Deckel
# abschneidet und die ihr Kontextfenster sprengen wuerden.
#
# Der Trick ist derselbe wie bei systemcheck: Der volle Text trifft NIE Milcrids
# Fenster. Ablauf:
#   1. url_scraper.volltext_holen(url)   -> voller Artikeltext (ungekuerzt)
#   2. In Stuecke zerlegen (an Zeilen-/Absatzgrenzen, nichts reisst mittendrin)
#   3. JEDES Stueck einzeln in einer weggeworfenen Mini-Unterhaltung zusammenfassen
#   4. Die Teil-Zusammenfassungen zu EINER Analyse zusammenfuehren
#   5. Nur diese Analyse kommt zurueck
#
# Kostet mehrere Modell-Laeufe (einer pro Stueck + Zusammenfuehrung), ist also
# nicht sofort - dafuer vollstaendig, egal wie lang der Text ist.

import ollama
import config
import url_scraper

# Modellname aus der einen Quelle - bei JEDEM Aufruf frisch aus config gelesen
# (config.MODELL), nicht als Konstante kopiert. Sonst wuerde ein Modellwechsel
# im Portal hier nicht ankommen und analyze_url weiter das alte (evtl. schon
# geloeschte) Modell anfassen.

# Zeichen pro Stueck. Klein genug, dass Stueck + Anweisung locker ins
# Kontextfenster passen (~1200 Token bei 4000 Zeichen), gross genug fuer
# moeglichst wenige Laeufe.
STUECK_ZEICHEN = 4000

# Sicherheitsdeckel: mehr Stuecke werden nicht verarbeitet (Schutz vor einem
# Riesen-Dokument, das ewig laeuft). 40 * 4000 = 160.000 Zeichen ~ dickes AGB.
MAX_STUECKE = 40

# Ab dieser Laenge (in Zeichen) passen die Teil-Zusammenfassungen nicht mehr
# sicher in EINEN Zusammenfuehr-Lauf -> dann wird mehrstufig verdichtet.
FUEHR_GRENZE = STUECK_ZEICHEN * 3

_STUECK_SYSTEM = (
    "Du bist ein sachlicher Zusammenfasser. Fasse den gezeigten Textabschnitt "
    "knapp und neutral zusammen: nur was drinsteht, keine Wertung, kein Vorwort. "
    "Nenne konkrete Punkte (Fristen, Pflichten, Rechte, Zahlen), wenn welche "
    "vorkommen."
)

_FUEHR_SYSTEM = (
    "Du fuehrst mehrere Abschnitts-Zusammenfassungen zu einer klaren "
    "Gesamt-Analyse zusammen. Sachlich, nach Themen geordnet, ohne Vorwort und "
    "ohne Wiederholungen."
)


def _stuecke_bilden(text):
    """Zerlegt den Text in Stuecke von hoechstens STUECK_ZEICHEN. Schneidet
    moeglichst an Zeilengrenzen, damit keine Saetze mittendrin reissen. Ein
    einzelner ueberlanger Absatz wird hart geteilt."""
    text = (text or "").strip()
    if not text:
        return []

    zeilen = text.split("\n")
    stuecke = []
    puffer = ""

    for zeile in zeilen:
        # Passt die Zeile noch in den Puffer? Dann anhaengen.
        if len(puffer) + len(zeile) + 1 <= STUECK_ZEICHEN:
            puffer = (puffer + "\n" + zeile) if puffer else zeile
            continue
        # Puffer ist voll -> wegschreiben.
        if puffer:
            stuecke.append(puffer)
            puffer = ""
        # Einzelne Zeile laenger als ein ganzes Stueck -> hart zerteilen.
        while len(zeile) > STUECK_ZEICHEN:
            stuecke.append(zeile[:STUECK_ZEICHEN])
            zeile = zeile[STUECK_ZEICHEN:]
        puffer = zeile

    if puffer:
        stuecke.append(puffer)

    return stuecke


def _stueck_zusammenfassen(nummer, gesamt, stueck):
    """Fasst EIN Stueck in einer eigenen, weggeworfenen Unterhaltung zusammen.
    Der Rohtext lebt nur hier drin und verschwindet danach wieder."""
    frage = f"Abschnitt {nummer} von {gesamt}. Fasse ihn sachlich zusammen:\n\n{stueck}"
    try:
        antwort = ollama.chat(
            model=config.MODELL,
            options=config.chat_optionen(),
            think=config.DENKEN_ERLAUBT,
            messages=[
                {"role": "system", "content": _STUECK_SYSTEM},
                {"role": "user", "content": frage},
            ],
        )
        return antwort["message"]["content"].strip()
    except Exception as e:
        return f"(Abschnitt {nummer} konnte nicht zusammengefasst werden: {e})"


def _einmal_fuehren(teile, frage):
    """Fuehrt eine Liste von Teil-Zusammenfassungen in EINEM Lauf zusammen."""
    verbunden = "\n\n".join(f"[{i}] {t}" for i, t in enumerate(teile, 1))
    auftrag = frage or (
        "Fasse die folgenden Abschnitts-Zusammenfassungen zu einer "
        "zusammenhaengenden Gesamt-Analyse zusammen. Ordne nach Themen, nenne "
        "konkrete Punkte, keine Wiederholungen."
    )
    inhalt = f"{auftrag}\n\nHier die Abschnitts-Zusammenfassungen:\n\n{verbunden}"
    try:
        antwort = ollama.chat(
            model=config.MODELL,
            options=config.chat_optionen(),
            think=config.DENKEN_ERLAUBT,
            messages=[
                {"role": "system", "content": _FUEHR_SYSTEM},
                {"role": "user", "content": inhalt},
            ],
        )
        return antwort["message"]["content"].strip()
    except Exception as e:
        return f"(Zusammenfuehrung fehlgeschlagen: {e})"


def _zusammenfuehren(teile, frage):
    """Fuehrt die Teil-Zusammenfassungen zu einer Analyse zusammen. Sind es zu
    viele fuer einen Lauf (ueber FUEHR_GRENZE Zeichen), werden sie zuerst in
    Gruppen vor-verdichtet und das Ergebnis erneut zusammengefuehrt. Damit
    passt auch ein sehr langes Dokument."""
    if not teile:
        return "(nichts zu analysieren)"

    verbunden_laenge = sum(len(t) for t in teile)
    if len(teile) == 1 or verbunden_laenge <= FUEHR_GRENZE:
        return _einmal_fuehren(teile, frage)

    # Zu viele -> in Gruppen vor-verdichten, dann erneut zusammenfuehren.
    gruppen = []
    aktuelle = []
    laenge = 0
    for t in teile:
        if laenge + len(t) > FUEHR_GRENZE and aktuelle:
            gruppen.append(aktuelle)
            aktuelle = []
            laenge = 0
        aktuelle.append(t)
        laenge += len(t)
    if aktuelle:
        gruppen.append(aktuelle)

    # Jede Gruppe neutral verdichten, dann die Zwischenergebnisse mit der
    # eigentlichen Frage final zusammenfuehren.
    vorverdichtet = [_einmal_fuehren(g, None) for g in gruppen]
    return _zusammenfuehren(vorverdichtet, frage)


def analyze_url(url, frage=""):
    """Werkzeug fuer Milcrid: liest eine URL und analysiert auch lange Texte
    vollstaendig, ohne das Kontextfenster zu sprengen.

    url   = die Adresse der Seite.
    frage = optional. Worauf soll die Analyse zielen? (z.B. "Kuendigungsfristen
            und Datenweitergabe"). Leer = allgemeine Zusammenfassung.
    """
    text, fehler = url_scraper.volltext_holen(url)
    if fehler:
        return f"[analyze_url] Konnte '{url}' nicht lesen: {fehler}"
    if not text:
        return f"[analyze_url] Kein Text auf '{url}' gefunden."

    stuecke = _stuecke_bilden(text)
    if not stuecke:
        return f"[analyze_url] Kein verwertbarer Text auf '{url}'."

    gekuerzt = False
    if len(stuecke) > MAX_STUECKE:
        stuecke = stuecke[:MAX_STUECKE]
        gekuerzt = True

    teile = [
        _stueck_zusammenfassen(i, len(stuecke), s)
        for i, s in enumerate(stuecke, 1)
    ]

    analyse = _zusammenfuehren(teile, (frage or "").strip() or None)

    kopf = (f"[analyze_url] '{url}' - {len(text)} Zeichen in {len(stuecke)} "
            f"Abschnitt(en) analysiert.")
    if gekuerzt:
        kopf += (f" ACHTUNG: Text sehr lang, nur die ersten {MAX_STUECKE} "
                 f"Abschnitte ausgewertet.")

    return kopf + "\n\n" + analyse


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        f = sys.argv[2] if len(sys.argv) > 2 else ""
        print(analyze_url(sys.argv[1], f))
    else:
        print("Aufruf: python analyze_url.py <URL> [frage]")
