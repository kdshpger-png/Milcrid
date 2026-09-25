# token_counter.py

import config


def auslastung(response):
    """Liest Token-Zahlen aus der Modell-Antwort und rechnet die Auslastung
    gegen das Kontextfenster aus. Gibt (gesamt_tokens, max_tokens, prozent)
    zurueck - reine Zahlen, ohne Text drumherum. Wird sowohl vom Terminal
    (zeige_auslastung) als auch vom Portal (main.py PortalSitzung) benutzt,
    damit beide exakt dieselbe Rechnung verwenden."""
    # Bei neueren Ollama-Versionen liegen die Zahlen direkt als Attribute auf
    # dem Objekt. Beide sind dort aber "int | None" mit Standard None - Ollama
    # laesst prompt_eval_count z.B. bei vollstaendig gecachtem Prompt weg.
    # Ohne das "or 0" gab das "None + 0" -> TypeError. Der wurde von beiden
    # Aufrufern abgefangen, also stuerzte nichts ab - aber die Anzeige blieb
    # still auf dem alten Stand stehen UND die 90%-Speicherfrage kam nie,
    # obwohl der Kontext volllief.
    prompt_tokens = getattr(response, 'prompt_eval_count', 0) or 0
    completion_tokens = getattr(response, 'eval_count', 0) or 0

    gesamt_tokens = prompt_tokens + completion_tokens
    # Kontextfenster kommt aus config (Quelle: num_ctx im Modelfile).
    # Fallback verhindert eine Division durch Null, falls num_ctx mal 0 ist.
    max_tokens = config.KONTEXT_FENSTER or config.STANDARD_FENSTER
    prozent = (gesamt_tokens / max_tokens) * 100
    return gesamt_tokens, max_tokens, prozent


def zeige_auslastung(response):
    # Gibt die sauber formatierte Zeile fürs Terminal zurück
    gesamt_tokens, max_tokens, prozent = auslastung(response)
    return f"[Kontext: {gesamt_tokens:,} / {max_tokens:,} Token | Auslastung: {prozent:.1f}%]"
