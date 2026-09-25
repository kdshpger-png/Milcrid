# codewort_verwaltung.py
# Wie darf die KI mithoeren (Klaus-Wunsch 2026-08-30/31): ZWEI unabhaengige
# Schalter - "Mikrofon" (Push-to-Talk-Knopf im Portal) und "Codewort"
# (reagiert von selbst, ohne Knopf). Beide koennen einzeln oder gleichzeitig
# an sein; sie behindern sich nicht, weil PipeWire mehrere Mitschnitte
# derselben Quelle erlaubt (2026-08-31 nachgemessen) - jeder Weg hat seinen
# eigenen Tonstrom.
#
# ---- Wie das Zuhoeren funktioniert (umgebaut 2026-08-31, Opus) ----
# Vorher: der Lauscher nahm in festen 3-Sekunden-Haeppchen auf, wertete jedes
# einzeln aus und war zwischen zwei Haeppchen fuer die Dauer der Erkennung
# (~0,3s) TAUB. Das hatte zwei Fehlerquellen, die sich nicht wegstellen
# liessen: faellt das Codewort in die Luecke, wird der Befehl gar nicht
# bemerkt; und ein Satz, der ueber die Haeppchen-Grenze laeuft, wird mitten
# im Wort zerschnitten ("schlie", "Minimi", "öffne" ohne Objekt - im
# Chatprotokoll vom 2026-08-31 mehrfach belegt). Beides zusammen liess
# geschaetzt jeden vierten bis fuenften Zuruf ins Leere laufen - fuer Klaus'
# Ziel ("frei mit der KI reden, ohne Knopf") zu viel.
#
# Jetzt: EIN durchgehender Tonstrom, der nie unterbrochen wird. Der Ton wird
# in 30-Millisekunden-Rahmen gelesen und nur auf seine Lautstaerke geprueft
# (billig, kein Modell noetig). Daraus eine einfache Zustandsmaschine:
#   Stille -> mehrere laute Rahmen  = jemand faengt an zu sprechen
#   Sprechen -> laengere Stille     = Satz ist zu Ende, JETZT erkennen
# Erkannt wird also immer ein VOLLSTAENDIGER Satz, nie ein Zeitfenster. Es
# gibt keine taube Luecke mehr: waehrend Whisper den fertigen Satz auswertet,
# laeuft der Tonstrom ungestoert weiter.
#
# Zwei Feinheiten, die leicht zu uebersehen sind:
#  - VORLAUF: der Sprechbeginn wird erst nach ein paar lauten Rahmen sicher
#    erkannt. Ohne Vorlaufspeicher fehlte genau der Wortanfang - also
#    ausgerechnet der Anfang des Codeworts. Darum laufen die letzten ~0,5s
#    immer in einem Ringspeicher mit und werden vorne angehaengt.
#  - SCHWELLE: kein fester Wert, sondern lernend. Der Grundpegel des Raums
#    wird waehrend der Stille laufend nachgefuehrt, die Sprechschwelle liegt
#    ein Vielfaches darueber - plus ein Mindestwert, damit in einem sehr
#    stillen Raum (gemessen: Pegel exakt 0) nicht jedes Knistern als
#    Sprechen zaehlt.

import collections
import json
import os
import subprocess
import tempfile
import threading
import time
import traceback
import wave

import numpy as np

import spracheingabe_verwaltung as stimme

BASIS_ORDNER = os.path.dirname(os.path.abspath(__file__))
DATEN_PFAD = os.path.join(BASIS_ORDNER, "codewort.json")

# mikrofon_an startet AN (Push-to-Talk gab es schon vorher, soll durch die
# neue Einstellung nicht ungefragt verschwinden). codewort_an startet AUS,
# wie jede neue Faehigkeit. codewort_text: das eigentliche Wort, aenderbar
# (Klaus-Wunsch 2026-08-31 - "wichtig wenn Nutzer seiner KI einen Namen
# geben kann"), auch benutzt als Whisper-Erkennungshinweis (siehe
# initial_prompt in spracheingabe_verwaltung.py) - ohne den Hinweis versteht
# das Modell einen ungewoehnlichen Namen leicht als klanglich naechstes
# bekanntes Wort (bei "Milcrid" wurde daraus "Mildred", siehe dortiger
# Kommentar).
_STANDARD = {"mikrofon_an": True, "codewort_an": False, "codewort_text": "Milcrid"}

