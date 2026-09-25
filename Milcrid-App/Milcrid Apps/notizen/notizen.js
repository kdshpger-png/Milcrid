/* ---- Notizen: Liste links (neueste zuerst), Notiz rechts. Datum oder
   Termin zuordnen, dann steht sie auch im Terminplaner bzw. am Termin.
   Eingeschlossen, damit kein Name mit dem Portal zusammenstoesst. ---- */
(() => {
  const P = window.milcridPlaner;
  const $ = id => document.getElementById(id);
  const liste = $('nzListe'), suche = $('nzSuche'), form = $('nzForm'), leer = $('nzLeer');
  const f = { titel: $('nzTitel'), text: $('nzText'), datum: $('nzDatum'), termin: $('nzTermin') };
  let daten = null;
  let auswahl = null;
  let formOffen = false;
  let formGeaendert = false;
  let loeschenScharf = null;
  let wartendesZeigen = null;

  function status(text, art){
    $('nzStatus').textContent = text || '';
    $('nzStatus').className = 'nz-status' + (art ? ' ' + art : '');
  }

  function naechstesDatum(termin){
    const heute = P.heuteIso();
    const v = (daten.vorkommen || []).find(x => x.id === termin.id && x.datum >= heute);
    return v ? v.datum : termin.datum;
  }

  function listeZeichnen(){
    liste.textContent = '';
    if (!daten) return;
    const wort = suche.value.trim().toLowerCase();
    const notizen = daten.notizen
      .filter(n => !wort || (n.titel + ' ' + n.text).toLowerCase().includes(wort))
      .sort((a, b) => b.geaendert - a.geaendert);
    for (const n of notizen){
      const zeile = document.createElement('div');
      zeile.className = 'nz-eintrag' + (n.id === auswahl ? ' gewaehlt' : '');
      const titel = document.createElement('div');
      titel.className = 'nz-eintrag-titel';
      titel.textContent = n.titel;
      const unter = document.createElement('div');
      unter.className = 'nz-eintrag-unter';
      const termin = n.termin_id && daten.termine.find(t => t.id === n.termin_id);
      unter.textContent = [n.datum ? '📅 ' + P.datumText(n.datum) : '', termin ? '🔗 ' + termin.titel : '',
                           (n.text.startsWith(n.titel) ? n.text.slice(n.titel.length) : n.text)
                             .replace(/\s+/g, ' ').trim().slice(0, 80)].filter(Boolean).join(' · ');
      zeile.append(titel, unter);
      zeile.addEventListener('click', () => waehlen(n.id));
      liste.append(zeile);
    }
    if (!notizen.length){
      const h = document.createElement('div');
      h.className = 'nz-leer';
      h.textContent = wort ? 'Nichts gefunden.' : 'Noch keine Notizen. Mit „+ Neu“ anlegen – oder Milcrid sagen: „notiere: Milch kaufen“.';
      liste.append(h);
    }
  }

  function terminAuswahlZeichnen(gewaehlt){
    f.termin.textContent = '';
    const keiner = document.createElement('option');
    keiner.value = '';
    keiner.textContent = '— keinem Termin —';
    f.termin.append(keiner);
    const termine = daten.termine.map(t => [naechstesDatum(t), t]).sort((a, b) => a[0].localeCompare(b[0]));
    for (const [datum, t] of termine){
      const o = document.createElement('option');
      o.value = t.id;
      o.textContent = `${P.datumText(datum, false)} ${t.titel}`;
      f.termin.append(o);
    }
    f.termin.value = gewaehlt || '';
    $('nzTerminZeigen').hidden = !f.termin.value;
  }

  function formFuellen(n){
    formOffen = true;
    formGeaendert = false;
    leer.hidden = true;
    form.hidden = false;
    loeschenEntschaerfen();
    f.titel.value = n ? n.titel : '';
    f.text.value = n ? n.text : '';
    f.datum.value = n ? n.datum : '';
    terminAuswahlZeichnen(n ? n.termin_id : '');
    $('nzLoeschen').hidden = !n;
    if (!n) f.text.focus();
  }

  function waehlen(id){
    if (!daten){ wartendesZeigen = id; return; }
    const n = daten.notizen.find(x => x.id === id);
    if (!n){ status('Diese Notiz gibt es nicht mehr.', 'fehler'); return; }
    auswahl = id;
    formFuellen(n);
    status('');
    listeZeichnen();
  }

  function neuAnlegen(){
    auswahl = null;
    formFuellen(null);
    status('');
    listeZeichnen();
  }

  function zeigen(id){
    if (!daten){ wartendesZeigen = id; return; }
    if (id === 'neu') neuAnlegen();
    else if (id) waehlen(id);
  }

  async function speichern(ev){
    ev.preventDefault();
    const eintrag = { titel: f.titel.value, text: f.text.value, datum: f.datum.value, termin_id: f.termin.value };
    if (auswahl) eintrag.id = auswahl;
    status('Speichere …');
    const antwort = await P.speichern('notiz', eintrag);
    if (!antwort.erfolg){ status(antwort.fehler, 'fehler'); return; }
    auswahl = antwort.eintrag.id;
    formFuellen(antwort.eintrag);
    listeZeichnen();
    status('Gespeichert.', 'erfolg');
  }

  function loeschenEntschaerfen(){
    clearTimeout(loeschenScharf);
    loeschenScharf = null;
    $('nzLoeschen').textContent = 'Löschen';
  }

  async function loeschen(){
    if (!auswahl) return;
    if (!loeschenScharf){
      $('nzLoeschen').textContent = 'Wirklich löschen?';
      loeschenScharf = setTimeout(loeschenEntschaerfen, 4000);
      return;
    }
    loeschenEntschaerfen();
    const antwort = await P.loeschen('notizen', auswahl);
    if (!antwort.erfolg){ status(antwort.fehler, 'fehler'); return; }
    auswahl = null;
    formOffen = false;
    form.hidden = true;
    leer.hidden = false;
    listeZeichnen();
  }

  function beiDaten(neu){
    daten = neu;
    listeZeichnen();
    if (wartendesZeigen){ const id = wartendesZeigen; wartendesZeigen = null; zeigen(id); return; }
    if (!formOffen) return;
    if (!auswahl){ if (!formGeaendert) terminAuswahlZeichnen(f.termin.value); return; }
    const n = daten.notizen.find(x => x.id === auswahl);
    if (!n){ auswahl = null; formOffen = false; form.hidden = true; leer.hidden = false; return; }
    if (!formGeaendert) formFuellen(n);
  }

  form.addEventListener('submit', speichern);
  form.addEventListener('input', () => { formGeaendert = true; });
  f.termin.addEventListener('change', () => { $('nzTerminZeigen').hidden = !f.termin.value; });
  suche.addEventListener('input', listeZeichnen);
  $('nzNeu').addEventListener('click', neuAnlegen);
  $('nzLoeschen').addEventListener('click', loeschen);
  $('nzTerminZeigen').addEventListener('click', () => { if (f.termin.value) P.zeigen('terminplaner', f.termin.value); });

  P.aufZeigen('notizen', zeigen);
  const abgeholt = P.zeigenAbholen('notizen');
  if (abgeholt) wartendesZeigen = abgeholt;
  P.anmelden(beiDaten);
})();
