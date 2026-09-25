/* ---- Milcrid Video: Videos und Musik abspielen, Blaettern im selben Ordner,
   Tempo, Vollbild. Was Chromium nicht kann, geht mit einem Klick an VLC.
   Eingeschlossen, damit kein Name mit dem Portal zusammenstoesst. ---- */
(() => {
  const M = window.milcrid || {};
  const $ = id => document.getElementById(id);
  const wurzel = document.querySelector('.vp');
  const video = $('vpVideo');
  const VIDEO = ['mp4', 'webm', 'mkv', 'mov', 'm4v', 'ogv', 'avi'];
  const MUSIK = ['mp3', 'ogg', 'oga', 'wav', 'flac', 'm4a', 'opus', 'aac'];
  const ALLE = [...VIDEO, ...MUSIK];

  let pfad = null, nachbarn = [], groesseBytes = 0;
  let meldungUhr = null;

  const dateiname = p => (p || '').split('/').pop();
  const endung = p => { const n = dateiname(p); const i = n.lastIndexOf('.'); return i > 0 ? n.slice(i + 1).toLowerCase() : ''; };
  const istMusik = p => MUSIK.includes(endung(p));
  const dateiUrl = p => 'file://' + p.split('/').map(encodeURIComponent).join('/');
  function zeitText(sek){
    if (!isFinite(sek)) return '–';
    sek = Math.round(sek);
    const h = Math.floor(sek / 3600), m = Math.floor(sek % 3600 / 60), s = sek % 60;
    return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(s).padStart(2, '0');
  }
  function groesseText(b){
    if (b < 1024) return b + ' B';
    const e = ['KB', 'MB', 'GB']; let w = b / 1024, i = 0;
    while (w >= 1024 && i < e.length - 1){ w /= 1024; i++; }
    return w.toLocaleString('de-DE', { maximumFractionDigits: w < 10 ? 1 : 0 }) + ' ' + e[i];
  }
  function meldung(t, art){
    clearTimeout(meldungUhr);
    $('vpMeldung').textContent = t || '';
    $('vpMeldung').className = art || '';
    if (t && art !== 'fehler') meldungUhr = setTimeout(() => meldung(''), 4000);
  }

  function knoepfeStellen(){
    const i = nachbarn.indexOf(pfad);
    $('vpZurueck').disabled = !pfad || i <= 0;
    $('vpVor').disabled = !pfad || i < 0 || i >= nachbarn.length - 1;
    $('vpSpielen').disabled = !pfad;
    $('vpVollbild').disabled = !pfad || istMusik(pfad);
    $('vpSpielen').textContent = video.paused ? '▶' : '⏸';
  }
  function infoZeichnen(){
    $('vpName').textContent = pfad ? pfad.replace(/^\/home\/[^/]+/, '~') : '';
    if (!pfad){ $('vpInfo').textContent = ''; return; }
    const i = nachbarn.indexOf(pfad);
    const teile = [zeitText(video.duration)];
    if (video.videoWidth) teile.push(`${video.videoWidth} × ${video.videoHeight}`);
    teile.push(groesseText(groesseBytes));
    if (nachbarn.length > 1 && i >= 0) teile.push(`Datei ${i + 1} von ${nachbarn.length}`);
    $('vpInfo').textContent = teile.join(' · ');
  }

  async function laden(neuerPfad, sofortSpielen){
    if (!neuerPfad) return;
    meldung('');
    const info = M.dateiPfadPruefen ? await M.dateiPfadPruefen(neuerPfad) : { gibt_es: true, pfad: neuerPfad, groesse: 0 };
    if (!info.gibt_es){ meldung(`„${dateiname(neuerPfad)}“ gibt es nicht (mehr).`, 'fehler'); return; }
    pfad = info.pfad;
    groesseBytes = info.groesse || 0;
    $('vpVlc').hidden = true;
    $('vpLeer').hidden = true;
    video.controls = true;
    $('vpMusik').hidden = !istMusik(pfad);
    $('vpMusikTitel').textContent = dateiname(pfad);
    // Musik: danach automatisch das naechste Stueck - bei Videos lieber nicht.
    $('vpWeiter').checked = istMusik(pfad);
    video.src = dateiUrl(pfad);
    video.playbackRate = Number($('vpTempo').value);
    nachbarn = M.ordnerDateienMitEndung ? await M.ordnerDateienMitEndung(pfad, istMusik(pfad) ? MUSIK : VIDEO) : [pfad];
    knoepfeStellen();
    infoZeichnen();
    if (sofortSpielen !== false) video.play().catch(() => { /* Fehler meldet 'error' unten */ });
  }
  video.addEventListener('loadedmetadata', infoZeichnen);
  ['play', 'pause', 'ended'].forEach(art => video.addEventListener(art, knoepfeStellen));
  video.addEventListener('ratechange', () => { $('vpTempo').value = String(video.playbackRate); });
  video.addEventListener('error', () => {
    if (!pfad) return;
    $('vpVlc').hidden = false;
    $('vpLeer').hidden = false;
    $('vpMusik').hidden = true;
    // Die Abspielleiste waere hier nur verwirrend - es gibt nichts abzuspielen.
    video.controls = false;
    $('vpLeerIcon').textContent = '⚠️';
    $('vpLeerText').textContent = 'Dieses Format kann Milcrid Video nicht abspielen. Oben „In VLC öffnen“ probiert es dort.';
    meldung(`„${dateiname(pfad)}“ kann Milcrid Video nicht abspielen (Format ${endung(pfad).toUpperCase() || 'unbekannt'}). „In VLC öffnen“ probiert es dort.`, 'fehler');
  });
  video.addEventListener('ended', () => { if ($('vpWeiter').checked) blaettern(1); });

  function blaettern(richtung){
    const i = nachbarn.indexOf(pfad);
    const ziel = nachbarn[i + richtung];
    if (ziel) laden(ziel);
  }
  function spielenPause(){
    if (!pfad) return;
    if (video.paused) video.play().catch(() => {}); else video.pause();
  }
  function vollbild(){
    if (!pfad || istMusik(pfad)) return;
    if (document.fullscreenElement) document.exitFullscreen(); else video.requestFullscreen().catch(() => {});
  }
  async function oeffnen(){
    const waehlen = M.dateiAuswaehlenArt || M.dateiAuswaehlen;
    if (!waehlen){ meldung('Öffnen geht nur in der Milcrid-App.', 'fehler'); return; }
    const pfade = await waehlen('video');
    if (pfade && pfade.length) laden(pfade[0]);
  }

  wurzel.addEventListener('keydown', ev => {
    if (ev.target.closest('select')) return;
    const strg = ev.ctrlKey || ev.metaKey;
    const t = ev.key;
    let erledigt = true;
    if (strg && t.toLowerCase() === 'o') oeffnen();
    else if (t === ' ' && ev.target !== video) spielenPause();   // auf dem Video selbst macht es Chromium schon
    else if (t.toLowerCase() === 'f') vollbild();
    else if (t.toLowerCase() === 'm') video.muted = !video.muted;
    else if (t === 'PageUp') blaettern(-1);
    else if (t === 'PageDown') blaettern(1);
    else if (t === 'ArrowLeft' && ev.target !== video) video.currentTime = Math.max(0, video.currentTime - 5);
    else if (t === 'ArrowRight' && ev.target !== video) video.currentTime = Math.min(video.duration || 0, video.currentTime + 5);
    else erledigt = false;
    if (erledigt) ev.preventDefault();
  });

  $('vpOeffnen').addEventListener('click', oeffnen);
  $('vpZurueck').addEventListener('click', () => blaettern(-1));
  $('vpVor').addEventListener('click', () => blaettern(1));
  $('vpSpielen').addEventListener('click', spielenPause);
  $('vpVollbild').addEventListener('click', vollbild);
  $('vpTempo').addEventListener('change', () => { video.playbackRate = Number($('vpTempo').value); });
  $('vpVlc').addEventListener('click', () => {
    if (pfad && window.milcridDateiOeffnen) window.milcridDateiOeffnen(pfad, 'linux:org.videolan.VLC.desktop');
  });

  // Fenster zu (×): das Portal legt den Inhalt nur versteckt zur Seite
  // (mwFensterSchliessen -> mwAblage, hidden=true) - ohne das hier spielte
  // das Video unsichtbar weiter (gemessen 24.09.2026, Tonstrom blieb aktiv).
  // Minimieren setzt hidden NICHT (nur das Fenster verschwindet) - Musik
  // laeuft dann weiter, wie bei jedem anderen Abspielprogramm.
  const huelle = wurzel.closest('.app-view') || wurzel.parentElement;
  new MutationObserver(() => { if (huelle.hidden && !video.paused) video.pause(); })
    .observe(huelle, { attributes: true, attributeFilter: ['hidden'] });

  window.milcridVideo = { oeffnen: p => { laden(p); wurzel.focus({ preventScroll: true }); } };
  knoepfeStellen();
  // Zum Oeffnen einer Datei gestartet? Siehe milcridAppMitDatei im Portal.
  const wartend = (window.milcridOeffnenWartend || {}).video;
  if (wartend){ delete window.milcridOeffnenWartend.video; laden(wartend); }
})();
