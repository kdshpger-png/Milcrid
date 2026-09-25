/* ---- Milcrid Editor: mehrere Reiter, je eine Datei (oder ein leeres Blatt).
   Oeffnen/Speichern ueber main.js, Entwuerfe ueberleben einen Portal-Neustart
   (localStorage). Eingeschlossen, damit kein Name mit dem Portal
   zusammenstoesst. ---- */
(() => {
  const M = window.milcrid || {};
  const $ = id => document.getElementById(id);
  const text = $('edText'), zeilen = $('edZeilen'), reiterLeiste = $('edReiter');
  const ENTWURF_SCHLUESSEL = 'milcridEditorEntwurf';

  // Dateiarten, die nach Programmcode aussehen: ohne Zeilenumbruch, mit
  // Zeilennummern. Alles andere (txt, md, neue Blaetter) bricht um wie ein
  // normaler Text.
  const CODE = /\.(py|js|json|sh|bash|html?|css|xml|ya?ml|toml|ini|conf|cfg|service|desktop|c|h|cpp|sql|jsonl|csv)$/i;
  const ARTEN = { py: 'Python', js: 'JavaScript', json: 'JSON', jsonl: 'JSON-Zeilen', sh: 'Shell', md: 'Markdown',
                  txt: 'Text', html: 'HTML', htm: 'HTML', css: 'CSS', log: 'Protokoll', csv: 'CSV', xml: 'XML',
                  yml: 'YAML', yaml: 'YAML', ini: 'Einstellungen', conf: 'Einstellungen', cfg: 'Einstellungen' };

  let reiter = [];          // { id, pfad, name, inhalt, gespeichert, umbruch, auswahl, scroll }
  let aktivId = null;
  let zaehler = 0;
  let entwurfTimer = null;
  let meldungTimer = null;

  const aktiv = () => reiter.find(r => r.id === aktivId);
  const dateiname = pfad => (pfad || '').split('/').pop();
  const kurzPfad = pfad => (pfad || '').replace(/^\/home\/[^/]+/, '~');
  const geaendert = r => r.inhalt !== r.gespeichert;

  function meldung(t, art){
    clearTimeout(meldungTimer);
    $('edMeldung').innerHTML = '';
    if (!t) return;
    const s = document.createElement('span');
    s.textContent = t;
    if (art) s.className = art;
    $('edMeldung').append(s);
    if (art !== 'fehler') meldungTimer = setTimeout(() => meldung(''), 4000);
  }

  // ---- Reiter ----------------------------------------------------------
  function neuerReiter(pfad, inhalt, gespeichert){
    const r = { id: 'ed' + (++zaehler), pfad: pfad || null,
                name: pfad ? dateiname(pfad) : 'Unbenannt ' + (reiter.filter(x => !x.pfad).length + 1),
                inhalt: inhalt || '', gespeichert: gespeichert === undefined ? (inhalt || '') : gespeichert,
                umbruch: !(pfad && CODE.test(pfad)), auswahl: 0, scroll: 0 };
    reiter.push(r);
    aktivieren(r.id);
    return r;
  }

  function aktivieren(id){
    const alt = aktiv();
    if (alt){ alt.auswahl = text.selectionStart; alt.scroll = text.scrollTop; }
    aktivId = id;
    const r = aktiv();
    text.value = r.inhalt;
    umbruchAnwenden(r);
    text.setSelectionRange(r.auswahl, r.auswahl);
    text.scrollTop = r.scroll;
    zeilenZeichnen();
    reiterZeichnen();
    statusZeichnen();
    text.focus();
  }

  function reiterZeichnen(){
    reiterLeiste.textContent = '';
    for (const r of reiter){
      const el = document.createElement('div');
      el.className = 'ed-reiter-eintrag' + (r.id === aktivId ? ' aktiv' : '');
      el.title = r.pfad ? kurzPfad(r.pfad) : 'noch nicht gespeichert';
      const name = document.createElement('span');
      name.className = 'ed-reiter-name';
      name.textContent = r.name;
      el.append(name);
      if (geaendert(r)){
        const p = document.createElement('span');
        p.className = 'ed-reiter-punkt';
        p.textContent = '●';
        p.title = 'noch nicht gespeichert';
        el.append(p);
      }
      const zu = document.createElement('button');
      zu.type = 'button';
      zu.className = 'ed-reiter-zu' + (r.scharf ? ' scharf' : '');
      zu.textContent = r.scharf ? 'verwerfen?' : '×';
      zu.title = 'Reiter schließen';
      zu.addEventListener('click', ev => { ev.stopPropagation(); schliessen(r.id); });
      el.append(zu);
      el.addEventListener('click', () => { if (r.id !== aktivId) aktivieren(r.id); });
      el.addEventListener('auxclick', ev => { if (ev.button === 1) schliessen(r.id); });
      reiterLeiste.append(el);
    }
    const neu = document.createElement('button');
    neu.type = 'button';
    neu.className = 'ed-reiter-neu';
    neu.textContent = '+';
    neu.title = 'Neuer Reiter';
    neu.addEventListener('click', () => neuerReiter());
    reiterLeiste.append(neu);
    const a = reiterLeiste.querySelector('.aktiv');
    if (a) a.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }

  // Ungespeichertes nicht mit einem Klick wegwerfen: erster Klick macht den
  // Knopf "scharf" (wie Loeschen bei den Notizen), zweiter innerhalb von 4 s
  // schliesst wirklich.
  function schliessen(id){
    const r = reiter.find(x => x.id === id);
    if (!r) return;
    if (geaendert(r) && !r.scharf){
      r.scharf = setTimeout(() => { r.scharf = null; reiterZeichnen(); }, 4000);
      reiterZeichnen();
      return;
    }
    clearTimeout(r.scharf);
    const stelle = reiter.indexOf(r);
    reiter.splice(stelle, 1);
    if (!reiter.length){ neuerReiter(); }
    else if (id === aktivId){ aktivId = null; aktivieren(reiter[Math.max(0, stelle - 1)].id); }
    else reiterZeichnen();
    entwurfMerken();
  }

  // ---- Schreibfeld -----------------------------------------------------
  function umbruchAnwenden(r){
    text.wrap = r.umbruch ? 'soft' : 'off';
    text.classList.toggle('umbruch', r.umbruch);
    // Mit Umbruch passen Zeilennummern nicht mehr zu den sichtbaren Zeilen.
    zeilen.hidden = r.umbruch;
    $('edUmbruch').classList.toggle('an', r.umbruch);
  }

  function zeilenZeichnen(){
    if (zeilen.hidden) return;
    const n = text.value.split('\n').length;
    if (zeilen.dataset.n === String(n)) return;
    zeilen.dataset.n = n;
    zeilen.textContent = Array.from({ length: n }, (_, i) => i + 1).join('\n');
    zeilen.scrollTop = text.scrollTop;
  }

  function statusZeichnen(){
    const r = aktiv();
    if (!r) return;
    $('edPfad').textContent = r.pfad ? kurzPfad(r.pfad) : 'noch nicht gespeichert';
    const vorher = text.value.slice(0, text.selectionStart);
    const zeile = vorher.split('\n').length;
    const spalte = vorher.length - vorher.lastIndexOf('\n');
    const endung = (r.pfad || '').split('.').pop().toLowerCase();
    const art = r.pfad ? (ARTEN[endung] || 'Text') : 'Text';
    const zustand = !r.pfad && !r.inhalt ? 'leer' : geaendert(r) ? 'nicht gespeichert' : 'gespeichert';
    $('edPosition').textContent = `Zeile ${zeile}, Spalte ${spalte} · ${art} · ${zustand}`;
  }

  text.addEventListener('input', () => {
    const r = aktiv();
    const warGeaendert = geaendert(r);
    r.inhalt = text.value;
    zeilenZeichnen();
    statusZeichnen();
    if (geaendert(r) !== warGeaendert) reiterZeichnen();
    entwurfMerken();
  });
  text.addEventListener('scroll', () => { zeilen.scrollTop = text.scrollTop; });
  ['click', 'keyup', 'select'].forEach(art => text.addEventListener(art, statusZeichnen));

  function einfuegen(t){
    // execCommand haelt Strg+Z intakt - direktes Setzen von value wuerde den
    // Rueckgaengig-Verlauf loeschen.
    document.execCommand('insertText', false, t);
  }

  text.addEventListener('keydown', ev => {
    const strg = ev.ctrlKey || ev.metaKey;
    if (ev.key === 'Tab' && !strg){
      ev.preventDefault();
      einfuegen('    ');
    } else if (ev.key === 'Enter' && !strg){
      // Einrueckung der aktuellen Zeile mitnehmen - bei Python wichtig.
      const vorher = text.value.slice(0, text.selectionStart);
      const zeile = vorher.slice(vorher.lastIndexOf('\n') + 1);
      let einzug = (zeile.match(/^[ \t]*/) || [''])[0];
      if (/:\s*$/.test(zeile) && /\.py$/i.test(aktiv().pfad || '')) einzug += '    ';
      if (einzug){ ev.preventDefault(); einfuegen('\n' + einzug); }
    }
  });

  // Tastenkuerzel, solange der Fokus im Editor steht
  document.querySelector('.ed').addEventListener('keydown', ev => {
    if (!(ev.ctrlKey || ev.metaKey)) return;
    const taste = ev.key.toLowerCase();
    if (taste === 's'){ ev.preventDefault(); ev.shiftKey ? speichernUnter() : speichern(); }
    else if (taste === 'o'){ ev.preventDefault(); oeffnen(); }
    else if (taste === 'n'){ ev.preventDefault(); neuerReiter(); }
  });

  // ---- Dateien -----------------------------------------------------------
  async function dateiLaden(pfad){
    const schon = reiter.find(r => r.pfad === pfad);
    if (schon){ aktivieren(schon.id); return; }
    if (!M.editorDateiLesen){ meldung('Öffnen geht nur in der Milcrid-App.', 'fehler'); return; }
    const antwort = await M.editorDateiLesen(pfad);
    if (!antwort.erfolg){ meldung(`${dateiname(pfad)}: ${antwort.fehler}`, 'fehler'); return; }
    // Ein leeres, unveraendertes Blatt wird ersetzt statt stehen zu bleiben.
    const leer = aktiv();
    const r = neuerReiter(antwort.pfad, antwort.inhalt);
    if (leer && !leer.pfad && !leer.inhalt && leer.id !== r.id){
      reiter = reiter.filter(x => x.id !== leer.id);
      reiterZeichnen();
    }
    entwurfMerken();
  }

  async function oeffnen(){
    if (!M.dateiAuswaehlen){ meldung('Öffnen geht nur in der Milcrid-App.', 'fehler'); return; }
    const pfade = await M.dateiAuswaehlen();
    for (const p of pfade || []) await dateiLaden(p);
  }

  async function speichern(){
    const r = aktiv();
    if (!r.pfad) return speichernUnter();
    if (!M.editorDateiSchreiben){ meldung('Speichern geht nur in der Milcrid-App.', 'fehler'); return; }
    const antwort = await M.editorDateiSchreiben(r.pfad, r.inhalt);
    if (!antwort.erfolg){ meldung('Nicht gespeichert: ' + antwort.fehler, 'fehler'); return; }
    r.gespeichert = r.inhalt;
    reiterZeichnen(); statusZeichnen(); entwurfMerken();
    meldung('Gespeichert.', 'erfolg');
  }

  async function speichernUnter(){
    const r = aktiv();
    if (!M.dateiSpeichernDialog){ meldung('Speichern geht nur in der Milcrid-App.', 'fehler'); return; }
    const antwort = await M.dateiSpeichernDialog({ vorschlagName: r.pfad || (r.name + '.txt'), inhalt: r.inhalt });
    if (antwort.abgebrochen) return;
    if (!antwort.erfolg){ meldung('Nicht gespeichert: ' + antwort.fehler, 'fehler'); return; }
    r.pfad = antwort.pfad;
    r.name = dateiname(antwort.pfad);
    r.gespeichert = r.inhalt;
    reiterZeichnen(); statusZeichnen(); entwurfMerken();
    meldung('Gespeichert.', 'erfolg');
  }

  // ---- Entwuerfe: ueberleben einen Portal-Neustart --------------------------
  // Gespeicherte Dateien werden nur als Pfad gemerkt und beim naechsten Mal
  // frisch von der Platte gelesen; nur Ungespeichertes wird mit Inhalt gemerkt.
  function entwurfMerken(){
    clearTimeout(entwurfTimer);
    entwurfTimer = setTimeout(() => {
      const daten = reiter.map(r => ({ pfad: r.pfad, name: r.name, umbruch: r.umbruch,
                                       inhalt: geaendert(r) ? r.inhalt : null }));
      try { localStorage.setItem(ENTWURF_SCHLUESSEL, JSON.stringify({ reiter: daten, aktiv: reiter.indexOf(aktiv()) })); }
      catch (e) { /* Speicher voll oder gesperrt - dann eben ohne Entwurf */ }
    }, 600);
  }

  async function entwurfLaden(){
    let daten = null;
    try { daten = JSON.parse(localStorage.getItem(ENTWURF_SCHLUESSEL) || 'null'); } catch (e) {}
    if (!daten || !Array.isArray(daten.reiter) || !daten.reiter.length) return false;
    for (const d of daten.reiter){
      if (d.inhalt !== null){
        // Ungespeichert: Inhalt zurueck, und er gilt weiter als ungespeichert.
        const r = neuerReiter(d.pfad, d.inhalt, d.pfad ? null : '');
        if (d.name && !d.pfad) r.name = d.name;
        if (typeof d.umbruch === 'boolean') r.umbruch = d.umbruch;
      } else if (d.pfad && M.editorDateiLesen){
        const antwort = await M.editorDateiLesen(d.pfad);
        if (antwort.erfolg){
          const r = neuerReiter(antwort.pfad, antwort.inhalt);
          if (typeof d.umbruch === 'boolean') r.umbruch = d.umbruch;
        }
      }
    }
    if (!reiter.length) return false;
    aktivieren(reiter[Math.min(Math.max(0, daten.aktiv || 0), reiter.length - 1)].id);
    return true;
  }

  // ---- Knoepfe -----------------------------------------------------------
  $('edNeu').addEventListener('click', () => neuerReiter());
  $('edOeffnen').addEventListener('click', oeffnen);
  $('edSpeichern').addEventListener('click', speichern);
  $('edSpeichernUnter').addEventListener('click', speichernUnter);
  $('edUmbruch').addEventListener('click', () => {
    const r = aktiv();
    r.umbruch = !r.umbruch;
    umbruchAnwenden(r);
    zeilen.dataset.n = '';
    zeilenZeichnen();
    entwurfMerken();
    text.focus();
  });

  // Fuer spaeter ("Oeffnen mit" im Datei Manager): eine Datei von aussen in
  // einem neuen Reiter oeffnen.
  window.milcridEditor = { oeffnen: dateiLaden };

  entwurfLaden().then(geladen => {
    if (!geladen) neuerReiter();
    // Wurde der Editor zum Oeffnen einer Datei gestartet (Datei Manager,
    // Themen, "oeffne notiz.txt"), liegt sie hier bereit - siehe
    // milcridAppMitDatei im Portal.
    const wartend = (window.milcridOeffnenWartend || {}).editor;
    if (wartend){ delete window.milcridOeffnenWartend.editor; dateiLaden(wartend); }
  });
})();
