/* ---- Taschenrechner: Grundrechenarten, Vorzeichen, Prozent - seit
   2026-09-14 (Klaus-Brainstorm: "ein paar Funktionen mehr, ist ja absoluter
   Standardrechner") auch Rueckschritt, CE, Wurzel, Quadrat, Kehrwert,
   Speicher und Tastatur. Die KI benutzt ihn nicht - er ist fuer Klaus
   zum Selbertippen. Eingeschlossen, damit kein Name mit dem Portal
   zusammenstoesst. ---- */
(() => {
  const $ = id => document.getElementById(id);
  const huelle = $('rechnerHuelle'), anzeigeEl = $('rechnerDisplay'), rechnungEl = $('rechnerRechnung');
  let anzeige = '0';
  let akku = null;
  let op = null;
  let ueberschreiben = true;
  let speicher = 0;
  let rechnung = '';

  const komma = t => String(t).replace('.', ',');
  function formatieren(n){
    if (!Number.isFinite(n)) return 'Fehler';
    return String(Math.round(n * 1e10) / 1e10);
  }
  const wert = () => (anzeige === 'Fehler' ? 0 : parseFloat(anzeige));

  function zeichnen(){
    anzeigeEl.textContent = komma(anzeige);
    rechnungEl.textContent = komma(rechnung);
    $('rechnerSpeicherZeichen').textContent = speicher ? 'M = ' + komma(formatieren(speicher)) : '';
  }

  function ziffer(d){
    if (ueberschreiben || anzeige === 'Fehler'){
      anzeige = d === '.' ? '0.' : d;
      ueberschreiben = false;
    } else if (d === '.'){
      if (!anzeige.includes('.')) anzeige += '.';
    } else {
      anzeige = anzeige === '0' ? d : anzeige + d;
    }
    zeichnen();
  }

  function rechnen(a, b, zeichen){
    switch (zeichen){
      case '+': return a + b;
      case '−': return a - b;
      case '×': return a * b;
      case '÷': return b === 0 ? NaN : a / b;
      default: return b;
    }
  }

  function operator(zeichen){
    if (op && !ueberschreiben){
      akku = rechnen(akku, wert(), op);
      anzeige = formatieren(akku);
    } else if (!op){
      akku = wert();
    }
    op = zeichen;
    rechnung = `${formatieren(akku)} ${zeichen}`;
    ueberschreiben = true;
    zeichnen();
  }

  function gleich(){
    if (op == null) return;
    const b = wert();
    const ergebnis = formatieren(rechnen(akku, b, op));
    const text = `${formatieren(akku)} ${op} ${formatieren(b)}`;
    anzeige = ergebnis;
    rechnung = text + ' =';
    akku = null;
    op = null;
    ueberschreiben = true;
    zeichnen();
  }

  // Eine Funktion auf die aktuelle Zahl anwenden (√, x², 1/x, ±)
  function einstellig(fn, name){
    const vorher = wert();
    anzeige = formatieren(fn(vorher));
    rechnung = `${name}(${formatieren(vorher)})`;
    ueberschreiben = true;
    zeichnen();
  }

  function prozent(){
    // Wie jeder Tischrechner: 200 + 10 % = 220 (10 % VON 200), 50 × 10 % = 5
    const x = wert();
    anzeige = formatieren(akku != null && (op === '+' || op === '−') ? akku * x / 100 : x / 100);
    ueberschreiben = false;
    zeichnen();
  }

  const aktionen = {
    clear(){ anzeige = '0'; akku = null; op = null; rechnung = ''; ueberschreiben = true; zeichnen(); },
    clearentry(){ anzeige = '0'; ueberschreiben = true; zeichnen(); },
    back(){
      if (ueberschreiben || anzeige === 'Fehler') return;
      anzeige = anzeige.length > 1 && !(anzeige.length === 2 && anzeige.startsWith('-')) ? anzeige.slice(0, -1) : '0';
      zeichnen();
    },
    sign(){ if (anzeige !== '0' && anzeige !== 'Fehler'){ anzeige = anzeige.startsWith('-') ? anzeige.slice(1) : '-' + anzeige; zeichnen(); } },
    percent: prozent,
    sqrt(){ einstellig(x => (x < 0 ? NaN : Math.sqrt(x)), '√'); },
    square(){ einstellig(x => x * x, 'sqr'); },
    inverse(){ einstellig(x => (x === 0 ? NaN : 1 / x), '1/'); },
    equals: gleich,
    mc(){ speicher = 0; zeichnen(); },
    mr(){ anzeige = formatieren(speicher); ueberschreiben = true; zeichnen(); },
    mplus(){ speicher += wert(); ueberschreiben = true; zeichnen(); },
    mminus(){ speicher -= wert(); ueberschreiben = true; zeichnen(); },
  };

  huelle.querySelectorAll('[data-digit]').forEach(b => b.addEventListener('click', () => ziffer(b.dataset.digit)));
  huelle.querySelectorAll('[data-op]').forEach(b => b.addEventListener('click', () => operator(b.dataset.op)));
  huelle.querySelectorAll('[data-action]').forEach(b => b.addEventListener('click', () => aktionen[b.dataset.action]()));

  // Tastatur nur, solange der Rechner den Fokus hat - sonst wuerde jede
  // Ziffer im Chat-Eingabefeld auch hier landen.
  const TASTEN = { '+': '+', '-': '−', '*': '×', '/': '÷', 'x': '×', ':': '÷' };
  huelle.addEventListener('keydown', e => {
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    let erledigt = true;
    if (/^[0-9]$/.test(e.key)) ziffer(e.key);
    else if (e.key === ',' || e.key === '.') ziffer('.');
    else if (TASTEN[e.key]) operator(TASTEN[e.key]);
    else if (e.key === 'Enter' || e.key === '=') gleich();
    else if (e.key === 'Backspace') aktionen.back();
    else if (e.key === 'Escape') aktionen.clear();
    else if (e.key === 'Delete') aktionen.clearentry();
    else if (e.key === '%') prozent();
    else erledigt = false;
    if (erledigt) e.preventDefault();   // Enter wuerde sonst auch den fokussierten Knopf noch einmal druecken
  });
  huelle.addEventListener('pointerdown', () => setTimeout(() => huelle.focus({ preventScroll: true }), 0));

  zeichnen();
})();
