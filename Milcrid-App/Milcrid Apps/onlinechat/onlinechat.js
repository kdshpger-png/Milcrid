/* ---- Online KI: Anbieter waehlen, Verbindung an/aus, chatten. Alles, was
   passiert, entscheidet main.py (online_ki_verwaltung.py) - diese App zeigt
   nur den Stand und schickt Wuensche. Eingeschlossen, damit kein Name mit
   dem Portal zusammenstoesst. ---- */
(() => {
  const K = window.milcridOnlineKi;
  const $ = id => document.getElementById(id);
  const auswahl = $('okAnbieter'), schalter = $('okVerbindung'), lage = $('okLage'), verlauf = $('okVerlauf');
  const text = $('okText'), sendenKnopf = $('okSenden'), anhaengeEl = $('okAnhaenge');
  let daten = null;
  let anhaenge = [];            // Pfade, die mit der naechsten Nachricht gehen
  let sendetGerade = false;     // diese App wartet selbst auf eine Antwort
  let gezeichneterChat = '';    // Fingerabdruck - nur neu zeichnen, wenn sich etwas geaendert hat
  let nachfragen = null;

  function status(t, art){
    $('okStatus').textContent = t || '';
    $('okStatus').className = 'ok-status' + (art ? ' ' + art : '');
  }

  function aktiveAnbieter(){ return daten ? daten.anbieter.filter(a => a.aktiv) : []; }

  function kopfZeichnen(){
    const aktive = aktiveAnbieter();
    const gewaehlt = daten.verbindung.offen ? daten.verbindung.anbieter : daten.auswahl;
    auswahl.textContent = '';
    if (!aktive.length){
      const o = document.createElement('option');
      o.textContent = 'kein Schlüssel aktiv';
      o.value = '';
      auswahl.append(o);
    }
    for (const a of aktive){
      const o = document.createElement('option');
      o.value = a.id;
      o.textContent = a.name;
      auswahl.append(o);
    }
    auswahl.value = gewaehlt || (aktive[0] ? aktive[0].id : '');
    auswahl.disabled = aktive.length < 2 || sendetGerade;
    const a = aktive.find(x => x.id === auswahl.value);
    $('okModell').textContent = a ? a.modell : '';
    $('okModell').title = a ? 'Modell – änderbar im Bereich API KI' : '';

    const offen = daten.verbindung.offen;
    schalter.classList.toggle('an', offen);
    schalter.disabled = !aktive.length || sendetGerade;
    lage.classList.toggle('offen', offen);
    if (offen){
      const name = (daten.anbieter.find(x => x.id === daten.verbindung.anbieter) || {}).name || '';
      lage.textContent = `Verbunden mit ${name} – was du sendest, geht nach draußen.`;
    } else {
      lage.textContent = aktive.length ? 'Verbindung aus – es geht nichts nach draußen.'
                                       : 'Kein Schlüssel aktiv – im Bereich API KI eintragen.';
    }
    const beschaeftigt = sendetGerade || daten.beschaeftigt;
    text.disabled = !offen;
    sendenKnopf.disabled = !offen || beschaeftigt;
    $('okDatei').disabled = !offen || beschaeftigt;
    $('okNeu').disabled = beschaeftigt || !daten.chat.length;
    $('okChatSpeichern').disabled = !daten.chat.length;
  }

  // Antwort-Text: Codebloecke (```sprache ... ```) als eigene Kaesten, der
  // Rest als Text. Nur textContent - was die KI schreibt, wird nie als HTML
  // ausgefuehrt.
  function textZerlegen(blase, inhalt){
    const muster = /```([\w+#.-]*)[^\n]*\n([\s\S]*?)```/g;
    let rest = 0, treffer;
    // Text zwischen den Codebloecken: ###, **fett**, Aufzaehlungen sauber
    // statt roh (22.09.) - die Darstellung kommt aus dem Portal, damit es sie
    // nur einmal gibt (siehe mdAufbauen dort).
    const absatz = t => {
      if (!t.trim()) return;
      const p = document.createElement('div');
      p.className = 'ok-absatz';
      const sauber = t.replace(/^\n+|\n+$/g, '');
      if (K.textAufbauen) p.append(K.textAufbauen(sauber)); else p.textContent = sauber;
      blase.append(p);
    };
    while ((treffer = muster.exec(inhalt))){
      absatz(inhalt.slice(rest, treffer.index));
      const kasten = document.createElement('div');
      kasten.className = 'ok-code';
      const kopf = document.createElement('div');
      kopf.className = 'ok-code-kopf';
      const sprache = document.createElement('span');
      sprache.textContent = treffer[1] || 'Code';
      const kopieren = document.createElement('button');
      kopieren.className = 'ok-knopf klein';
      kopieren.type = 'button';
      kopieren.textContent = 'Kopieren';
      const code = treffer[2];
      kopieren.addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(code); kopieren.textContent = 'Kopiert ✓'; }
        catch (e) { kopieren.textContent = 'ging nicht'; }
        setTimeout(() => { kopieren.textContent = 'Kopieren'; }, 1800);
      });
      kopf.append(sprache, kopieren);
      const pre = document.createElement('pre');
      pre.textContent = code;
      kasten.append(kopf, pre);
      blase.append(kasten);
      rest = muster.lastIndex;
    }
    absatz(inhalt.slice(rest));
  }

  function knopf(beschriftung, fn){
    const b = document.createElement('button');
    b.className = 'ok-knopf klein';
    b.type = 'button';
    b.textContent = beschriftung;
    b.addEventListener('click', fn);
    return b;
  }

  async function speichernMelden(versprechen){
    const antwort = await versprechen;
    status(antwort.erfolg ? antwort.meldung : antwort.fehler, antwort.erfolg ? 'erfolg' : 'fehler');
  }

  function verlaufZeichnen(){
    const fingerabdruck = JSON.stringify([daten.chat, sendetGerade || daten.beschaeftigt, aktiveAnbieter().length]);
    if (fingerabdruck === gezeichneterChat) return;
    gezeichneterChat = fingerabdruck;
    const warUnten = verlauf.scrollHeight - verlauf.scrollTop - verlauf.clientHeight < 40;
    verlauf.textContent = '';
    if (!daten.chat.length && !(sendetGerade || daten.beschaeftigt)){
      const leer = document.createElement('div');
      leer.className = 'ok-leer';
      if (!aktiveAnbieter().length){
        leer.append('Noch kein Schlüssel aktiv. Trag ihn im Bereich ', Object.assign(document.createElement('b'), { textContent: 'API KI' }),
                    ' ein – dann hier den Schalter ', Object.assign(document.createElement('b'), { textContent: 'Verbindung' }), ' einschalten.');
      } else {
        leer.append('Schalter ', Object.assign(document.createElement('b'), { textContent: 'Verbindung' }),
                    ' einschalten und losschreiben. Mit 📎 gehen PDFs, Bilder, Text- und Office-Dateien mit.');
      }
      verlauf.append(leer);
    }
    daten.chat.forEach((n, index) => {
      const blase = document.createElement('div');
      blase.className = 'ok-blase ' + n.rolle;
      const kopf = document.createElement('div');
      kopf.className = 'ok-blase-kopf';
      kopf.textContent = (n.rolle === 'nutzer' ? 'Ich' : `${n.anbieter} · ${n.modell}`) + ' · ' + n.zeit;
      blase.append(kopf);
      if (n.dateien.length){
        const d = document.createElement('div');
        d.className = 'ok-dateien';
        d.textContent = '📎 ' + n.dateien.join(', ');
        blase.append(d);
      }
      if (n.rolle === 'nutzer'){
        const p = document.createElement('div');
        p.className = 'ok-absatz';
        p.textContent = n.text;
        blase.append(p);
      } else {
        textZerlegen(blase, n.text);
        const fuss = document.createElement('div');
        fuss.className = 'ok-blase-fuss';
        fuss.append(knopf('Antwort speichern', () => speichernMelden(K.antwortSpeichern(index, false))));
        if (n.code) fuss.append(knopf(n.code > 1 ? `Code speichern (${n.code} Dateien)` : 'Code als Datei speichern',
                                      () => speichernMelden(K.antwortSpeichern(index, true))));
        fuss.append(knopf('Kopieren', async () => {
          try { await navigator.clipboard.writeText(n.text); status('Antwort kopiert.', 'erfolg'); }
          catch (e) { status('Kopieren ging nicht.', 'fehler'); }
        }));
        blase.append(fuss);
      }
      verlauf.append(blase);
    });
    if (sendetGerade || daten.beschaeftigt){
      const w = document.createElement('div');
      w.className = 'ok-warten';
      const name = (daten.anbieter.find(x => x.id === daten.verbindung.anbieter) || {}).name || 'Die Online-KI';
      w.textContent = `${name} antwortet`;
      verlauf.append(w);
    }
    if (warUnten || sendetGerade) verlauf.scrollTop = verlauf.scrollHeight;
  }

  function anhaengeZeichnen(){
    anhaengeEl.textContent = '';
    anhaengeEl.hidden = !anhaenge.length;
    anhaenge.forEach((pfad, i) => {
      const chip = document.createElement('span');
      chip.className = 'ok-anhang';
      chip.title = pfad;
      chip.append(pfad.split('/').pop());
      const weg = document.createElement('button');
      weg.type = 'button';
      weg.textContent = '✕';
      weg.title = 'Nicht mitsenden';
      weg.addEventListener('click', () => { anhaenge.splice(i, 1); anhaengeZeichnen(); });
      chip.append(weg);
      anhaengeEl.append(chip);
    });
  }

  function beiDaten(neu){
    daten = neu;
    kopfZeichnen();
    verlaufZeichnen();
    // Laeuft eine Anfrage, die nicht von hier kam (Portal neu geladen, waehrend
    // eine Antwort unterwegs war): nachsehen, bis sie da ist.
    clearTimeout(nachfragen);
    if (daten.beschaeftigt && !sendetGerade) nachfragen = setTimeout(() => K.holen(), 2000);
  }

  async function senden(){
    if (!daten || !daten.verbindung.offen || sendetGerade) return;
    const eingabe = text.value.trim();
    if (!eingabe && !anhaenge.length) return;
    sendetGerade = true;
    status('');
    // Die Frage sofort zeigen, nicht erst mit der Antwort
    const vorlaeufig = Object.assign({}, daten, { chat: daten.chat.concat([{ rolle: 'nutzer', text: eingabe,
      dateien: anhaenge.map(p => p.split('/').pop()), anbieter: '', modell: '', zeit: 'jetzt', code: 0 }]) });
    beiDaten(vorlaeufig);
    const mitgeschickt = anhaenge.slice();
    text.value = '';
    anhaenge = [];
    anhaengeZeichnen();
    const antwort = await K.senden(eingabe, mitgeschickt);
    sendetGerade = false;
    if (!antwort.erfolg){
      // Nichts verlieren: Text und Dateien zurueck ins Eingabefeld
      text.value = eingabe;
      anhaenge = mitgeschickt;
      anhaengeZeichnen();
      status(antwort.fehler, 'fehler');
    } else {
      status(`Antwort in ${antwort.dauer} s.`);
    }
    if (antwort.daten) beiDaten(antwort.daten); else K.holen();
    text.focus();
  }

  schalter.addEventListener('click', async () => {
    if (!daten) return;
    const an = !daten.verbindung.offen;
    const antwort = await K.verbindung(an, auswahl.value);
    if (!antwort.erfolg) status(antwort.fehler, 'fehler');
    else status(an ? 'Verbindung an.' : 'Verbindung aus.');
    if (an && antwort.erfolg) text.focus();
  });
  auswahl.addEventListener('change', async () => {
    // VOR dem Senden merken - die Antwort bringt schon den neuen Stand (aus)
    const warOffen = !!(daten && daten.verbindung.offen);
    const antwort = await K.auswahl(auswahl.value);
    if (!antwort.erfolg) status(antwort.fehler, 'fehler');
    else status(warOffen ? 'Anbieter gewechselt – die Verbindung ist jetzt aus, bitte wieder einschalten.' : '');
  });
  sendenKnopf.addEventListener('click', senden);
  text.addEventListener('keydown', ev => {
    if (ev.key === 'Enter' && !ev.shiftKey){ ev.preventDefault(); senden(); }
  });
  text.addEventListener('input', () => {
    text.style.height = 'auto';
    text.style.height = Math.min(text.scrollHeight, 160) + 'px';
  });
  $('okDatei').addEventListener('click', async () => {
    const pfade = await K.dateiWaehlen();
    for (const p of pfade) if (!anhaenge.includes(p)) anhaenge.push(p);
    anhaengeZeichnen();
  });
  let neuScharf = null;
  $('okNeu').addEventListener('click', async () => {
    if (!neuScharf){
      $('okNeu').textContent = 'Wirklich leeren?';
      neuScharf = setTimeout(() => { neuScharf = null; $('okNeu').textContent = 'Neuer Chat'; }, 4000);
      return;
    }
    clearTimeout(neuScharf);
    neuScharf = null;
    $('okNeu').textContent = 'Neuer Chat';
    const antwort = await K.neuerChat();
    status(antwort.erfolg ? 'Neuer Chat.' : antwort.fehler, antwort.erfolg ? '' : 'fehler');
  });
  $('okChatSpeichern').addEventListener('click', () => speichernMelden(K.chatSpeichern()));
  $('okOrdner').addEventListener('click', async () => {
    const fehler = await K.ordnerOeffnen();
    if (fehler) status('Den Ordner gibt es erst, wenn etwas gespeichert wurde.', 'fehler');
  });
  $('okApiKi').addEventListener('click', () => K.apiKiOeffnen());

  K.anmelden(beiDaten);
})();
