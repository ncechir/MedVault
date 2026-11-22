// ==========================================================================
// Medvault — interface de test
// Le serveur reste seul juge : cette page n'applique aucune règle de
// conformité, elle affiche ce que l'API décide.
// ==========================================================================
// Servie par l'API elle-même (http://127.0.0.1:8000) : appels en même origine.
// Servie à part (python -m http.server 3000) : on vise l'API sur le port 8000.
const API = location.port === "3000" ? "http://127.0.0.1:8000" : "";

// La session vit dans sessionStorage : elle survit à un rafraîchissement,
// mais disparaît à la fermeture de l'onglet. Sur un portail de données de
// santé, un jeton qui persiste après la fermeture du navigateur serait une
// mauvaise idée sur un poste partagé.
const CLE_JETON = "medvault.jeton";
const CLE_VUE = "medvault.vue";
const CLE_THEME = "medvault.theme";

const etat = {
  token: null,
  user: null,
  lots: [],
  lotCourant: null,
  selection: {},
  demandeId: null,
  parametres: { delai_purge_jours: 30, seuil_anonymat: 5 },
};

// Les 5 catégories, dites simplement : ce que c'est, et ce qui se passe par défaut.
// Chacune porte en plus une pastille de couleur (couleur, en mode clair — le
// mode sombre peut la redéfinir via la classe pastille-<code>, voir le CSS),
// pour la repérer d'un coup d'œil dans les listes denses.
const CATEGORIES = {
  IDENTIFIANT_DIRECT: { code: "identite", label: "Identité du patient", classe: "border-brique/40 text-brique bg-briquepale",
    couleur: "#3B3A12",
    explication: "Nom, IPP... Toujours remplacé par un code, jamais servi tel quel." },
  QUASI_IDENTIFIANT:  { code: "quasi", label: "Peut identifier indirectement", classe: "border-ambre/40 text-ambre bg-ambrepale",
    couleur: "#4F0C28",
    explication: "Date, code postal... Réduit par défaut (l'année plutôt que le jour, par exemple)." },
  DONNEE_SANTE:       { code: "sante", label: "Donnée médicale", classe: "border-vert/40 text-vert bg-vertpale",
    couleur: "#106305",
    explication: "Diagnostic, traitement... Servie telle quelle, en expliquant pourquoi." },
  ADMINISTRATIF:      { code: "admin", label: "Donnée administrative", classe: "border-trait text-ardoise bg-sable",
    couleur: "#E7993A",
    explication: "Service, durée de séjour... Aucune protection nécessaire." },
  DONNEE_PUBLIQUE:    { code: "public", label: "Donnée publique", classe: "border-lavande/40 text-lavande bg-bleuetpale",
    couleur: "#4A230E",
    explication: "Statistique ou référentiel déjà public : aucun patient concerné." },
};

const STATUTS = {
  BROUILLON:      "border-trait text-ardoise",
  SOUMISE:        "border-encre text-encre",
  EN_INSTRUCTION: "border-ambre text-ambre bg-ambrepale",
  VALIDEE:        "border-vert text-vert bg-vertpale",
  REFUSEE:        "border-brique text-brique bg-briquepale",
  ACTIVE:         "border-vert text-vert bg-vertpale",
  EXPIREE:        "border-trait text-ardoise",
  REVOQUEE:       "border-brique text-brique bg-briquepale",
  PURGEE:         "border-trait text-ardoise",
};

const LIBELLES_STATUT = {
  BROUILLON: "Brouillon", SOUMISE: "Soumise", EN_INSTRUCTION: "En instruction",
  VALIDEE: "Validée", REFUSEE: "Refusée", ACTIVE: "Ouvert", EXPIREE: "Clos",
  REVOQUEE: "Révoqué", PURGEE: "Données supprimées",
};


// Les codes techniques (R2_IDENTITE_EN_CLAIR...) ne s'affichent jamais tels quels.
const REGLES = {
  R1: "Aucune colonne", R2: "Identité en clair", R3: "Durée d'accès",
  R4: "Finalité", R5: "Ré-identification", R6: "Minimisation",
  R7: "Donnée de santé", R8: "Qualité des données", R9: "Périmètre de la demande",
};
const nomRegle = (code) => REGLES[String(code).split("_")[0]] ?? code;

const LIBELLES_NOTIF = {
  DECISION_VALIDEE:     ["Accès accordé",   "border-vert text-vert bg-vertpale"],
  DECISION_REFUSEE:     ["Demande refusée", "border-brique text-brique bg-briquepale"],
  ACCES_BIENTOT_EXPIRE: ["Échéance proche", "border-ambre text-ambre bg-ambrepale"],
  ACCES_EXPIRE:         ["Accès clos",      "border-trait text-ardoise"],
  ACCES_REVOQUE:        ["Accès révoqué",   "border-brique text-brique bg-briquepale"],
};

