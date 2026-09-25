/* ---- Milcrid Handbuch: Inhaltsverzeichnis aus den Ueberschriften (nummeriert
   wie bei Wikipedia), das gerade gelesene Kapitel markiert, Suche filtert
   Kapitel, Querverweise springen im Fenster. Eingeschlossen, damit kein Name
   mit dem Portal zusammenstoesst. ---- */
(() => {
  const $ = id => document.getElementById(id);
  const seite = $('hbSeite'), artikel = $('hbArtikel'), verzeichnis = $('hbVerzeichnis');
  const suche = $('hbSuche'), treffer = $('hbTreffer');

  // Deutsch / English (Klaus 26.09.2026: "englisches Handbuch mit in Milcrid").
  // Der deutsche Text steht in handbuch.html, der englische in handbuch-en.html
  // daneben; beim Umschalten wird der Artikel ausgetauscht und alles neu aufgebaut.
  const DEUTSCH = artikel.innerHTML;
  let englisch = null;
  const WORTE = {
    de: { inhalt: 'Inhalt', suche: '🔍 Im Handbuch suchen', oben: '↑ nach oben', gefunden: n => `${n} Kapitel gefunden`, nichts: 'Nichts gefunden.' },
    en: { inhalt: 'Contents', suche: '🔍 Search the handbook', oben: '↑ to top', gefunden: n => `${n} ${n === 1 ? 'chapter' : 'chapters'} found`, nichts: 'Nothing found.' },
  };
  let sprache = 'de';

  let kapitel = [], eintraege = [];     // eintraege: { a, ueberschrift, kapitel }
  function aufbauen(){
  // Portal-Logo in die Infobox (liegt neben milcrid_portal.html) - nur im deutschen Text.
  if ($('hbLogo')) $('hbLogo').src = 'milcrid-icon-alt.jpg';

  // ---- Kapitel bilden: jede <h2> mit allem bis zur naechsten <h2> ----
  kapitel = []; eintraege = [];
  verzeichnis.textContent = '';
  let aktuell = null;
  for (const el of [...artikel.children]){
    if (el.tagName === 'H2'){
      aktuell = document.createElement('section');
      el.before(aktuell);
      kapitel.push(aktuell);
    }
    if (aktuell && el !== aktuell) aktuell.append(el);
  }

  // ---- Inhaltsverzeichnis ----
  let n2 = 0, n3 = 0;
  for (const k of kapitel){
    for (const h of k.querySelectorAll('h2, h3')){
      const stufe3 = h.tagName === 'H3';
      if (stufe3) n3++; else { n2++; n3 = 0; }
      const nr = stufe3 ? `${n2}.${n3}` : `${n2}`;
      const a = document.createElement('a');
      a.href = '#' + h.id;
      a.className = stufe3 ? 'stufe3' : '';
      const nrEl = document.createElement('span'); nrEl.className = 'nr'; nrEl.textContent = nr;
      const text = document.createElement('span'); text.textContent = h.textContent;
      a.append(nrEl, text);
      verzeichnis.append(a);
      // Nummer auch vor die Ueberschrift im Text, wie bei Wikipedia
      h.textContent = nr + '  ' + h.textContent;
      eintraege.push({ a, ueberschrift: h, kapitel: k });
    }
  }
  }
  aufbauen();

  async function spracheWechseln(neu){
    if (neu === sprache) return;
    if (neu === 'en' && englisch === null){
      try { englisch = await window.milcrid.appDateiLesen('handbuch/handbuch-en.html'); }
      catch (e) { englisch = '<p>The English handbook could not be loaded.</p>'; }
    }
    sprache = neu;
    artikel.innerHTML = neu === 'en' ? englisch : DEUTSCH;
    const w = WORTE[neu];
    document.querySelector('.hb-inhalt-titel').textContent = w.inhalt;
    suche.placeholder = w.suche;
    $('hbNachOben').textContent = w.oben;
    document.querySelectorAll('.hb-sprache button').forEach(b => b.classList.toggle('aktiv', b.dataset.sprache === neu));
    suche.value = '';
    aufbauen();
    filtern();
  }
  document.querySelectorAll('.hb-sprache button').forEach(b =>
    b.addEventListener('click', () => spracheWechseln(b.dataset.sprache)));

  // ---- Springen: im Fenster scrollen, nie die Portal-Adresse aendern ----
  function springen(id){
    const ziel = document.getElementById(id);
    if (!ziel || !artikel.contains(ziel)) return;
    if (ziel.closest('section') && ziel.closest('section').hidden){ suche.value = ''; filtern(); }
    // Aus den Bildschirm-Positionen gerechnet: offsetTop haengt davon ab, welches
    // Element gerade "positioniert" ist - im Portal ein anderes als in der Probe.
    const ziel_y = seite.scrollTop + ziel.getBoundingClientRect().top - seite.getBoundingClientRect().top - 8;
    seite.scrollTo({ top: ziel_y, behavior: 'smooth' });
  }
  document.querySelector('.hb').addEventListener('click', ev => {
    const a = ev.target.closest('a[href^="#hb-"]');
    if (!a) return;
    ev.preventDefault();
    springen(a.getAttribute('href').slice(1));
  });

  // ---- Wo bin ich? Das oberste sichtbare Kapitel markieren ----
  let markierUhr = null;
  function markieren(){
    const oben = seite.getBoundingClientRect().top + 40;
    let bester = null;
    for (const e of eintraege){
      if (e.kapitel.hidden) continue;
      if (e.ueberschrift.getBoundingClientRect().top <= oben) bester = e;
    }
    eintraege.forEach(e => e.a.classList.toggle('aktiv', e === bester));
    // Markierten Eintrag im Verzeichnis sichtbar halten - bewusst OHNE
    // scrollIntoView: das bricht in Chromium ein laufendes sanftes Scrollen im
    // Artikel ab, ein Sprung blieb dann auf halbem Weg stehen (Probe 24.09.).
    if (bester){
      const a = bester.a, v = verzeichnis;
      if (a.offsetTop < v.scrollTop || a.offsetTop + a.offsetHeight > v.scrollTop + v.clientHeight)
        v.scrollTop = a.offsetTop - v.clientHeight / 2;
    }
    $('hbNachOben').hidden = seite.scrollTop < 400;
  }
  seite.addEventListener('scroll', () => {
    // hoechstens einmal je Bild rechnen - nicht bei jedem Scroll-Ereignis
    if (markierUhr) return;
    markierUhr = requestAnimationFrame(() => { markierUhr = null; markieren(); });
  }, { passive: true });
  $('hbNachOben').addEventListener('click', () => seite.scrollTo({ top: 0, behavior: 'smooth' }));

  // ---- Suche: nur Kapitel zeigen, in denen das Wort vorkommt ----
  function filtern(){
    const wort = suche.value.trim().toLowerCase();
    let gezeigt = 0;
    for (const k of kapitel){
      const passt = !wort || k.textContent.toLowerCase().includes(wort);
      k.hidden = !passt;
      if (passt) gezeigt++;
    }
    for (const e of eintraege){
      e.a.hidden = e.kapitel.hidden
        || (wort && e.ueberschrift.tagName === 'H3' && !unterabschnittText(e).includes(wort));
    }
    // Einleitung (vor dem ersten Kapitel) nur ohne Suche zeigen
    for (const el of artikel.children){ if (el.tagName !== 'SECTION') el.hidden = !!wort && el.tagName !== 'H1'; }
    treffer.hidden = !wort;
    treffer.textContent = gezeigt ? WORTE[sprache].gefunden(gezeigt) : WORTE[sprache].nichts;
    // sofort nach oben - ein sanftes Scrollen liefe sonst einem Sprung direkt danach in die Quere
    seite.scrollTo({ top: 0, behavior: 'instant' });
    markieren();
  }
  // Text eines Unterabschnitts: von seiner <h3> bis zur naechsten Ueberschrift
  function unterabschnittText(e){
    let t = e.ueberschrift.textContent, el = e.ueberschrift.nextElementSibling;
    while (el && !/^H[23]$/.test(el.tagName)){ t += ' ' + el.textContent; el = el.nextElementSibling; }
    return t.toLowerCase();
  }
  suche.addEventListener('input', filtern);
  suche.addEventListener('keydown', ev => { if (ev.key === 'Escape'){ suche.value = ''; filtern(); } });

  // Von aussen: ein bestimmtes Kapitel zeigen (z. B. spaeter "oeffne Handbuch Tastatur").
  window.milcridHandbuch = { zeigen: id => springen(id.startsWith('hb-') ? id : 'hb-' + id) };
  markieren();
})();
