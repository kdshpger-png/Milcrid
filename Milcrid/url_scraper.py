# url_scraper.py
# Holt eine Webseite und gibt Milcrid FAKTEN zurueck - nicht nur eine Deutung.
#
# Regel: Das Skript beobachtet. Milcrid interpretiert.
#
# ABLAUF:
#   1. requests holt die Seite   -> HTTP-Status + rohes HTML + Laenge
#   2. trafilatura extrahiert ZWEIMAL (streng + grosszuegig)
#   3. Fallback                  -> sichtbarer Seitentext, falls trafilatura
#                                   aussteigt (passiert oefter als gedacht)
#   4. Aufraeumen                -> Navigation weg, alles nach dem Artikel weg
#   5. Bericht                   -> Zahlen, Methode, Inhalt
#
# INSTALLATION:
#     pip install requests trafilatura

import re
import html as html_entities

try:
    import requests
except ImportError:
    requests = None

try:
    import trafilatura
except ImportError:
    trafilatura = None


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TIMEOUT = 20           # Sekunden bis Abbruch
MAX_ZEICHEN = 12000    # Obergrenze fuer den zurueckgegebenen Text


# Ab hier ist der Artikel VORBEI. Alles danach fliegt raus.
#
# WARUM DAS WICHTIG IST:
#   Beim Test schleppte der Fallback zehn Leserkommentare mit. Einer davon
#   widersprach dem Autor scharf. Milcrid haette das fuer einen Teil des
#   Artikels gehalten und einen Widerspruch "gefunden", den der Autor nie
#   geschrieben hat.
#   Fehlender Text macht eine Analyse duenn. FREMDER Text macht sie FALSCH.
ARTIKEL_ENDE = (
    "kommentare (",
    "kommentar schreiben",
    "wenn ihnen unser artikel gefallen hat",
    "unterstützen sie diese form",
    "ähnliche artikel",
    "das könnte sie auch interessieren",
    "mehr zum thema",
    "inline feedbacks",
    "alle kommentare ansehen",
    "bitte loggen sie sich ein",
)


def _ist_navigation(zeile):
    """Erkennt Menue-Eintraege, Buttons und Werbezeilen.

    Trick: Ein echter Absatz ist LANG und hat Satzzeichen.
    Ein Menue-Eintrag ist KURZ und hat keine."""
    z = zeile.strip()

    if not z:
        return True

    # Sehr lange Zeilen sind immer Text, nie Menue.
    if len(z) > 160:
        return False

    # Kurze Zeile ohne Satzende -> hoechstwahrscheinlich Navigation.
    if len(z) < 60 and not z.endswith((".", "!", "?", "“", '"', ":")):
        return True

    muell = (
        "facebook", "twitter", "linkedin", "xing", "email", "print",
        "skip to content", "suche nach", "anmelden", "menü", "menue",
        "abo", "shop", "podcast", "newsletter", "cookie", "anzeige",
        "unterstützen sie uns", "ich unterstütze", "wir danken unseren lesern",
        "paypal", "kreditkarte", "lastschrift", "überweisung",
    )
    klein = z.lower()
    if any(m in klein for m in muell):
        return True

    return False


def _nach_artikel_abschneiden(text):
    """Schneidet alles ab, was NACH dem Artikel kommt:
    Kommentare, Spendenformular, Login-Maske, verwandte Artikel."""
    if not text:
        return ""

    zeilen = text.split("\n")
    for i, z in enumerate(zeilen):
        klein = z.strip().lower()
        if any(marke in klein for marke in ARTIKEL_ENDE):
            return "\n".join(zeilen[:i]).strip()
    return text.strip()


def _aufraeumen(text):
    """Erst hinten abschneiden, dann Navigation rauswerfen."""
    text = _nach_artikel_abschneiden(text)
    if not text:
        return ""
    zeilen = [z for z in text.split("\n") if not _ist_navigation(z)]
    return "\n".join(zeilen).strip()


