# spracheingabe_verwaltung.py
# Aufnahme + Spracherkennung fuer die BEIDEN Wege, ueber die gesprochener
# Text nach Milcrid kommt:
#   - Knopf im Portal (Push-to-Talk): aufnahme_starten() /
#     aufnahme_stoppen_und_erkennen() - eine Aufnahme pro Knopfdruck.
#   - Codewort-Dauerlauscher: hat einen EIGENEN, dauerhaft laufenden
#     Tonstrom (siehe codewort_verwaltung.py) und benutzt hier nur
#     erkennen().
# Beide duerfen gleichzeitig laufen: PipeWire erlaubt mehrere Mitschnitte
# derselben Quelle (2026-08-31 nachgemessen - zwei pw-record-Prozesse
# lieferten beide vollstaendigen Ton). Sie teilen sich also NICHT ein
# Mikrofon, sondern haben je einen eigenen Mitschnitt - dadurch entfaellt
# jedes Vorrang-/Besitz-Gerangel zwischen ihnen.
#
# Der erkannte Text geht NICHT hier ins Modell - er wird ans Portal
# zurueckgeschickt und dort ganz normal ueber die bestehende Chat-Eingabe
# abgeschickt, als haette Klaus ihn getippt. Spracheingabe ist also nur ein
# zweiter Weg, Text in denselben Chat zu bringen - keine eigene
# Sicherheitsschicht noetig, das regeln weiterhin die Faehigkeiten-Schalter
# (siehe faehigkeiten_verwaltung.py).
#
# cuBLAS/cuDNN muessen VOR dem faster_whisper-Import geladen sein (kein
# System-CUDA-Toolkit auf Milcrid noetig, die pip-Pakete nvidia-cublas-cu12/
# nvidia-cudnn-cu12 reichen). Bewusst per ctypes.CDLL mit ABSOLUTEM Pfad statt
# ueber LD_LIBRARY_PATH: Testreihe 2026-08-30 hat gezeigt, dass ein zur
# Laufzeit per os.environ gesetztes LD_LIBRARY_PATH nur manchmal wirkt (glibc
# liest die Variable beim Prozessstart, nicht zuverlaessig bei jedem
# spaeteren dlopen) - im echten main.py-Prozess klappte darum nur der JEWEILS
# ERSTE Erkennungsversuch, jeder weitere schlug mit "libcublas.so.12 is not
# found" fehl. Mit ctypes.CDLL(absoluter_pfad, RTLD_GLOBAL) ist die Bibliothek
# schon im Prozess geladen, bevor ctranslate2 sie sucht - unabhaengig von
# LD_LIBRARY_PATH.
import ctypes
import traceback
import time
import os

_NVIDIA_DIR = os.path.join(os.path.dirname(__file__), "venv", "lib", "python3.12", "site-packages", "nvidia")
for _lib in ("cublas/lib/libcublasLt.so.12", "cublas/lib/libcublas.so.12", "cudnn/lib/libcudnn.so.9"):
    ctypes.CDLL(os.path.join(_NVIDIA_DIR, _lib), mode=ctypes.RTLD_GLOBAL)

import subprocess
import tempfile
import threading

from faster_whisper import WhisperModel

# Tonformat, das beide Wege benutzen (auch der Dauerlauscher, siehe
# codewort_verwaltung.py) - Whisper arbeitet ohnehin intern mit 16 kHz.
ABTASTRATE = 16000

# "medium" (mehrsprachig): auf der RTX 4060 Ti in Bruchteilen einer Sekunde
# pro Satz, deutlich genauer bei Deutsch als "small". Bei Bedarf hier auf
# "large-v3" hochstellen (mehr VRAM/Zeit pro Satz, noch genauer).
# 2026-09-06 von "medium" auf "large-v3" umgestellt. Grund: Klaus musste
# Befehle oft zweimal sagen und half sich damit, betont deutlich zu
# sprechen. Gemessen wurde vorher, dass es NICHT am Pegel liegt (seine
# Stimme ~2120, Schwelle 500) - es liegt an der Aussprache. Genau da ist
# der Unterschied zwischen medium und large am groessten: bei klarer
# Sprache koennen beide, bei beilaeufiger nicht. Kostet ~1,5 GB mehr
# Grafikspeicher und ein paar Zehntelsekunden. "medium" liegt weiter im
# Zwischenspeicher, das Zurueckstellen ist diese eine Zeile.
MODELL_GROESSE = "large-v3"

