#!/usr/bin/env python3
# Liest fuer eine Liste von {schema, schluessel}-Paaren die kurze,
# UEBERSETZTE Beschriftung (GLib-Schema "summary") aus - im Unterschied zu
# "gsettings describe" (laengerer Erklaerungstext) oder dem rohen
# technischen Schluesselnamen (schluesselHuebschMachen in main.js, nur ein
# englischer Notbehelf ohne echte Uebersetzung).
#
# Aufruf: schluessel_namen.py '[{"schema": "...", "schluessel": "..."}, ...]'
# Ausgabe: JSON-Objekt {"schema::schluessel": "Uebersetzter Name", ...} -
# Paare ohne Treffer fehlen einfach (main.js faellt dann auf
# schluesselHuebschMachen zurueck).
import sys
import json
import locale

# Noetig, damit GLib die Schema-Uebersetzung (gettext) fuer die aktuelle
# Sprache tatsaechlich laedt - ohne das kommt get_summary() immer auf
# Englisch zurueck, selbst wenn LANG=de_DE.UTF-8 gesetzt ist.
locale.setlocale(locale.LC_ALL, '')

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio

paare = json.loads(sys.argv[1]) if len(sys.argv) > 1 else json.load(sys.stdin)

quelle = Gio.SettingsSchemaSource.get_default()
schema_cache = {}
ergebnis = {}

for eintrag in paare:
    schema_id = eintrag.get('schema')
    schluessel = eintrag.get('schluessel')
    if not schema_id or not schluessel:
        continue
    try:
        if schema_id not in schema_cache:
            schema_cache[schema_id] = quelle.lookup(schema_id, True)
        schema = schema_cache[schema_id]
        if schema is None:
            continue
        # WICHTIG: schema.get_key() fuer einen dort nicht existierenden
        # Schluessel loest keinen normalen Python-Fehler aus, sondern einen
        # GLib-Abbruch (Prozess stirbt sofort, try/except greift nicht).
        # Deshalb vorher mit has_key() (sicher, gibt nur True/False) pruefen.
        # Kommt vor bei "Basis"-Schemas wie org.gnome.desktop.break-reminders,
        # deren Schluessel gsettings nur bei den Unter-Schemas (.eyesight,
        # .movement, ...) wirklich hat.
        if not schema.has_key(schluessel):
            continue
        zusammenfassung = schema.get_key(schluessel).get_summary()
        if zusammenfassung:
            ergebnis[schema_id + '::' + schluessel] = zusammenfassung
    except Exception:
        continue

print(json.dumps(ergebnis))