// ==========================================================================
// Utilitaires
// ==========================================================================
const $ = (s, racine = document) => racine.querySelector(s);
const $$ = (s, racine = document) => [...racine.querySelectorAll(s)];
const echapper = (t) => String(t ?? "").replace(/[&<>"]/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function notifier(message, type = "ok") {
  const n = $("#notif");
  n.textContent = message;
  n.className = "fixed bottom-6 left-1/2 -translate-x-1/2 rounded-lg px-4 py-2.5 text-sm text-white shadow-lg z-50 "
              + (type === "erreur" ? "bg-brique" : "bg-encre");
  clearTimeout(notifier.minuteur);
  notifier.minuteur = setTimeout(() => n.classList.add("hidden"), 4000);
  n.classList.remove("hidden");
}

const chip = (texte, classes) =>
  `<span class="inline-block border px-2 py-0.5 text-[11px] leading-4 rounded-full ${classes}">${echapper(texte)}</span>`;

// Pastille de catégorie : un rond de couleur + le libellé.
function chipCat(cat, libelleSecours, classesSecours) {
  if (!cat) return chip(libelleSecours, classesSecours || "border-trait text-ardoise");
  // Taille généreuse et liseré gris pour que la pastille reste repérable même
  // sur un fond très pâle (Porcelaine Mist) où la couleur seule ne suffit pas.
  return `<span class="inline-flex items-center gap-2 border px-2 py-0.5 text-[11px] leading-4 rounded-full ${cat.classe}">
    <span class="inline-block w-2.5 h-2.5 rounded-full shrink-0 pastille-${cat.code}" style="background:${cat.couleur}; box-shadow:0 0 0 1.5px #7C8696"></span>
    ${echapper(cat.label)}
  </span>`;
}

const statut = (code) => chip(LIBELLES_STATUT[code] ?? code, STATUTS[code] ?? "border-trait text-ardoise");

function dateFR(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("fr-FR",
    { day: "2-digit", month: "long", year: "numeric" });
}

function dateCourte(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("fr-FR",
    { day: "2-digit", month: "2-digit", year: "numeric" });
}

/** Ajoute des jours à une date ISO (AAAA-MM-JJ) et renvoie une date ISO. */
function ajouterJours(iso, jours) {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + jours);
  const deux = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${deux(d.getMonth() + 1)}-${deux(d.getDate())}`;
}

function horodatageFR(iso) {
  return new Date(iso).toLocaleString("fr-FR",
    { dateStyle: "short", timeStyle: "medium" });
}

/** Référence administrative d'un dossier, telle qu'on la citerait par écrit. */
function reference(demande) {
  if (demande.reference) return demande.reference;
  const annee = new Date(demande.cree_le ?? Date.now()).getFullYear();
  return `DA-${annee}-${String(demande.id).padStart(4, "0")}`;
}

async function api(chemin, { methode = "GET", corps = null, formulaire = null } = {}) {
  const options = { method: methode, headers: {} };
  if (etat.token) options.headers["Authorization"] = `Bearer ${etat.token}`;
  if (formulaire) {
    options.body = new URLSearchParams(formulaire);
  } else if (corps) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(corps);
  }

  let reponse;
  try {
    reponse = await fetch(API + chemin, options);
  } catch {
    throw { message: "Le serveur ne répond pas. Lancez « uvicorn app.main:app » depuis le dossier backend, "
                   + "puis ouvrez http://127.0.0.1:8000 dans le navigateur." };
  }

  if (reponse.status === 204) return null;
  const donnees = await reponse.json().catch(() => ({}));
  if (!reponse.ok) {
    const detail = donnees.detail;
    if (detail && typeof detail === "object" && detail.rapport) {
      throw { message: detail.message, rapport: detail.rapport };
    }
    const message = typeof detail === "string" ? detail
      : Array.isArray(detail) ? detail.map(d => d.msg).join(", ")
      : "Requête refusée par le serveur.";
    throw { message, statut: reponse.status };
  }
  return donnees;
}

async function telecharger(chemin, nomParDefaut) {
  try {
    const reponse = await fetch(API + chemin, {
      headers: { Authorization: `Bearer ${etat.token}` },
    });
    if (!reponse.ok) throw new Error();
    const blob = await reponse.blob();
    const lien = document.createElement("a");
    lien.href = URL.createObjectURL(blob);
    lien.download = nomParDefaut;
    lien.click();
    URL.revokeObjectURL(lien.href);
    notifier("Fichier téléchargé.");
  } catch {
    notifier("Le téléchargement a échoué.", "erreur");
  }
}

const vide = (texte) =>
  `<p class="px-5 py-8 text-sm text-ardoise leading-relaxed">${texte}</p>`;

// ==========================================================================
// Mode sombre
// ==========================================================================
function appliquerTheme(theme) {
  const sombre = theme === "sombre";
  document.documentElement.classList.toggle("dark", sombre);
  $$(".interrupteur-sombre").forEach(b => b.setAttribute("aria-pressed", String(sombre)));
  // Logos : une version claire du texte pour le fond bleu du mode sombre.
  $$(".logo-marque").forEach(img => img.src = sombre ? "assets/logo-sombre.png" : "assets/logo.png");
  $$(".marque-filigrane").forEach(img => img.src = sombre ? "assets/marque-sombre.png" : "assets/marque.png");
}
(function initTheme() {
  const prefere = localStorage.getItem(CLE_THEME)
    || (matchMedia("(prefers-color-scheme: dark)").matches ? "sombre" : "clair");
  appliquerTheme(prefere);
})();
function basculerTheme() {
  const actuel = document.documentElement.classList.contains("dark") ? "sombre" : "clair";
  const suivant = actuel === "sombre" ? "clair" : "sombre";
  localStorage.setItem(CLE_THEME, suivant);
  appliquerTheme(suivant);
}
$("#interrupteur-theme")?.addEventListener("click", basculerTheme);
$("#interrupteur-theme-connexion")?.addEventListener("click", basculerTheme);

// ==========================================================================
// Connexion
// ==========================================================================
$$(".raccourci").forEach(b => b.addEventListener("click", () => {
  $("#email").value = b.dataset.email;
  $("#mdp").value = b.dataset.mdp;
}));

$("#form-connexion").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#erreur-connexion").classList.add("hidden");
  try {
    const { access_token } = await api("/auth/login", {
      methode: "POST",
      formulaire: { username: $("#email").value, password: $("#mdp").value },
    });
    etat.token = access_token;
    sessionStorage.setItem(CLE_JETON, access_token);
    etat.user = await api("/auth/me");
    await demarrer();
  } catch (err) {
    const p = $("#erreur-connexion");
    p.textContent = err.message;
    p.classList.remove("hidden");
  }
});

$("#onglet-connexion").addEventListener("click", () => afficherOngletAuth("connexion"));
$("#onglet-inscription").addEventListener("click", () => afficherOngletAuth("inscription"));
$("#retour-connexion").addEventListener("click", () => afficherOngletAuth("connexion"));

function afficherOngletAuth(cle) {
  const connexion = cle === "connexion";
  $("#panneau-connexion").classList.toggle("hidden", !connexion);
  $("#panneau-inscription").classList.toggle("hidden", connexion);
  $("#onglet-connexion").classList.toggle("bg-carte", connexion);
  $("#onglet-connexion").classList.toggle("shadow-sm", connexion);
  $("#onglet-connexion").classList.toggle("text-ardoise", !connexion);
  $("#onglet-inscription").classList.toggle("bg-carte", !connexion);
  $("#onglet-inscription").classList.toggle("shadow-sm", !connexion);
  $("#onglet-inscription").classList.toggle("text-ardoise", connexion);
  $("#onglet-connexion").setAttribute("aria-selected", String(connexion));
  $("#onglet-inscription").setAttribute("aria-selected", String(!connexion));
}

$("#form-inscription").addEventListener("submit", async (e) => {
  e.preventDefault();
  const erreur = $("#erreur-inscription");
  erreur.classList.add("hidden");
  try {
    const { access_token } = await api("/auth/inscription", {
      methode: "POST",
      corps: {
        nom_complet: $("#i-nom").value.trim(),
        email: $("#i-email").value.trim(),
        service: $("#i-service").value.trim(),
        mot_de_passe: $("#i-mdp").value,
        engagement: $("#i-engagement").checked,
      },
    });
    etat.token = access_token;
    sessionStorage.setItem(CLE_JETON, access_token);
    etat.user = await api("/auth/me");
    await demarrer();
  } catch (err) {
    erreur.textContent = err.message;
    erreur.classList.remove("hidden");
  }
});

$("#btn-deconnexion").addEventListener("click", () => {
  sessionStorage.removeItem(CLE_JETON);
  sessionStorage.removeItem(CLE_VUE);
  location.reload();
});

// ==========================================================================
// Navigation
// ==========================================================================
const ROLES = { CHERCHEUR: "Chercheur", DPO: "Délégué à la protection des données", ADMIN: "Administrateur" };

const ONGLETS = [
  { cle: "pilotage",      libelle: "Tableau de bord",  roles: ["DPO"] },
  { cle: "accueil",       libelle: "Accueil",          roles: ["CHERCHEUR"] },
  { cle: "nouvelle",      libelle: "Nouvelle demande", roles: ["CHERCHEUR"] },
  { cle: "demandes",      libelle: "Demandes",         roles: ["CHERCHEUR", "DPO"] },
  { cle: "extraction",    libelle: "Extraction",       roles: ["CHERCHEUR", "DPO"] },
  { cle: "autorisations", libelle: "Accès",            roles: ["CHERCHEUR", "DPO", "ADMIN"] },
  { cle: "notifications", libelle: "Alertes",          roles: ["CHERCHEUR", "DPO"] },
  { cle: "catalogue",     libelle: "Catalogue",        roles: ["CHERCHEUR", "DPO", "ADMIN"] },
  { cle: "carte",         libelle: "Carte",            roles: ["CHERCHEUR", "DPO"] },
  { cle: "import",        libelle: "Import",           roles: ["DPO"] },
  { cle: "comptes",       libelle: "Comptes",          roles: ["ADMIN"] },
  { cle: "synthese",      libelle: "Synthèse",         roles: ["DPO"] },
  { cle: "journal",       libelle: "Connexions",       roles: ["ADMIN"] },
  { cle: "mails",         libelle: "E-mails",          roles: ["ADMIN"] },
];

async function demarrer() {
  $("#ecran-connexion").classList.add("hidden");
  $("#ecran-app").classList.remove("hidden");
  $("#identite").textContent = etat.user.nom_complet;
  $("#badge-role").textContent = ROLES[etat.user.role] ?? etat.user.role;
  $("#titre-demandes").textContent =
    etat.user.role === "CHERCHEUR" ? "Mes demandes" : "Demandes";
  $("#sous-titre-demandes").textContent = etat.user.role === "CHERCHEUR"
    ? "Vos dépôts et les décisions rendues."
    : "Les dossiers déposés par les équipes de recherche.";
  $("#btn-expiration").classList.toggle("hidden", etat.user.role === "CHERCHEUR");

  const visibles = ONGLETS.filter(o => o.roles.includes(etat.user.role));
  $("#onglets").innerHTML = visibles.map(o => `
    <button data-onglet="${o.cle}"
            class="onglet shrink-0 px-3.5 py-3 text-sm font-medium text-ardoise hover:text-encre
                   border-b-2 border-transparent transition-colors whitespace-nowrap">
      <span class="libelle">${o.libelle}</span>
    </button>`).join("");
  $$(".onglet").forEach(b => b.addEventListener("click", () => afficher(b.dataset.onglet)));
  $$(".aller").forEach(b => b.addEventListener("click", () => afficher(b.dataset.aller)));

  etat.parametres = await api("/parametres");
  etat.lots = await api("/lots");
  $("#d-lot").innerHTML = etat.lots
    .map(l => `<option value="${l.id}">${echapper(l.libelle)}</option>`).join("");
  if (etat.lots.length) await chargerChamps(etat.lots[0].id);

  const aujourdhui = new Date();
  const dans6mois = new Date(); dans6mois.setMonth(dans6mois.getMonth() + 6);
  $("#d-debut").value = aujourdhui.toISOString().slice(0, 10);
  $("#d-fin").value = dans6mois.toISOString().slice(0, 10);

  const heure = new Date().getHours();
  const moment = heure < 18 ? "Bonjour" : "Bonsoir";
  const prenom = etat.user.nom_complet.split(" ")[0];
  $("#salutation").textContent = `${moment} ${prenom}`;
  $("#salutation-dpo").textContent = `${moment} ${prenom}`;

  await majCompteurAlertes();

  // On retrouve l'onglet quitté, s'il reste ouvert à ce rôle
  const memorisee = sessionStorage.getItem(CLE_VUE);
  const parDefaut = etat.user.role === "ADMIN" ? "comptes" : visibles[0].cle;
  const depart = visibles.some(o => o.cle === memorisee) ? memorisee : parDefaut;
  afficher(depart);
}

async function afficher(cle) {
  sessionStorage.setItem(CLE_VUE, cle);
  $$(".vue").forEach(v => v.classList.toggle("hidden", v.dataset.vue !== cle));
  $$(".onglet").forEach(b => {
    const actif = b.dataset.onglet === cle;
    b.classList.toggle("border-corail", actif);
    b.classList.toggle("border-transparent", !actif);
    b.classList.toggle("text-encre", actif);
    b.classList.toggle("font-semibold", actif);
    b.classList.toggle("text-ardoise", !actif);
  });
  if (cle === "accueil")       await chargerAccueil();
  if (cle === "pilotage")      await chargerPilotage();
  if (cle === "demandes")      await chargerDemandes();
  if (cle === "extraction")    await chargerAccesOuverts();
  if (cle === "autorisations") await chargerAutorisations();
  if (cle === "notifications") await chargerNotifications();
  if (cle === "catalogue")     await chargerCatalogue();
  if (cle === "carte")         await chargerCarte();
  if (cle === "import")        await chargerImport();
  if (cle === "comptes")       await chargerComptes();
  if (cle === "synthese")      await chargerSynthese();
  if (cle === "journal")       await chargerJournal();
  if (cle === "mails")         await chargerMails();
}

// ==========================================================================
// Formulaire de demande
// ==========================================================================
$("#d-finalite").addEventListener("input", (e) => {
  const n = e.target.value.trim().length;
  const compteur = $("#compteur-finalite");
  compteur.textContent = n;
  compteur.className = n >= 50 ? "text-vert" : "text-brique";
});

$("#d-lot").addEventListener("change", (e) => chargerChamps(Number(e.target.value)));

async function chargerChamps(lotId) {
  etat.lotCourant = await api(`/lots/${lotId}`);
  etat.selection = {};
  etat.servicesChoisis = [];
  etat.demandeId = null;
  $("#btn-soumettre").disabled = true;
  $("#etat-brouillon").textContent = "";
  $("#panneau-conformite").innerHTML =
    `<p class="text-sm text-ardoise leading-relaxed">
       Choisissez au moins une colonne pour lancer le contrôle. Il se met à
       jour automatiquement pendant que vous complétez le formulaire.
     </p>`;

  // Services : uniquement pour les lots de séjours qui ne visent pas déjà un
  // service précis. Aucune case cochée = tous les services (avertissement).
  const services = etat.lotCourant.services || [];
  $("#bloc-services").classList.toggle("hidden", services.length === 0);
  $("#liste-services").innerHTML = services.map(nomService => `
    <label class="service-case inline-flex items-center gap-1.5 rounded-lg border border-trait
                  px-3 py-1.5 text-sm cursor-pointer hover:border-corail transition-colors"
           data-service="${echapper(nomService)}">
      <input type="checkbox" class="accent-[#507593]"> ${echapper(nomService)}
    </label>`).join("");
  $$("#liste-services input").forEach(i => i.addEventListener("change", () => {
    i.closest(".service-case").classList.toggle("border-indigo", i.checked);
    planifierAutosave();
  }));

  // Établissements : régions à cocher d'un coup, ou un établissement précis.
  // Aucun territoire ne figure déjà dans un lot filtré (le filtre « services »
  // ne concerne que les séjours) : c'est pourquoi le champ hopitaux arrive du
  // catalogue, pas d'un filtre fixe comme service_source.
  const hopitaux = etat.lotCourant.hopitaux || [];
  $("#bloc-hopitaux").classList.toggle("hidden", hopitaux.length === 0);
  const parRegion = {};
  hopitaux.forEach(h => (parRegion[h.region] ??= []).push(h));
  $("#liste-hopitaux").innerHTML = Object.entries(parRegion).sort(([a], [b]) => a.localeCompare(b))
    .map(([region, etabs]) => `
      <div>
        <label class="region-case flex items-center gap-2 text-sm font-semibold cursor-pointer">
          <input type="checkbox" class="case-region accent-[#507593]" data-region="${echapper(region)}">
          ${echapper(region)}
        </label>
        <div class="mt-1.5 ml-6 flex flex-wrap gap-2">
          ${etabs.map(h => `
            <label class="hopital-case inline-flex items-center gap-1.5 rounded-lg border border-trait
                          px-2.5 py-1 text-xs cursor-pointer hover:border-corail transition-colors"
                   data-code="${echapper(h.code)}" data-region="${echapper(region)}">
              <input type="checkbox" class="accent-[#507593]"> ${echapper(h.nom)}
            </label>`).join("")}
        </div>
      </div>`).join("");
  $$("#liste-hopitaux .hopital-case input").forEach(i => i.addEventListener("change", () => {
    i.closest(".hopital-case").classList.toggle("border-indigo", i.checked);
    majCaseRegion(i.closest(".hopital-case").dataset.region);
    planifierAutosave();
  }));
  $$("#liste-hopitaux .case-region").forEach(i => i.addEventListener("change", () => {
    $$(`.hopital-case[data-region="${i.dataset.region}"] input`).forEach(c => {
      c.checked = i.checked;
      c.closest(".hopital-case").classList.toggle("border-indigo", i.checked);
    });
    planifierAutosave();
  }));

  $("#liste-champs").innerHTML = etat.lotCourant.champs.map(champHTML).join("");
  $$("#liste-champs .mode").forEach(sel => sel.addEventListener("change", (e) => {
    reagirChangementMode(e.target.closest("[data-champ]"));
    planifierAutosave();
  }));
  $$("#liste-champs .justif").forEach(i => i.addEventListener("input", planifierAutosave));
}

/** Options de forme d'accès, adaptées à la catégorie de la colonne. */
function optionsMode(c) {
  const options = [{ v: "", texte: "Ne pas demander" }];
  if (c.categorie === "IDENTIFIANT_DIRECT") {
    options.push({ v: "PSEUDONYMISE", texte: "Inclure — reçue sous forme de code anonyme" });
  } else if (c.categorie === "QUASI_IDENTIFIANT" && c.reductible) {
    options.push({ v: "PSEUDONYMISE", texte: `Inclure — reçue réduite (${c.protection})` });
    options.push({ v: "BRUT", texte: "Inclure en version précise (justification requise)" });
  } else if (c.categorie === "DONNEE_SANTE") {
    options.push({ v: "BRUT", texte: "Inclure (justification requise)" });
  } else {
    options.push({ v: c.categorie === "QUASI_IDENTIFIANT" ? "PSEUDONYMISE" : "BRUT", texte: "Inclure" });
  }
  options.push({ v: "AGREGE", texte: "Ne récupérer que des chiffres globaux (effectifs)" });
  return options;
}

function champHTML(c) {
  const cat = CATEGORIES[c.categorie];
  const demandeJustification = c.categorie === "DONNEE_SANTE" || c.reductible;
  return `
    <div class="rangee bg-carte rounded-xl border border-trait px-5 py-4" data-champ="${c.id}"
         data-justif-si="${demandeJustification ? "BRUT" : ""}">
      <div class="flex items-start justify-between gap-3 flex-wrap">
        <div class="min-w-0">
          <span class="text-sm font-medium">${echapper(c.libelle)}</span>
          <div class="mt-1">${chipCat(cat)}</div>
        </div>
        <select class="mode rounded-lg border border-trait bg-sable/50 px-2.5 py-2 text-sm min-w-[220px]"
                aria-label="Forme d'accès : ${echapper(c.libelle)}">
          ${optionsMode(c).map(o => `<option value="${o.v}">${echapper(o.texte)}</option>`).join("")}
        </select>
      </div>
      <p class="text-xs text-ardoise mt-2 leading-snug">${echapper(cat.explication)}</p>
      <input class="justif hidden mt-3 w-full rounded-lg border border-trait bg-sable/50 px-3 py-2 text-sm"
             placeholder="Pourquoi cette colonne est-elle nécessaire sous cette forme ?">
    </div>`;
}

function reagirChangementMode(ligne) {
  const declencheurs = (ligne.dataset.justifSi || "").split(",").filter(Boolean);
  const mode = $(".mode", ligne).value;
  $(".justif", ligne).classList.toggle("hidden", !declencheurs.includes(mode));
}

function servicesSelectionnes() {
  return $$("#liste-services input:checked")
    .map(i => i.closest(".service-case").dataset.service);
}

function majCaseRegion(region) {
  const cases = $$(`.hopital-case[data-region="${region}"] input`);
  const caseRegion = $(`.case-region[data-region="${region}"]`);
  if (caseRegion) caseRegion.checked = cases.length > 0 && cases.every(c => c.checked);
}

function hopitauxSelectionnes() {
  return $$("#liste-hopitaux .hopital-case input:checked")
    .map(i => i.closest(".hopital-case").dataset.code);
}

function selectionChamps() {
  const selection = {};
  $$("#liste-champs [data-champ]").forEach(ligne => {
    const mode = $(".mode", ligne).value;
    if (!mode) return;
    selection[Number(ligne.dataset.champ)] = { mode, justification: $(".justif", ligne).value };
  });
  return selection;
}

function corpsDemande() {
  return {
    lot_id: Number($("#d-lot").value),
    titre_projet: $("#d-titre").value.trim(),
    finalite: $("#d-finalite").value.trim(),
    date_debut_souhaitee: $("#d-debut").value,
    date_fin_souhaitee: $("#d-fin").value,
    services: servicesSelectionnes(),
    hopitaux: hopitauxSelectionnes(),
    champs: Object.entries(selectionChamps()).map(([id, v]) => ({
      champ_id: Number(id), mode: v.mode, justification: v.justification,
    })),
  };
}

// Enregistrement automatique : la personne ne clique plus sur « Enregistrer »,
// le brouillon suit la saisie. Un court délai évite un appel à chaque frappe.
let minuteurAutosave = null;
function planifierAutosave() {
  clearTimeout(minuteurAutosave);
  $("#etat-brouillon").textContent = "Enregistrement...";
  minuteurAutosave = setTimeout(sauvegarderBrouillon, 500);
}

async function sauvegarderBrouillon() {
  const corps = corpsDemande();
  if (!corps.titre_projet || !corps.finalite || !Object.keys(selectionChamps()).length) {
    $("#etat-brouillon").textContent = "";
    $("#btn-soumettre").disabled = true;
    return null;
  }
  try {
    let d;
    if (etat.demandeId) {
      d = await api(`/demandes/${etat.demandeId}`, { methode: "PATCH", corps });
    } else {
      d = await api("/demandes", { methode: "POST", corps });
      etat.demandeId = d.id;
    }
    $("#etat-brouillon").textContent = `Brouillon ${reference(d)} enregistré automatiquement.`;
    await verifier();
    return etat.demandeId;
  } catch (err) {
    $("#etat-brouillon").textContent = "";
    notifier(err.message, "erreur");
    return null;
  }
}

$("#d-titre").addEventListener("input", planifierAutosave);
$("#d-debut").addEventListener("change", planifierAutosave);
$("#d-fin").addEventListener("change", planifierAutosave);
$("#d-finalite").addEventListener("input", planifierAutosave);

async function verifier() {
  if (!etat.demandeId) return;
  const rapport = await api(`/demandes/${etat.demandeId}/controle-rgpd`);
  rendreConformite(rapport, $("#panneau-conformite"));
  $("#btn-soumettre").disabled = !rapport.conforme;
}

$("#btn-soumettre").addEventListener("click", async () => {
  clearTimeout(minuteurAutosave);
  const id = await sauvegarderBrouillon();
  if (!id) return notifier("Complétez le titre, la finalité et au moins une colonne.", "erreur");
  try {
    await api(`/demandes/${id}/soumettre`, { methode: "POST" });
    notifier("Demande transmise au délégué.");
    etat.demandeId = null;
    $("#btn-soumettre").disabled = true;
    afficher("demandes");
  } catch (err) {
    if (err.rapport) rendreConformite(err.rapport, $("#panneau-conformite"));
    notifier(err.message, "erreur");
  }
});

// ==========================================================================
// Rapport de conformité
// ==========================================================================
function rendreConformite(rapport, cible) {
  const enTete = rapport.conforme
    ? `<div class="border-l-2 border-vert bg-vertpale px-3.5 py-2.5">
         <p class="text-sm text-vert font-medium">Conforme</p>
         <p class="text-xs text-vert/80 mt-0.5">La demande peut être transmise.</p>
       </div>`
    : `<div class="border-l-2 border-brique bg-briquepale px-3.5 py-2.5">
         <p class="text-sm text-brique font-medium">
           ${rapport.nb_bloquants} règle${rapport.nb_bloquants > 1 ? "s" : ""} bloquante${rapport.nb_bloquants > 1 ? "s" : ""}
         </p>
         <p class="text-xs text-brique/80 mt-0.5">Corrigez pour pouvoir transmettre.</p>
       </div>`;

  const masque = rapport.identites_masquees !== false;
  const identites = `
    <div class="flex items-center justify-between gap-3 pb-3 mb-4 border-b border-trait">
      <span class="text-xs text-ardoise">Identités des patients</span>
      ${masque ? chip("Masquées", "border-vert/40 text-vert bg-vertpale")
               : chip("Exposées", "border-brique/40 text-brique bg-briquepale")}
    </div>`;

  const alertes = rapport.alertes.map(a => {
    const bloquant = a.niveau === "BLOQUANT";
    return `
      <li class="border-l-2 ${bloquant ? "border-brique" : "border-ambre"} pl-3.5 py-1">
        <div class="flex items-baseline justify-between gap-2">
          <span class="text-xs font-medium ${bloquant ? "text-brique" : "text-ambre"}">
            ${bloquant ? "Blocage" : "Avertissement"}
          </span>
          <span class="text-[11px] text-ardoise">${echapper(nomRegle(a.code))}</span>
        </div>
        <p class="text-sm mt-1 leading-snug">${echapper(a.message)}</p>
        <p class="text-xs text-ardoise mt-1">${echapper(a.reference)}</p>
      </li>`;
  }).join("");

  cible.innerHTML = identites + enTete + (rapport.alertes.length
    ? `<ul class="mt-4 space-y-4">${alertes}</ul>`
    : `<p class="mt-4 text-sm text-ardoise">Aucune alerte.</p>`);
}

// ==========================================================================
// Demandes
// ==========================================================================
$("#btn-rafraichir").addEventListener("click", chargerDemandes);

async function chargerDemandes() {
  const demandes = await api("/demandes");
  const cible = $("#liste-demandes");
  if (!demandes.length) {
    cible.innerHTML = vide(etat.user.role === "CHERCHEUR"
      ? "Vous n'avez pas encore déposé de demande. Commencez par l'onglet « Nouvelle demande »."
      : "Aucun dossier n'a été transmis pour le moment.");
    $("#detail-demande").innerHTML = "";
    return;
  }
  cible.innerHTML = demandes.map(d => `
    <button data-id="${d.id}" class="ligne-demande rubrique w-full text-left px-5 py-4 hover:bg-sable transition-colors">
      <div class="flex items-baseline justify-between gap-3">
        <span class="text-sm font-medium">${echapper(d.titre_projet)}</span>
        ${statut(d.statut)}
      </div>
      <p class="text-xs text-ardoise mt-1.5">
        <span>${reference(d)}</span>
        <span class="ml-3">${echapper(d.demandeur.nom_complet)}</span>
        <span class="ml-3">${d.champs_demandes.length} colonne${d.champs_demandes.length > 1 ? "s" : ""}</span>
      </p>
    </button>`).join("");
  $$(".ligne-demande").forEach(b =>
    b.addEventListener("click", () => ouvrirDemande(Number(b.dataset.id))));
}

/** Le geste central du métier : une décision signée et datée. */
function rendreDecision(d) {
  if (!d.decision) return "";
  const refus = d.decision.sens === "REFUSEE";
  const couleur = refus ? "text-brique" : "text-vert";
  const conditions = d.decision.conditions
    ? `<p class="text-sm mt-2 leading-snug">Conditions : ${echapper(d.decision.conditions)}</p>` : "";
  const fin = d.decision.date_fin_acces
    ? `<p class="text-xs text-ardoise mt-2">Accès jusqu'au ${dateFR(d.decision.date_fin_acces)}</p>` : "";

  const purge = d.autorisation && d.autorisation.date_purge_prevue
    ? `<p class="text-xs text-ardoise mt-1">Suppression des données au plus tard le ${dateFR(d.autorisation.date_purge_prevue)}</p>` : "";

  const attestation = !refus && d.autorisation
    ? `<div class="flex justify-center mt-4">
         <button class="telecharger-attestation rounded-lg border border-vert text-vert px-3.5 py-1.5
                        text-xs font-semibold hover:bg-vertpale transition-colors"
                 data-id="${d.autorisation.id}">
           Télécharger l'attestation (PDF)
         </button>
       </div>` : "";

  return `
    <div class="px-5 py-5 border-t border-trait">
      <div class="flex justify-center py-2">
        <div class="tampon tampon-anime ${couleur} text-center">
          <p class="text-sm font-bold leading-tight">${refus ? "Refusé" : "Accès accordé"}</p>
          <p class="text-[11px] mt-1 leading-tight">${echapper(d.decision.dpo.nom_complet)}</p>
          <p class="font-mono text-[10px] leading-tight">${dateCourte(d.decision.prise_le)}</p>
        </div>
      </div>
      <p class="text-sm mt-4 leading-snug">${echapper(d.decision.motif)}</p>
      ${conditions}
      ${fin}
      ${purge}
      ${attestation}
    </div>`;
}

