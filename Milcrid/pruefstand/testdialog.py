#!/usr/bin/env python3
"""Ein Testfenster, das sich wie ein ECHTER Dialog verhaelt.

Warum es das braucht (Fund 20.09.2026): die erste Messung lief mit xmessage -
und xmessage kennt Escape ueberhaupt nicht. Fuenf Laeufe meldeten "nicht
abgebrochen", obwohl dialog_abbrechen jedes Mal sauber ausgefuehrt hat. Der
Test hat also das Falsche gemessen. Jeder echte Dialog (GTK, Qt, LibreOffice)
schliesst bei Escape - dieses Fenster tut dasselbe und ist damit eine faire
Probe.
"""
import sys
import tkinter as tk

titel = sys.argv[1] if len(sys.argv) > 1 else "Software-Aktualisierung"
text = sys.argv[2] if len(sys.argv) > 2 else (
    "Ein Update ist verfügbar.\nSoll die Aktualisierung jetzt installiert werden?")

w = tk.Tk()
w.title(titel)
w.geometry("520x180+900+500")
tk.Label(w, text=text, wraplength=480, justify="left", pady=20).pack()
rahmen = tk.Frame(w)
rahmen.pack(pady=10)
tk.Button(rahmen, text="Jetzt installieren", width=18).pack(side="left", padx=6)
tk.Button(rahmen, text="Später", width=12, command=w.destroy).pack(side="left", padx=6)
# Genau das macht jeder echte Dialog: Escape = abbrechen/später.
w.bind("<Escape>", lambda e: w.destroy())
w.mainloop()