_modell = None
_modell_lock = threading.Lock()


def _modell_laden():
    global _modell
    with _modell_lock:
        if _modell is None:
            _modell = WhisperModel(MODELL_GROESSE, device="cuda", compute_type="float16")
    return _modell


# Schreibt in dasselbe Protokoll wie codewort_verwaltung.py - bewusst kein
# Import von dort, das Modul importiert diese Datei bereits (Ringbezug).
_LAUSCH_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "codewort-lauscher.log")


def _lausch_log(text):
    try:
        with open(_LAUSCH_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {text}\n")
    except Exception:
        pass


def erkennen(datei):
    """Wandelt eine fertige WAV-Datei in Text. Gemeinsamer Weg fuer den
    Knopf und den Codewort-Dauerlauscher - beide koennen gleichzeitig hier
    ankommen, darum die Sperre ums Modell."""
    try:
        modell = _modell_laden()
        # Lazy-Import (nicht oben im Modul): codewort_verwaltung importiert
        # umgekehrt dieses Modul - ein Import ganz oben in beiden Dateien
        # waere ein Ringimport. Hier drin, erst wenn tatsaechlich
        # transkribiert wird, sind beide Module laengst fertig geladen.
        import codewort_verwaltung
        # Whisper bekommt die wichtigen Eigennamen als Hinweis. NICHT nur das
        # Codewort: "Milcrid" kommt auch mitten in Befehlen vor ("Milcrid
        # Uhr") und verlor seinen Hinweis, als das Codewort aenderbar wurde
        # und Klaus es auf "Computer" stellte - seitdem verstand sie
        # ausgerechnet den eigenen Namen nicht mehr (Klaus-Fund 2026-09-01).
        namen = ["Milcrid", codewort_verwaltung.codewort_text()]
        codewort = ", ".join(dict.fromkeys(n for n in namen if n))
        # _modell_lock haelt auch waehrend transcribe(): zwei GLEICHZEITIGE
        # Aufrufe auf demselben Modell fuehrten zu sporadischem "nichts
        # verstanden" (Klaus-Fund 2026-08-31). Die Segmente sind ein
        # Generator - erst list() loest die eigentliche Erkennung aus, das
        # muss also INNERHALB der Sperre passieren.
        with _modell_lock:
            # vad_filter=True: unterdrueckt Whispers bekannte Neigung, auf
            # Stille/Rauschen frei erfundenen Text zu erkennen (getestet
            # 2026-08-30 - ohne Filter kam auf einer stillen Aufnahme "Vielen
            # Dank fuers Zuschauen" heraus, mit Filter leer).
            # initial_prompt=<Codewort>: ohne den Hinweis versteht das Modell
            # einen ungewoehnlichen Eigennamen als das klanglich naechste
            # bekannte Wort - bei "Milcrid" wurde daraus "Mildred" (Klaus-
            # Test 2026-08-30, per Debug-Aufnahme nachvollzogen und mit
            # diesem Prompt behoben). Nutzt das AKTUELLE, aenderbare
            # Codewort statt eines fest eingetragenen Wortes.
            segments, _info = modell.transcribe(
                datei, language="de", vad_filter=True, initial_prompt=codewort)
            teile = list(segments)
            text = " ".join(s.text.strip() for s in teile).strip()
            # Kam nichts heraus, wird das nur vermerkt - NICHT mehr ein
            # zweites Mal ohne vad_filter erkannt. Diese Gegenprobe stand hier
            # vom 06.09. und hat ihre Frage beantwortet (der Filter ist
            # unschuldig; er unterdrueckt korrekt die Faelle, in denen Whisper
            # nur seinen eigenen Hinweistext zurueckgibt). Behalten durfte sie
            # nicht bleiben: der zweite Durchlauf lief INNERHALB von
            # _modell_lock, blockierte also bei jedem Geraeusch die Erkennung
            # fuer alles andere - Milcrid wurde dadurch spuerbar traege und
            # musste oefter zweimal angesprochen werden (Klaus, 06.09.).
            if not text:
                _lausch_log("Whisper lieferte keinen Text")
        return text
    except Exception:
        # Frueher wurde hier JEDE Ausnahme still zu "nichts verstanden".
        # Genau das hat am 30.08. den cuBLAS-Ladefehler wochenlang als
        # harmloses Nicht-Verstehen getarnt. Ab jetzt steht der echte
        # Grund im Protokoll (Opus 2026-09-06).
        try:
            _lausch_log("AUSNAHME bei der Erkennung: "
                        + traceback.format_exc().strip().replace("\n", " | "))
        except Exception:
            pass
        # Bei einem sehr kurzen Antippen (Loslassen fast sofort nach dem
        # Draufdruecken) ist die WAV-Datei manchmal noch nicht gueltig
        # geschrieben (Klaus-Test 2026-08-30: "Invalid data found when
        # processing input"). Zaehlt wie Stille - nichts verstanden statt
        # Absturz der ganzen Verbindung.
        return ""


# ---- Knopf-Aufnahme (Push-to-Talk) ----------------------------------------
# Nur der Portal-Knopf benutzt diesen Teil. Der Dauerlauscher hat seinen
# eigenen Tonstrom und fasst diese Zustandsvariablen nicht an.

_aufnahme_prozess = None
_aufnahme_datei = None
_aufnahme_lock = threading.Lock()
_sicherheits_timer = None

# Haerter Deckel gegen eine Aufnahme, die nie gestoppt wird (Klaus-Test
# 2026-08-30: Knopf einmal gedrueckt, losgeredet, nie wieder geklickt -
# pw-record lief minutenlang unbemerkt weiter). Reine Ressourcen-Sicherung,
# keine Transkription - wenn niemand stoppt, hoert auch niemand auf Text.
MAX_AUFNAHME_SEKUNDEN = 30


def _sicherheitsstopp(erwarteter_prozess):
    global _aufnahme_prozess, _aufnahme_datei
    with _aufnahme_lock:
        if _aufnahme_prozess is not erwarteter_prozess:
            return  # laengst regulaer gestoppt, Timer kam zu spaet
        prozess, datei = _aufnahme_prozess, _aufnahme_datei
        _aufnahme_prozess, _aufnahme_datei = None, None
    prozess.kill()
    try:
        os.remove(datei)
    except OSError:
        pass


def aufnahme_laeuft():
    """True, solange der Knopf gedrueckt ist. Der Dauerlauscher fragt das ab
    und verwirft, was er waehrenddessen gehoert hat - sonst wuerde ein
    Satz, den Klaus bewusst in den Knopf spricht, zusaetzlich auch noch als
    Codewort-Befehl ausgewertet und doppelt ausgefuehrt."""
    return _aufnahme_prozess is not None


def aufnahme_starten():
    """Startet die Mikrofon-Aufnahme fuer den Knopf. Gibt False zurueck,
    wenn schon eine laeuft."""
    global _aufnahme_prozess, _aufnahme_datei, _sicherheits_timer
    with _aufnahme_lock:
        if _aufnahme_prozess is not None:
            return False
        fd, _aufnahme_datei = tempfile.mkstemp(suffix=".wav", prefix="milcrid_stimme_")
        os.close(fd)
        _aufnahme_prozess = subprocess.Popen(
            ["pw-record", "--rate", str(ABTASTRATE), "--channels", "1", "--format", "s16", _aufnahme_datei],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        _sicherheits_timer = threading.Timer(MAX_AUFNAHME_SEKUNDEN, _sicherheitsstopp, args=(_aufnahme_prozess,))
        _sicherheits_timer.daemon = True
        _sicherheits_timer.start()
        return True


def aufnahme_stoppen_und_erkennen():
    """Beendet die Knopf-Aufnahme und gibt den erkannten Text zurueck
    (leerer String, wenn nichts gesprochen wurde oder gerade keine Aufnahme
    lief)."""
    global _aufnahme_prozess, _aufnahme_datei
    with _aufnahme_lock:
        if _aufnahme_prozess is None:
            return ""
        prozess, datei = _aufnahme_prozess, _aufnahme_datei
        _aufnahme_prozess, _aufnahme_datei = None, None
        if _sicherheits_timer is not None:
            _sicherheits_timer.cancel()

    prozess.terminate()
    try:
        prozess.wait(timeout=3)
    except subprocess.TimeoutExpired:
        prozess.kill()

    try:
        return erkennen(datei)
    finally:
        try:
            os.remove(datei)
        except OSError:
            pass