function brancherTelechargementAttestation(racine = document) {
  $$(".telecharger-attestation", racine).forEach(b => b.addEventListener("click", () =>
    telecharger(`/autorisations/${b.dataset.id}/attestation`, `attestation-${b.dataset.id}.pdf`)));
}

async function ouvrirDemande(id) {
  const d = await api(`/demandes/${id}`);
  const rapport = await api(`/demandes/${id}/controle-rgpd`);

  const colonnes = d.champs_demandes.map(c => {
    const cat = CATEGORIES[c.champ.categorie];
    const risque = c.mode === "BRUT" && c.champ.categorie === "IDENTIFIANT_DIRECT";
    return `<li class="rangee grid grid-cols-[minmax(0,1fr)_190px_150px] gap-x-3 items-center py-2">
      <span class="text-sm leading-snug">${echapper(c.champ.libelle)}</span>
      <span>${chipCat(cat)}</span>
      <span class="text-xs text-right ${risque ? "text-brique font-medium" : "text-ardoise"}">${echapper(c.protection)}</span>
    </li>`;
  }).join("");

  const services = d.services && d.services.length
    ? d.services.map(echapper).join(", ")
    : "Tous les services de l'hôpital";

  const estDPO = etat.user.role === "DPO";
  let actions = "";
  if (estDPO && d.statut === "SOUMISE") {
    actions += `<button class="acte mt-5 w-full rounded-lg bg-indigo hover:bg-encre text-white py-2.5 text-sm font-semibold transition-colors" data-acte="instruire">
                 Ouvrir l'instruction</button>`;
  }
  if (estDPO && (d.statut === "SOUMISE" || d.statut === "EN_INSTRUCTION")) {
    const aujourdhui = new Date().toISOString().slice(0, 10);
    actions += `
      <label class="block text-xs text-ardoise mt-5 mb-1.5" for="motif">Motif de la décision</label>
      <textarea id="motif" rows="3" class="w-full rounded-lg border border-trait bg-sable/50 px-3 py-2 text-sm leading-relaxed"
                placeholder="Ce que vous retenez, en dix caractères au moins."></textarea>

      <label class="block text-xs text-ardoise mt-4 mb-1.5" for="fin-acces">Fin d'accès accordée</label>
      <input id="fin-acces" type="date" value="${d.date_fin_souhaitee}" min="${aujourdhui}" max="${d.date_fin_souhaitee}"
             class="rounded-lg border border-trait bg-sable/50 px-3 py-2 text-sm">
      <p id="purge-prevue" class="text-xs text-ardoise mt-1.5 leading-snug"></p>

      <label class="block text-xs text-ardoise mt-4 mb-1.5" for="conditions">Conditions (facultatif)</label>
      <input id="conditions" class="w-full rounded-lg border border-trait bg-sable/50 px-3 py-2 text-sm"
             placeholder="Ex. : consultation sur poste sécurisé uniquement.">
      <label class="flex items-center gap-2 mt-3 text-sm">
        <input id="sous-condition" type="checkbox" class="accent-[#507593]"> Accord sous condition
      </label>

      <div class="flex gap-2 mt-4">
        <button class="acte flex-1 rounded-lg bg-vert hover:bg-encre text-white py-2.5 text-sm font-semibold transition-colors" data-acte="valider">
          Accorder l'accès</button>
        <button class="acte flex-1 rounded-lg border border-brique text-brique py-2.5 text-sm font-semibold hover:bg-briquepale transition-colors" data-acte="refuser">
          Refuser</button>
      </div>`;
  }

  $("#detail-demande").innerHTML = `
    <div class="bg-carte rounded-xl border border-trait overflow-hidden">
      <div class="px-5 py-4 border-b border-trait">
        <span class="text-xs text-lavande font-medium">${reference(d)}</span>
        <h3 class="text-lg font-bold mt-1.5 leading-tight">${echapper(d.titre_projet)}</h3>
        <div class="flex items-center gap-3 mt-2.5">
          ${statut(d.statut)}
          <span class="text-xs text-ardoise">${echapper(d.demandeur.nom_complet)}</span>
        </div>
      </div>

      <div class="px-5 py-4 space-y-4">
        <div>
          <p class="text-xs text-ardoise">Finalité</p>
          <p class="text-sm mt-1 leading-snug break-words">${echapper(d.finalite)}</p>
        </div>
        <div>
          <p class="text-xs text-ardoise">Période demandée</p>
          <p class="text-sm mt-1">du ${dateFR(d.date_debut_souhaitee)} au ${dateFR(d.date_fin_souhaitee)}</p>
        </div>
        <div>
          <p class="text-xs text-ardoise">Services concernés</p>
          <p class="text-sm mt-1">${services}</p>
        </div>
        <div>
          <p class="text-xs text-ardoise mb-1">Colonnes</p>
          <ul>${colonnes || '<li class="text-sm text-ardoise py-2">Aucune colonne demandée.</li>'}</ul>
        </div>
      </div>

      ${rendreDecision(d)}

      <div class="px-5 py-4 border-t border-trait">
        <div id="conformite-detail"></div>
        ${actions}
      </div>
    </div>`;

  rendreConformite(rapport, $("#conformite-detail"));
  brancherTelechargementAttestation($("#detail-demande"));

  const majPurge = () => {
    const champ = $("#fin-acces"); const cible = $("#purge-prevue");
    if (!champ || !cible) return;
    cible.textContent = champ.value
      ? `Suppression des données au plus tard le ${dateFR(ajouterJours(champ.value, etat.parametres.delai_purge_jours))}.`
      : "";
  };
  if ($("#fin-acces")) { $("#fin-acces").addEventListener("input", majPurge); majPurge(); }

  $$(".acte").forEach(b => b.addEventListener("click", async () => {
    const acte = b.dataset.acte;
    try {
      if (acte === "instruire") {
        await api(`/demandes/${id}/instruire`, { methode: "POST" });
        notifier("Instruction ouverte.");
      } else {
        const motif = $("#motif").value.trim();
        if (motif.length < 10) {
          return notifier("Le motif doit faire au moins dix caractères.", "erreur");
        }
        const corps = { motif };
        if (acte === "valider") {
          corps.date_fin_acces = $("#fin-acces").value || null;
          corps.conditions = $("#conditions").value.trim();
          corps.sous_condition = $("#sous-condition").checked;
          if (corps.sous_condition && !corps.conditions) {
            return notifier("Précisez la condition posée à l'accès.", "erreur");
          }
        }
        await api(`/demandes/${id}/${acte}`, { methode: "POST", corps });
        notifier(acte === "valider" ? "Accès accordé." : "Demande refusée.");
      }
      await chargerDemandes();
      await ouvrirDemande(id);
      await majCompteurAlertes();
    } catch (err) {
      notifier(err.message, "erreur");
    }
  }));
}

