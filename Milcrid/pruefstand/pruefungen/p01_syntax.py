"""
Syntax: Python-Module, Portal-Skript, main.js, preload.js

Billigste Pruefung mit dem groessten Schutz vor dem schlimmsten Fall: eine
Datei mit Syntaxfehler laesst den Kiosk gar nicht erst starten (Electron
zeigt dann nur noch "A JavaScript error occurred in the main process", oder
das Portal bleibt weiss).

Node liegt auf Milcrid unter /usr/bin/node. Auf cubi gibt es keins - dann
wird die JS-Pruefung uebersprungen und das ausdruecklich gesagt, statt
stillschweigend "ok" zu melden.

Ausserdem: die grobe Klammer-Balance im Portal-Skript als Notnagel, falls
node fehlt (findet die haeufigste Ursache eines kaputten Portals).
"""
import os
import py_compile
import shutil
import subprocess
import tempfile
from pathlib import Path


# Milcrid hat node unter /usr/bin/node, cubi hat keins. Laeuft der Pruefstand
# auf cubi, wird node per SSH auf Milcrid benutzt - das ist die einzige
# VERLAESSLICHE JS-Syntaxpruefung (siehe Kommentar bei _balance unten).
# Seit 26.09.2026 nur noch per Einstellung (MILCRID_PRUEFSTAND_SSH) - im
# oeffentlichen Paket gibt es keinen zweiten Rechner, dort wird ohne node die
# Pruefung einfach uebersprungen statt 45 s ins Leere zu verbinden.
SSH_ZIEL = os.environ.get("MILCRID_PRUEFSTAND_SSH", "")


def _node_pruefen(quelltext, name, ctx, befunde):
    """Prueft mit node --check. Gibt zurueck, ob node ueberhaupt erreichbar war."""
    node = shutil.which("node")
    if node:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                         encoding="utf-8") as f:
            f.write(quelltext)
            tmp = f.name
        try:
            e = subprocess.run([node, "--check", tmp], capture_output=True, text=True)
        finally:
            Path(tmp).unlink(missing_ok=True)
    else:
        # Kein node hier -> ueber SSH auf Milcrid pruefen lassen
        if not SSH_ZIEL:
            return False
        try:
            e = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", SSH_ZIEL,
                 "cat > /tmp/pruefstand_syntax.js && node --check /tmp/pruefstand_syntax.js"],
                input=quelltext, capture_output=True, text=True, timeout=45)
        except (OSError, subprocess.TimeoutExpired):
            return False
        if "Permission denied" in e.stderr or "Could not resolve" in e.stderr \
                or "Connection timed out" in e.stderr:
            return False

    if e.returncode != 0:
        meldung = (e.stderr or e.stdout).strip().splitlines()
        befunde.append(ctx.fehler(f"{name}: Syntaxfehler", "\n".join(meldung[:6])))
    return True


def _balance(quelltext):
    """Klammer-Saldo ausserhalb von Zeichenketten/Kommentaren (GROB).

    ACHTUNG - das Ergebnis ist NICHT verlaesslich: Regex-Literale wie /[{]/
    oder /\\)/ zaehlen faelschlich mit, weil ein handgeschriebener Zaehler
    Regex nicht von Division unterscheiden kann. Auf dem echten Portal
    meldet dieser Zaehler ein Ungleichgewicht, obwohl node --check die Datei
    sauber durchwinkt. Deshalb geht das Ergebnis nur als HINWEIS raus, nie
    als Fehler - ein Pruefer, der ohne Grund Alarm schlaegt, wird nach dem
    dritten Mal ignoriert und ist damit wertlos."""
    tiefe = {"{": 0, "(": 0, "[": 0}
    paare = {"}": "{", ")": "(", "]": "["}
    i, n, in_str = 0, len(quelltext), None
    while i < n:
        z = quelltext[i]
        if in_str:
            if z == "\\":
                i += 2
                continue
            if z == in_str:
                in_str = None
        elif z in "'\"`":
            in_str = z
        elif z == "/" and i + 1 < n and quelltext[i + 1] == "/":
            i = quelltext.find("\n", i)
            if i == -1:
                break
            continue
        elif z == "/" and i + 1 < n and quelltext[i + 1] == "*":
            i = quelltext.find("*/", i)
            if i == -1:
                break
            i += 2
            continue
        elif z in tiefe:
            tiefe[z] += 1
        elif z in paare:
            tiefe[paare[z]] -= 1
        i += 1
    return tiefe


def pruefe(ctx):
    befunde = []

    # ---------------------------------------------------------- Python-Module
    anzahl_py = 0
    for datei in ctx.python_dateien():
        anzahl_py += 1
        try:
            py_compile.compile(str(datei), doraise=True, cfile=tempfile.mktemp())
        except py_compile.PyCompileError as e:
            befunde.append(ctx.fehler(
                f"{datei.name}: Python-Syntaxfehler",
                str(e).strip()[:300],
            ))

    # ------------------------------------------------------------ JavaScript
    node_da = _node_pruefen(ctx.portal_js, "milcrid_portal.html (Skriptblock)", ctx, befunde)
    if node_da:
        _node_pruefen(ctx.main_js, "main.js", ctx, befunde)
        _node_pruefen(ctx.preload_js, "preload.js", ctx, befunde)
    else:
        befunde.append(ctx.hinweis(
            "node nicht erreichbar - JS-Syntax NICHT wirklich geprueft",
            "Weder lokal noch per SSH auf Milcrid. Unten laeuft nur der grobe "
            "Klammer-Zaehler, der bekannt unzuverlaessig ist (Regex-Literale).",
        ))
        for name, quelle in (("Portal-Skript", ctx.portal_js),
                             ("main.js", ctx.main_js),
                             ("preload.js", ctx.preload_js)):
            schief = {z: s for z, s in _balance(quelle).items() if s != 0}
            if schief:
                befunde.append(ctx.hinweis(
                    f"{name}: Klammer-Saldo {schief} (grobe Zaehlung)",
                    "Nur ein schwaches Indiz - Regex-Literale verfaelschen das "
                    "Ergebnis. Zur echten Pruefung node --check benutzen.",
                ))

    ctx.zaehle("Syntax", python_module=anzahl_py, node=("ja" if node_da else "fehlt"))
    return befunde
