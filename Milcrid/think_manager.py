# think_manager.py
import re

# Erkennt <think>...</think> auch ueber mehrere Zeilen (DOTALL),
# Gross-/Kleinschreibung egal (IGNORECASE).
THINK_PATTERN = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)


class ThinkManager:
    """Schaltet die Anzeige des <think>-Denkprozesses an/aus und filtert ihn."""

    def __init__(self, aktiv=False):
        # Standard: Denkprozess wird NICHT angezeigt.
        self.aktiv = aktiv

    def status_text(self):
        return "AN" if self.aktiv else "AUS"

    # --- Befehls-Erkennung (haelt main.py sauber) ---

    def ist_befehl(self, eingabe):
        # Wahr, wenn die Eingabe ein Think-Befehl ist.
        return eingabe.strip().lower() in (
            "think", "/think",
            "think an", "think aus",
            "think on", "think off",
        )

    def befehl_ausfuehren(self, eingabe):
        # Setzt den Zustand und meldet das Ergebnis zurueck.
        e = eingabe.strip().lower()
        if e in ("think an", "think on"):
            self.aktiv = True
        elif e in ("think aus", "think off"):
            self.aktiv = False
        else:
            # Reiner Toggle: kippt den aktuellen Zustand.
            self.aktiv = not self.aktiv
        return f"Think-Modus ist jetzt {self.status_text()}."

    # --- Text-Verarbeitung ---

    def _trennen(self, roh_text):
        # Liefert (denken, klartext) getrennt zurueck.
        denk_teile = THINK_PATTERN.findall(roh_text)
        denken = "\n".join(t.strip() for t in denk_teile if t.strip())
        klartext = THINK_PATTERN.sub("", roh_text).strip()
        return denken, klartext

    def nur_antwort(self, roh_text):
        # Reine Antwort ohne Denkprozess - egal ob Modus an oder aus.
        # Wird an bridge.parse_and_execute weitergegeben.
        _, klartext = self._trennen(roh_text)
        return klartext

    def aufbereiten(self, roh_text):
        # Baut den Text, der im Terminal angezeigt wird.
        denken, klartext = self._trennen(roh_text)

        # Think AUS: nur die fertige Antwort zeigen.
        if not self.aktiv:
            return klartext or denken or roh_text.strip()

        # Think AN: erst Denkprozess, dann saubere Antwort.
        if not denken:
            # Keine <think>-Tags im Text vorhanden.
            return klartext or roh_text.strip()

        ausgabe = "[Denkprozess]\n" + denken + "\n" + "-" * 40
        if klartext:
            ausgabe += "\n" + klartext
        return ausgabe
