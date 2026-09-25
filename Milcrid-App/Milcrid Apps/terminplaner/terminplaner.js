/* ---- Terminplaner: Liste links (Heute, Morgen, 7 Tage, Später, Vergangen),
   Eintrag rechts mit Erinnerung, Wiederholung, Dateien (Verweis) und Notizen.
   In einer Funktion eingeschlossen: das Skript laeuft im Portal-Dokument, und
   jeder Name hier oben wuerde sonst mit dem Portal zusammenstossen. ---- */
(() => {
  const P = window.milcridPlaner;
  const $ = id => document.getElementById(id);
  const liste = $('tpListe'), suche = $('tpSuche'), form = $('tpForm'), leer = $('tpLeer');
  const f = {
    titel: $('tpTitel'), datum: $('tpDatum'), uhrzeit: $('tpUhrzeit'), ort: $('tpOrt'), details: $('tpDetails'),
    erinnerungAn: $('tpErinnerungAn'), erinnerungWert: $('tpErinnerungWert'),
    erinnerungEinheit: $('tpErinnerungEinheit'), wiederholung: $('tpWiederholung'),
  };
  let daten = null;
  let auswahl = null;            // id des gezeigten Termins, null = neuer Termin
  let formOffen = false;
  let formGeaendert = false;     // dann ueberschreibt ein neuer Stand die Eingaben NICHT
  let formDateien = [];
  let loeschenScharf = null;
  let wartendesZeigen = null;

  const tagePlus = (iso, n) => { const [j, m, t] = iso.split('-').map(Number); return P.iso(new Date(j, m - 1, t + n)); };

  function status(text, art){
    $('tpStatus').textContent = text || '';
    $('tpStatus').className = 'tp-status' + (art ? ' ' + art : '');
  }

  // ---------------- Liste
  function listeZeichnen(){
    liste.textContent = '';
    if (!daten) return;
    const heute = P.heuteIso(), morgen = tagePlus(heute, 1), in7 = tagePlus(heute, 7), vor30 = tagePlus(heute, -30);
    const nachId = new Map(daten.termine.map(t => [t.id, t]));
    const wort = suche.value.trim().toLowerCase();
    const passt = t => !wort || [t.titel, t.ort, t.details].join(' ').toLowerCase().includes(wort);
    const gruppen = [['Heute', []], ['Morgen', []], ['Nächste 7 Tage', []], ['Später', []], ['Vergangen (30 Tage)', []]];
    const schonGezeigt = new Set();
    for (const v of daten.vorkommen || []){
      const t = nachId.get(v.id);
      if (!t || !passt(t) || v.datum < vor30) continue;
      let g;
      if (v.datum < heute){
        if (t.wiederholung !== 'keine') continue;   // Serien stehen mit ihrem naechsten Termin oben
        g = 4;
      } else if (v.datum === heute) g = 0;
      else if (v.datum === morgen) g = 1;
      else if (v.datum <= in7) g = 2;
      else {
        if (schonGezeigt.has(t.id)) continue;       // Serien spaeter nur einmal, mit dem naechsten Datum
        g = 3;
      }
      schonGezeigt.add(t.id);
      gruppen[g][1].push([v.datum, t]);
    }
    gruppen[4][1].reverse();
    let irgendwas = false;
    for (const [name, eintraege] of gruppen){
      if (!eintraege.length) continue;
      irgendwas = true;
      const kopf = document.createElement('div');
      kopf.className = 'tp-gruppe';
      kopf.textContent = name;
      liste.append(kopf);
      for (const [datum, t] of eintraege){
        const zeile = document.createElement('div');
        zeile.className = 'tp-eintrag' + (t.id === auswahl ? ' gewaehlt' : '');
        const wann = document.createElement('span');
        wann.className = 'tp-eintrag-wann';
        wann.textContent = P.datumText(datum, false) + ' ' + (t.uhrzeit || 'ganztags');
        const titel = document.createElement('span');
        titel.className = 'tp-eintrag-titel';
        titel.textContent = t.titel;
        const zeichen = document.createElement('span');
        zeichen.className = 'tp-eintrag-zeichen';
        const notizen = daten.notizen.filter(n => n.termin_id === t.id).length;
        zeichen.textContent = [t.wiederholung !== 'keine' ? '🔁' : '', (t.dateien || []).length ? '📎' : '',
                               notizen ? '📝' : '', t.erinnerung ? '🔔' : ''].join('');
        zeile.append(wann, titel, zeichen);
        zeile.addEventListener('click', () => waehlen(t.id));
        liste.append(zeile);
      }
    }
    if (!irgendwas){
      const hinweis = document.createElement('div');
      hinweis.className = 'tp-leer';
      hinweis.textContent = wort ? 'Nichts gefunden.'
        : 'Noch keine Termine. Mit „+ Neu“ anlegen – oder Milcrid sagen: „trag morgen um 10 Uhr Zahnarzt ein“.';
      liste.append(hinweis);
    }
  }

  // ---------------- Formular
  function formFuellen(t, neuDatum){
    formOffen = true;
    formGeaendert = false;
    leer.hidden = true;
    form.hidden = false;
    loeschenEntschaerfen();
    f.titel.value = t ? t.titel : '';
    f.datum.value = t ? t.datum : (neuDatum || P.heuteIso());
    f.uhrzeit.value = t ? t.uhrzeit : '';
    f.ort.value = t ? t.ort : '';
    f.details.value = t ? t.details : '';
    const e = t ? t.erinnerung : { wert: 1, einheit: 'stunden' };
    f.erinnerungAn.value = e ? 'an' : 'aus';
    f.erinnerungWert.value = e ? e.wert : 1;
    f.erinnerungEinheit.value = e ? e.einheit : 'stunden';
    f.wiederholung.value = t ? t.wiederholung : 'keine';
    formDateien = t ? [...(t.dateien || [])] : [];
    $('tpLoeschen').hidden = !t;
    $('tpVorbereiten').hidden = !t;
    $('tpNotizAbschnitt').hidden = !t;
    erinnerungSperren();
    nebenteileZeichnen();
    if (!t) f.titel.focus();
  }

  function nebenteileZeichnen(){
    const t = auswahl && daten ? daten.termine.find(x => x.id === auswahl) : null;
    // Hinweis bei Serien: welches Datum als naechstes dran ist
    if (t && t.wiederholung !== 'keine'){
      const heute = P.heuteIso();
      const naechster = (daten.vorkommen || []).find(v => v.id === t.id && v.datum >= heute);
      $('tpSerieHinweis').textContent = `Wiederholt sich ${P.wiederholungText(t.wiederholung)} ab ${P.datumText(t.datum)}` +
        (naechster ? ` – nächstes Mal ${P.datumText(naechster.datum)}.` : '.');
    } else {
      $('tpSerieHinweis').textContent = 'Uhrzeit leer lassen = ganztägig.';
    }
    dateienZeichnen();
    notizenZeichnen(t);
  }

  function dateienZeichnen(){
    const box = $('tpDateien');
    box.textContent = '';
    if (!formDateien.length){
      const h = document.createElement('div');
      h.className = 'tp-hinweis';
      h.textContent = 'Keine Datei verknüpft. Die Datei bleibt, wo sie ist – der Termin merkt sich nur, wo sie liegt.';
      box.append(h);
      return;
    }
    const da = (daten && daten.dateien_da) || {};
    formDateien.forEach((pfad, i) => {
      // Unbekannt (gerade erst gewaehlt, noch nicht gespeichert) gilt als vorhanden
      const fehlt = pfad in da && !da[pfad];
      const zeile = document.createElement('div');
      zeile.className = 'tp-anhang' + (fehlt ? ' fehlt' : '');
      const name = document.createElement('span');
      name.className = 'tp-anhang-name';
      name.title = pfad;
      name.textContent = (fehlt ? '⚠ nicht gefunden: ' : '📎 ') + pfad.split('/').pop();
      zeile.append(name);
      if (fehlt){
        zeile.append(knopf('Neu wählen', async () => {
          const neu = await P.dateiWaehlen();
          if (neu.length){ formDateien[i] = neu[0]; geaendert('Datei ersetzt – noch speichern.'); dateienZeichnen(); }
        }));
      } else {
        zeile.append(knopf('Öffnen', () => P.dateiOeffnen(pfad)));
      }
      zeile.append(knopf('Entfernen', () => { formDateien.splice(i, 1); geaendert('Verknüpfung entfernt – noch speichern.'); dateienZeichnen(); }));
      box.append(zeile);
    });
  }

  function notizenZeichnen(t){
    const box = $('tpNotizen');
    box.textContent = '';
    if (!t || !daten) return;
    const notizen = daten.notizen.filter(n => n.termin_id === t.id);
    if (!notizen.length){
      const h = document.createElement('div');
      h.className = 'tp-hinweis';
      h.textContent = 'Noch keine Notizen zu diesem Termin.';
      box.append(h);
    }
    for (const n of notizen){
      const zeile = document.createElement('div');
      zeile.className = 'tp-notiz';
      zeile.title = 'In den Notizen öffnen';
      const titel = document.createElement('b');
      titel.textContent = n.titel;
      // Der Titel ist oft die erste Zeile des Textes - dann nicht doppelt zeigen
      const rest = n.text.startsWith(n.titel) ? n.text.slice(n.titel.length).trim() : n.text;
      zeile.append(titel, document.createTextNode(rest ? '\n' + rest : ''));
      zeile.addEventListener('click', () => P.zeigen('notizen', n.id));
      box.append(zeile);
    }
  }

  function knopf(text, aktion){
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'tp-knopf klein';
    b.textContent = text;
    b.addEventListener('click', aktion);
    return b;
  }

  function geaendert(text){
    formGeaendert = true;
    status(text || '');
  }

  function erinnerungSperren(){
    const aus = f.erinnerungAn.value === 'aus';
    f.erinnerungWert.disabled = aus;
    f.erinnerungEinheit.disabled = aus;
  }

  function waehlen(id){
    if (!daten) { wartendesZeigen = id; return; }
    const t = daten.termine.find(x => x.id === id);
    if (!t){ status('Diesen Termin gibt es nicht mehr.', 'fehler'); return; }
    auswahl = id;
    formFuellen(t);
    status('');
    listeZeichnen();
  }

  function neuAnlegen(datum){
    auswahl = null;
    formFuellen(null, datum);
    status('');
    listeZeichnen();
  }

  function zeigen(id){
    if (!daten){ wartendesZeigen = id; return; }
    if (!id) return;
    if (String(id).startsWith('neu:')) neuAnlegen(String(id).slice(4));
    else waehlen(id);
  }

  async function speichern(ev){
    ev.preventDefault();
    const eintrag = {
      titel: f.titel.value, datum: f.datum.value, uhrzeit: f.uhrzeit.value, ort: f.ort.value,
      details: f.details.value, wiederholung: f.wiederholung.value, dateien: formDateien,
      erinnerung: f.erinnerungAn.value === 'aus' ? 'keine'
        : { wert: Number(f.erinnerungWert.value), einheit: f.erinnerungEinheit.value },
    };
    if (auswahl) eintrag.id = auswahl;
    if (!eintrag.datum){ status('Bitte ein Datum wählen.', 'fehler'); return; }
    status('Speichere …');
    const antwort = await P.speichern('termin', eintrag);
    if (!antwort.erfolg){ status(antwort.fehler, 'fehler'); return; }
    auswahl = antwort.eintrag.id;
    formFuellen(antwort.eintrag);
    listeZeichnen();
    status('Gespeichert.', 'erfolg');
  }

  function loeschenEntschaerfen(){
    clearTimeout(loeschenScharf);
    loeschenScharf = null;
    $('tpLoeschen').textContent = 'Löschen';
  }

  async function loeschen(){
    if (!auswahl) return;
    if (!loeschenScharf){
      // Zwei Klicks statt eines Browser-Dialogs: der wuerde das ganze Portal anhalten
      $('tpLoeschen').textContent = 'Wirklich löschen?';
      loeschenScharf = setTimeout(loeschenEntschaerfen, 4000);
      return;
    }
    loeschenEntschaerfen();
    const antwort = await P.loeschen('termine', auswahl);
    if (!antwort.erfolg){ status(antwort.fehler, 'fehler'); return; }
    auswahl = null;
    formOffen = false;
    form.hidden = true;
    leer.hidden = false;
    listeZeichnen();
  }

  function vorbereiten(){
    const t = daten && daten.termine.find(x => x.id === auswahl);
    if (!t) return;
    const da = daten.dateien_da || {};
    let offen = 0, fehlt = 0;
    for (const pfad of t.dateien || []){
      if (da[pfad]){ P.dateiOeffnen(pfad); offen++; } else fehlt++;
    }
    const notizen = [...document.querySelectorAll('#tpNotizen .tp-notiz')];
    notizen.forEach(n => n.classList.add('leuchtet'));
    setTimeout(() => notizen.forEach(n => n.classList.remove('leuchtet')), 3000);
    $('tpNotizAbschnitt').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    status([`${offen} Datei${offen === 1 ? '' : 'en'} geöffnet`, fehlt ? `${fehlt} nicht gefunden` : '',
            `${notizen.length} Notiz${notizen.length === 1 ? '' : 'en'}`].filter(Boolean).join(' · '), fehlt ? 'fehler' : 'erfolg');
  }

  async function notizSpeichern(){
    const text = $('tpNotizText').value.trim();
    if (!auswahl || !text) return;
    const antwort = await P.speichern('notiz', { text, termin_id: auswahl });
    if (!antwort.erfolg){ status(antwort.fehler, 'fehler'); return; }
    $('tpNotizText').value = '';
    status('Notiz gespeichert.', 'erfolg');
  }

  function beiDaten(neu){
    daten = neu;
    listeZeichnen();
    if (wartendesZeigen){ const id = wartendesZeigen; wartendesZeigen = null; zeigen(id); return; }
    if (!formOffen || !auswahl) return;
    const t = daten.termine.find(x => x.id === auswahl);
    if (!t){ auswahl = null; formOffen = false; form.hidden = true; leer.hidden = false; status(''); return; }
    // Neuer Stand von aussen (KI, Kalender, Melder): Eingaben nicht wegwerfen
    if (formGeaendert) nebenteileZeichnen();
    else formFuellen(t);
  }

  form.addEventListener('submit', speichern);
  form.addEventListener('input', () => { formGeaendert = true; });
  f.erinnerungAn.addEventListener('change', erinnerungSperren);
  suche.addEventListener('input', listeZeichnen);
  $('tpNeu').addEventListener('click', () => neuAnlegen());
  $('tpLoeschen').addEventListener('click', loeschen);
  $('tpVorbereiten').addEventListener('click', vorbereiten);
  $('tpNotizNeu').addEventListener('click', notizSpeichern);
  $('tpDateiNeu').addEventListener('click', async () => {
    const neu = await P.dateiWaehlen();
    const vorher = formDateien.length;
    for (const p of neu) if (!formDateien.includes(p)) formDateien.push(p);
    if (formDateien.length !== vorher){ geaendert('Datei verknüpft – noch speichern.'); dateienZeichnen(); }
  });

  P.aufZeigen('terminplaner', zeigen);
  const abgeholt = P.zeigenAbholen('terminplaner');
  if (abgeholt) wartendesZeigen = abgeholt;
  P.anmelden(beiDaten);
})();
