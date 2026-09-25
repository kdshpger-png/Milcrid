# Milcrid-Prüfstand

Ein Testprogramm, das Milcrid als **Ganzes** prüft – nicht einzelne Dateien,
sondern vor allem das Zusammenspiel der vier Teile:

```
milcrid_portal.html      Oberfläche        ~10.600 Zeilen
main.py                  Python-Backend     ~1.450 Zeilen
Milcrid-App/main.js      Systemzugriff      ~2.100 Zeilen
Milcrid-App/preload.js   Brücke dazwischen     ~50 Zeilen
```

## Warum es das gibt

Die gefährlichsten Fehler in Milcrid waren nie Syntaxfehler – die fallen
sofort auf. Es waren immer **stille** Fehler, bei denen jede einzelne Datei
für sich fehlerfrei war und nur das Dazwischen kaputt:

| Fund | Was passierte | Wie lange unbemerkt |
|---|---|---|
| M-2 | Ein Empfänger wurde beim Aufräumen mitgelöscht → Direkt-Aufgaben-Liste blieb für immer leer | Tage |
| M-3 | Dialog lag hinter dem Fenster, das ihn öffnet → „Profil erstellen" unbedienbar | Wochen |
| M-6 | Ein Zähler ohne Deckel überholte das Kontextmenü | tickte still |
| M-1 | Ein Dateiname konnte Code ausführen | – |

Kein Syntaxprüfer findet so etwas. Der Prüfstand sucht genau danach.

## Benutzung

### Im Portal (der normale Weg)

**Milcrid → System Test → „Prüfung starten"** 🧪

Dauert etwa eine Sekunde. Zeigt oben das Gesamtergebnis (grün/rot), darunter
jede Prüfung einzeln – Fehler rot mit Erklärung, Hinweise gelb. Ganz unten
steht, ob das laufende Backend antwortet, und wie viele Zeilen geprüft wurden.

Das Fenster ist **nur Startknopf und Anzeige** – die ganze Prüf-Logik liegt
hier im Ordner. Es gibt genau **einen** Prüfstand: der, den man im Terminal
startet, ist derselbe, den das Fenster benutzt. Zwei Fassungen würden früher
oder später auseinanderlaufen, und dann hätte man zwei Wahrheiten statt einer.

### Der Stresstest (zweiter Knopf)

Macht das **Gegenteil** vom Prüfstand. Der Prüfstand stellt jede Frage einmal
und sucht Widersprüche – der Stresstest tut Milcrid absichtlich weh und sucht,
was bei *einem* Versuch nie auffällt:

| Phase | Was passiert | Wonach gesucht wird |
|---|---|---|
| Dauerfeuer | ~100.000 Anfragen in 25 s, ohne Pause | Antwortzeit, die im Lauf schlechter wird |
| Gleichzeitig | 8 Verbindungen parallel, 20 s | zwei Zugriffe, die sich ins Gehege kommen |
| Kaputte Nachrichten | 150 absichtlich falsche Nachrichten | eine davon, die den Server mitreißt |
| Datei-Manager | 120 Dateien anlegen, auflisten, löschen | Zählfehler, Reste, Inkonsistenz |
| KI-Werkzeugwahl | echte Fragen ans Sprachmodell | wählt Milcrid das richtige Werkzeug? |
| (durchgehend) | Speicher von main.py vorher/nachher | Speicher, der nur wächst |

Dauert 1–3 Minuten – **durch echte Arbeit, nicht durch eine eingebaute
Wartezeit**. Eine künstliche Verzögerung wäre genau die Sorte Schummelei,
die einen Test wertlos macht.

```bash
~/Milcrid/venv/bin/python3 stresstest.py              # voll
~/Milcrid/venv/bin/python3 stresstest.py --ohne-ki    # ohne Modell, ~70 s
~/Milcrid/venv/bin/python3 stresstest.py --dauerfeuer 60 --verbindungen 20
```

Die KI-Phase ist die einzige, die etwas über Milcrids **Verstand** sagt statt
über seine Geschwindigkeit. Sie unterscheidet zwei Fälle, die sich von außen
gleich anfühlen:

- **Werkzeug fehlt** → Milcrid nimmt ersatzweise irgendetwas. Bauen hilft,
  Training nicht.
- **Werkzeug ist da, wird aber nicht gewählt** → hier hilft Training/Prompt.

### Im Terminal (für mehr Möglichkeiten)

```bash
cd ~/Milcrid/pruefstand
python3 pruefstand.py                 # alles prüfen
python3 pruefstand.py --leise         # nur Fehler, ohne Hinweise
python3 pruefstand.py --nur ipc       # nur eine Prüfung
python3 pruefstand.py --pfad /woanders # anderen Stand prüfen (z.B. Sicherung)
python3 pruefstand.py --json          # maschinenlesbar (nutzt das Portal-Fenster)
```

Rückgabewert `0` = sauber, `1` = Fehler gefunden.

**Zusätzlich der Live-Test** (muss auf Milcrid laufen, braucht das venv):

```bash
~/Milcrid/venv/bin/python3 ~/Milcrid/pruefstand/live_test.py
```

Der fragt das **laufende** Backend alles, was auch das Portal beim Öffnen
eines Bereichs fragt, und prüft, ob eine brauchbare Antwort kommt.

