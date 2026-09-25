/* ---- Uhr: Uhrzeit, Wecker, Timer, Stoppuhr - vier Reiter in einer App.
   Seit 2026-09-14 (Klaus-Brainstorm) liegen Wecker und Timer im Planer
   (planer_verwaltung.py) statt nur im Arbeitsspeicher dieser App: sie
   ueberleben einen Neustart, und gemeldet wird vom Portal selbst - auch wenn
   die Uhr nie geoeffnet wurde. Die Stoppuhr bleibt hier, sie meldet nichts. ---- */
(() => {
  const P = window.milcridPlaner;
  const $ = id => document.getElementById(id);
  const pad = n => String(n).padStart(2, '0');
  let daten = null;

  /* ---------- Reiter ---------- */
  document.querySelectorAll('.uhr-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.uhr-tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.uhr-abschnitt').forEach(t => t.classList.remove('active'));
      btn.classList.add('active');
      $('uhrTab' + btn.dataset.tab[0].toUpperCase() + btn.dataset.tab.slice(1)).classList.add('active');
    });
  });
  // Von aussen (Bestaetigungskarte "Ansehen"): den passenden Reiter zeigen
  function reiter(name){
    const btn = document.querySelector(`.uhr-tab-btn[data-tab="${name}"]`);
    if (btn) btn.click();
  }

  /* ---------- Uhrzeit ---------- */
  const WOCHENTAGE = ['Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag'];
  const MONATE = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
  function sekundenTakt(){
    const jetzt = new Date(P.jetzt());
    $('uhrClockZeit').textContent = `${pad(jetzt.getHours())}:${pad(jetzt.getMinutes())}:${pad(jetzt.getSeconds())}`;
    $('uhrClockDatum').textContent = `${WOCHENTAGE[jetzt.getDay()]}, ${jetzt.getDate()}. ${MONATE[jetzt.getMonth()]} ${jetzt.getFullYear()}`;
    timerAnzeigen();
  }

  /* ---------- Meldungs-Schalter (gilt fuer Wecker, Timer UND Termine) ---------- */
  document.querySelectorAll('.uhr-meldung-knopf').forEach(btn => {
    btn.addEventListener('click', async () => {
      const antwort = await P.einstellung(btn.dataset.meldung);
      if (!antwort.erfolg) $('uhrAlarmFehler').textContent = antwort.fehler;
    });
  });
  function meldungZeichnen(){
    const art = (daten && daten.einstellungen && daten.einstellungen.meldung) || 'beides';
    document.querySelectorAll('.uhr-meldung-knopf').forEach(b => b.classList.toggle('an', b.dataset.meldung === art));
  }

  /* ---------- Wecker ---------- */
  function weckerZeichnen(){
    const liste = $('uhrAlarmListe');
    liste.textContent = '';
    const wecker = daten ? [...daten.wecker].sort((a, b) => a.uhrzeit.localeCompare(b.uhrzeit)) : [];
    $('uhrAlarmLeerHinweis').style.display = wecker.length ? 'none' : 'block';
    for (const w of wecker){
      const li = document.createElement('li');
      li.className = 'uhr-alarm-eintrag' + (w.aktiv ? '' : ' aus');
      const zeit = document.createElement('span');
      zeit.className = 'uhr-zeit';
      zeit.textContent = w.uhrzeit;
      const label = document.createElement('span');
      label.className = 'uhr-label';
      label.textContent = [w.bezeichnung || 'Wecker', P.wiederholungText(w.wiederholung)].join(' · ');
      const schalter = document.createElement('label');
      schalter.className = 'uhr-switch';
      const haken = document.createElement('input');
      haken.type = 'checkbox';
      haken.checked = !!w.aktiv;
      haken.addEventListener('change', () => P.speichern('wecker', { id: w.id, aktiv: haken.checked }));
      const track = document.createElement('span');
      track.className = 'uhr-track';
      const thumb = document.createElement('span');
      thumb.className = 'uhr-thumb';
      schalter.append(haken, track, thumb);
      const weg = document.createElement('button');
      weg.type = 'button';
      weg.className = 'uhr-btn uhr-btn-danger';
      weg.textContent = 'Löschen';
      weg.addEventListener('click', () => P.loeschen('wecker', w.id));
      li.append(zeit, label, schalter, weg);
      liste.append(li);
    }
  }
  $('uhrAlarmHinzufuegenBtn').addEventListener('click', async () => {
    const zeit = $('uhrAlarmZeitInput');
    if (!zeit.value){ zeit.focus(); return; }
    const antwort = await P.speichern('wecker', {
      uhrzeit: zeit.value, bezeichnung: $('uhrAlarmLabelInput').value.trim(), wiederholung: $('uhrAlarmWiederholung').value });
    $('uhrAlarmFehler').textContent = antwort.erfolg ? '' : antwort.fehler;
    if (antwort.erfolg){ zeit.value = ''; $('uhrAlarmLabelInput').value = ''; }
  });

  /* ---------- Timer ---------- */
  function restText(sekunden){
    sekunden = Math.max(0, Math.round(sekunden));
    return `${pad(Math.floor(sekunden / 3600))}:${pad(Math.floor(sekunden % 3600 / 60))}:${pad(sekunden % 60)}`;
  }
  function timerZeichnen(){
    const liste = $('uhrTimerListe');
    liste.textContent = '';
    for (const z of daten ? [...daten.timer].sort((a, b) => a.ende - b.ende) : []){
      const li = document.createElement('li');
      li.className = 'uhr-timer-eintrag';
      const zeit = document.createElement('span');
      zeit.className = 'uhr-zeit';
      zeit.dataset.ende = z.ende;
      const label = document.createElement('span');
      label.className = 'uhr-label';
      const ende = new Date(z.ende * 1000);
      label.textContent = `${z.bezeichnung || 'Timer'} · fertig um ${pad(ende.getHours())}:${pad(ende.getMinutes())}`;
      const weg = document.createElement('button');
      weg.type = 'button';
      weg.className = 'uhr-btn uhr-btn-danger';
      weg.textContent = 'Abbrechen';
      weg.addEventListener('click', () => P.loeschen('timer', z.id));
      li.append(zeit, label, weg);
      liste.append(li);
    }
    timerAnzeigen();
  }
  function timerAnzeigen(){
    const jetzt = P.jetzt() / 1000;
    document.querySelectorAll('#uhrTimerListe .uhr-zeit').forEach(el => { el.textContent = restText(el.dataset.ende - jetzt); });
    const naechster = daten && daten.timer.length ? Math.min(...daten.timer.map(z => z.ende)) : null;
    $('uhrTimerAnzeige').textContent = naechster ? restText(naechster - jetzt) : '00:00:00';
  }
  $('uhrTimerStartBtn').addEventListener('click', async () => {
    const sekunden = (Number($('uhrTimerStunden').value) || 0) * 3600 + (Number($('uhrTimerMinuten').value) || 0) * 60
                   + (Number($('uhrTimerSekunden').value) || 0);
    if (sekunden <= 0){ $('uhrTimerFehler').textContent = 'Bitte eine Dauer eingeben.'; return; }
    const antwort = await P.speichern('timer', { dauer: `${sekunden} Sekunden`, bezeichnung: $('uhrTimerLabelInput').value.trim() });
    $('uhrTimerFehler').textContent = antwort.erfolg ? '' : antwort.fehler;
    if (antwort.erfolg){
      ['uhrTimerStunden', 'uhrTimerMinuten', 'uhrTimerSekunden', 'uhrTimerLabelInput'].forEach(id => { $(id).value = ''; });
    }
  });

  /* ---------- Stoppuhr (bleibt lokal) ---------- */
  let swLaeuft = false, swStart = 0, swVerstrichen = 0, swHandle = null, swRunde = 0;
  function swZeigen(ms){
    const cs = Math.floor(ms / 10);
    const sek = Math.floor(cs / 100);
    $('uhrStoppuhrAnzeige').textContent = `${pad(Math.floor(sek / 60))}:${pad(sek % 60)}.${pad(cs % 100)}`;
  }
  $('uhrSwStartBtn').addEventListener('click', () => {
    if (!swLaeuft){
      swLaeuft = true;
      swStart = Date.now() - swVerstrichen;
      swHandle = setInterval(() => { swVerstrichen = Date.now() - swStart; swZeigen(swVerstrichen); }, 30);
      $('uhrSwStartBtn').textContent = 'Stopp';
      $('uhrSwRundeBtn').disabled = false;
      $('uhrSwResetBtn').disabled = false;
    } else {
      swLaeuft = false;
      clearInterval(swHandle);
      $('uhrSwStartBtn').textContent = 'Start';
      $('uhrSwRundeBtn').disabled = true;
    }
  });
  $('uhrSwRundeBtn').addEventListener('click', () => {
    swRunde++;
    const li = document.createElement('li');
    const a = document.createElement('span');
    a.textContent = 'Runde ' + swRunde;
    const b = document.createElement('span');
    b.textContent = $('uhrStoppuhrAnzeige').textContent;
    li.append(a, b);
    $('uhrSwRunden').append(li);
  });
  $('uhrSwResetBtn').addEventListener('click', () => {
    swLaeuft = false;
    clearInterval(swHandle);
    swVerstrichen = 0;
    swRunde = 0;
    swZeigen(0);
    $('uhrSwRunden').textContent = '';
    $('uhrSwStartBtn').textContent = 'Start';
    $('uhrSwRundeBtn').disabled = true;
    $('uhrSwResetBtn').disabled = true;
  });

  /* ---------- Start ---------- */
  swZeigen(0);
  sekundenTakt();
  setInterval(sekundenTakt, 1000);
  P.aufZeigen('uhr', id => reiter(String(id || '').startsWith('z') ? 'timer' : 'wecker'));
  const abgeholt = P.zeigenAbholen('uhr');
  if (abgeholt) reiter(String(abgeholt).startsWith('z') ? 'timer' : 'wecker');
  P.anmelden(neu => { daten = neu; meldungZeichnen(); weckerZeichnen(); timerZeichnen(); });
})();