def _sichtbarer_text(roh_html):
    """Zieht stumpf den sichtbaren Text aus dem HTML.
    Kein Artikel-Erkenner - genau deshalb funktioniert es auch dort,
    wo trafilatura komplett aussteigt."""
    if not roh_html:
        return ""

    t = roh_html
    t = re.sub(r"(?is)<(script|style|noscript|template|svg)[^>]*>.*?</\1>", " ", t)
    t = re.sub(r"(?s)<!--.*?-->", " ", t)
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = re.sub(r"(?i)</(p|div|li|h[1-6]|tr|td|section|article|header|footer)>", "\n", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = html_entities.unescape(t)
    t = re.sub(r"[ \t\r\f\v]+", " ", t)

    zeilen = [z.strip() for z in t.split("\n")]
    zeilen = [z for z in zeilen if z]
    return "\n".join(zeilen).strip()


def _extrahieren(roh_html, grosszuegig):
    """Ein trafilatura-Lauf. grosszuegig=True behaelt im Zweifel mehr."""
    if trafilatura is None or not roh_html:
        return ""
    try:
        return (trafilatura.extract(
            roh_html,
            include_comments=False,
            include_tables=False,
            favor_recall=grosszuegig,
        ) or "").strip()
    except Exception:
        return ""


def _bester_text(roh_html):
    """Erzeugt drei Kandidaten (trafilatura streng/grosszuegig + Fallback) und
    gibt den laengsten zurueck. trafilatura ist nicht verlaesslich (mal 5.100
    Zeichen, mal null bei derselben URL), darum laeuft der Fallback IMMER mit.

    Rueckgabe: (inhalt, methode, laenge_streng, laenge_grob, laenge_fallback).
    Genau diese Logik nutzen read_url UND volltext_holen - eine Quelle."""
    streng = _aufraeumen(_extrahieren(roh_html, grosszuegig=False))
    grob = _aufraeumen(_extrahieren(roh_html, grosszuegig=True))
    fallback = _aufraeumen(_sichtbarer_text(roh_html))

    kandidaten = [
        (len(streng), streng, "trafilatura streng"),
        (len(grob), grob, "trafilatura grosszuegig"),
        (len(fallback), fallback, "Fallback (Seitentext)"),
    ]
    laenge, inhalt, methode = max(kandidaten, key=lambda k: k[0])
    if laenge == 0:
        inhalt, methode = "", "nichts gefunden"

    return inhalt, methode, len(streng), len(grob), len(fallback)


def volltext_holen(url):
    """Wie read_url, aber gibt den VOLLEN, ungekuerzten Artikeltext zurueck -
    ohne den 12000-Zeichen-Deckel und ohne den Bericht-Rahmen. Gedacht fuer
    analyze_url, das lange Texte selbst in Stuecke zerlegt.

    Rueckgabe: (text, fehler)
      text   = Artikeltext als String (leer, wenn nichts gefunden)
      fehler = None, oder eine kurze Fehlermeldung als String
    """
    if requests is None:
        return "", "Paket fehlt: pip install requests trafilatura"

    url = (url or "").strip()
    if not url:
        return "", "Keine Adresse angegeben."
    if not (url.startswith("http://") or url.startswith("https://")):
        return "", "Nur http:// oder https:// erlaubt."

    try:
        antwort = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.Timeout:
        return "", f"Zeitueberschreitung nach {TIMEOUT} Sekunden."
    except requests.RequestException as e:
        return "", f"keine Verbindung ({type(e).__name__})."

    if not antwort.encoding or antwort.encoding.lower() == "iso-8859-1":
        antwort.encoding = antwort.apparent_encoding or "utf-8"

    roh_html = antwort.text or ""
    inhalt, methode, *_ = _bester_text(roh_html)

    if not inhalt:
        return "", (f"Kein lesbarer Text gefunden (HTTP {antwort.status_code}, "
                    f"{len(roh_html)} Zeichen HTML - evtl. JavaScript-Seite oder "
                    f"Bot-Schutz).")
    return inhalt, None


def read_url(url):
    """Laedt eine URL und gibt einen Bericht mit gemessenen Fakten + Inhalt."""

    if requests is None:
        return "[URL] Paket fehlt. Bitte installieren: pip install requests"

    url = (url or "").strip()
    if not url:
        return "[URL] Keine Adresse angegeben."

    if not (url.startswith("http://") or url.startswith("https://")):
        return "[URL abgelehnt] Nur http:// oder https:// erlaubt."

    # --- 1. Seite holen ---------------------------------------------------
    try:
        antwort = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.Timeout:
        return (f"[URL-BERICHT]\n"
                f"Adresse : {url}\n"
                f"Status  : keine Antwort\n"
                f"Ergebnis: Zeitueberschreitung nach {TIMEOUT} Sekunden.")
    except requests.RequestException as e:
        return (f"[URL-BERICHT]\n"
                f"Adresse : {url}\n"
                f"Status  : keine Verbindung\n"
                f"Fehler  : {type(e).__name__}: {e}")

    if not antwort.encoding or antwort.encoding.lower() == "iso-8859-1":
        antwort.encoding = antwort.apparent_encoding or "utf-8"

    status = antwort.status_code
    roh_html = antwort.text or ""
    html_laenge = len(roh_html)
    ziel_url = antwort.url

    # --- 2./3. Bester Text aus drei Kandidaten (laengster gewinnt) --------
    # Ausgelagert nach _bester_text, damit volltext_holen() fuer analyze_url
    # exakt dieselbe Logik nutzt - eine Quelle, kein Auseinanderlaufen.
    inhalt, methode, l_streng, l_grob, l_fallback = _bester_text(roh_html)

    gekuerzt = False
    if len(inhalt) > MAX_ZEICHEN:
        inhalt = inhalt[:MAX_ZEICHEN].rstrip()
        gekuerzt = True

    # --- 4. Bericht bauen --------------------------------------------------
    zeilen = ["[URL-BERICHT]", f"Adresse  : {url}"]

    if ziel_url != url:
        zeilen.append(f"Umleitung: {ziel_url}")

    zeilen += [
        f"Status   : HTTP {status}",
        f"HTML     : {html_laenge} Zeichen empfangen",
        f"Streng   : {l_streng} Zeichen",
        f"Grob     : {l_grob} Zeichen",
        f"Fallback : {l_fallback} Zeichen",
        f"Benutzt  : {methode}",
    ]

    if gekuerzt:
        zeilen.append(f"ACHTUNG  : Bei {MAX_ZEICHEN} Zeichen ABGESCHNITTEN. "
                      f"Das Ende des Artikels fehlt.")

    zeilen += [
        "",
        "DEUTUNG NUR ANHAND DIESER ZAHLEN - nichts dazuerfinden:",
        "  Status 403 / 429 ............ Bot-Schutz blockt.",
        "  Wenig Text bei viel HTML .... Seite laedt per JavaScript nach.",
        "  Alle drei 0 bei viel HTML ... Seite hat keinen Artikel",
        "                                (z.B. Startseite). KEIN Blocken.",
        "",
        "--- INHALT ---",
        inhalt if inhalt else "(leer)",
    ]

    return "\n".join(zeilen)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(read_url(sys.argv[1]))
    else:
        print("Aufruf: python url_scraper.py <URL>")