// ==========================================================================
// Extraction
// ==========================================================================
async function chargerAccesOuverts() {
  const demandes = await api("/demandes");
  // Le chercheur ne voit que ses accès ouverts ; le délégué supervise toute
  // extraction déjà autorisée, même close, pour contrôler ce qui a été remis.
  const estDPO = etat.user.role === "DPO";
  const ouvertes = demandes.filter(d => d.autorisation
    && (estDPO || d.autorisation.statut === "ACTIVE"));

  $("#acces-ouverts").innerHTML = ouvertes.length
    ? ouvertes.map(d => `
        <button class="acces rounded-xl border border-trait bg-carte px-4 py-3 text-left hover:border-corail transition-colors"
                data-id="${d.id}">
          <span class="text-sm font-medium">${echapper(d.titre_projet)}</span>
          <span class="block text-xs text-ardoise mt-0.5">
            <span>${reference(d)}</span>
            <span class="ml-2">jusqu'au ${dateCourte(d.autorisation.date_fin)}</span>
          </span>
        </button>`).join("")
    : `<p class="text-sm text-ardoise max-w-xl leading-relaxed">
         Aucun accès ouvert. Un accès apparaît ici dès que le délégué a validé
         une demande, et disparaît à son échéance.
       </p>`;

  $("#resultat-extraction").innerHTML = "";
  $$(".acces").forEach(b =>
    b.addEventListener("click", () => extraire(Number(b.dataset.id))));

  if (ouvertes.length === 1) extraire(ouvertes[0].id);
}

