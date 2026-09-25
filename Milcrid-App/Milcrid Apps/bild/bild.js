/* ---- Milcrid Bildbetrachter: ein Bild, Blaettern im selben Ordner, Zoomen,
   Verschieben, Drehen, Speichern. Eingeschlossen, damit kein Name mit dem
   Portal zusammenstoesst. ---- */
(() => {
  const M = window.milcrid || {};
  const $ = id => document.getElementById(id);
  const wurzel = document.querySelector('.bb');
  const flaeche = $('bbFlaeche'), bild = $('bbBild');
  const ENDUNGEN = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'avif', 'ico', 'tif', 'tiff'];
  // Nur diese kann ein Canvas ohne Verlust zurueckschreiben. GIF (Animation),
  // SVG (Vektor) & Co. gehen nur als neue PNG-Datei.
  const SPEICHERBAR = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', webp: 'image/webp' };

  let pfad = null, nachbarn = [], groesseBytes = 0;
  let s = 1, r = 0, px = 0, py = 0;     // Massstab, Drehung, Bildmitte auf der Flaeche
  let eingepasst = true;
  let meldungUhr = null;

  const dateiname = p => (p || '').split('/').pop();
  const endung = p => { const n = dateiname(p); const i = n.lastIndexOf('.'); return i > 0 ? n.slice(i + 1).toLowerCase() : ''; };
  const dateiUrl = p => 'file://' + p.split('/').map(encodeURIComponent).join('/');
  function groesseText(b){
    if (b < 1024) return b + ' B';
    const e = ['KB', 'MB', 'GB']; let w = b / 1024, i = 0;
    while (w >= 1024 && i < e.length - 1){ w /= 1024; i++; }
    return w.toLocaleString('de-DE', { maximumFractionDigits: w < 10 ? 1 : 0 }) + ' ' + e[i];
  }
  function meldung(t, art){
    clearTimeout(meldungUhr);
    const el = $('bbMeldung');
    el.textContent = t || '';
    el.className = art || '';
    if (t && art !== 'fehler') meldungUhr = setTimeout(() => meldung(''), 4000);
  }

  // ---- Darstellung ----------------------------------------------------------
  function zeichnen(){
    const w = bild.naturalWidth, h = bild.naturalHeight;
    bild.style.transformOrigin = `${w / 2}px ${h / 2}px`;
    bild.style.transform = `translate(${px - w / 2}px, ${py - h / 2}px) rotate(${r}deg) scale(${s})`;
    // Bei starker Vergroesserung Pixel scharf zeigen statt verwaschen.
    bild.classList.toggle('pixel', s >= 3);
    $('bbZoom').textContent = pfad ? Math.round(s * 100) + ' %' : '–';
    knoepfeStellen();
  }
  function gedrehteMasse(){
    return r % 180 ? [bild.naturalHeight, bild.naturalWidth] : [bild.naturalWidth, bild.naturalHeight];
  }
  function einpassen(){
    if (!pfad) return;
    const [bw, bh] = gedrehteMasse();
    const fw = flaeche.clientWidth, fh = flaeche.clientHeight;
    if (!bw || !bh || !fw || !fh) return;   // SVG ohne feste Groesse / Fenster noch unsichtbar
    // Wie bei Windows/Ubuntu: grosse Bilder verkleinern, kleine NICHT aufblasen.
    s = Math.min(1, (fw - 16) / bw, (fh - 16) / bh);
    px = fw / 2; py = fh / 2;
    eingepasst = true;
    zeichnen();
  }
  function zoomen(neu, mx, my){
    neu = Math.min(32, Math.max(0.02, neu));
    if (mx === undefined){ mx = flaeche.clientWidth / 2; my = flaeche.clientHeight / 2; }
    px = mx - (mx - px) * neu / s;
    py = my - (my - py) * neu / s;
    s = neu;
    eingepasst = false;
    zeichnen();
  }
  function originalgroesse(mx, my){ zoomen(1, mx, my); }

  function knoepfeStellen(){
    const i = nachbarn.indexOf(pfad);
    $('bbZurueck').disabled = !pfad || i <= 0;
    $('bbVor').disabled = !pfad || i < 0 || i >= nachbarn.length - 1;
    ['bbKleiner', 'bbGroesser', 'bbEinpassen', 'bbOriginal', 'bbLinks', 'bbRechts', 'bbSpeichernUnter']
      .forEach(id => { $(id).disabled = !pfad; });
    const speicherbar = !!SPEICHERBAR[endung(pfad)];
    $('bbSpeichern').disabled = !pfad || r === 0 || !speicherbar;
    $('bbSpeichern').title = !speicherbar && pfad
      ? 'Diese Bildart lässt sich nicht verlustfrei zurückschreiben – „Speichern unter“ legt eine PNG-Datei an.'
      : 'Gedrehtes Bild speichern (Strg+S)';
  }
  function infoZeichnen(){
    $('bbName').textContent = pfad ? pfad.replace(/^\/home\/[^/]+/, '~') : '';
    if (!pfad){ $('bbInfo').textContent = ''; return; }
    const i = nachbarn.indexOf(pfad);
    $('bbInfo').textContent = `${bild.naturalWidth} × ${bild.naturalHeight} Pixel · ${groesseText(groesseBytes)}`
                             + (nachbarn.length > 1 && i >= 0 ? ` · Bild ${i + 1} von ${nachbarn.length}` : '');
  }

  // ---- Laden ----------------------------------------------------------------
  async function laden(neuerPfad){
    if (!neuerPfad) return;
    meldung('');
    const info = M.dateiPfadPruefen ? await M.dateiPfadPruefen(neuerPfad) : { gibt_es: true, pfad: neuerPfad, groesse: 0 };
    if (!info.gibt_es){ meldung(`„${dateiname(neuerPfad)}“ gibt es nicht (mehr).`, 'fehler'); return; }
    pfad = info.pfad;
    groesseBytes = info.groesse || 0;
    r = 0;
    bild.hidden = true;
    $('bbLeer').hidden = true;
    // ?v= zwingt zum Neuladen nach dem Speichern (sonst zeigt Chromium das alte Bild).
    bild.src = dateiUrl(pfad) + '?v=' + Date.now();
    nachbarn = M.ordnerDateienMitEndung ? await M.ordnerDateienMitEndung(pfad, ENDUNGEN) : [pfad];
    knoepfeStellen();
  }
  bild.addEventListener('load', () => {
    bild.hidden = false;
    einpassen();
    infoZeichnen();
  });
  bild.addEventListener('error', () => {
    if (!pfad) return;
    bild.hidden = true;
    $('bbLeer').hidden = false;
    meldung(`„${dateiname(pfad)}“ lässt sich nicht anzeigen – kein Bild oder ein Format, das Milcrid nicht kennt.`, 'fehler');
  });
  function blaettern(richtung){
    const i = nachbarn.indexOf(pfad);
    const ziel = nachbarn[i + richtung];
    if (ziel) laden(ziel);
  }

  async function oeffnen(){
    const waehlen = M.dateiAuswaehlenArt || M.dateiAuswaehlen;
    if (!waehlen){ meldung('Öffnen geht nur in der Milcrid-App.', 'fehler'); return; }
    const pfade = await waehlen('bild');
    if (pfade && pfade.length) laden(pfade[0]);
  }

  // ---- Drehen und Speichern ---------------------------------------------------
  function drehen(grad){
    if (!pfad) return;
    r = (r + grad + 360) % 360;
    einpassen();
    meldung(r ? 'Gedreht – „Speichern“ übernimmt es in die Datei.' : '');
  }
  function alsDataUrl(mime){
    const w = bild.naturalWidth, h = bild.naturalHeight;
    const [cw, ch] = gedrehteMasse();
    const c = document.createElement('canvas');
    c.width = cw; c.height = ch;
    const g = c.getContext('2d');
    if (mime === 'image/jpeg'){ g.fillStyle = '#fff'; g.fillRect(0, 0, cw, ch); }  // JPG kennt keine Transparenz
    g.translate(cw / 2, ch / 2);
    g.rotate(r * Math.PI / 180);
    g.drawImage(bild, -w / 2, -h / 2);
    return c.toDataURL(mime, 0.92);
  }
  async function speichern(){
    const mime = SPEICHERBAR[endung(pfad)];
    if (!pfad || !r || !mime || !M.bildSpeichern) return;
    const antwort = await M.bildSpeichern(pfad, alsDataUrl(mime));
    if (!antwort.erfolg){ meldung('Nicht gespeichert: ' + antwort.fehler, 'fehler'); return; }
    await laden(pfad);
    meldung('Gespeichert.', 'erfolg');
  }
  async function speichernUnter(){
    if (!pfad || !M.bildSpeichernUnter) return;
    // Der Inhalt entsteht VOR dem Dialog - darum steht die Endung im Vorschlag
    // fest: JPG/PNG/WEBP bleiben, alles andere wird PNG.
    const e = endung(pfad);
    const mime = SPEICHERBAR[e] || 'image/png';
    const basis = pfad.slice(0, pfad.length - e.length - (e ? 1 : 0));
    const vorschlag = `${basis}${r ? '_gedreht' : '_kopie'}.${SPEICHERBAR[e] ? e : 'png'}`;
    const antwort = await M.bildSpeichernUnter(vorschlag, alsDataUrl(mime));
    if (antwort.abgebrochen) return;
    if (!antwort.erfolg){ meldung('Nicht gespeichert: ' + antwort.fehler, 'fehler'); return; }
    await laden(antwort.pfad);
    meldung('Als neue Datei gespeichert.', 'erfolg');
  }

  // ---- Maus -------------------------------------------------------------------
  flaeche.addEventListener('wheel', ev => {
    if (!pfad) return;
    ev.preventDefault();
    const b = flaeche.getBoundingClientRect();
    zoomen(s * (ev.deltaY < 0 ? 1.15 : 1 / 1.15), ev.clientX - b.left, ev.clientY - b.top);
  }, { passive: false });
  let zug = null;
  flaeche.addEventListener('mousedown', ev => {
    if (!pfad || ev.button !== 0) return;
    zug = { x: ev.clientX, y: ev.clientY, px, py };
    flaeche.classList.add('zieht');
    wurzel.focus({ preventScroll: true });
  });
  window.addEventListener('mousemove', ev => {
    if (!zug) return;
    px = zug.px + ev.clientX - zug.x;
    py = zug.py + ev.clientY - zug.y;
    eingepasst = false;
    zeichnen();
  });
  window.addEventListener('mouseup', () => { zug = null; flaeche.classList.remove('zieht'); });
  flaeche.addEventListener('dblclick', ev => {
    if (!pfad) return;
    const b = flaeche.getBoundingClientRect();
    if (eingepasst) originalgroesse(ev.clientX - b.left, ev.clientY - b.top);
    else einpassen();
  });
  // Fenster groesser/kleiner gezogen: eingepasste Bilder passen sich mit an.
  new ResizeObserver(() => { if (pfad && eingepasst) einpassen(); }).observe(flaeche);

  // ---- Tastatur ---------------------------------------------------------------
  wurzel.addEventListener('keydown', ev => {
    const strg = ev.ctrlKey || ev.metaKey;
    const t = ev.key;
    let erledigt = true;
    if (strg && t.toLowerCase() === 's') ev.shiftKey ? speichernUnter() : speichern();
    else if (strg && t.toLowerCase() === 'o') oeffnen();
    else if (t === 'ArrowLeft') blaettern(-1);
    else if (t === 'ArrowRight') blaettern(1);
    else if (t === '+' || t === '=') zoomen(s * 1.25);
    else if (t === '-') zoomen(s / 1.25);
    else if (t === '0') einpassen();
    else if (t === '1') originalgroesse();
    else if (t.toLowerCase() === 'r') drehen(ev.shiftKey ? -90 : 90);
    else erledigt = false;
    if (erledigt) ev.preventDefault();
  });

  $('bbOeffnen').addEventListener('click', oeffnen);
  $('bbZurueck').addEventListener('click', () => blaettern(-1));
  $('bbVor').addEventListener('click', () => blaettern(1));
  $('bbKleiner').addEventListener('click', () => zoomen(s / 1.25));
  $('bbGroesser').addEventListener('click', () => zoomen(s * 1.25));
  $('bbEinpassen').addEventListener('click', einpassen);
  $('bbOriginal').addEventListener('click', () => originalgroesse());
  $('bbLinks').addEventListener('click', () => drehen(-90));
  $('bbRechts').addEventListener('click', () => drehen(90));
  $('bbSpeichern').addEventListener('click', speichern);
  $('bbSpeichernUnter').addEventListener('click', speichernUnter);

  window.milcridBild = { oeffnen: p => { laden(p); wurzel.focus({ preventScroll: true }); } };
  knoepfeStellen();
  // Zum Oeffnen einer Datei gestartet? Siehe milcridAppMitDatei im Portal.
  const wartend = (window.milcridOeffnenWartend || {}).bild;
  if (wartend){ delete window.milcridOeffnenWartend.bild; laden(wartend); }
})();
