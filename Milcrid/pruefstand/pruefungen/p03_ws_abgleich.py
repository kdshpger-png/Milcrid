"""
WebSocket-Abgleich: Portal  <->  main.py

Beide Seiten reden ueber Nachrichten mit einem "typ"-Feld. Faellt auf einer
Seite ein Sender oder ein Empfaenger weg, merkt das NIEMAND:

  - kein Syntaxfehler
  - keine Fehlermeldung im Log
  - die Funktion bleibt einfach still stehen

Genau so ist Fund M-2 im Opus-Check vom 2026-08-27 entstanden: beim
Agenten-Rueckbau wurde ein 151-Zeilen-Block am Stueck geloescht, in dem
zwischen den Agenten-Handlern auch der fremde Empfaenger fuer
'direktaufgaben_antwort' lag. Die Direkt-Aufgaben-Liste blieb danach fuer
immer leer, ohne jeden Hinweis. Der ID-Pruefer konnte das nicht finden -
es fehlte kein Element, es fehlte ein Empfaenger.

Vier Richtungen werden geprueft:
  1. Portal sendet  -> main.py behandelt nicht        [FEHLER] Aktion passiert nie
  2. main.py antwortet -> Portal empfaengt nicht      [FEHLER] Antwort verpufft (M-2!)
  3. main.py behandelt -> Portal sendet nie           [Hinweis] Leiche
  4. Portal empfaengt  -> main.py sendet nie          [Hinweis] Leiche
"""
import io
import re
import tokenize


def _ohne_kommentare(quelltext):
    """Python-Kommentare entfernen - sonst zaehlen Beispiele in der Kopf-
    Dokumentation als echte Nachrichten mit.

    (Gefunden beim ersten Lauf dieses Pruefers: main.py erklaert oben im
    Kommentar das Protokoll mit {"typ":"frage"} / {"typ":"token"} - der
    Pruefer meldete daraufhin 'frage' als angeblich unbeantwortete Nachricht.
    Ein Pruefer, der Fehlalarm schlaegt, ist schlimmer als keiner.)"""
    try:
        stuecke = []
        for tok in tokenize.generate_tokens(io.StringIO(quelltext).readline):
            if tok.type == tokenize.COMMENT:
                continue
            stuecke.append(tok.string)
        return "\n".join(stuecke)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # Notfalls die grobe Variante (Zeilen, die mit # beginnen)
        return "\n".join(z for z in quelltext.splitlines()
                         if not z.lstrip().startswith("#"))


