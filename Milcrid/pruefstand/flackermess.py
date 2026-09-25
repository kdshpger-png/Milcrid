#!/usr/bin/env python3
"""Flackermessung (Opus 2026-09-19): filmt den Bildschirm (das, was die
Grafikkarte an den Monitor schickt) mit 60 Bildern/s, klickt in Sekunde 1,5
einen Seitenknopf und sucht danach Bilder, deren Helligkeit kurz ausreisst
(Blitz/Einbruch, der nach 1-4 Bildern wieder zurueckgeht).

    flackermess.py <name> <x> <y>
"""
import subprocess, sys, time, numpy as np, os
name, x, y = sys.argv[1], sys.argv[2], sys.argv[3]
B, H, FPS, SEK = 320, 180, 60, 7
raw = f"/dev/shm/flacker_{name}.rgb"
ff = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "x11grab", "-framerate", str(FPS),
                       "-video_size", "2560x1440", "-i", ":0.0", "-t", str(SEK),
                       "-vf", f"scale={B}:{H}", "-pix_fmt", "rgb24", "-f", "rawvideo", raw],
                      env={**os.environ, "DISPLAY": ":0"})
t0 = time.time()
time.sleep(1.5)
subprocess.run(["xdotool", "mousemove", x, y, "click", "1"], env={**os.environ, "DISPLAY": ":0"})
klick = time.time() - t0
subprocess.run(["xdotool", "mousemove", "1280", "200"], env={**os.environ, "DISPLAY": ":0"})
ff.wait()
d = np.fromfile(raw, dtype=np.uint8)
n = len(d) // (B * H * 3)
f = d[:n * B * H * 3].reshape(n, H, B, 3).astype(np.float32)
os.remove(raw)
hell = f.mean(axis=(1, 2, 3))                       # ganzes Bild
# 16 Kacheln (4x4): ein Blitz kann auch nur ein Stueck des Bildes treffen
kach = f.reshape(n, 4, H // 4, 4, B // 4, 3).mean(axis=(2, 4, 5)).reshape(n, 16)
print(f"{name}: {n} Bilder in {SEK} s (~{n/SEK:.0f}/s), Klick bei {klick:.2f} s")
funde = []
for i in range(1, n - 1):
    for k in range(16):
        vor, jetzt = kach[i - 1, k], kach[i, k]
        sprung = jetzt - vor
        if abs(sprung) < 6:
            continue
        # zurueck zum alten Wert innerhalb von 4 Bildern = kurzer Ausreisser
        spaeter = kach[i + 1:i + 5, k]
        if len(spaeter) and np.min(np.abs(spaeter - vor)) < 2.5:
            funde.append((i, k, vor, jetzt))
if not funde:
    print("   kein kurzer Ausreisser (Blitz/Einbruch) gefunden")
seen = set()
for i, k, vor, jetzt in funde:
    if (i, k) in seen: continue
    seen.add((i, k))
    print(f"   Bild {i:3d} ({i/FPS:5.2f} s): Kachel {k:2d} {vor:6.1f} -> {jetzt:6.1f} und gleich wieder zurueck")
# grober Verlauf ums Klicken herum
print("   Helligkeit je 0,25 s:", " ".join(f"{hell[i]:.1f}" for i in range(0, n, 15)))
stufen = [i for i in range(1, n) if abs(hell[i] - hell[i - 1]) > 0.3]
print("   Bilder mit Aenderung:", stufen[:30], "..." if len(stufen) > 30 else "")