CODEWORT_MAX_LAENGE = 40

# ---- Einstellungen fuer das Dauerzuhoeren ----
RAHMEN_MS = 30
RAHMEN_BYTES = stimme.ABTASTRATE * 2 * RAHMEN_MS // 1000   # s16 = 2 Byte/Wert
# Mindest-Lautstaerke, ab der ueberhaupt von Sprechen ausgegangen wird.
# Nicht geschaetzt, sondern gemessen (2026-08-31, Razer Seiren V3 Mini in
# Klaus' Raum): Grundrauschen im Mittel ~99 mit Spitzen bis 276, Klaus'
# Sprechstimme dagegen ~1700-2900. 500 liegt klar ueber den Rauschspitzen
# und weit unter der Sprechstimme - Luft nach beiden Seiten. Eine zu knapp
# gewaehlte Schwelle (erst 300) haette bei Rauschspitzen von 276 gelegentlich
# Sprechen vorgetaeuscht.
MIN_SCHWELLE = 500.0
RAUSCH_FAKTOR = 3.0        # Sprechen muss so viel lauter sein als der Raum
START_RAHMEN = 3           # ~90ms ueber der Schwelle = Sprechbeginn
# Klaus-Fund 2026-09-10: "der Zeitraum wo man der KI was sagen kann nach
# Computer ist sehr kurz, spricht man normal bekommt KI die letzten 2-3
# Woerter oft gar nicht mit". 750ms Stille galt schon als Satzende - eine
# ganz normale kurze Sprechpause (Luft holen, kurz ueberlegen) ist oft
# laenger als das, und schnitt den Satz vorzeitig ab. Auf ~1,35s erhoeht -
# spuerbar mehr Luft zum Sprechen, ohne dass Milcrid nach jedem Satz lange
# braeuchte, um zu reagieren.
ENDE_RAHMEN = 45           # ~1350ms Stille = Satzende
VORLAUF_RAHMEN = 17        # ~500ms Vorlauf, damit der Wortanfang nicht fehlt
PRUEF_RAHMEN = 33          # ~1x pro Sekunde nachsehen, ob noch eingeschaltet
MAX_SEGMENT_SEKUNDEN = 15  # Notbremse gegen Dauerreden/Dauerlaerm
MIN_SEGMENT_SEKUNDEN = 0.4 # kuerzeres ist Huesteln/Klopfen, kein Satz

# Wird nur das Codewort allein gerufen ("Computer." + Pause), gilt der
# NAECHSTE gesprochene Satz als Befehl - auch ohne erneutes Codewort.
WARTEZEIT_NACH_CODEWORT = 8.0
_wartet_auf_befehl_bis = 0.0


def _daten_laden():
    try:
        with open(DATEN_PFAD, "r", encoding="utf-8") as f:
            daten = json.load(f)
    except Exception:
        daten = {}
    if not isinstance(daten, dict):
        daten = {}
    text = daten.get("codewort_text")
    if not isinstance(text, str) or not text.strip():
        text = _STANDARD["codewort_text"]
    return {
        "mikrofon_an": bool(daten.get("mikrofon_an", _STANDARD["mikrofon_an"])),
        "codewort_an": bool(daten.get("codewort_an", _STANDARD["codewort_an"])),
        "codewort_text": text.strip(),
    }


def info():
    return {"erfolg": True, **_daten_laden()}


