# duckduckgo_search.py
# Web-Suche fuer Milcrid ueber DuckDuckGo.
#
# WICHTIG: Das alte PyPI-Paket "duckduckgo_search" wurde in "ddgs"
# umbenannt. Auf deinem Rechner installieren mit:
#
#     pip install ddgs
#
# Der Import ist abgesichert: Fehlt das Paket, stuerzt NICHT die ganze
# Bruecke ab - die Suche meldet stattdessen sauber, dass sie fehlt.

try:
    from ddgs import DDGS
    _IMPORT_FEHLER = None
except ImportError as e:
    DDGS = None
    _IMPORT_FEHLER = e


def web_search(query, max_results=5):
    """Sucht im Web und gibt das Ergebnis als lesbaren Text zurueck.

    Das Ergebnis ist bewusst ein String, damit Milcrid ihn direkt
    weiterlesen und in ihrer Antwort verwenden kann.
    """
    if DDGS is None:
        return ("[Suche nicht verfuegbar] Paket fehlt. "
                "Bitte installieren mit: pip install ddgs")

    query = (query or "").strip()
    if not query:
        return "[Suche] Kein Suchbegriff angegeben."

    # max_results robust in eine sinnvolle Zahl wandeln (1 bis 10).
    try:
        anzahl = int(max_results)
    except (TypeError, ValueError):
        anzahl = 5
    anzahl = max(1, min(anzahl, 10))

    try:
        with DDGS() as ddgs:
            treffer = ddgs.text(query, region="de-de", max_results=anzahl)
    except Exception as e:
        # Netzfehler, Zeitueberschreitung, Rate-Limit usw. abfangen,
        # damit der Chat nicht abstuerzt.
        return f"[Suche fehlgeschlagen] {e}"

    if not treffer:
        return f"[Suche] Keine Ergebnisse fuer '{query}'."

    zeilen = [f"Suchergebnisse fuer '{query}':", ""]
    for i, t in enumerate(treffer, start=1):
        titel = (t.get("title") or "Ohne Titel").strip()
        link = (t.get("href") or t.get("url") or "").strip()
        text = (t.get("body") or t.get("content") or "").strip()
        zeilen.append(f"{i}. {titel}")
        if link:
            zeilen.append(f"   Quelle: {link}")
        if text:
            zeilen.append(f"   {text}")
        zeilen.append("")

    return "\n".join(zeilen).rstrip()


def nachrichten_suche(query, max_results=10, zeitraum=None, seiten=None):
    """Echte NACHRICHTEN-Suche (fuer das Agenten-System C26).

    Unterschied zu web_search: nutzt die Nachrichten-Suche von DuckDuckGo -
    die liefert Datum und Quelle mit, was fuer Recherche der halbe Wert ist.
    Kann die installierte Fassung das nicht, faellt sie sauber auf die
    normale Websuche zurueck statt einen Fehler zu werfen.

    zeitraum: 'd' (Tag), 'w' (Woche), 'm' (Monat), 'y' (Jahr) - gibt es bei
              DuckDuckGo nur in diesen Stufen, nicht tagegenau.
    seiten:   Liste von Adressen/Domains - dann wird NUR dort gesucht.
    """
    if DDGS is None:
        return ("[Suche nicht verfuegbar] Paket fehlt. "
                "Bitte installieren mit: pip install ddgs")

    query = (query or "").strip()
    if not query:
        return "[Suche] Kein Thema angegeben."

    # Auf bestimmte Quellen einschraenken: "site:" versteht die Suche selbst.
    quellen_text = ""
    if seiten:
        teile = []
        for eintrag in seiten:
            domain = (eintrag or "").strip()
            if not domain:
                continue
            # Aus "https://www.spiegel.de/politik" wird "spiegel.de".
            domain = domain.split("//")[-1].split("/")[0]
            if domain.startswith("www."):
                domain = domain[4:]
            if domain:
                teile.append(f"site:{domain}")
        if teile:
            query = f"{query} ({' OR '.join(teile)})"
            quellen_text = " (nur von: " + ", ".join(t[5:] for t in teile) + ")"

    try:
        anzahl = int(max_results)
    except (TypeError, ValueError):
        anzahl = 10
    anzahl = max(1, min(anzahl, 50))

    treffer = []
    fehler = None
    try:
        with DDGS() as ddgs:
            try:
                if seiten:
                    # Mit "site:"-Einschraenkung liefert die Nachrichten-Suche
                    # oft irgendwelche Artikel der Seite statt der zum Thema
                    # (am 13.08.2026 nachgemessen: Suche nach "Künstliche
                    # Intelligenz" auf spiegel.de/zeit.de brachte Politik-
                    # Meldungen). Die normale Websuche nimmt "site:" ernst -
                    # dafuer fehlen dort Datum/Quelle, das ist der Tausch.
                    treffer = ddgs.text(query, region="de-de", timelimit=zeitraum,
                                        max_results=anzahl)
                else:
                    treffer = ddgs.news(query, region="de-de", timelimit=zeitraum,
                                        max_results=anzahl)
            except (AttributeError, TypeError):
                # Aeltere/andere Fassung ohne news() oder ohne timelimit -
                # dann eben die normale Websuche.
                try:
                    treffer = ddgs.text(query, region="de-de", timelimit=zeitraum,
                                        max_results=anzahl)
                except TypeError:
                    treffer = ddgs.text(query, region="de-de", max_results=anzahl)
    except Exception as e:
        fehler = e

    if fehler:
        return f"[Nachrichtensuche fehlgeschlagen] {fehler}"
    if not treffer:
        return f"[Nachrichtensuche] Keine Treffer fuer '{query}'."

    zeilen = [f"Nachrichten zu '{query}'{quellen_text} - {len(treffer)} Treffer:", ""]
    for i, t in enumerate(treffer, start=1):
        titel = (t.get("title") or "Ohne Titel").strip()
        link = (t.get("url") or t.get("href") or "").strip()
        quelle = (t.get("source") or "").strip()
        datum = (t.get("date") or "").strip()
        text = (t.get("body") or t.get("excerpt") or "").strip()
        kopf = f"{i}. {titel}"
        if datum or quelle:
            kopf += f"   [{' | '.join(x for x in (datum, quelle) if x)}]"
        zeilen.append(kopf)
        if link:
            zeilen.append(f"   Quelle: {link}")
        if text:
            zeilen.append(f"   {text}")
        zeilen.append("")

    return "\n".join(zeilen).rstrip()


if __name__ == "__main__":
    # Direkttest - laeuft nur, wenn DuckDuckGo erreichbar ist.
    print(web_search("aktuelle Nachrichten Deutschland", max_results=3))
