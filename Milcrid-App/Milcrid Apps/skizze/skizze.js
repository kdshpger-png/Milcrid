/* ---- Milcrid Skizze: Zeichnung als Liste von Objekten (nicht als Pixel) -
   daraus wird die Flaeche UND das PNG gezeichnet, Objekte lassen sich
   verschieben und einzeln radieren. Eingeschlossen, damit kein Name mit dem
   Portal zusammenstoesst. ---- */
(() => {
  const S = window.milcridSkizze;
  const $ = id => document.getElementById(id);
  const app = $('skApp'), flaeche = $('skFlaeche'), canvas = $('skCanvas'), ctx = canvas.getContext('2d');
  const RASTER = 20;
  const FARBEN = ['#111111', '#7d8595', '#e53935', '#fb8c00', '#fdd835', '#43a047', '#1e88e5', '#8e24aa'];
  const WERKZEUGE = [
    ['stift', '✎', 'Stift'], ['linie', '╱', 'Linie'], ['pfeil', '➝', 'Pfeil'], ['rechteck', '▭', 'Rechteck'],
    ['rund', '▢', 'Abgerundet'], ['ellipse', '◯', 'Ellipse'], ['text', 'T', 'Text'],
    ['verschieben', '✥', 'Verschieben'], ['radierer', '⌫', 'Radierer'],
  ];

  let objekte = [];
  let verlaufZurueck = [], verlaufVor = [];
  let werkzeug = 'stift', farbe = FARBEN[0], staerke = 3, fuellung = false, raster = true;
  let zug = null;            // laufender Maus-Zug
  let gewaehlt = null;       // Objekt beim Verschieben
  let geaendert = false;     // seit dem letzten Speichern/Oeffnen
  let skizzen = [];
  let ordner = '';
  const scharf = {};         // zweistufige Knoepfe: id -> Zeitgeber

  function status(text, art){
    $('skStatus').textContent = text || '';
    $('skStatus').className = 'sk-status' + (art ? ' ' + art : '');
  }
  // Zweimal klicken fuer alles, was sich nicht zuruecknehmen laesst
  function zweistufig(id, frage, aktion){
    const knopf = $(id);
    if (!scharf[id]){
      knopf.dataset.text = knopf.textContent;
      knopf.textContent = frage;
      scharf[id] = setTimeout(() => { knopf.textContent = knopf.dataset.text; delete scharf[id]; }, 4000);
      return;
    }
    clearTimeout(scharf[id]);
    delete scharf[id];
    knopf.textContent = knopf.dataset.text;
    aktion();
  }

  // ---------- Verlauf ----------
  function merken(){
    verlaufZurueck.push(JSON.stringify(objekte));
    if (verlaufZurueck.length > 100) verlaufZurueck.shift();
    verlaufVor = [];
    geaendert = true;
    knoepfeAuffrischen();
  }
  function zurueck(){
    if (!verlaufZurueck.length) return;
    verlaufVor.push(JSON.stringify(objekte));
    objekte = JSON.parse(verlaufZurueck.pop());
    gewaehlt = null; geaendert = true; zeichnen(); knoepfeAuffrischen();
  }
  function vor(){
    if (!verlaufVor.length) return;
    verlaufZurueck.push(JSON.stringify(objekte));
    objekte = JSON.parse(verlaufVor.pop());
    gewaehlt = null; geaendert = true; zeichnen(); knoepfeAuffrischen();
  }
  function knoepfeAuffrischen(){
    $('skZurueck').disabled = !verlaufZurueck.length;
    $('skVor').disabled = !verlaufVor.length;
  }

  // ---------- Zeichnen ----------
  function textSchrift(o){ return `${o.groesse}px system-ui, sans-serif`; }

  function objektZeichnen(c, o){
    c.strokeStyle = o.farbe; c.fillStyle = o.farbe; c.lineWidth = o.staerke;
    c.lineCap = 'round'; c.lineJoin = 'round';
    const x = Math.min(o.x1, o.x2), y = Math.min(o.y1, o.y2), b = Math.abs(o.x2 - o.x1), h = Math.abs(o.y2 - o.y1);
    c.beginPath();
    if (o.art === 'stift'){
      o.punkte.forEach(([px, py], i) => i ? c.lineTo(px, py) : c.moveTo(px, py));
      if (o.punkte.length === 1) c.lineTo(o.punkte[0][0] + 0.1, o.punkte[0][1]);
      c.stroke();
    } else if (o.art === 'linie' || o.art === 'pfeil'){
      c.moveTo(o.x1, o.y1); c.lineTo(o.x2, o.y2); c.stroke();
      if (o.art === 'pfeil'){
        const winkel = Math.atan2(o.y2 - o.y1, o.x2 - o.x1), l = 10 + o.staerke * 2.5;
        c.beginPath();
        c.moveTo(o.x2, o.y2);
        c.lineTo(o.x2 - l * Math.cos(winkel - 0.45), o.y2 - l * Math.sin(winkel - 0.45));
        c.moveTo(o.x2, o.y2);
        c.lineTo(o.x2 - l * Math.cos(winkel + 0.45), o.y2 - l * Math.sin(winkel + 0.45));
        c.stroke();
      }
    } else if (o.art === 'rechteck' || o.art === 'rund'){
      if (o.art === 'rund') c.roundRect(x, y, b, h, Math.min(16, b / 2, h / 2));
      else c.rect(x, y, b, h);
      if (o.fuellung) c.fill(); else c.stroke();
    } else if (o.art === 'ellipse'){
      c.ellipse(x + b / 2, y + h / 2, b / 2, h / 2, 0, 0, Math.PI * 2);
      if (o.fuellung) c.fill(); else c.stroke();
    } else if (o.art === 'text'){
      c.font = textSchrift(o);
      c.textBaseline = 'top';
      o.zeilen = String(o.text).split('\n');
      o.breite = Math.max(...o.zeilen.map(z => c.measureText(z).width));
      o.zeilen.forEach((z, i) => c.fillText(z, o.x, o.y + i * o.groesse * 1.25));
    }
  }

  function alleZeichnen(c, breite, hoehe, mitRaster){
    c.fillStyle = '#ffffff';
    c.fillRect(0, 0, breite, hoehe);
    if (mitRaster){
      c.strokeStyle = '#e8edf5'; c.lineWidth = 1;
      c.beginPath();
      for (let x = RASTER; x < breite; x += RASTER){ c.moveTo(x + 0.5, 0); c.lineTo(x + 0.5, hoehe); }
      for (let y = RASTER; y < hoehe; y += RASTER){ c.moveTo(0, y + 0.5); c.lineTo(breite, y + 0.5); }
      c.stroke();
    }
    objekte.forEach(o => objektZeichnen(c, o));
  }

  function zeichnen(){
    const dpr = window.devicePixelRatio || 1;
    const b = flaeche.clientWidth, h = flaeche.clientHeight;
    if (canvas.width !== Math.round(b * dpr) || canvas.height !== Math.round(h * dpr)){
      canvas.width = Math.round(b * dpr);
      canvas.height = Math.round(h * dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    alleZeichnen(ctx, b, h, raster);
    if (zug && zug.vorschau) objektZeichnen(ctx, zug.vorschau);
    if (gewaehlt){
      const r = rahmen(gewaehlt);
      ctx.save();
      ctx.setLineDash([5, 4]); ctx.strokeStyle = '#2f7bff'; ctx.lineWidth = 1.5;
      ctx.strokeRect(r.x - 6, r.y - 6, r.b + 12, r.h + 12);
      ctx.restore();
    }
  }
  // Das Raster zeichnet sich bei jeder Groessenaenderung neu (Geminis Fassung
  // zeigte es erst nach dem ersten Strich, weil die Groesse beim Start 1 war).
  new ResizeObserver(zeichnen).observe(flaeche);

  // ---------- Treffer (Radierer, Verschieben) ----------
  function rahmen(o){
    if (o.art === 'stift'){
      const xs = o.punkte.map(p => p[0]), ys = o.punkte.map(p => p[1]);
      return { x: Math.min(...xs), y: Math.min(...ys), b: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) };
    }
    if (o.art === 'text'){
      if (o.breite === undefined) { ctx.font = textSchrift(o); o.breite = ctx.measureText(o.text).width; }
      return { x: o.x, y: o.y, b: o.breite, h: String(o.text).split('\n').length * o.groesse * 1.25 };
    }
    return { x: Math.min(o.x1, o.x2), y: Math.min(o.y1, o.y2), b: Math.abs(o.x2 - o.x1), h: Math.abs(o.y2 - o.y1) };
  }
  function abstandStrecke(px, py, x1, y1, x2, y2){
    const dx = x2 - x1, dy = y2 - y1, l = dx * dx + dy * dy;
    const t = l ? Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / l)) : 0;
    return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
  }
  // Getroffen wird die Linie selbst, nicht der Rahmen drumherum (bei Gemini
  // loeschte der Radierer eine schraege Linie schon neben ihr).
  function trifft(o, px, py){
    const tol = o.staerke / 2 + 6;
    if (o.art === 'stift'){
      if (o.punkte.length === 1) return Math.hypot(px - o.punkte[0][0], py - o.punkte[0][1]) <= tol;
      return o.punkte.some((p, i) => i && abstandStrecke(px, py, ...o.punkte[i - 1], ...p) <= tol);
    }
    if (o.art === 'linie' || o.art === 'pfeil') return abstandStrecke(px, py, o.x1, o.y1, o.x2, o.y2) <= tol;
    const r = rahmen(o);
    if (o.art === 'text') return px >= r.x - 4 && px <= r.x + r.b + 4 && py >= r.y - 4 && py <= r.y + r.h + 4;
    if (o.art === 'ellipse'){
      const rx = r.b / 2, ry = r.h / 2;
      if (rx < 1 || ry < 1) return false;
      const d = Math.hypot((px - r.x - rx) / rx, (py - r.y - ry) / ry);
      return o.fuellung ? d <= 1 + tol / Math.min(rx, ry) : Math.abs(d - 1) * Math.min(rx, ry) <= tol;
    }
    const innen = px >= r.x - tol && px <= r.x + r.b + tol && py >= r.y - tol && py <= r.y + r.h + tol;
    if (o.fuellung || !innen) return innen;
    return px <= r.x + tol || px >= r.x + r.b - tol || py <= r.y + tol || py >= r.y + r.h - tol;
  }
  function oberstesObjekt(px, py){
    for (let i = objekte.length - 1; i >= 0; i--) if (trifft(objekte[i], px, py)) return objekte[i];
    return null;
  }

  // ---------- Maus ----------
  const einrasten = v => raster ? Math.round(v / RASTER) * RASTER : v;
  function punkt(ev){
    const r = canvas.getBoundingClientRect();
    // Das Portal ist per CSS skaliert - darum ueber die sichtbare Groesse rechnen
    return [(ev.clientX - r.left) * flaeche.clientWidth / r.width, (ev.clientY - r.top) * flaeche.clientHeight / r.height];
  }

  canvas.addEventListener('pointerdown', ev => {
    if (ev.button !== 0) return;
    textFeldAbschliessen();
    const [px, py] = punkt(ev);
    canvas.setPointerCapture(ev.pointerId);
    if (werkzeug === 'text'){ textFeldZeigen(einrasten(px), einrasten(py)); return; }
    if (werkzeug === 'radierer'){
      zug = { art: 'radierer', gemerkt: false };
      radieren(px, py);
      return;
    }
    if (werkzeug === 'verschieben'){
      gewaehlt = oberstesObjekt(px, py);
      zug = gewaehlt ? { art: 'verschieben', x: px, y: py, gemerkt: false } : null;
      zeichnen();
      return;
    }
    const grund = { farbe, staerke };
    if (werkzeug === 'stift') zug = { art: 'stift', vorschau: Object.assign({ art: 'stift', punkte: [[px, py]] }, grund) };
    else {
      const x = einrasten(px), y = einrasten(py);
      zug = { art: werkzeug, vorschau: Object.assign({ art: werkzeug, x1: x, y1: y, x2: x, y2: y, fuellung }, grund) };
    }
    gewaehlt = null;
    zeichnen();
  });

  canvas.addEventListener('pointermove', ev => {
    if (!zug) return;
    const [px, py] = punkt(ev);
    if (zug.art === 'radierer'){ radieren(px, py); return; }
    if (zug.art === 'verschieben'){
      const dx = px - zug.x, dy = py - zug.y;
      if (!dx && !dy) return;
      if (!zug.gemerkt){ merken(); zug.gemerkt = true; }
      if (gewaehlt.art === 'stift') gewaehlt.punkte = gewaehlt.punkte.map(([x, y]) => [x + dx, y + dy]);
      else if (gewaehlt.art === 'text'){ gewaehlt.x += dx; gewaehlt.y += dy; }
      else { gewaehlt.x1 += dx; gewaehlt.x2 += dx; gewaehlt.y1 += dy; gewaehlt.y2 += dy; }
      zug.x = px; zug.y = py;
      zeichnen();
      return;
    }
    const v = zug.vorschau;
    if (v.art === 'stift') v.punkte.push([Math.round(px * 10) / 10, Math.round(py * 10) / 10]);
    else { v.x2 = einrasten(px); v.y2 = einrasten(py); }
    zeichnen();
  });

  function zugBeenden(){
    if (!zug) return;
    const v = zug.vorschau;
    zug = null;
    if (v){
      const leer = v.art === 'stift' ? false : (v.x1 === v.x2 && v.y1 === v.y2);
      if (!leer){ merken(); objekte.push(v); }
    }
    zeichnen();
  }
  canvas.addEventListener('pointerup', zugBeenden);
  canvas.addEventListener('pointercancel', zugBeenden);

  function radieren(px, py){
    const o = oberstesObjekt(px, py);
    if (!o) return;
    if (!zug.gemerkt){ merken(); zug.gemerkt = true; }   // ein Zug = ein Rückgängig
    objekte.splice(objekte.indexOf(o), 1);
    zeichnen();
  }

  // ---------- Text: eigenes Feld auf der Flaeche (prompt() gibt es in Electron nicht) ----------
  let textFeld = null;
  function textFeldZeigen(x, y){
    textFeld = document.createElement('textarea');
    textFeld.className = 'sk-textfeld';
    textFeld.rows = 1;
    const groesse = 12 + staerke * 2;
    Object.assign(textFeld.style, { left: x + 'px', top: y + 'px', fontSize: groesse + 'px', color: farbe });
    textFeld.dataset.x = x; textFeld.dataset.y = y; textFeld.dataset.groesse = groesse; textFeld.dataset.farbe = farbe;
    textFeld.placeholder = 'Text – Enter fertig';
    flaeche.append(textFeld);
    textFeld.addEventListener('keydown', ev => {
      ev.stopPropagation();
      if (ev.key === 'Enter' && !ev.shiftKey){ ev.preventDefault(); textFeldAbschliessen(); }
      if (ev.key === 'Escape'){ textFeld.value = ''; textFeldAbschliessen(); }
    });
    textFeld.addEventListener('blur', () => setTimeout(textFeldAbschliessen, 0));
    setTimeout(() => textFeld && textFeld.focus(), 0);
  }
  function textFeldAbschliessen(){
    if (!textFeld) return;
    const feld = textFeld;
    textFeld = null;
    const text = feld.value.replace(/\s+$/, '');
    if (text){
      merken();
      objekte.push({ art: 'text', x: +feld.dataset.x, y: +feld.dataset.y, text, farbe: feld.dataset.farbe,
                     groesse: +feld.dataset.groesse, staerke: 1 });
    }
    feld.remove();
    zeichnen();
  }

  // ---------- Leisten ----------
  FARBEN.forEach(f => {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'sk-farbe'; b.style.background = f; b.title = f; b.dataset.farbe = f;
    b.addEventListener('click', () => farbeSetzen(f));
    $('skFarben').append(b);
  });
  const eigene = document.createElement('input');
  eigene.type = 'color'; eigene.className = 'sk-eigene'; eigene.title = 'Eigene Farbe';
  eigene.addEventListener('input', () => farbeSetzen(eigene.value));
  $('skFarben').append(eigene);
  function farbeSetzen(f){
    farbe = f;
    document.querySelectorAll('.sk-farbe').forEach(b => b.classList.toggle('gewaehlt', b.dataset.farbe === f));
    if (gewaehlt){ merken(); gewaehlt.farbe = f; zeichnen(); }
  }
  farbeSetzen(farbe);

  WERKZEUGE.forEach(([id, zeichen, name]) => {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'sk-werkzeug'; b.dataset.werkzeug = id; b.title = name;
    const s = document.createElement('span'); s.textContent = zeichen;
    const n = document.createElement('b'); n.textContent = name; n.style.fontWeight = 'inherit';
    b.append(s, n);
    b.addEventListener('click', () => werkzeugSetzen(id));
    $('skWerkzeuge').append(b);
  });
  function werkzeugSetzen(id){
    textFeldAbschliessen();
    werkzeug = id;
    if (id !== 'verschieben') gewaehlt = null;
    document.querySelectorAll('.sk-werkzeug').forEach(b => b.classList.toggle('gewaehlt', b.dataset.werkzeug === id));
    canvas.style.cursor = { verschieben: 'move', text: 'text', radierer: 'cell' }[id] || 'crosshair';
    zeichnen();
  }
  werkzeugSetzen('stift');

  $('skStaerke').addEventListener('input', () => {
    staerke = +$('skStaerke').value;
    $('skStaerkeWert').textContent = staerke;
  });
  $('skFuellung').addEventListener('click', () => { fuellung = !fuellung; $('skFuellung').classList.toggle('an', fuellung); });
  $('skRaster').addEventListener('click', () => { raster = !raster; $('skRaster').classList.toggle('an', raster); zeichnen(); });
  $('skZurueck').addEventListener('click', zurueck);
  $('skVor').addEventListener('click', vor);
  $('skLeeren').addEventListener('click', () => zweistufig('skLeeren', 'Wirklich alles löschen?', () => {
    if (!objekte.length) return;
    merken(); objekte = []; gewaehlt = null; zeichnen(); status('Alles gelöscht – mit ↶ zurückholbar.');
  }));

  // Tasten nur, wenn diese App den Fokus hat - das Portal selbst bleibt unberuehrt
  app.addEventListener('keydown', ev => {
    if (ev.target.closest('input, textarea, select')) return;
    const taste = ev.key.toLowerCase();
    if ((ev.ctrlKey || ev.metaKey) && taste === 'z' && !ev.shiftKey){ ev.preventDefault(); zurueck(); }
    else if ((ev.ctrlKey || ev.metaKey) && (taste === 'y' || (taste === 'z' && ev.shiftKey))){ ev.preventDefault(); vor(); }
    else if ((ev.key === 'Delete' || ev.key === 'Backspace') && gewaehlt){
      ev.preventDefault(); merken(); objekte.splice(objekte.indexOf(gewaehlt), 1); gewaehlt = null; zeichnen();
    }
  });
  canvas.addEventListener('pointerdown', () => app.focus({ preventScroll: true }));

  // ---------- Bild ----------
  // Weisser Hintergrund, kein Raster, doppelte Aufloesung (gut lesbar fuer die
  // KI), mindestens so gross, dass alle Objekte draufpassen.
  function alsPng(){
    let b = flaeche.clientWidth, h = flaeche.clientHeight;
    objekte.forEach(o => { const r = rahmen(o); b = Math.max(b, r.x + r.b + 20); h = Math.max(h, r.y + r.h + 20); });
    const faktor = Math.min(2, 2400 / b);
    const bild = document.createElement('canvas');
    bild.width = Math.round(b * faktor); bild.height = Math.round(h * faktor);
    const c = bild.getContext('2d');
    c.setTransform(faktor, 0, 0, faktor, 0, 0);
    alleZeichnen(c, b, h, false);
    return bild.toDataURL('image/png');
  }

  // ---------- Speichern / Oeffnen ----------
  function listeZeichnen(){
    const liste = $('skListe');
    const vorher = liste.value;
    liste.textContent = '';
    const kopf = document.createElement('option');
    kopf.value = ''; kopf.textContent = skizzen.length ? 'Öffnen …' : 'noch nichts gespeichert';
    liste.append(kopf);
    skizzen.forEach(s => { const o = document.createElement('option'); o.value = s.name; o.textContent = s.name; liste.append(o); });
    liste.value = skizzen.some(s => s.name === vorher) ? vorher : '';
    $('skLoeschen').hidden = !liste.value;
  }
  function infoUebernehmen(antwort){
    if (antwort && antwort.skizzen){ skizzen = antwort.skizzen; ordner = antwort.ordner; listeZeichnen(); }
  }

  async function speichern(ueberschreiben){
    textFeldAbschliessen();
    const name = $('skName').value.trim();
    if (!name){ status('Bitte oben links einen Namen eingeben.', 'fehler'); $('skName').focus(); return; }
    status('Speichere …');
    const antwort = await S.speichern(name, objekte, $('skBeschreibung').value, alsPng(), ueberschreiben);
    infoUebernehmen(antwort);
    if (antwort.gibt_es_schon){
      status(antwort.fehler, 'fehler');
      const knopf = $('skSpeichern');
      knopf.textContent = 'Überschreiben';
      knopf.classList.add('warnung');
      knopf.dataset.ueberschreiben = '1';
      setTimeout(() => { knopf.textContent = 'Speichern'; knopf.classList.remove('warnung'); delete knopf.dataset.ueberschreiben; }, 5000);
      return;
    }
    if (!antwort.erfolg){ status(antwort.fehler, 'fehler'); return; }
    $('skName').value = antwort.name;
    geaendert = false;
    status(antwort.meldung, 'erfolg');
  }
  $('skSpeichern').addEventListener('click', () => {
    const ueber = !!$('skSpeichern').dataset.ueberschreiben;
    if (ueber){ $('skSpeichern').textContent = 'Speichern'; $('skSpeichern').classList.remove('warnung'); delete $('skSpeichern').dataset.ueberschreiben; }
    speichern(ueber);
  });

  let oeffnenScharf = null;
  $('skListe').addEventListener('change', async () => {
    const name = $('skListe').value;
    $('skLoeschen').hidden = !name;
    if (!name) return;
    if (geaendert && oeffnenScharf !== name){
      oeffnenScharf = name;
      status('Die aktuelle Zeichnung ist nicht gespeichert – zum Verwerfen dieselbe Skizze nochmal wählen.', 'fehler');
      $('skListe').value = '';
      $('skLoeschen').hidden = true;
      return;
    }
    oeffnenScharf = null;
    const antwort = await S.laden(name);
    infoUebernehmen(antwort);
    if (!antwort.erfolg){ status(antwort.fehler, 'fehler'); return; }
    objekte = antwort.objekte; verlaufZurueck = []; verlaufVor = []; gewaehlt = null; geaendert = false;
    $('skName').value = antwort.name;
    $('skBeschreibung').value = antwort.beschreibung || '';
    $('skListe').value = name;
    $('skLoeschen').hidden = false;
    knoepfeAuffrischen(); zeichnen();
    status(`„${antwort.name}“ geöffnet.`, 'erfolg');
  });
  $('skLoeschen').addEventListener('click', () => {
    const name = $('skListe').value;
    if (!name) return;
    zweistufig('skLoeschen', `„${name}“ wirklich löschen?`, async () => {
      const antwort = await S.loeschen(name);
      infoUebernehmen(antwort);
      status(antwort.erfolg ? antwort.meldung : antwort.fehler, antwort.erfolg ? 'erfolg' : 'fehler');
    });
  });
  $('skNeu').addEventListener('click', () => {
    const neu = () => {
      objekte = []; verlaufZurueck = []; verlaufVor = []; gewaehlt = null; geaendert = false;
      $('skName').value = ''; $('skBeschreibung').value = ''; $('skListe').value = ''; $('skLoeschen').hidden = true;
      knoepfeAuffrischen(); zeichnen(); status('Neue Skizze.');
    };
    if (geaendert && objekte.length) zweistufig('skNeu', 'Verwerfen?', neu); else neu();
  });
  $('skOrdner').addEventListener('click', async () => {
    if (!(ordner && window.milcrid && window.milcrid.dateiOeffnen)){ status('Ordner: Documents/Skizzen'); return; }
    const fehler = await window.milcrid.dateiOeffnen(ordner);
    if (fehler) status(fehler, 'fehler');
  });

  // ---------- An die KI ----------
  function frageText(){
    const eigenes = $('skBeschreibung').value.trim();
    return eigenes || 'Schau dir meine Skizze an – was könnte daraus werden?';
  }
  async function bildAblegen(){
    textFeldAbschliessen();
    if (!objekte.length){ status('Die Zeichenfläche ist leer.', 'fehler'); return null; }
    const antwort = await S.fuerKi(alsPng(), $('skBeschreibung').value, $('skName').value.trim());
    infoUebernehmen(antwort);
    if (!antwort.erfolg){ status(antwort.fehler, 'fehler'); return null; }
    return antwort.bild;
  }

  $('skLokal').addEventListener('click', async () => {
    const bild = await bildAblegen();
    if (!bild) return;
    if (S.chatMitBild(`Meine Skizze aus Milcrid Skizze: ${frageText()}`, [bild])) {
      status('An die lokale KI geschickt – die Antwort kommt im Milcrid-Chat.', 'erfolg');
    } else {
      status('Milcrid ist gerade nicht verbunden.', 'fehler');
    }
  });

  $('skOnline').addEventListener('click', async () => {
    const K = window.milcridOnlineKi;
    const stand = await K.holen();
    const daten = stand.daten || K.daten;
    if (!daten || !daten.verbindung.offen){
      K.chatOeffnen();
      status('Die Verbindung zur Online-KI ist aus – im Fenster Online KI einschalten, dann nochmal senden.', 'fehler');
      return;
    }
    if (daten.beschaeftigt){ status('Die Online-KI beantwortet gerade noch etwas anderes.', 'fehler'); return; }
    const bild = await bildAblegen();
    if (!bild) return;
    K.chatOeffnen();
    status('Geht an die Online-KI … die Antwort kommt im Fenster Online KI.');
    const unterwegs = K.senden(frageText(), [bild]);
    setTimeout(() => K.holen(), 500);   // damit das Chatfenster "antwortet …" zeigt
    const antwort = await unterwegs;
    status(antwort.erfolg ? 'Die Online-KI hat geantwortet – siehe Fenster Online KI.' : antwort.fehler,
           antwort.erfolg ? 'erfolg' : 'fehler');
  });

  knoepfeAuffrischen();
  S.info().then(infoUebernehmen);
})();