def speichern(feld, an):
    if feld not in ("mikrofon_an", "codewort_an"):
        return {"erfolg": False, "fehler": f'Unbekanntes Feld "{feld}".'}
    daten = _daten_laden()
    daten[feld] = bool(an)
    with open(DATEN_PFAD, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
    # Alle aktuellen Werte mitschicken, nicht nur "erfolg" - das Portal
    # aktualisiert die Anzeige aus DIESER Antwort (siehe
    # mithoerenAnzeigenAktualisieren in milcrid_portal.html). Ohne die Werte
    # hier wurden bei jedem Klick beide Schalter auf "aus" zurueckgesetzt,
    # egal was wirklich gespeichert wurde (Klaus-Fund 2026-08-31).
    return {"erfolg": True, **daten}


def text_speichern(text):
    text = (text or "").strip()
    if not text:
        return {"erfolg": False, "fehler": "Codewort darf nicht leer sein."}
    if len(text) > CODEWORT_MAX_LAENGE:
        return {"erfolg": False, "fehler": f"Codewort ist zu lang (max. {CODEWORT_MAX_LAENGE} Zeichen)."}
    daten = _daten_laden()
    daten["codewort_text"] = text
    with open(DATEN_PFAD, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
    return {"erfolg": True, **daten}


def mikrofon_erlaubt():
    """Von main.py vor stimme_start geprueft - der Knopf im Portal darf nur
    dann wirklich aufnehmen, wenn dieser Schalter an ist."""
    return _daten_laden()["mikrofon_an"]


def codewort_text():
    """Von spracheingabe_verwaltung.py genutzt, um Whisper das aktuell
    gueltige Codewort als Erkennungshinweis mitzugeben (initial_prompt)."""
    return _daten_laden()["codewort_text"]


# ---- Spur fuer den stillen Ausfall (Opus 2026-09-06) ----
# Klaus' Beobachtung: von etwa zehn Ansprachen reagiert Milcrid einmal GAR
# nicht - keine falsche Antwort, sondern gar keine. Die Tonerkennung wurde am
# 06.09. an einer echten 30-Sekunden-Aufnahme geprueft und arbeitet fehlerfrei
# (fuenf gesprochene Saetze, fuenf erkannte Segmente). Es bleiben genau zwei
# Stellen weiter unten, an denen ein fertig erkannter Satz WORTLOS verworfen
# wird: kein Text von Whisper, oder das Codewort steht buchstabengenau nicht
# im Text ("Komputer" statt "Computer" reicht schon). Beide schreiben ab jetzt
# eine Zeile hierhin, damit der naechste Aussetzer nicht wieder nur ein
# Gefuehl ist. Bewusst eine eigene kleine Datei mit Deckel - portal-monitor.log
# ist ohne Begrenzung auf 68 MB angewachsen.
LAUSCH_LOG_PFAD = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "codewort-lauscher.log")
LAUSCH_LOG_MAX_BYTES = 2 * 1024 * 1024
# Klaus-Wunsch 2026-09-10 ("alles behalten"): bei 2 MB wandert das Log mit
# Datum ins Archiv, statt ".alt" zu ueberschreiben - vorher war alles, was
# aelter als die letzten zwei Dateien war, verloren. Gleiches Vorgehen wie
# bei mitschrift.py. Der Deckel bleibt, er haelt nur die AKTUELLE Datei klein.
LAUSCH_ARCHIV_ORDNER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "codewort-lauscher-archiv")