async function extraire(demandeId) {
  let e;
  try {
    e = await api(`/extractions/${demandeId}?limite=50`);
  } catch (err) {
    $("#resultat-extraction").innerHTML =
      `<div class="border-l-2 border-brique bg-briquepale px-4 py-3 text-sm text-brique">
         ${echapper(err.message)}
       </div>`;
    return;
  }

  const transformee = c => c.transformation !== "Valeur exacte";

  const legende = e.colonnes.map(c => {
    const cat = CATEGORIES[c.categorie];
    return `<li class="rangee grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 items-start py-2.5">
      <span class="min-w-0">
        <span class="block text-sm leading-snug">${echapper(c.libelle)}</span>
        <span class="block text-xs mt-1 ${transformee(c) ? "text-vert font-medium" : "text-ardoise"}">
          ${echapper(c.transformation)}
        </span>
      </span>
      <span class="justify-self-end">${chipCat(cat)}</span>
    </li>`;
  }).join("");

  const nbIdentites = e.colonnes.filter(c => c.categorie === "IDENTIFIANT_DIRECT").length;
  const bandeau = e.identites_masquees !== false
    ? `<div class="mb-5 rounded-xl border border-vert/40 bg-vertpale px-5 py-3.5">
         <p class="text-sm font-semibold text-vert">Identités des patients masquées</p>
         <p class="text-xs text-vert/90 mt-1 leading-relaxed">
           ${nbIdentites
             ? `${nbIdentites} colonne${nbIdentites > 1 ? "s" : ""} d'identité remplacée${nbIdentites > 1 ? "s" : ""} par un pseudonyme propre à cette étude.`
             : "Aucune colonne d'identité dans cette extraction."}
           Aucun nom ni numéro de sécurité sociale n'existe dans la base.
         </p>
       </div>`
    : `<div class="mb-5 rounded-xl border border-brique/40 bg-briquepale px-5 py-3.5">
         <p class="text-sm font-semibold text-brique">Identités exposées</p>
       </div>`;

  // Lisibilité : une première ligne d'en-tête regroupe les colonnes par thème
  // (« Maladie », « Profil du patient »...), la seconde nomme chaque colonne —
  // la même logique de regroupement que dans le fichier Excel téléchargé.
  const groupes = [];
  for (const c of e.colonnes) {
    const dernier = groupes[groupes.length - 1];
    if (dernier && dernier.nom === (c.groupe || "Données")) dernier.n += 1;
    else groupes.push({ nom: c.groupe || "Données", n: 1 });
  }
  const ligneGroupes = groupes.map(g => `
    <th colspan="${g.n}" class="text-left px-3 py-1.5 bg-bleuetpale text-indigo text-[11px] font-semibold
                                uppercase tracking-wide border-b border-trait">
      ${echapper(g.nom)}
    </th>`).join("");
  const entetes = e.colonnes.map(c => `
    <th class="text-left px-3 py-2.5 border-b border-trait font-medium text-xs whitespace-nowrap">
      ${echapper(c.libelle)}
    </th>`).join("");

  const corps = e.lignes.map(ligne => `
    <tr class="rangee">
      ${e.colonnes.map(c => `
        <td class="px-3 py-2 whitespace-nowrap text-sm ${transformee(c) ? "font-mono text-xs text-lavande bg-vertpale" : ""}">
          ${echapper(ligne[c.code])}
        </td>`).join("")}
    </tr>`).join("");

  const stats = e.statistiques.length ? `
    <div class="mt-9">
      <h3 class="text-base font-semibold">Effectifs</h3>
      <p class="text-xs text-ardoise mt-1.5">
        Colonnes demandées en agrégé. Elles ne figurent pas au niveau ligne.
      </p>
      <div class="mt-4 bg-carte rounded-xl border border-trait overflow-hidden">
        ${e.statistiques.map(s => `
          <div class="rangee px-5 py-2.5 flex items-baseline justify-between text-sm">
            <span>${echapper(s.colonne)}, ${echapper(s.valeur)}</span>
            <span class="font-medium">${s.effectif}</span>
          </div>`).join("")}
      </div>
    </div>` : "";

  $("#resultat-extraction").innerHTML = `
    ${bandeau}
    <div class="grid lg:grid-cols-[1fr_360px] gap-10 items-start">
      <div class="min-w-0">
        <div class="flex items-end justify-between gap-4">
          <div>
            <h3 class="text-lg font-bold leading-tight">${echapper(e.titre_projet)}</h3>
            <p class="text-xs text-ardoise mt-1.5">
              ${echapper(e.lot)}
              <span class="ml-3">
                ${e.nb_lignes} ligne${e.nb_lignes > 1 ? "s" : ""} affichée${e.nb_lignes > 1 ? "s" : ""}${
                  e.nb_total > e.nb_lignes ? ` sur ${e.nb_total} au total` : ""}
              </span>
              <span class="ml-3">extraction du ${dateCourte(e.produite_le)}</span>
            </p>
          </div>
          <div class="flex gap-2 shrink-0">
            <button id="btn-export-extraction"
                    class="rounded-lg text-xs font-medium border border-trait bg-carte px-3.5 py-2 hover:border-corail transition-colors">
              Télécharger en CSV
            </button>
            <button id="btn-export-excel"
                    class="rounded-lg text-xs font-medium border border-vert text-vert bg-carte px-3.5 py-2 hover:bg-vertpale transition-colors">
              Télécharger en Excel
            </button>
          </div>
        </div>
        <div class="mt-4 bg-carte rounded-xl border border-trait overflow-x-auto">
          <table class="w-full">
            <thead class="bg-sable">
              <tr>${ligneGroupes}</tr>
              <tr>${entetes}</tr>
            </thead>
            <tbody>${corps}</tbody>
          </table>
        </div>
        ${stats}
      </div>

      <aside class="bg-carte rounded-xl border border-trait overflow-hidden lg:sticky lg:top-[150px]">
        <div class="px-5 py-3.5 border-b border-trait">
          <h3 class="text-base font-semibold leading-none">Protections appliquées</h3>
          <p class="text-xs text-ardoise mt-1.5">Une par colonne servie.</p>
        </div>
        <ul class="px-5 py-2">${legende}</ul>
      </aside>
    </div>`;

  $("#btn-export-extraction").addEventListener("click", () =>
    telecharger(`/extractions/${demandeId}/export`, `extraction-${demandeId}.csv`));
  $("#btn-export-excel").addEventListener("click", () =>
    telecharger(`/extractions/${demandeId}/export?format=xlsx`, `extraction-${demandeId}.xlsx`));
}

// ==========================================================================
// Accès accordés
// ==========================================================================
$("#btn-expiration").addEventListener("click", async () => {
  const r = await api("/autorisations/taches/expiration", { methode: "POST" });
  notifier(`${r.preavis_envoyes} préavis, ${r.acces_clotures.length} accès clos, `
         + `${r.donnees_purgees} purge${r.donnees_purgees > 1 ? "s" : ""}.`);
  await chargerAutorisations();
  await majCompteurAlertes();
});

async function chargerAutorisations() {
  const [liste, demandes] = await Promise.all([api("/autorisations"), api("/demandes")]);
  const parId = Object.fromEntries(demandes.map(d => [d.id, d]));
  const cible = $("#liste-autorisations");
  if (!liste.length) {
    cible.innerHTML = vide("Aucun accès accordé pour l'instant.");
    return;
  }
  const estDPO = etat.user.role === "DPO";
  cible.innerHTML = liste.map(a => {
    const d = parId[a.demande_id];
    const dec = d && d.decision;
    const purge = a.purge_effectuee_le
      ? `Données supprimées le ${dateCourte(a.purge_effectuee_le)}`
      : `Suppression des données au plus tard le ${dateCourte(a.date_purge_prevue)}`;
    return `
    <div class="rangee px-5 py-4 flex items-start justify-between gap-4 flex-wrap">
      <div class="min-w-0 max-w-2xl">
        <div class="flex items-center gap-2.5 flex-wrap">
          <span class="text-sm font-medium">${echapper(d ? d.titre_projet : `Dossier n° ${a.demande_id}`)}</span>
          ${statut(a.statut)}
        </div>
        <p class="text-xs text-ardoise mt-1.5">
          ${d ? `<span>${echapper(d.demandeur.nom_complet)}</span><span class="ml-3">${reference(d)}</span>` : ""}
          <span class="${d ? "ml-3" : ""}">Accès du ${dateCourte(a.date_debut)} au ${dateCourte(a.date_fin)}</span>
        </p>
        <p class="text-xs text-ardoise mt-1">${purge}</p>
        ${dec ? `<p class="text-xs text-ardoise mt-1.5 leading-relaxed">
          Accordé par ${echapper(dec.dpo.nom_complet)} le ${dateCourte(dec.prise_le)} : ${echapper(dec.motif)}
          ${dec.conditions ? `<span class="block">Conditions : ${echapper(dec.conditions)}</span>` : ""}
        </p>` : ""}
        ${a.motif_revocation ? `<p class="text-xs text-brique mt-1.5">Révoqué : ${echapper(a.motif_revocation)}</p>` : ""}
      </div>
      <div class="flex gap-2">
        ${dec && dec.sens !== "REFUSEE"
          ? `<button class="telecharger-attestation rounded-lg border border-vert text-vert px-3 py-1.5 text-xs font-medium hover:bg-vertpale transition-colors" data-id="${a.id}">Attestation (PDF)</button>`
          : ""}
        ${estDPO && a.statut === "ACTIVE"
          ? `<button class="revoquer rounded-lg border border-brique text-brique px-3 py-1.5 text-xs font-medium hover:bg-briquepale transition-colors" data-id="${a.id}">Révoquer</button>`
          : ""}
        ${estDPO && ["EXPIREE", "REVOQUEE"].includes(a.statut)
          ? `<button class="purger rounded-lg border border-trait px-3 py-1.5 text-xs font-medium hover:border-corail transition-colors" data-id="${a.id}">Attester la suppression</button>`
          : ""}
      </div>
    </div>`;
  }).join("");
  brancherTelechargementAttestation($("#liste-autorisations"));

  $$(".revoquer").forEach(b => b.addEventListener("click", async () => {
    const motif = prompt("Motif de la révocation :");
    if (!motif) return;
    try {
      await api(`/autorisations/${b.dataset.id}/revoquer`, { methode: "POST", corps: { motif } });
      notifier("Accès révoqué.");
      await chargerAutorisations();
    } catch (err) { notifier(err.message, "erreur"); }
  }));

  $$(".purger").forEach(b => b.addEventListener("click", async () => {
    try {
      await api(`/autorisations/${b.dataset.id}/purger`, { methode: "POST" });
      notifier("Suppression attestée.");
      await chargerAutorisations();
    } catch (err) { notifier(err.message, "erreur"); }
  }));
}

// ==========================================================================
// Alertes
// ==========================================================================
async function majCompteurAlertes() {
  try {
    const { non_lues } = await api("/notifications/compte");
    const onglet = $('[data-onglet="notifications"] .libelle');
    if (!onglet) return;
    onglet.innerHTML = non_lues
      ? `Alertes <span class="ml-1 inline-block rounded-full bg-corail text-white px-1.5 text-[11px] font-semibold">${non_lues}</span>`
      : "Alertes";
  } catch { /* silencieux */ }
}

async function chargerNotifications() {
  const [notifs, echeances] = await Promise.all([
    api("/notifications"), api("/autorisations/echeances"),
  ]);

  $("#liste-echeances").innerHTML = echeances.length
    ? `<div class="border-l-2 border-ambre bg-ambrepale px-5 py-4">
         <p class="text-sm font-medium text-ambre">
           ${echeances.length} accès arrive${echeances.length > 1 ? "nt" : ""} à terme sous peu
         </p>
         <ul class="mt-2.5 space-y-1.5">
           ${echeances.map(e => `<li class="text-sm">
              ${echapper(e.titre_projet)}, ${echapper(e.demandeur)},
              <span class="text-ambre font-medium">${e.jours_restants} jour${e.jours_restants > 1 ? "s" : ""}</span>
              restant${e.jours_restants > 1 ? "s" : ""}
            </li>`).join("")}
         </ul>
       </div>`
    : "";

  $("#liste-notifications").innerHTML = notifs.length
    ? notifs.map(n => {
        const [libelle, classes] = LIBELLES_NOTIF[n.type] ?? [n.type, "border-trait text-ardoise"];
        return `
        <div class="rangee px-5 py-4 ${n.lue ? "" : "bg-sable"}">
          <div class="flex items-baseline justify-between gap-3">
            <span class="text-sm font-medium">${echapper(n.titre)}</span>
            ${chip(libelle, classes)}
          </div>
          <p class="text-sm mt-1.5 leading-snug">${echapper(n.message)}</p>
          <div class="flex items-center gap-4 mt-2.5">
            <span class="text-xs text-ardoise font-mono">${horodatageFR(n.cree_le)}</span>
            ${n.lue ? "" : `<button class="lire text-xs text-corailfonce hover:underline" data-id="${n.id}">Marquer comme lue</button>`}
          </div>
        </div>`;
      }).join("")
    : vide("Rien à signaler. Les décisions du délégué et les fins d'accès s'afficheront ici.");

  $$(".lire").forEach(b => b.addEventListener("click", async () => {
    await api(`/notifications/${b.dataset.id}/lue`, { methode: "POST" });
    await chargerNotifications();
    await majCompteurAlertes();
  }));
}

// ==========================================================================
// Catalogue
// ==========================================================================
async function chargerCatalogue() {
  rendreLegendeCategories();
  const lots = await Promise.all(etat.lots.map(l => api(`/lots/${l.id}`)));
  $("#liste-lots").innerHTML = lots.map(lot => `
    <div class="bg-carte rounded-xl border border-trait overflow-hidden">
      <div class="px-5 py-4 border-b border-trait">
        <h3 class="text-lg font-bold leading-tight">${echapper(lot.libelle)}</h3>
        ${lot.description
          ? `<p class="text-sm text-ardoise mt-1.5 leading-snug">${echapper(lot.description)}</p>` : ""}
        ${lot.responsable
          ? `<p class="text-xs text-ardoise mt-1.5">Responsable : ${echapper(lot.responsable)}</p>` : ""}
        ${lot.services && lot.services.length > 1
          ? `<p class="text-xs text-ardoise mt-1.5">${lot.services.length} services, au choix à la demande.</p>` : ""}
      </div>
      <div>
        ${lot.champs.map(c => `
          <div class="rangee px-5 py-3 grid grid-cols-[minmax(0,1fr)_190px_150px] gap-x-4 items-center">
            <span class="text-sm">${echapper(c.libelle)}</span>
            <div class="justify-self-center">${chipCat(CATEGORIES[c.categorie])}</div>
            <span class="text-xs text-ardoise text-left justify-self-center">Reçue : ${echapper(c.protection)}</span>
          </div>`).join("")}
      </div>
    </div>`).join("");
}

// ==========================================================================
// Carte des établissements
// ==========================================================================
const LIBELLES_INDICATEUR = {
  taux_hospitalisation: "Taux d'hospitalisation (pour 100 000 hab.)",
  taux_mortalite: "Taux de mortalité (pour 100 000 hab.)",
  hospitalisations_covid: "Hospitalisations liées au COVID-19",
};

// Bassin métropolitain approximatif : suffisant pour situer les points les
// uns par rapport aux autres, sans prétendre à un fond de carte géographique.
const PROJECTION = { lonMin: -5.2, lonMax: 9.6, latMin: 41.1, latMax: 51.3 };
function projeter(lat, lon, largeur = 600, hauteur = 560, marge = 40) {
  const x = marge + (lon - PROJECTION.lonMin) / (PROJECTION.lonMax - PROJECTION.lonMin) * (largeur - marge * 2);
  const y = marge + (PROJECTION.latMax - lat) / (PROJECTION.latMax - PROJECTION.latMin) * (hauteur - marge * 2);
  return { x, y };
}

function melangerCouleur(c1, c2, t) {
  const h = (c) => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16));
  const [r1, g1, b1] = h(c1.replace("#", ""));
  const [r2, g2, b2] = h(c2.replace("#", ""));
  const r = Math.round(r1 + (r2 - r1) * t), g = Math.round(g1 + (g2 - g1) * t), b = Math.round(b1 + (b2 - b1) * t);
  return `#${[r, g, b].map(v => v.toString(16).padStart(2, "0")).join("")}`;
}
function couleurIndicateur(t) {
  return t < 0.5 ? melangerCouleur("#507593", "#BEB06C", t * 2)
                 : melangerCouleur("#BEB06C", "#8F1437", (t - 0.5) * 2);
}