def pruefe(ctx):
    portal = ctx.portal_js
    mainpy = _ohne_kommentare(ctx.main_py)
    befunde = []

    # ---------------------------------------------------------- Portal: senden
    # a) direkt:  ws.send(JSON.stringify({ typ: 'x' ...
    portal_sendet = set(re.findall(
        r"ws\.send\(JSON\.stringify\(\{\s*typ\s*:\s*['\"]([a-z_]+)['\"]", portal))
    # b) ueber die Sammel-Helfer. Es gibt zwei Schreibweisen im Portal:
    #    grossgeschrieben (gedaechtnisSenden, mfSenden, kiTestSenden, ...) und
    #    KLEIN geschrieben: der Datei Manager hat eine eigene lokale
    #    senden(typ, extra) je Fenster-Instanz. Ohne das kleine "s" meldete
    #    der Pruefer beim ersten Lauf alle sieben dm_*-Handler faelschlich
    #    als tot (dritter Fehlalarm) - deshalb hier ausdruecklich beides.
    portal_sendet |= set(re.findall(r"\b\w*[Ss]enden\(\s*['\"]([a-z_]+)['\"]", portal))
    # c) Ueber eine Zwischen-Variable:
    #       const nachricht = { typ: 'theme_speichern', modus };
    #       if (...) nachricht.hue = hue;          <- deshalb die Variable
    #       ws.send(JSON.stringify(nachricht));
    #    Ohne diesen Fall meldete der Pruefer 'theme_speichern' faelschlich
    #    als nie gesendet (vierter Fehlalarm beim Aufbau).
    #
    #    WICHTIG - nicht einfach ALLE "typ: '...'" einsammeln: das Portal
    #    benutzt denselben Schluesselnamen auch fuer eigene Daten, die nie
    #    ueber die Leitung gehen (typ: 'linux' / 'datei' / 'link' /
    #    'schreibtisch' / 'milcrid' in apps.json-Eintraegen). Die wuerden
    #    sonst als "Portal sendet, main.py behandelt nicht" gemeldet - also
    #    genau derselbe Fehlalarm nur in der anderen Richtung.
    for var in set(re.findall(r"ws\.send\(JSON\.stringify\(\s*(\w+)\s*\)", portal)):
        for m in re.finditer(
            rf"(?:const|let|var)\s+{re.escape(var)}\s*=\s*\{{[^}}]*?typ\s*:\s*['\"]([a-z_]+)['\"]",
            portal,
        ):
            portal_sendet.add(m.group(1))

    # ------------------------------------------------------- Portal: empfangen
    portal_empfaengt = set(re.findall(r"m\.typ\s*===\s*['\"]([a-z_]+)['\"]", portal))
    # switch/case-Form, falls irgendwo genutzt
    portal_empfaengt |= set(re.findall(r"case\s+['\"]([a-z_]+)['\"]\s*:", portal))
    # in Listen geprueft:  ['a','b'].includes(m.typ)
    for liste in re.findall(r"\[([^\]]*)\]\s*\.includes\(\s*m\.typ\s*\)", portal):
        portal_empfaengt |= set(re.findall(r"['\"]([a-z_]+)['\"]", liste))

    # ---------------------------------------------------------- main.py: lesen
    main_behandelt = set(re.findall(r"typ\s*==\s*['\"]([a-z_]+)['\"]", mainpy))
    # typ in ("a", "b")  -> Mehrfachpruefung
    for gruppe in re.findall(r"typ\s+in\s+\(([^)]*)\)", mainpy):
        main_behandelt |= set(re.findall(r"['\"]([a-z_]+)['\"]", gruppe))
    # Verneinte Form:  if typ != "frage": continue   -> danach wird GENAU
    # dieser Typ verarbeitet. Ohne diese Zeile meldete der Pruefer 'frage'
    # faelschlich als unbehandelt (zweiter Fehlalarm beim ersten Lauf).
    main_behandelt |= set(re.findall(r"typ\s*!=\s*['\"]([a-z_]+)['\"]", mainpy))
    # startswith-Praefixe merken (z.B. alle "gedaechtnis_"-Nachrichten in einem Block)
    main_praefixe = set(re.findall(r"typ\.startswith\(\s*['\"]([a-z_]+)['\"]", mainpy))

    main_antwortet = set(re.findall(r"['\"]typ['\"]\s*:\s*['\"]([a-z_]+)['\"]", mainpy))

    def von_praefix_gedeckt(name):
        return any(name.startswith(p) for p in main_praefixe)

    # ------------------------------------- 1. Portal sendet, main.py hoert nicht
    for typ in sorted(portal_sendet):
        if typ not in main_behandelt and not von_praefix_gedeckt(typ):
            zeilen = ctx.portal_zeilen(f"'{typ}'")
            befunde.append(ctx.fehler(
                f"Portal sendet '{typ}', main.py behandelt das nicht",
                f"Die Aktion passiert nie - ohne Fehlermeldung. Zeile(n): {zeilen}",
            ))

    # ---------------------------- 2. main.py antwortet, Portal empfaengt nicht
    # Bewusst ohne Portal-Empfaenger (Systemcheck 24.09.2026): diese Antworten
    # gehen an die Testwerkzeuge auf der Zentrale (ki-pruefstand/sprech_lauf.py,
    # modelltest.py) oder sind eine Quittung, die niemand braucht. Vorher standen
    # sie acht Tage als "4 FEHLER" da - ein fuenfter echter waere kaum aufgefallen.
    # Neuer Eintrag hier nur mit Grund; sonst ist es ein echter Fehler.
    OHNE_PORTAL_EMPFAENGER = {
        "testaudio_fertig": "Testwerkzeug sprech_lauf.py",
        "testeingabe_fertig": "Testwerkzeuge sprech_lauf.py, modelltest.py",
        "urteil_antwort": "Quittung auf den Daumen - Portal schickt ab und wartet nicht",
    }
    for typ in sorted(main_antwortet):
        if typ not in portal_empfaengt and typ not in OHNE_PORTAL_EMPFAENGER:
            befunde.append(ctx.fehler(
                f"main.py sendet '{typ}', das Portal hat dafuer keinen Empfaenger",
                "Die Antwort kommt an und verpufft - Anzeige bleibt leer/veraltet. "
                "Genau die Bauart von Fund M-2 (2026-08-27).",
            ))

    # ------------------------------- 3. main.py behandelt, Portal sendet nie
    for typ in sorted(main_behandelt):
        if typ not in portal_sendet:
            befunde.append(ctx.hinweis(
                f"main.py behandelt '{typ}', das Portal sendet es nirgends",
                "Toter Handler (Leiche aus einem Rueckbau) - oder nur von der KI genutzt.",
            ))

    # ------------------------------- 4. Portal empfaengt, main.py sendet nie
    for typ in sorted(portal_empfaengt):
        if typ not in main_antwortet:
            befunde.append(ctx.hinweis(
                f"Portal empfaengt '{typ}', main.py sendet das nirgends",
                "Toter Empfaenger - oder die Nachricht kommt aus einer anderen Quelle.",
            ))

    ctx.zaehle(
        "WebSocket-Typen",
        portal_sendet=len(portal_sendet),
        portal_empfaengt=len(portal_empfaengt),
        main_behandelt=len(main_behandelt),
        main_antwortet=len(main_antwortet),
    )
    return befunde