## Was geprüft wird

| Prüfung | Findet |
|---|---|
| `p01_syntax` | Syntaxfehler in allen Python-Modulen, im Portal-Skript, main.js, preload.js |
| `p02_portal_ids` | `getElementById` auf Elemente, die es nicht gibt; doppelte IDs; Knöpfe ohne Funktion |
| `p03_ws_abgleich` | Nachrichten, die eine Seite sendet und die andere nicht kennt (**Bauart von M-2**) |
| `p04_ipc_abgleich` | Lücken in der Kette Portal → preload.js → main.js |
| `p05_befehls_einschleusung` | `execSync` mit Fremddaten (Shell-Einschleusung) |
| `p06_innerhtml` | `innerHTML` mit fremden Daten (**Bauart von M-1**) |
| `p07_ebenen` | Dialoge/Menüs, die hinter Fenstern verschwinden (**Bauart von M-3/M-6**) |
| `p08_sandkasten` | Datei-Manager: Ausbruch aus dem Home, Verknüpfungen (**echte Ausführung**) |
| `p09_spuren_muster` | Millok-Erkennung von Unsicherheit/Bestätigung/Ablehnung |
| `p10_bridge_sandkasten` | KI-Werkzeuge: Sandkasten, geschützte Steuer-Dateien (**echte Ausführung**) |
| `p11_faehigkeiten` | Werden die KI-Fähigkeiten überhaupt angeboten? Testet 15 echte Sätze gegen die Stichwörter |

`p08` und `p10` **führen den Code wirklich aus**, gegen einen Wegwerf-Ordner.
Das echte Home und `~/Milcrid` werden dabei nie angefasst.

## Der wichtigste Grundsatz dieses Werkzeugs

**Ein Prüfer, der Fehlalarm schlägt, ist schlimmer als keiner** – nach dem
dritten falschen Alarm schaut niemand mehr hin.

Beim Bauen hat der Prüfstand selbst vier Fehlalarme produziert, alle vier
sind behoben und im Quelltext als Kommentar dokumentiert:

1. Protokoll-Beispiele in main.pys **Kopfkommentar** zählten als echte Nachrichten
2. Die verneinte Form `if typ != "frage"` wurde nicht als Behandlung erkannt
3. Der Datei-Manager nutzt `senden()` **klein** geschrieben, die anderen `…Senden()`
4. Nachrichten, die über eine **Zwischenvariable** verschickt werden

Deshalb gilt: Jeder gemeldete Fehler wird einmal von Hand nachgeprüft,
**bevor** er als echter Fund gilt.

## Gegenprobe

Ein Test, der nie rot wird, misst nichts. Alle Prüfungen wurden mit
absichtlich eingebauten Fehlern gegengeprüft:

| Eingebauter Fehler | Wurde gefunden |
|---|---|
| preload-Eintrag gelöscht | ✓ |
| main.js-Handler verschrieben | ✓ |
| Portal-Empfänger entfernt (M-2 nachgestellt) | ✓ |
| `execSync` mit Netzwerknamen | ✓ |
| Ausbruchsschutz im Datei-Manager entschärft | ✓ (5 Wege) |
| M-4-Reparatur zurückgedreht (Verknüpfungen) | ✓ |
| erfundener Nachrichtentyp im Live-Test | ✓ |

Das lässt sich jederzeit wiederholen: eine Kopie anlegen, etwas kaputt
machen, `--pfad` darauf zeigen lassen.

## Die Einzeltests daneben

Neben `pruefstand.py` (statisch) und `live_test.py` (fragt das laufende
Milcrid) liegen hier Tests für einzelne Bauteile. Sie laufen im venv:
`~/Milcrid/venv/bin/python3 pruefstand/<test>.py`

| Test | Prüft | Stand |
|---|---|---|
| `test_verlauf.py` | Verlauf kürzen, Anleitungen ein-/ausblenden | 21 Prüfungen |
| `test_dateien.py` | Welche Datei meint Klaus? Thema-Vorrang, Rückfrage bei mehreren | 14 Prüfungen |
| `test_lagebild.py` | Sieht Milcrid, was offen ist? Vorderes Fenster, Dateien im Thema | 10 Prüfungen |

`test_verlauf.py` braucht `PYTHONPATH=/home/miluh/Milcrid` davor, die beiden
anderen nicht (sie setzen den Pfad selbst).

`test_dateien.py` legt eigene Dateien in Test-Themen an und räumt sie am Ende
wieder weg – er hinterlässt keine Spuren in Klaus' Themen.

## Grenzen – was der Prüfstand NICHT kann

- **Kein Ersatz für einen Blick auf den echten Bildschirm.** Ein
  `portal_aktion` geht an die Verbindung zurück, die gefragt hat – ein
  Testskript bekommt also eine völlig richtige Antwort, während auf dem
  Kiosk nichts passiert. Antwortet alles sauber, heißt das: das Backend ist
  in Ordnung, nicht dass die Oberfläche es anzeigt.
- **Er kennt keine Absicht.** Ob ein Knopf das Richtige tut, sieht nur ein
  Mensch. Er prüft, ob die Teile zusammenpassen – nicht, ob sie das
  Gewünschte tun.
- **Layout und Optik** kommen darin gar nicht vor.
