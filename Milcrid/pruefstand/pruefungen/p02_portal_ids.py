"""
Portal: tote Element-Verweise, doppelte IDs, verwaiste Knoepfe

getElementById auf ein Element, das es nicht (mehr) gibt, liefert null.
Der Fehler faellt erst auf, wenn jemand die Stelle benutzt - dann bricht
das ganze Skript ab ("Cannot read properties of null"), und ALLES was
danach in derselben Funktion stand, passiert nicht mehr.

Doppelte IDs sind heimtueckischer: getElementById nimmt immer das erste
Vorkommen. Zwei Elemente mit gleicher ID heisst, dass eines davon nie
angesprochen wird - es sieht aus wie ein "toter" Knopf.
"""
import re
from collections import Counter


def pruefe(ctx):
    js = ctx.portal_js
    html = ctx.portal_html_ohne_js
    befunde = []

    vorhandene = set(re.findall(r'(?<![-\w])id="([^"]+)"', html))
    # im JS dynamisch vergebene IDs
    dyn = set(re.findall(r"\.id\s*=\s*['\"]([A-Za-z0-9_-]+)['\"]", js))
    dyn_praefixe = set(re.findall(r"\.id\s*=\s*['\"]([A-Za-z0-9_]+)['\"]\s*\+", js))
    attr = set(re.findall(r"setAttribute\(\s*['\"]id['\"]\s*,\s*['\"]([^'\"]+)['\"]", js))
    # Vorlagen werden geklont (Datei Manager) - deren IDs stehen im Template
    vorlagen = set(re.findall(r'(?<![-\w])id="([^"]+)"', ctx.portal_html))
    alle = vorhandene | dyn | attr | vorlagen

    # ------------------------------------------------------ getElementById
    for name in sorted(set(re.findall(r"getElementById\(\s*['\"]([^'\"]+)['\"]\s*\)", js))):
        if name in alle:
            continue
        if any(name.startswith(p) for p in dyn_praefixe):
            continue
        fundstellen = ctx.portal_zeilen(f"getElementById('{name}')")
        befunde.append(ctx.fehler(
            f"getElementById('{name}') - dieses Element gibt es nicht",
            f"Liefert null; die Funktion bricht dort ab. Zeile(n): {fundstellen}",
        ))

    # ------------------------------------------------------- querySelector
    for name in sorted(set(re.findall(r"querySelector\(\s*['\"]#([A-Za-z0-9_-]+)['\"]", js))):
        if name not in alle and not any(name.startswith(p) for p in dyn_praefixe):
            befunde.append(ctx.fehler(
                f"querySelector('#{name}') - dieses Element gibt es nicht", ""))

    # --------------------------------------------------------- doppelte IDs
    for name, anzahl in sorted(Counter(re.findall(r'(?<![-\w])id="([^"]+)"', html)).items()):
        if anzahl > 1:
            befunde.append(ctx.fehler(
                f'id="{name}" kommt {anzahl}x vor',
                "getElementById findet nur das erste - das zweite Element ist "
                "vom Code aus unerreichbar (sieht aus wie ein toter Knopf).",
            ))

    # ------------------------------- Knoepfe im HTML, die nirgends benutzt werden
    knopf_ids = set(re.findall(r'<button[^>]*(?<![-\w])id="([^"]+)"', html))
    unbenutzt = sorted(k for k in knopf_ids
                       if k not in js and f'"{k}"' not in js and f"'{k}'" not in js)
    for k in unbenutzt:
        befunde.append(ctx.hinweis(
            f'Knopf id="{k}" wird im Skript nirgends angesprochen',
            "Entweder ohne Funktion (toter Knopf) oder nur ueber eine "
            "Sammel-Zuweisung erreicht.",
        ))

    ctx.zaehle("Portal-Elemente", ids=len(vorhandene), knoepfe=len(knopf_ids))
    return befunde