def _lausch_log(text):
    try:
        if os.path.exists(LAUSCH_LOG_PFAD) and os.path.getsize(LAUSCH_LOG_PFAD) > LAUSCH_LOG_MAX_BYTES:
            os.makedirs(LAUSCH_ARCHIV_ORDNER, exist_ok=True)
            ziel = os.path.join(LAUSCH_ARCHIV_ORDNER,
                                f"codewort-lauscher-{time.strftime('%Y-%m-%d_%H%M%S')}.log")
            if not os.path.exists(ziel):
                os.replace(LAUSCH_LOG_PFAD, ziel)
        with open(LAUSCH_LOG_PFAD, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {text}\n")
    except Exception:
        pass  # Mitschreiben darf das Zuhoeren nie stoeren


def _ist_wiederholungs_muell(text):
    """Whisper erfindet bei Rauschen (Tippen, Klappern) gern Ketten wie
    "5 Video 1 Video 2 Video ..." - Klaus 25.09.2026, beim Tippen in LibreOffice
    kam genau das als Befehl an. Ein Wort, das mindestens 4x vorkommt und ein
    Drittel des Satzes ausmacht, ist kein Befehl. An allen 343 Codewort-Treffern
    bis dahin gemessen: verwirft genau diesen einen."""
    import re, collections
    w = re.findall(r"\w+", (text or "").lower())
    if len(w) < 6:
        return False
    n = collections.Counter(w).most_common(1)[0][1]
    return n >= 4 and n / len(w) >= 0.3


def _segment_auswerten(segment, on_erkannt):
    """Ein fertig gesprochener Satz (rohe Tonwerte): erkennen, auf das
    Codewort pruefen, bei Treffer den Befehl melden."""
    global _wartet_auf_befehl_bis
    dauer = len(segment) / 2 / stimme.ABTASTRATE
    if dauer < MIN_SEGMENT_SEKUNDEN:
        return

    fd, datei = tempfile.mkstemp(suffix=".wav", prefix="milcrid_lausch_")
    os.close(fd)
    try:
        with wave.open(datei, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(stimme.ABTASTRATE)
            w.writeframes(segment)
        text = (stimme.erkennen(datei) or "").strip()
    finally:
        try:
            os.remove(datei)
        except OSError:
            pass

    if not text:
        _lausch_log(f"VERWORFEN: Whisper lieferte keinen Text (Segment {dauer:.1f}s)")
        return

    wort = _daten_laden()["codewort_text"].lower()
    stelle = text.lower().find(wort)
    if stelle == -1:
        # Kein Codewort - normalerweise Gerede, das uns nichts angeht. Es sei
        # denn, gerade eben wurde das Codewort ALLEIN gerufen: dann ist das
        # hier die Fortsetzung ("Computer." ... "öffne den Browser").
        if time.time() < _wartet_auf_befehl_bis:
            _wartet_auf_befehl_bis = 0.0
            if _ist_wiederholungs_muell(text):
                _lausch_log(f"VERWORFEN: Wiederholung, vermutlich Rauschen: {text!r}")
                return
            # Ganzer Satz (Klaus 25.09.2026): so sieht man, was ohne "Computer"
            # als Fortsetzung durchging.
            _lausch_log(f"FORTSETZUNG nach Codewort -> Befehl: {text!r}")
            on_erkannt(text)
            return
        _lausch_log(f"KEIN CODEWORT ('{wort}') in: {text!r}")
        return

    befehl = text[stelle + len(wort):].strip(" ,.!?-")
    davor = text[:stelle].strip(" ,.!?-")
    if befehl and _ist_wiederholungs_muell(befehl):
        _lausch_log(f"VERWORFEN: Wiederholung, vermutlich Rauschen: {befehl!r}  | ganzer Satz: {text!r}")
        return
    if befehl:
        _wartet_auf_befehl_bis = 0.0
        _lausch_log(f"TREFFER -> Befehl: {befehl!r}  | ganzer Satz: {text!r}")
        on_erkannt(befehl)
    elif not davor:
        # Das Codewort wurde ALLEIN gerufen ("Computer." + Pause) - eine
        # bewusste "hör mir zu"-Geste, der naechste Satz ist der Befehl.
        _wartet_auf_befehl_bis = time.time() + WARTEZEIT_NACH_CODEWORT
    # Steht das Codewort dagegen am ENDE eines laengeren Satzes ("...ich
    # gehe mal an den Computer"), war es hoechstwahrscheinlich normales
    # Gerede - dann bewusst NICHT scharf schalten. Ohne diese
    # Unterscheidung haette jeder Nebensatz, der zufaellig auf das Codewort
    # endet, acht Sekunden lang JEDEN weiteren Satz zum Befehl gemacht
    # (beim Testen 2026-08-31 genau so aufgefallen).


def _dauerlauschen(on_erkannt):
    """Hoert durchgehend zu und meldet jeden fertig gesprochenen Satz an
    _segment_auswerten. Kehrt zurueck, wenn das Codewort ausgeschaltet wird
    oder der Tonstrom abreisst - die aeussere Schleife baut dann neu auf."""
    prozess = subprocess.Popen(
        ["pw-record", "--rate", str(stimme.ABTASTRATE), "--channels", "1", "--format", "s16", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    try:
        vorlauf = collections.deque(maxlen=VORLAUF_RAHMEN)
        gesammelt = []
        im_sprechen = False
        laut = still = 0
        rauschpegel = 0.0
        knopf_dazwischen = False
        seit_pruefung = 0

        while True:
            block = prozess.stdout.read(RAHMEN_BYTES)
            if not block or len(block) < RAHMEN_BYTES:
                return  # Tonstrom abgerissen

            seit_pruefung += 1
            if seit_pruefung >= PRUEF_RAHMEN:
                seit_pruefung = 0
                if not _daten_laden()["codewort_an"]:
                    return  # ausgeschaltet - Mikrofon wieder freigeben

            werte = np.frombuffer(block, dtype=np.int16).astype(np.float32)
            pegel = float(np.sqrt((werte * werte).mean()))
            schwelle = max(MIN_SCHWELLE, rauschpegel * RAUSCH_FAKTOR)

            if pegel >= schwelle:
                laut += 1
                still = 0
            else:
                still += 1
                laut = 0
                if not im_sprechen:
                    # Grundpegel des Raums langsam nachfuehren - nur in der
                    # Stille, damit die eigene Stimme ihn nicht hochzieht.
                    rauschpegel = 0.95 * rauschpegel + 0.05 * pegel

            if not im_sprechen:
                vorlauf.append(block)
                if laut >= START_RAHMEN:
                    im_sprechen = True
                    gesammelt = list(vorlauf)  # Vorlauf MIT den ersten lauten Rahmen
                    vorlauf.clear()
                    knopf_dazwischen = stimme.aufnahme_laeuft()
                continue

            gesammelt.append(block)
            if stimme.aufnahme_laeuft():
                knopf_dazwischen = True
            zu_lang = len(gesammelt) * RAHMEN_MS / 1000.0 >= MAX_SEGMENT_SEKUNDEN
            if still >= ENDE_RAHMEN or zu_lang:
                segment = b"".join(gesammelt)
                gesammelt = []
                im_sprechen = False
                laut = still = 0
                # Was Klaus bewusst in den Knopf gesprochen hat, geht ueber
                # den Knopf-Weg in den Chat - hier nicht ein zweites Mal
                # auswerten, sonst wird derselbe Satz doppelt ausgefuehrt.
                if not knopf_dazwischen:
                    _segment_auswerten(segment, on_erkannt)
                knopf_dazwischen = False
    finally:
        prozess.terminate()
        try:
            prozess.wait(timeout=3)
        except subprocess.TimeoutExpired:
            prozess.kill()


def _lauscher_schleife(on_erkannt):
    while True:
        try:
            if not _daten_laden()["codewort_an"]:
                time.sleep(1)
                continue
            beginn = time.time()
            _dauerlauschen(on_erkannt)
            # Kommt der Tonstrom gar nicht erst zustande - Mikrofon abgezogen,
            # oder PipeWire ist direkt nach dem Hochfahren noch nicht bereit -,
            # kehrt _dauerlauschen sofort zurueck. Ohne diese Bremse wuerde
            # die Schleife dann ununterbrochen neue pw-record-Prozesse starten
            # und den Rechner grundlos belasten. Nach einem normalen Lauf
            # (Codewort abgeschaltet) wird dagegen nicht gewartet.
            if time.time() - beginn < 1.0:
                time.sleep(2)
        except Exception:
            # Diese Schleife darf NIE sterben. Ohne Schutz haette eine
            # einzige Ausnahme die Codewort-Erkennung bis zum naechsten
            # Neustart still abgeschaltet, ohne dass irgendwo etwas davon
            # gestanden haette (Opus-Pruefung 2026-08-31).
            traceback.print_exc()
            time.sleep(2)


def starten(on_erkannt):
    """Startet das Dauerzuhoeren im Hintergrund (einmal pro Prozesslauf, von
    main.py beim Hochfahren aufgerufen). Der Faden laeuft dauerhaft mit,
    hoert aber nur wirklich hin, wenn "codewort_an" gesetzt ist. Ruft
    on_erkannt(befehlstext) auf, sobald ein Satz mit dem Codewort (oder die
    Fortsetzung danach) erkannt wurde."""
    thread = threading.Thread(target=_lauscher_schleife, args=(on_erkannt,), daemon=True)
    thread.start()
