/* Langues du site.
 *
 * Le texte français écrit dans la page et dans app.js sert de clé : un
 * dictionnaire par langue (langues/<code>.js, qui définit window.TRAD) donne
 * la traduction. Un moteur parcourt la page et traduit les textes affichés
 * (et ceux ajoutés plus tard par app.js). Un texte absent du dictionnaire
 * reste en français, sans casser la page.
 *
 *   - ajouter une langue : un bloc dans LANGUES + un fichier langues/<code>.js ;
 *   - ajouter un texte    : l'écrire en français dans la page, puis ajouter
 *     sa traduction dans chaque langues/<code>.js ;
 *   - un texte variable s'écrit avec {0}, {1}… (ex. "du {0} au {1}") ;
 *   - un pluriel prend un objet à la place d'une chaîne ({one, other, …}).
 */
const LANGUES = [
  { code: "fr", nom: "Français",  lieu: "fr-FR", dir: "ltr" },
  { code: "en", nom: "English",   lieu: "en-GB", dir: "ltr" },
  { code: "es", nom: "Español",   lieu: "es-ES", dir: "ltr" },
  { code: "de", nom: "Deutsch",   lieu: "de-DE", dir: "ltr" },
  { code: "pt", nom: "Português", lieu: "pt-PT", dir: "ltr" },
  { code: "ro", nom: "Română",    lieu: "ro-RO", dir: "ltr" },
  { code: "ru", nom: "Русский",   lieu: "ru-RU", dir: "ltr" },
  { code: "pl", nom: "Polski",    lieu: "pl-PL", dir: "ltr" },
  { code: "ar", nom: "العربية",   lieu: "ar-u-nu-latn", dir: "rtl" },
];
const CLE_LANGUE = "medvault.langue";
let langueCourante = "fr";
try {
  const m = localStorage.getItem(CLE_LANGUE);
  if (LANGUES.some(l => l.code === m)) langueCourante = m;
} catch { /* stockage indisponible : français */ }
const infoLangue = LANGUES.find(l => l.code === langueCourante);
const lieu = () => infoLangue.lieu;

document.documentElement.lang = langueCourante;
document.documentElement.dir = infoLangue.dir;
// Le dictionnaire se charge avant le reste de la page.
if (langueCourante !== "fr") {
  document.write('<script src="langues/' + langueCourante + '.js?v=8"><\/script>');
}

function changerLangue(code) {
  try { localStorage.setItem(CLE_LANGUE, code); } catch {}
  location.reload();
}

(function moteur() {
  const norm = (s) => s.replace(/\s+/g, " ").trim();
  const echapper = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  let exact = new Map();
  let motifs = [];
  const regles = new Intl.PluralRules(infoLangue.lieu.split("-")[0]);
  const manquants = new Set();
  window.nonTraduits = () => [...manquants].sort();

  function preparer() {
    exact = new Map(); motifs = [];
    for (const [cle, val] of Object.entries(window.TRAD || {})) {
      if (/\{\d+\}/.test(cle)) {
        const morceaux = cle.split(/\{\d+\}/);
        const re = new RegExp("^" + morceaux.map(echapper).join("(.+?)") + "$");
        motifs.push({ re, val, poids: morceaux.join("").length });
      } else exact.set(cle, val);
    }
    motifs.sort((a, b) => b.poids - a.poids);
  }
  function forme(val, args) {
    if (typeof val === "string") return val;
    const n = Number(args && args[0]);
    const cat = Number.isFinite(n) ? regles.select(n) : "other";
    return val[cat] ?? val.other;
  }
  function traduire(texte) {
    const cle = norm(texte);
    if (!cle) return null;
    if (exact.has(cle)) return forme(exact.get(cle));
    for (const m of motifs) {
      const r = m.re.exec(cle);
      if (r) {
        const args = r.slice(1).map(a => traduire(a) ?? a);  // les valeurs variables se traduisent aussi
        return forme(m.val, args).replace(/\{(\d+)\}/g, (_, i) => args[i] ?? "");
      }
    }
    return null;
  }
  window.traduire = (t) => (langueCourante === "fr" ? t : (traduire(t) ?? t));

  const IGNORER = new Set(["SCRIPT", "STYLE", "TEXTAREA", "NOSCRIPT", "OPTION_VALUE"]);
  function noeud(n) {
    const v = n.nodeValue;
    if (n.__tr !== undefined && v === n.__tr) return;
    const p = n.parentElement;
    if (!p || IGNORER.has(p.tagName) || p.closest('[translate="no"]')) return;
    const t = traduire(v);
    if (t === null) {
      if (/[A-Za-zÀ-ÿ]{3}/.test(v) && !/@|^\s*[\d\/:.\-, ]+\s*$/.test(v)) manquants.add(norm(v));
      return;
    }
    n.__tr = v.match(/^\s*/)[0] + t + v.match(/\s*$/)[0];
    n.nodeValue = n.__tr;
  }
  const ATTRS = ["placeholder", "title", "aria-label", "alt"];
  function attributs(el) {
    for (const a of ATTRS) {
      const v = el.getAttribute && el.getAttribute(a);
      if (!v) continue;
      el.__trAttr = el.__trAttr || {};
      if (el.__trAttr[a] === v) continue;
      const t = traduire(v);
      if (t !== null) { el.__trAttr[a] = t; el.setAttribute(a, t); }
      else if (/[A-Za-zÀ-ÿ]{3}/.test(v) && !/@/.test(v)) manquants.add(norm(v));
    }
  }
  function arbre(racine) {
    if (racine.nodeType === 3) return noeud(racine);
    if (racine.nodeType !== 1) return;
    if (IGNORER.has(racine.tagName)) return;
    attributs(racine);
    const w = document.createTreeWalker(racine, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    let c;
    while ((c = w.nextNode())) c.nodeType === 3 ? noeud(c) : attributs(c);
  }

  function selecteurs() {
    document.querySelectorAll("[data-selecteur-langue]").forEach(sel => {
      if (sel.options.length) return;
      LANGUES.forEach(l => sel.add(new Option(l.nom, l.code, false, l.code === langueCourante)));
      sel.addEventListener("change", () => changerLangue(sel.value));
    });
  }

  function demarrer() {
    selecteurs();
    if (langueCourante === "fr") return;
    preparer();
    document.title = traduire(document.title) ?? document.title;
    arbre(document.body);
    new MutationObserver(muts => {
      for (const m of muts) {
        if (m.type === "childList") m.addedNodes.forEach(arbre);
        else if (m.type === "characterData") noeud(m.target);
        else if (m.type === "attributes") attributs(m.target);
      }
    }).observe(document.body, { childList: true, subtree: true, characterData: true,
                                attributes: true, attributeFilter: ATTRS });
    // Boîtes de dialogue natives
    for (const f of ["confirm", "alert"]) {
      const orig = window[f].bind(window);
      window[f] = (msg) => orig(traduire(String(msg)) ?? msg);
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", demarrer);
  else demarrer();
})();