async function chargerCarte() {
  if (!etat.hopitauxCarte) {
    const liste = await api("/hopitaux");
    etat.hopitauxCarte = await Promise.all(
      liste.map(h => api(`/hopitaux/${h.id}`))
    );
    const annees = [...new Set(
      etat.hopitauxCarte.flatMap(h => h.historique.map(l => l.annee))
    )].sort();
    $("#carte-annee").innerHTML = annees.map(a =>
      `<option value="${a}" ${a === annees[annees.length - 1] ? "selected" : ""}>${a}</option>`).join("");
  }
  dessinerCarte();
}

$("#carte-indicateur").addEventListener("change", dessinerCarte);
$("#carte-annee").addEventListener("change", dessinerCarte);

function dessinerCarte() {
  const hopitaux = etat.hopitauxCarte;
  if (!hopitaux) return;
  const indicateur = $("#carte-indicateur").value;
  const annee = Number($("#carte-annee").value);

  const points = hopitaux.map(h => {
    const ligne = h.historique.find(l => l.annee === annee);
    return { h, valeur: ligne ? ligne[indicateur] : null };
  }).filter(p => p.valeur !== null);

  const valeurs = points.map(p => p.valeur);
  const min = Math.min(...valeurs), max = Math.max(...valeurs) || 1;
  const rayonPop = (pop) => 5 + Math.sqrt(pop) / 46;

  const cercles = points.map(({ h, valeur }) => {
    const { x, y } = projeter(h.latitude, h.longitude);
    const t = max > min ? (valeur - min) / (max - min) : 0;
    const couleur = couleurIndicateur(t);
    return `<circle class="point-hopital" data-id="${h.id}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}"
                     r="${rayonPop(h.population_bassin).toFixed(1)}" fill="${couleur}"
                     fill-opacity="0.82" stroke="#fff" stroke-width="1.5" style="cursor:pointer">
              <title>${h.nom} — ${valeur.toLocaleString("fr-FR")}</title>
            </circle>`;
  }).join("");

  const grille = [0, 1, 2, 3, 4].map(i => {
    const y = 40 + i * (480 / 4);
    return `<line x1="40" y1="${y}" x2="560" y2="${y}" stroke="#D9E1E6" stroke-width="1"/>`;
  }).join("");

  $("#carte-svg").innerHTML = `
    <rect x="0" y="0" width="600" height="560" fill="#F4F1EA"/>
    ${grille}
    <text x="40" y="24" font-size="12" fill="#507593" font-weight="600">France métropolitaine</text>
    ${cercles}`;

  $("#carte-echelle").innerHTML = `
    <span>${Math.round(min).toLocaleString("fr-FR")}</span>
    <span class="inline-block w-24 h-2.5 rounded-full" style="background:linear-gradient(90deg,#507593,#BEB06C,#8F1437)"></span>
    <span>${Math.round(max).toLocaleString("fr-FR")}</span>`;

  $$(".point-hopital").forEach(c => c.addEventListener("click", () =>
    afficherDetailHopital(Number(c.dataset.id), indicateur)));

  if (!$("#carte-detail").innerHTML && points.length) {
    afficherDetailHopital(points[0].h.id, indicateur);
  }
}

function afficherDetailHopital(id, indicateur) {
  const h = etat.hopitauxCarte.find(x => x.id === id);
  if (!h) return;
  const historique = h.historique.map(l => ({ libelle: String(l.annee), valeur: l[indicateur] }));
  $("#carte-detail").innerHTML = `
    <div class="px-5 py-4 border-b border-trait">
      <h3 class="text-base font-bold leading-tight">${echapper(h.nom)}</h3>
      <p class="text-xs text-ardoise mt-1">${echapper(h.ville)} · ${echapper(h.region)}</p>
    </div>
    <div class="px-5 py-4 space-y-4">
      <p class="text-xs text-ardoise">Bassin de population desservi : <span class="font-medium text-encre">${h.population_bassin.toLocaleString("fr-FR")}</span></p>
      <p class="text-xs text-ardoise">Séjours enregistrés dans la base : <span class="font-medium text-encre">${h.nb_sejours}</span></p>
      ${barres(LIBELLES_INDICATEUR[indicateur], historique, "w-10")}
    </div>`;
}

