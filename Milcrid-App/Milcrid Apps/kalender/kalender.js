/* ---- Kalender: Monatsblatt als Uebersicht ueber den Terminplaner.
   Seit 2026-09-14 (Klaus-Brainstorm) ohne eigene Ablage: Termine und datierte
   Notizen kommen aus planer_verwaltung.py, "+" traegt in den Terminplaner ein,
   ein Klick auf einen Eintrag oeffnet ihn dort bzw. in den Notizen.
   Vorher speicherte der Kalender in kalender.json - die Termine daraus hat
   der Planer beim ersten Start uebernommen. ---- */
(() => {
  const P = window.milcridPlaner;
  const $ = id => document.getElementById(id);
  const kalenderTitel = $('kalenderTitel'), kalenderTage = $('kalenderTage');
  const termineTitel = $('termineTitel'), termineListe = $('termineListe');
  const titelEingabe = $('termTitelInput'), zeitEingabe = $('termZeitInput'), detailsEingabe = $('termDetailsInput');
  const hinzufuegen = $('termHinzufuegen'), planerKnopf = $('kalenderPlanerBtn');
  const MONAT_FMT = new Intl.DateTimeFormat('de-DE', { month: 'long', year: 'numeric' });
  const TAG_FMT = new Intl.DateTimeFormat('de-DE', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  let blick = new Date();
  blick.setDate(1);
  let ausgewaehlt = null;     // "JJJJ-MM-TT"
  let daten = null;

  // Was an einem Tag steht: Termine (mit Wiederholungen, fertig vom Planer
  // gerechnet) und Notizen mit Datum
  function eintraegeAm(tag){
    if (!daten) return { termine: [], notizen: [] };
    const nachId = new Map(daten.termine.map(t => [t.id, t]));
    const termine = (daten.vorkommen || []).filter(v => v.datum === tag).map(v => nachId.get(v.id)).filter(Boolean)
      .sort((a, b) => (a.uhrzeit || '').localeCompare(b.uhrzeit || ''));
    return { termine, notizen: daten.notizen.filter(n => n.datum === tag) };
  }

  function monatZeichnen(){
    kalenderTitel.textContent = MONAT_FMT.format(blick);
    kalenderTage.textContent = '';
    const jahr = blick.getFullYear(), monat = blick.getMonth();
    const anzahl = new Date(jahr, monat + 1, 0).getDate();
    const versatz = (new Date(jahr, monat, 1).getDay() + 6) % 7;   // Woche beginnt Montag
    const heute = P.heuteIso();
    for (let i = 0; i < versatz; i++){
      const leer = document.createElement('div');
      leer.className = 'kalender-tag leer';
      kalenderTage.append(leer);
    }
    for (let tag = 1; tag <= anzahl; tag++){
      const key = P.iso(new Date(jahr, monat, tag));
      const zelle = document.createElement('div');
      zelle.className = 'kalender-tag' + (key === heute ? ' heute' : '') + (key === ausgewaehlt ? ' ausgewaehlt' : '');
      const zahl = document.createElement('span');
      zahl.textContent = tag;
      zelle.append(zahl);
      const { termine, notizen } = eintraegeAm(key);
      const alle = [...termine.map(t => t.titel), ...notizen.map(n => '📝 ' + n.titel)];
      if (alle.length){
        const kurz = document.createElement('span');
        kurz.className = 'kalender-tag-kurz';
        kurz.textContent = alle.length > 1 ? `${alle[0]} +${alle.length - 1}` : alle[0];
        zelle.append(kurz);
      }
      zelle.addEventListener('click', () => tagWaehlen(key));
      kalenderTage.append(zelle);
    }
  }

  function tagWaehlen(key){
    ausgewaehlt = key;
    const [j, m, t] = key.split('-').map(Number);
    termineTitel.textContent = TAG_FMT.format(new Date(j, m - 1, t));
    [titelEingabe, zeitEingabe, detailsEingabe, hinzufuegen].forEach(e => { e.disabled = false; });
    planerKnopf.hidden = false;
    $('termStatus').textContent = '';
    monatZeichnen();
    tagZeichnen();
  }

  function zeile(zeit, titel, details, aktion, hinweis){
    const z = document.createElement('div');
    z.className = 'termin-zeile';
    z.title = hinweis;
    const zeitEl = document.createElement('div');
    zeitEl.className = 'termin-zeit';
    zeitEl.textContent = zeit;
    const text = document.createElement('div');
    text.className = 'termin-text';
    const t = document.createElement('div');
    t.className = 'termin-titel';
    t.textContent = titel;
    text.append(t);
    if (details){
      const d = document.createElement('div');
      d.className = 'termin-details';
      d.textContent = details;
      text.append(d);
    }
    z.append(zeitEl, text);
    z.addEventListener('click', aktion);
    return z;
  }

  function tagZeichnen(){
    termineListe.textContent = '';
    if (!ausgewaehlt) return;
    const { termine, notizen } = eintraegeAm(ausgewaehlt);
    for (const t of termine){
      termineListe.append(zeile(t.uhrzeit || 'ganztags', t.titel + (t.wiederholung !== 'keine' ? ' 🔁' : ''),
        [t.ort, t.details].filter(Boolean).join(' · '), () => P.zeigen('terminplaner', t.id), 'Im Terminplaner öffnen'));
    }
    for (const n of notizen){
      const rest = n.text.startsWith(n.titel) ? n.text.slice(n.titel.length).trim() : n.text;
      termineListe.append(zeile('📝 Notiz', n.titel, rest.slice(0, 120),
        () => P.zeigen('notizen', n.id), 'In den Notizen öffnen'));
    }
    if (!termine.length && !notizen.length){
      const leer = document.createElement('div');
      leer.className = 'kalender-termine-leer';
      leer.textContent = 'Nichts eingetragen.';
      termineListe.append(leer);
    }
  }

  async function eintragen(){
    if (!ausgewaehlt) return;
    const titel = titelEingabe.value.trim();
    if (!titel){ titelEingabe.focus(); return; }
    hinzufuegen.disabled = true;
    const antwort = await P.speichern('termin', {
      titel, datum: ausgewaehlt, uhrzeit: zeitEingabe.value, details: detailsEingabe.value.trim() });
    hinzufuegen.disabled = false;
    if (!antwort.erfolg){ $('termStatus').textContent = antwort.fehler; return; }
    titelEingabe.value = '';
    zeitEingabe.value = '';
    detailsEingabe.value = '';
    $('termStatus').textContent = '';
  }

  hinzufuegen.addEventListener('click', eintragen);
  [titelEingabe, zeitEingabe, detailsEingabe].forEach(feld =>
    feld.addEventListener('keydown', e => { if (e.key === 'Enter') eintragen(); }));
  planerKnopf.addEventListener('click', () => { if (ausgewaehlt) P.zeigen('terminplaner', 'neu:' + ausgewaehlt); });
  $('kalenderZurueckMonat').addEventListener('click', () => { blick.setMonth(blick.getMonth() - 1); monatZeichnen(); });
  $('kalenderVorMonat').addEventListener('click', () => { blick.setMonth(blick.getMonth() + 1); monatZeichnen(); });
  $('kalenderHeute').addEventListener('click', () => {
    blick = new Date();
    blick.setDate(1);
    tagWaehlen(P.heuteIso());
  });

  monatZeichnen();    // sofort das leere Blatt zeigen, die Eintraege kommen gleich
  P.anmelden(neu => { daten = neu; monatZeichnen(); tagZeichnen(); });
})();