// ==========================================================================
// Import de données (délégué)
// ==========================================================================
async function chargerImport() {
  const lots = await api("/import");
  $("#liste-imports").innerHTML = lots.length
    ? lots.map(l => `
      <div class="rangee px-5 py-4 flex items-start justify-between gap-4 flex-wrap">
        <div class="min-w-0">
          <span class="text-sm font-medium">${echapper(l.libelle)}</span>
          <p class="text-xs text-ardoise mt-1 leading-snug">
            ${echapper(l.description || "Aucune description.")}
          </p>
          <p class="text-xs text-ardoise mt-1.5">
            ${l.nb_lignes} ligne${l.nb_lignes > 1 ? "s" : ""}
            <span class="ml-3">${chipCat(CATEGORIES[l.categorie], l.categorie, "border-trait text-ardoise")}</span>
            ${l.importe_par ? `<span class="ml-3">importé par ${echapper(l.importe_par)}</span>` : ""}
          </p>
        </div>
        <button class="supprimer-import rounded-lg border border-brique text-brique px-3 py-1.5 text-xs font-medium hover:bg-briquepale transition-colors"
                data-id="${l.id}">Supprimer</button>
      </div>`).join("")
    : vide("Aucun jeu de données importé pour l'instant. Utilisez le formulaire ci-dessus.");

  $$(".supprimer-import").forEach(b => b.addEventListener("click", async () => {
    if (!confirm("Supprimer définitivement ce jeu de données importé ?")) return;
    try {
      await api(`/import/${b.dataset.id}`, { methode: "DELETE" });
      notifier("Jeu de données supprimé.");
      await chargerImport();
    } catch (err) { notifier(err.message, "erreur"); }
  }));
}

$("#form-import").addEventListener("submit", async (e) => {
  e.preventDefault();
  const etatTexte = $("#import-etat");
  const fichier = $("#im-fichier").files[0];
  if (!fichier) return;

  const donnees = new FormData();
  donnees.set("libelle", $("#im-libelle").value.trim());
  donnees.set("description", $("#im-description").value.trim());
  donnees.set("categorie", $("#im-categorie").value);
  donnees.set("fichier", fichier);

  etatTexte.textContent = "Import en cours...";
  try {
    const reponse = await fetch(API + "/import", {
      method: "POST",
      headers: { Authorization: `Bearer ${etat.token}` },
      body: donnees,
    });
    const resultat = await reponse.json().catch(() => ({}));
    if (!reponse.ok) throw new Error(
      typeof resultat.detail === "string" ? resultat.detail : "Import refusé par le serveur."
    );
    etatTexte.textContent = "";
    notifier(`« ${resultat.libelle} » importé : ${resultat.nb_lignes} lignes.`);
    e.target.reset();
    await chargerImport();
  } catch (err) {
    etatTexte.textContent = "";
    notifier(err.message, "erreur");
  }
});

// ==========================================================================
// E-mails (administrateur)
// ==========================================================================
const LIBELLES_TYPE_MAIL = {
  CREATION_COMPTE: "Confirmation de création de compte",
  CONNEXION: "Confirmation de connexion",
  DEMANDE_ACCEPTEE: "Demande acceptée",
  DEMANDE_REFUSEE: "Demande refusée",
};
const STATUT_MAIL = {
  ENVOYE: "border-vert/40 text-vert bg-vertpale",
  SIMULE: "border-trait text-ardoise",
  ECHEC: "border-brique/40 text-brique bg-briquepale",
};
const LIBELLE_STATUT_MAIL = { ENVOYE: "Envoyé", SIMULE: "Simulé", ECHEC: "Échec" };

async function chargerMails() {
  const mails = await api("/mails");
  $("#liste-mails").innerHTML = mails.length
    ? mails.map(m => `
      <div class="rangee px-5 py-4">
        <div class="flex items-baseline justify-between gap-3 flex-wrap">
          <span class="text-sm font-medium">${echapper(m.sujet)}</span>
          ${chip(LIBELLE_STATUT_MAIL[m.statut] ?? m.statut, STATUT_MAIL[m.statut] ?? "border-trait text-ardoise")}
        </div>
        <p class="text-xs text-ardoise mt-1.5">
          à ${echapper(m.destinataire)}
          <span class="ml-3">${echapper(LIBELLES_TYPE_MAIL[m.type_notification] ?? m.type_notification)}</span>
          <span class="ml-3 font-mono">${horodatageFR(m.cree_le)}</span>
          ${m.piece_jointe_nom ? `<span class="ml-3">pièce jointe : ${echapper(m.piece_jointe_nom)}</span>` : ""}
        </p>
        ${m.erreur ? `<p class="text-xs text-brique mt-1.5">${echapper(m.erreur)}</p>` : ""}
      </div>`).join("")
    : vide("Aucun e-mail n'a encore été généré.");
}

// ==========================================================================
// Comptes (administrateur)
// ==========================================================================
const LIBELLES_ROLE_COURT = { CHERCHEUR: "Chercheur", DPO: "Délégué", ADMIN: "Administrateur" };

async function chargerComptes() {
  const comptes = await api("/utilisateurs");
  $("#liste-comptes").innerHTML = comptes.map(c => `
    <div class="rangee px-5 py-4 flex items-center justify-between gap-4 flex-wrap">
      <div class="min-w-0">
        <div class="flex items-center gap-2.5 flex-wrap">
          <span class="text-sm font-medium">${echapper(c.nom_complet)}</span>
          ${chip(LIBELLES_ROLE_COURT[c.role] ?? c.role, "border-trait text-ardoise")}
          ${c.actif ? "" : chip("Désactivé", "border-brique/40 text-brique bg-briquepale")}
        </div>
        <p class="text-xs text-ardoise mt-1">
          ${echapper(c.email)}${c.service ? ` · ${echapper(c.service)}` : ""}
          ${c.role === "CHERCHEUR" ? ` · ${c.nb_demandes} demande${c.nb_demandes > 1 ? "s" : ""} déposée${c.nb_demandes > 1 ? "s" : ""}` : ""}
        </p>
      </div>
      <div class="flex items-center gap-2">
        <select class="role rounded-lg border border-trait bg-sable/50 px-2.5 py-1.5 text-xs" data-id="${c.id}">
          ${Object.entries(LIBELLES_ROLE_COURT).map(([v, texte]) =>
            `<option value="${v}" ${v === c.role ? "selected" : ""}>${texte}</option>`).join("")}
        </select>
        <button class="basculer rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors
                       ${c.actif ? "border-brique text-brique hover:bg-briquepale" : "border-vert text-vert hover:bg-vertpale"}"
                data-id="${c.id}" data-actif="${c.actif}">
          ${c.actif ? "Désactiver" : "Réactiver"}
        </button>
        <button class="demarrer-suppression rounded-lg border border-trait text-ardoise px-3 py-1.5 text-xs font-medium hover:border-brique hover:text-brique transition-colors"
                data-id="${c.id}" data-email="${echapper(c.email)}" data-nom="${echapper(c.nom_complet)}">
          Supprimer
        </button>
      </div>
    </div>
    <div class="confirmation-suppression hidden rangee px-5 py-4 bg-briquepale/40 border-b border-trait" data-id="${c.id}"></div>`).join("");

  $$("#liste-comptes .role").forEach(sel => sel.addEventListener("change", async (e) => {
    try {
      await api(`/utilisateurs/${e.target.dataset.id}`, { methode: "PATCH", corps: { role: e.target.value } });
      notifier("Rôle mis à jour.");
      await chargerComptes();
    } catch (err) { notifier(err.message, "erreur"); }
  }));
  $$("#liste-comptes .basculer").forEach(b => b.addEventListener("click", async () => {
    try {
      await api(`/utilisateurs/${b.dataset.id}`, {
        methode: "PATCH", corps: { actif: b.dataset.actif !== "true" },
      });
      await chargerComptes();
    } catch (err) { notifier(err.message, "erreur"); }
  }));

  // Suppression définitive : double confirmation. Un premier clic ouvre un
  // panneau où l'administrateur doit retaper l'adresse e-mail exacte du
  // compte ; un second clic, seulement actif si elle correspond, confirme.
  $$(".demarrer-suppression").forEach(b => b.addEventListener("click", () => {
    const { id, email, nom } = b.dataset;
    const panneau = $(`.confirmation-suppression[data-id="${id}"]`);
    const dejaOuvert = !panneau.classList.contains("hidden");
    $$(".confirmation-suppression").forEach(p => p.classList.add("hidden"));
    if (dejaOuvert) return;
    panneau.classList.remove("hidden");
    panneau.innerHTML = `
      <p class="text-sm font-medium text-brique">Supprimer définitivement le compte de ${echapper(nom)} ?</p>
      <p class="text-xs text-ardoise mt-1.5 leading-relaxed">
        Cette action est irréversible et supprime le compte, pas seulement son
        accès. Pour confirmer, retapez son adresse e-mail : <strong>${echapper(email)}</strong>
      </p>
      <div class="flex items-center gap-2 mt-3">
        <input class="saisie-confirmation rounded-lg border border-trait px-3 py-1.5 text-sm w-72"
               placeholder="${echapper(email)}">
        <button class="confirmer-suppression rounded-lg bg-brique hover:bg-encre text-white px-3.5 py-1.5 text-xs font-semibold
                       disabled:opacity-40 disabled:cursor-not-allowed transition-colors" disabled
                data-id="${id}" data-email="${echapper(email)}">
          Confirmer la suppression
        </button>
        <button class="annuler-suppression text-xs font-semibold text-ardoise hover:text-encre">Annuler</button>
      </div>`;
    const saisie = $(".saisie-confirmation", panneau);
    const bouton = $(".confirmer-suppression", panneau);
    saisie.addEventListener("input", () => {
      bouton.disabled = saisie.value.trim().toLowerCase() !== email.toLowerCase();
    });
    $(".annuler-suppression", panneau).addEventListener("click", () => panneau.classList.add("hidden"));
    bouton.addEventListener("click", async () => {
      try {
        await api(`/utilisateurs/${id}?confirmation=${encodeURIComponent(saisie.value.trim())}`,
                   { methode: "DELETE" });
        notifier("Compte supprimé définitivement.");
        await chargerComptes();
      } catch (err) { notifier(err.message, "erreur"); }
    });
    saisie.focus();
  }));
}

// ==========================================================================
// Indicateurs
// ==========================================================================
function tuile(libelle, valeur, alerte = false) {
  const vif = alerte && Number(valeur) > 0;
  return `
    <div class="bg-carte rounded-xl border ${vif ? "border-corail" : "border-trait"} p-5">
      <p class="text-[2rem] font-bold leading-none tracking-tight ${vif ? "text-corail" : ""}">${valeur}</p>
      <p class="text-xs text-ardoise mt-2.5 leading-snug">${libelle}</p>
    </div>`;
}

// Toute clé technique affichée dans une barre (statut, catégorie, mode
// d'accès) passe par ce lexique avant d'atteindre l'écran.
const LIBELLES_MODE_COURT = { BRUT: "Valeur précise", PSEUDONYMISE: "Protégée", AGREGE: "Chiffres seulement" };
function libelleLisible(cle) {
  return LIBELLES_STATUT[cle] ?? CATEGORIES[cle]?.label ?? LIBELLES_MODE_COURT[cle] ?? cle;
}

function barres(titre, lignes, largeur = "w-36") {
  const total = Math.max(1, ...lignes.map(l => l.valeur));
  return `
    <div>
      <p class="text-xs text-ardoise mb-2.5">${titre}</p>
      <div class="space-y-2">
        ${lignes.map(l => `
          <div class="flex items-center gap-3">
            <span class="text-xs ${largeur} shrink-0 leading-snug">${echapper(libelleLisible(l.libelle))}</span>
            <div class="flex-1 bg-carte rounded-full border border-trait h-3.5 overflow-hidden">
              <div class="jauge h-full rounded-full" style="width:${Math.max(4, (l.valeur / total) * 100)}%"></div>
            </div>
            <span class="text-xs w-6 text-right font-mono">${l.valeur}</span>
          </div>`).join("")}
      </div>
    </div>`;
}

async function chargerPilotage() {
  const t = await api("/rapports/tableau-de-bord");

  $("#indicateurs").innerHTML =
      tuile("Demandes à instruire", t.a_instruire, true)
    + tuile("Accès ouverts", t.acces_actifs)
    + tuile("Échéances sous sept jours", t.echeances_proches, true)
    + tuile("Accès clos non purgés", t.dette_de_purge, true)
    + tuile("Soumissions bloquées par le contrôle", t.soumissions_bloquees);

  $("#pilotage-echeances").innerHTML = t.echeances.length
    ? t.echeances.map(e => `
        <div class="rangee px-5 py-3.5 flex items-baseline justify-between gap-3">
          <div>
            <p class="text-sm font-medium">${echapper(e.titre_projet)}</p>
            <p class="text-xs text-ardoise mt-1">
              ${echapper(e.demandeur)}<span class="ml-3">fin le ${dateCourte(e.autorisation.date_fin)}</span>
            </p>
          </div>
          <span class="text-sm text-ambre font-medium whitespace-nowrap">${e.jours_restants} j</span>
        </div>`).join("")
    : vide("Aucun accès n'arrive à terme dans les sept prochains jours.");

  $("#pilotage-repartition").innerHTML =
      barres("Demandes par statut", t.demandes_par_statut)
    + barres("Accès par statut", t.acces_par_statut);
}


// ==========================================================================
// Accueil du chercheur
// ==========================================================================
async function chargerAccueil() {
  const [demandes, autorisations, compte] = await Promise.all([
    api("/demandes"), api("/autorisations"), api("/notifications/compte"),
  ]);

  const enAttente = demandes.filter(d => ["SOUMISE", "EN_INSTRUCTION"].includes(d.statut));
  const ouverts = autorisations.filter(a => a.statut === "ACTIVE");

  $("#accueil-indicateurs").innerHTML =
      tuile("Demandes déposées", demandes.length)
    + tuile("En attente de décision", enAttente.length, true)
    + tuile("Accès ouverts", ouverts.length)
    + tuile("Alertes non lues", compte.non_lues, true);

  const recentes = demandes.slice(0, 5);
  $("#accueil-demandes").innerHTML = recentes.length
    ? recentes.map(d => `
        <button data-id="${d.id}" class="ligne-accueil rangee w-full text-left px-5 py-4 hover:bg-sable transition-colors">
          <div class="flex items-baseline justify-between gap-3">
            <span class="text-sm font-semibold">${echapper(d.titre_projet)}</span>
            ${statut(d.statut)}
          </div>
          <p class="text-xs text-ardoise mt-1.5">
            <span>${reference(d)}</span>
            <span class="ml-3">${d.champs_demandes.length} colonne${d.champs_demandes.length > 1 ? "s" : ""}</span>
            <span class="ml-3">déposée le ${dateCourte(d.cree_le)}</span>
          </p>
        </button>`).join("")
    : vide("Vous n'avez pas encore déposé de demande. Le bouton « Déposer une demande » ouvre le formulaire.");

  $$(".ligne-accueil").forEach(b => b.addEventListener("click", async () => {
    await afficher("demandes");
    await ouvrirDemande(Number(b.dataset.id));
  }));
}

// ==========================================================================
// Activité récente du délégué
// ==========================================================================
const RESUMES_ACTION = {
  DEMANDE_CREEE: "Demande créée", DEMANDE_MODIFIEE: "Demande modifiée",
  DEMANDE_SOUMISE: "Demande transmise", INSTRUCTION_OUVERTE: "Instruction ouverte",
  DEMANDE_VALIDEE: "Accès accordé", DEMANDE_REFUSEE: "Demande refusée",
  SOUMISSION_REFUSEE_AUTO: "Transmission bloquée par le contrôle",
  ACCES_REVOQUE: "Accès révoqué", ACCES_EXPIRE: "Accès clos",
  PREAVIS_EXPIRATION: "Préavis envoyé", DONNEES_PURGEES: "Suppression attestée",
  PURGE_AUTOMATIQUE: "Suppression automatique", EXTRACTION_CONSULTEE: "Données consultées",
  EXTRACTION_EXPORTEE: "Données exportées", JOURNAL_EXPORTE: "Journal exporté",
  CONNEXION: "Connexion", CONNEXION_ECHOUEE: "Échec de connexion",
  EXTRACTION_CONSULTEE_DPO: "Données consultées (supervision)",
  EXTRACTION_EXPORTEE_DPO: "Données exportées (supervision)",
  DONNEES_IMPORTEES: "Jeu de données importé", IMPORT_SUPPRIME: "Import supprimé",
  COMPTE_SUPPRIME: "Compte supprimé", ATTESTATION_TELECHARGEE: "Attestation téléchargée",
  COMPTE_CREE: "Compte créé", COMPTE_MODIFIE: "Compte modifié",
};


// ==========================================================================
// Légende du catalogue
// ==========================================================================
function rendreLegendeCategories() {
  $("#legende-categories").innerHTML = Object.values(CATEGORIES).map(cat => `
    <div class="rounded-xl border border-trait bg-carte px-4 py-3 max-w-[220px]">
      ${chipCat(cat)}
      <p class="text-xs text-ardoise mt-2 leading-snug">${echapper(cat.explication)}</p>
    </div>`).join("");
}

// ==========================================================================
// Synthèse
// ==========================================================================
function formaterDelai(jours) {
  if (jours === null || jours === undefined) return "—";
  if (jours < 1) return `${Math.round(jours * 24)} h`;
  return `${jours.toFixed(1)} j`;
}

function periodeSynthese() {
  const params = new URLSearchParams();
  if ($("#s-debut").value) params.set("debut", $("#s-debut").value);
  if ($("#s-fin").value) params.set("fin", $("#s-fin").value);
  return params.toString() ? `?${params}` : "";
}

async function chargerSynthese() {
  if (!$("#s-fin").value) {
    const fin = new Date();
    const debut = new Date(); debut.setDate(debut.getDate() - 90);
    $("#s-fin").value = fin.toISOString().slice(0, 10);
    $("#s-debut").value = debut.toISOString().slice(0, 10);
  }

  const s = await api(`/rapports/synthese${periodeSynthese()}`);

  $("#synthese-indicateurs").innerHTML =
      tuile("Demandes déposées", s.demandes_deposees)
    + tuile("Accès accordés", s.demandes_validees)
    + tuile("Demandes refusées", s.demandes_refusees)
    + tuile("Taux de refus", `${s.taux_de_refus} %`)
    + tuile("Délai moyen d'instruction", formaterDelai(s.delai_moyen_instruction_jours))
    + tuile("Durée moyenne d'accès, en jours", s.duree_moyenne_acces_jours ?? "—")
    + tuile("Soumissions bloquées par le contrôle", s.soumissions_bloquees)
    + tuile("Accès purgés", s.acces_purges);

  $("#synthese-repartitions").innerHTML = s.alertes_les_plus_frequentes.length
    ? `<div>
         <p class="text-xs text-ardoise mb-2.5">Alertes les plus fréquentes</p>
         <div class="bg-carte rounded-xl border border-trait overflow-hidden">
           ${s.alertes_les_plus_frequentes.map(a => `
             <div class="rangee px-4 py-2.5 flex items-baseline justify-between text-sm">
               <span class="text-sm">${echapper(nomRegle(a.libelle))}</span>
               <span class="font-medium">${a.valeur}</span>
             </div>`).join("")}
         </div>
       </div>`
    : "";
}

// ==========================================================================
// Journal
// ==========================================================================
function filtresJournal() {
  const params = new URLSearchParams();
  if ($("#j-action").value) params.set("action", $("#j-action").value);
  if ($("#j-debut").value) params.set("debut", $("#j-debut").value);
  if ($("#j-fin").value) params.set("fin", $("#j-fin").value);
  return params;
}

async function chargerJournal() {
  const selecteur = $("#j-action");
  if (selecteur.options.length <= 1) {
    const actions = await api("/journal/actions");
    selecteur.insertAdjacentHTML("beforeend", actions.map(a =>
      `<option value="${echapper(a)}">${echapper(RESUMES_ACTION[a] ?? a)}</option>`).join(""));
  }

  const params = filtresJournal();
  const entrees = await api(`/journal${params.toString() ? "?" + params : ""}`);

  $("#journal-compte").textContent = entrees.length
    ? `${entrees.length} entrée${entrees.length > 1 ? "s" : ""}` : "";

  $("#liste-journal").innerHTML = entrees.length
    ? entrees.map(e => `
      <div class="rangee px-5 py-2.5 grid sm:grid-cols-[160px_200px_1fr] gap-2 items-baseline">
        <span class="text-xs font-mono text-ardoise">${horodatageFR(e.horodatage)}</span>
        <span class="text-sm font-medium">${echapper(RESUMES_ACTION[e.action] ?? e.action)}</span>
        <span class="text-xs text-ardoise">
          ${echapper(e.utilisateur_email)}
          <span class="ml-3">${echapper(e.entite)}${e.entite_id ? " n° " + e.entite_id : ""}</span>
        </span>
      </div>`).join("")
    : vide("Aucune entrée pour ces critères. Élargissez la période ou choisissez « Toutes ».");
}

// ==========================================================================
// Boutons des vues de pilotage
// ==========================================================================
$("#btn-synthese").addEventListener("click", chargerSynthese);
$("#btn-export-synthese").addEventListener("click", () =>
  telecharger(`/rapports/synthese/export${periodeSynthese()}`, "synthese-acces.csv"));

$("#btn-filtrer-journal").addEventListener("click", chargerJournal);
$("#j-action").addEventListener("change", chargerJournal);

for (const [bouton, format] of [["#btn-journal-csv", "csv"], ["#btn-journal-json", "json"]]) {
  $(bouton).addEventListener("click", () => {
    const params = filtresJournal();
    params.set("format", format);
    telecharger(`/journal/export?${params}`, `journal.${format}`);
  });
}


// ==========================================================================
// Reprise de session
// ==========================================================================
(async function reprendre() {
  const jeton = sessionStorage.getItem(CLE_JETON);
  if (!jeton) return;
  etat.token = jeton;
  try {
    etat.user = await api("/auth/me");
    await demarrer();
  } catch {
    // Jeton expiré ou serveur redémarré : on repart du portail, sans bruit.
    sessionStorage.removeItem(CLE_JETON);
    etat.token = null;
  }
})();
