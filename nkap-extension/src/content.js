/**
 * content.js — M4-web : Extraction du contexte DOM, résolution de cibles et traduction locale
 *
 * Calibré sur l'environnement officiel https://safinum.cm/hackathon-test :
 * - Gère les boutons contenant des icônes SVG (<button><svg/> Texte</button>)
 * - Résout les paires Libellé → Valeur (`NKAP_QUERY_VALUE_OF`) pour les lignes
 *   de Frais, Total à débiter, Solde après opération, Récapitulatif (<dt>/<dd>) et Reçu
 * - Détecte l'écran actif (1 Solde, 2 Frais, 3 Bénéficiaire, 4 Récapitulatif, 5 Confirmation)
 *   ainsi que les bannières d'erreur et de contenu inédit injecté par le jury
 * - Nettoie automatiquement les marques quand l'utilisateur change d'étape
 */

(function () {
  if (window.__NKAP_CONTENT__) return;
  window.__NKAP_CONTENT__ = true;

  const hasChrome = typeof chrome !== "undefined" && !!chrome.runtime && !!chrome.runtime.id;
  let langOn = false;
  let lastStep = null;
  const restoredTextNodes = new Map(); // TextNode → string original

  const OVERLAY_SEL =
    "#nkap-overlay-host, #nkap-caption, #nkap-bubble, #nkap-cursor, #nkap-status-pill, #nkap-question-panel";

  /** Normalise : minuscules, sans accents/diacritiques, voyelles africaines et homoglyphes unifiés. */
  const norm = (s) =>
    String(s || "")
      .normalize("NFD")
      .replace(/\p{Diacritic}/gu, "")
      .toLowerCase()
      .replace(/[ɔ]/g, "o")
      .replace(/[ɛ]/g, "e")
      .replace(/[ŋ]/g, "n")
      .replace(/а/g, "a")
      .replace(/е/g, "e")
      .replace(/о/g, "o")
      .replace(/р/g, "p")
      .replace(/с/g, "c")
      .replace(/у/g, "y")
      .replace(/х/g, "x")
      .replace(/м/g, "m")
      .replace(/т/g, "t")
      .replace(/к/g, "k")
      .replace(/\s+/g, " ")
      .trim();

  /** Un élément est visible et hors de notre propre overlay / panneau jury. */
  function isVisibleTarget(el) {
    if (!el || el.nodeType !== 1) return false;
    if (el.closest(OVERLAY_SEL) || el.closest("[data-nkap]")) return false;
    const tag = el.tagName.toLowerCase();
    if (tag === "script" || tag === "style" || tag === "svg" || tag === "path") return false;
    if (el.offsetParent === null && window.getComputedStyle(el).position !== "fixed") return false;
    const r = el.getBoundingClientRect();
    return r.width > 4 && r.height > 4;
  }

  /** True si l'élément est à l'intérieur du tiroir outil interne jury Safinum. */
  function isJuryDrawer(el) {
    if (!el) return false;
    const pane = el.closest("aside, .fixed, [class*='overflow-y']");
    return !!(pane && /Outil interne Safinum|DÉCLENCHER UNE ERREUR|INJECTER DU CONTENU INÉDIT/i.test(pane.textContent || ""));
  }

  /** True si l'élément fait partie du bandeau jaune d'environnement de test tout en haut de Safinum. */
  function isTestBanner(el) {
    if (!el) return false;
    let cur = el;
    for (let depth = 0; depth < 5 && cur && cur !== document.body; depth++, cur = cur.parentElement) {
      const r = cur.getBoundingClientRect();
      if (r.height > 0 && r.height <= 85 && r.top <= 45) {
        const t = (cur.textContent || "").trim();
        if (/Environnement de test\s*[—–-]\s*données fictives|Protocole de test/i.test(t)) {
          return true;
        }
      }
    }
    return false;
  }

  /** Un élément fait partie du contenu lisible (exclut le stepper <ol>, <nav>, <footer>, le tiroir jury et le bandeau test). */
  function isMainTarget(el) {
    if (!isVisibleTarget(el)) return false;
    if (el.closest("ol, nav, footer")) return false;
    if (isJuryDrawer(el) || isTestBanner(el)) return false;
    return true;
  }

  /**
   * Un élément est un bloc de texte atomique ciblable s'il n'a pas d'enfants
   * sous-blocs de texte (on autorise les enfants purement graphiques comme <svg>).
   */
  function isTextAtom(el) {
    if (!isVisibleTarget(el)) return false;
    for (const child of el.children) {
      const cTag = child.tagName.toLowerCase();
      if (cTag !== "svg" && cTag !== "img" && cTag !== "br") {
        return false;
      }
    }
    return el.textContent.trim().length >= 2;
  }

  /** Texte original (français) d'un élément ou son texte courant. */
  function origOrCurrentText(el) {
    if (!el) return "";
    return (el.getAttribute("data-nkap-orig") || el.textContent || "").replace(/\s+/g, " ").trim();
  }

  /** Premier nœud texte direct d'un élément (ex: "Frais " dans <span>Frais <span>Gratuit</span></span>). */
  function directText(el) {
    if (!el) return "";
    let out = "";
    for (const n of el.childNodes) {
      if (n.nodeType === 3) {
        out += restoredTextNodes.get(n) || n.nodeValue;
      }
    }
    return out.trim();
  }

  function priorityScore(el, exactMatch) {
    let score = 0;
    if (exactMatch) score += 100;
    if (el.closest("section")) score += 50; // Zone principale de safinum.cm
    if (el.closest("aside")) score -= 60;   // Sidebar secondaire ou panneau jury
    const tag = el.tagName.toLowerCase();
    if (tag === "button" || tag === "a") score += 15;
    score -= Math.min(30, el.textContent.trim().length * 0.2);
    return score;
  }

  // ---- 1. Couche de traduction locale (TreeWalker respectueux des SVG) -----

  function translateTextNode(textNode) {
    if (!langOn || !window.NKAP_LEXICON) return false;
    const parent = textNode.parentElement;
    if (!parent || !isVisibleTarget(parent)) return false;
    const tag = parent.tagName.toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || parent.isContentEditable) {
      return false;
    }

    const raw = textNode.nodeValue || "";
    const trimmed = raw.trim();
    if (trimmed.length < 2) return false;
    if (window.NKAP_LEXICON.hasDigits(trimmed)) return false; // Règle d'or : montants intacts

    const entry = window.NKAP_LEXICON.exactMatch(trimmed);
    if (!entry) return false;

    // Ewondo est la langue principale du projet (fallback Douala si absent)
    const translated = entry.ewo || entry.dua;
    if (!translated) return false;

    if (!restoredTextNodes.has(textNode)) {
      restoredTextNodes.set(textNode, raw);
      parent.setAttribute("data-nkap-orig", trimmed);
    }
    const lead = raw.match(/^\s*/)[0];
    const trail = raw.match(/\s*$/)[0];
    textNode.nodeValue = lead + translated + trail;
    parent.setAttribute("data-nkap-translated", entry.key);
    return true;
  }

  function translateVisible(root = document.body) {
    if (!root || !langOn) return 0;
    let count = 0;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    let n;
    while ((n = walker.nextNode())) nodes.push(n);
    for (const tn of nodes) {
      if (translateTextNode(tn)) count++;
    }
    return count;
  }

  function restoreAll() {
    restoredTextNodes.forEach((orig, textNode) => {
      try {
        textNode.nodeValue = orig;
        if (textNode.parentElement) {
          textNode.parentElement.removeAttribute("data-nkap-translated");
          textNode.parentElement.removeAttribute("data-nkap-orig");
        }
      } catch (_) { }
    });
    restoredTextNodes.clear();
    if (window.NKAP_OVERLAY) window.NKAP_OVERLAY.clear();
  }

  // ---- 2. Détection de l'écran actif & des bannières (safinum.cm + mock) ---

  function detectScreenState() {
    // 1. Détection via les marqueurs textuels et formulaires uniques de chaque étape
    // On extrait le texte visible de toute la page (et les originaux en data-nkap-orig si traduits)
    const bodyText = norm(document.body ? document.body.innerText : "");
    const origTexts = Array.from(document.querySelectorAll("[data-nkap-orig]"))
      .map((el) => norm(el.getAttribute("data-nkap-orig")))
      .join(" ");
    const fullText = (bodyText + " " + origTexts).replace(/\s+/g, " ");

    let step = "home";

    // Étape 5 : Reçu / Confirmation
    if (
      /transfert confirme|transfert effectue|operation a ete enregistree|nouveau transfert|nouveau solde disponible|retour a l'accueil|loma dibamsebe|ebolo ango e tilabe|timba o bekombo|loma dipepe/.test(fullText)
    ) {
      step = "receipt";
    }
    // Étape 4 : Récapitulatif avant confirmation
    else if (
      /confirmer le transfert|verifiez les informations avant de confirmer|je confirme que les informations|total debite.*modifier|ombwa myango mese|na bamse na myango|bamse loma/.test(fullText) ||
      (window.NKAP_QUERY && (window.NKAP_QUERY("Confirmer le transfert") || window.NKAP_QUERY("Bamse loma")) && !window.NKAP_QUERY("Nom du bénéficiaire"))
    ) {
      step = "recap";
    }
    // Étape 3 : Saisie / Vérification du bénéficiaire
    else if (
      /nom du beneficiaire|renseignez les informations du destinataire|motif du transfert|j'ai verifie le nom et le numero|jai verifie le nom|dina la mukusa|tila myango ma mukusa|nimero a telefone|na ombwe dina na nimero/.test(fullText) ||
      (window.NKAP_QUERY && (window.NKAP_QUERY("Nom du bénéficiaire") || window.NKAP_QUERY("Dina la mukusa") || window.NKAP_QUERY("Renseignez les informations du destinataire")))
    ) {
      step = "beneficiary";
    }
    // Étape 2 : Frais de transfert & Montant
    else if (
      /frais de transfert|choisissez le type de transfert|type d'operation|montant a envoyer|mabala ma loma|moni ma loma|botali ba busa|moni ma dia ombusa/.test(fullText) ||
      (window.NKAP_QUERY && (window.NKAP_QUERY("Frais de transfert") || window.NKAP_QUERY("Mabála ma loma") || window.NKAP_QUERY("Montant à envoyer")))
    ) {
      step = "fees";
    }
    // Étape 1 : Solde & Accueil
    else {
      step = "home";
    }

    // Détection d'une bannière d'erreur / alerte critique active (hors boutons et panneau jury)
    const hasError = !!findActiveErrorBanner();

    // Détection d'un bloc de contenu inédit injecté (#injected-* ou "Message important")
    const hasUnseen =
      !!document.querySelector('[id^="injected-"]') ||
      !!window.NKAP_QUERY("Message important");

    return { step, hasError, hasUnseen };
  }

  window.NKAP_DETECT_SCREEN = detectScreenState;

  // ---- 3. MutationObserver (contenu inédit & changements d'étape Vue) ------

  /** Extrait le texte canonique (FR d'origine si déjà traduit) d'une bannière d'erreur. */
  function extractErrorKeyText(container) {
    if (!container) return "";
    const parts = [];
    container.querySelectorAll("*").forEach((el) => {
      if (el.children.length > 0) return;
      const t = (el.getAttribute("data-nkap-orig") || el.textContent || "").trim();
      if (t && !parts.includes(t)) parts.push(t);
    });
    if (!parts.length) {
      return (container.getAttribute("data-nkap-orig") || container.textContent || "").trim();
    }
    return parts.join(" — ").slice(0, 260);
  }

  /** Détecte une bannière d'erreur/alerte réelle hors boutons et hors tiroir interne jury. */
  function findActiveErrorBanner() {
    const candidates = [
      "Une erreur est survenue",
      "Solde insuffisant pour effectuer ce transfert.",
      "Alerte de sécurité",
      "Erreur réseau :",
      "Le service est temporairement indisponible. Réessayez.",
    ];
    for (const phrase of candidates) {
      const target = phrase.toLowerCase();
      for (const el of document.querySelectorAll("body *")) {
        if (!isMainTarget(el) || !isTextAtom(el)) continue;
        if (el.closest("button")) continue;
        const pane = el.closest("aside, .fixed, [class*='overflow-y']");
        if (pane && /Outil interne Safinum|DÉCLENCHER UNE ERREUR/i.test(pane.textContent || "")) {
          continue;
        }
        const card = el.closest('[class*="border-"]');
        if (card && /border-emerald|bg-emerald|border-green|bg-green/i.test(card.className || "")) {
          continue;
        }
        const cur = (el.textContent || "").trim().toLowerCase();
        const orig = (el.getAttribute("data-nkap-orig") || "").trim().toLowerCase();
        if (cur.includes(target) || orig.includes(target)) {
          return (
            el.closest('[role="alert"], [class*="border-red"], [class*="bg-red"], [class*="border-amber"], .rounded-xl, .rounded-lg') ||
            el.parentElement ||
            el
          );
        }
      }
    }
    return null;
  }

  let lastHasError = false;
  let lastErrorText = "";
  let stepCheckTimer = null;
  let isTranslatingDom = false;
  const mo = new MutationObserver((mutations) => {
    if (isTranslatingDom) return;
    let domChanged = false;
    for (const m of mutations) {
      const targetEl = m.target?.nodeType === 1 ? m.target : m.target?.parentElement;
      if (targetEl && (targetEl.id === "nkap-overlay-host" || targetEl.closest?.(OVERLAY_SEL))) {
        continue;
      }
      if (m.type === "characterData" || m.type === "attributes") {
        domChanged = true;
        continue;
      }
      if (m.removedNodes && m.removedNodes.length > 0) domChanged = true;
      m.addedNodes.forEach((node) => {
        if (node.nodeType !== 1) return;
        if (node.id === "nkap-overlay-host" || node.closest?.(OVERLAY_SEL)) return;
        domChanged = true;

        if (langOn) {
          isTranslatingDom = true;
          try {
            translateVisible(node);
          } finally {
            mo.takeRecords();
            isTranslatingDom = false;
          }
        }

        // Détection immédiate de contenu inédit injecté par le jury
        if ((node.id && node.id.startsWith("injected-")) || /message important/i.test(node.textContent || "")) {
          const txt = node.textContent.trim();
          if (txt && window.NKAP_ASSISTANT) {
            setTimeout(() => window.NKAP_ASSISTANT.onUnseenContent(txt), 120);
          }
        }
      });
    }

    if (domChanged) {
      if (stepCheckTimer) clearTimeout(stepCheckTimer);
      stepCheckTimer = setTimeout(() => {
        // Re-traduit après layout/transition (bannières dynamiques, texte asynchrone)
        if (langOn) {
          isTranslatingDom = true;
          try {
            translateVisible();
          } finally {
            mo.takeRecords();
            isTranslatingDom = false;
          }
        }
        const state = detectScreenState();
        const errBanner = state.hasError ? findActiveErrorBanner() : null;
        const errText = errBanner ? extractErrorKeyText(errBanner) : "";

        if (lastStep !== null && state.step !== lastStep) {
          lastStep = state.step;
          lastHasError = state.hasError;
          lastErrorText = errText;
          window.NKAP_ASSISTANT?.onScreenChanged?.(state.step);
          if (state.hasError) {
            setTimeout(() => window.NKAP_ASSISTANT?.onErrorDetected?.(errText), 150);
          }
        } else {
          lastStep = state.step;
          if (state.hasError && (!lastHasError || errText !== lastErrorText)) {
            lastHasError = true;
            lastErrorText = errText;
            window.NKAP_ASSISTANT?.onErrorDetected?.(errText);
          } else if (!state.hasError && lastHasError) {
            lastHasError = false;
            lastErrorText = "";
          }
        }
      }, 100);
    }
  });

  // ---- 4. Cibles & Contexte I5-web (docs/02 v1.1 §2) -----------------------

  window.NKAP_QUERY = function (textFragment) {
    const target = norm(textFragment);
    if (!target) return null;

    const candidates = [];
    for (const el of document.querySelectorAll("body *")) {
      if (!isMainTarget(el) || !isTextAtom(el)) continue;
      const currentNorm = norm(el.textContent);
      const origNorm = norm(el.getAttribute("data-nkap-orig") || "");
      if (currentNorm.includes(target) || origNorm.includes(target)) {
        const isExact = currentNorm === target || origNorm === target;
        candidates.push({ el, score: priorityScore(el, isExact) });
      }
    }
    if (!candidates.length) return null;
    candidates.sort((a, b) => b.score - a.score);
    return candidates[0].el;
  };

  /**
   * Trouve la valeur placée en face d'un libellé (ex: "Frais" → "0 FCFA",
   * "Total à débiter" → "25 000 FCFA", "Référence" → "SAF-2026-...",
   * "Salaire reçu" → "+180 000 FCFA").
   */
  window.NKAP_QUERY_VALUE_OF = function (labels) {
    const list = Array.isArray(labels) ? labels : [labels];
    for (const rawLabel of list) {
      const target = norm(rawLabel);
      if (!target) continue;

      for (const el of document.querySelectorAll("body *")) {
        if (!isMainTarget(el)) continue;
        if (el.querySelector("label, dt, dd, p, div, input, select, textarea")) continue;
        const full = norm(origOrCurrentText(el));
        const direct = norm(directText(el));
        if (full === target || direct === target) {
          // Cas 1 : voisin direct (<dt>Frais</dt><dd>0 FCFA</dd> ou <span>Frais</span><span>0 FCFA</span>)
          if (el.nextElementSibling && isMainTarget(el.nextElementSibling)) {
            const sib = el.nextElementSibling;
            // Évite de retourner la sous-ligne de date dans l'historique ("04 nov. 2026")
            const row = el.closest(".justify-between");
            if (row && row.lastElementChild && !row.lastElementChild.contains(el) && row.lastElementChild !== sib) {
              return row.lastElementChild;
            }
            return sib;
          }
          // Cas 2 : ligne flex .justify-between (ex: historique des transactions)
          const row = el.closest(".justify-between");
          if (row && row.lastElementChild && !row.lastElementChild.contains(el) && isMainTarget(row.lastElementChild)) {
            return row.lastElementChild;
          }
          // Cas 3 : parent direct suivi de la valeur
          if (
            el.parentElement &&
            el.parentElement.nextElementSibling &&
            isMainTarget(el.parentElement.nextElementSibling)
          ) {
            return el.parentElement.nextElementSibling;
          }
        }
      }
    }
    return null;
  };

  /**
   * Trouve le champ de saisie (<input>, <select>, <textarea> ou conteneur .relative)
   * situé juste sous un <label> (ex: "Montant à envoyer", "Nom du bénéficiaire", "Numéro de téléphone").
   */
  window.NKAP_QUERY_FIELD_OF = function (labels) {
    const list = Array.isArray(labels) ? labels : [labels];
    for (const rawLabel of list) {
      const target = norm(rawLabel);
      if (!target) continue;

      for (const el of document.querySelectorAll("label, span, p")) {
        if (!isMainTarget(el) || !isTextAtom(el)) continue;
        const full = norm(origOrCurrentText(el));
        if (full === target || full.includes(target)) {
          const next = el.nextElementSibling;
          if (next && isMainTarget(next)) {
            const tag = next.tagName.toLowerCase();
            if (
              tag === "input" ||
              tag === "select" ||
              tag === "textarea" ||
              next.querySelector("input, select, textarea")
            ) {
              return next;
            }
          }
        }
      }
    }
    return null;
  };

  window.NKAP_QUERY_REGEX = function (pattern, pick = "first") {
    let re;
    try {
      re = new RegExp(pattern, "iu");
    } catch (_) {
      return null;
    }

    const cands = Array.from(document.querySelectorAll("body *")).filter(
      (el) =>
        isMainTarget(el) &&
        isTextAtom(el) &&
        (re.test(el.textContent) || re.test(el.getAttribute("data-nkap-orig") || ""))
    );
    if (!cands.length) return null;

    const num = (s) => {
      const m = String(s).match(/[\d][\d\s.,\u00A0\u202F]*/g);
      if (!m) return -1;
      const raw = m[m.length - 1].replace(/[\s\u00A0\u202F]/g, "");
      const val = parseFloat(raw.replace(/,(?=\d{1,2}\b)/, "."));
      return isNaN(val) ? -1 : val;
    };

    switch (pick) {
      case "largest_value":
        return cands.reduce((a, b) => (num(b.textContent) > num(a.textContent) ? b : a));
      case "smallest_value":
        return cands.reduce((a, b) => (num(b.textContent) < num(a.textContent) ? b : a));
      case "last":
        return cands[cands.length - 1];
      case "largest":
        return cands.reduce((a, b) => (b.textContent.length > a.textContent.length ? b : a));
      default:
        return cands[0];
    }
  };

  window.NKAP_QUERY_BY_ID = function (nodeId) {
    if (!nodeId) return null;
    try {
      return document.querySelector(`[data-nkap-id="${CSS.escape(nodeId)}"]`);
    } catch (_) {
      return null;
    }
  };

  /** Filtre strict M4 (règle d'or #3) : ne jamais lire un champ PIN / mot de passe / OTP. */
  function isSensitiveInput(el) {
    const tag = el.tagName.toLowerCase();
    if (tag !== "input" && tag !== "textarea" && !el.isContentEditable) return false;
    const t = (el.getAttribute("type") || "").toLowerCase();
    if (t === "password") return true;
    const meta = [
      el.getAttribute("name") || "",
      el.id || "",
      el.getAttribute("placeholder") || "",
      el.getAttribute("aria-label") || "",
      el.getAttribute("autocomplete") || "",
    ].join(" ");
    return /pin|password|mot de passe|secret|code|otp|cvv/i.test(meta);
  }

  window.NKAP_EXTRACT_CONTEXT = function () {
    const nodes = [];
    let counter = window.__nkapIdCounter || 1;
    const state = detectScreenState();

    for (const el of document.querySelectorAll("body *")) {
      if (nodes.length >= 200) break;
      if (!isMainTarget(el)) continue;
      const tag = el.tagName.toLowerCase();
      if (tag === "textarea" || el.isContentEditable) continue;
      if (tag === "input" && isSensitiveInput(el)) continue;

      const isInputOrSelect = tag === "input" || tag === "select";
      const clickable =
        tag === "button" || tag === "a" || el.getAttribute("role") === "button";
      const atom = isTextAtom(el);
      if (!isInputOrSelect && !atom && !clickable) continue;

      let rawText = "";
      if (tag === "input") {
        const inpType = (el.getAttribute("type") || "").toLowerCase();
        if (inpType === "checkbox" || inpType === "radio") {
          rawText = el.checked ? "[Coché]" : "[Case à cocher]";
        } else {
          rawText = String(el.value || "").trim();
        }
      } else if (tag === "select") {
        const opt = el.options && el.selectedIndex >= 0 ? el.options[el.selectedIndex] : null;
        rawText = String((opt && opt.text) || el.value || "").trim();
      } else {
        rawText = origOrCurrentText(el);
      }
      if (rawText.length < 1) continue;
      if (rawText.length < 2 && !/\d/.test(rawText)) continue;

      let contextText = rawText.slice(0, 140);
      if (window.NKAP_LEXICON && Array.isArray(window.NKAP_LEXICON.entries)) {
        const findFr = (txt) => {
          const low = txt.toLowerCase();
          const nrmTxt = norm(txt);
          const hit = window.NKAP_LEXICON.entries.find(
            (e) =>
              (e.dua && (e.dua.toLowerCase() === low || norm(e.dua) === nrmTxt)) ||
              (e.ewo && (e.ewo.toLowerCase() === low || norm(e.ewo) === nrmTxt))
          );
          return hit && hit.fr ? hit.fr : null;
        };
        const directFr = findFr(contextText);
        if (directFr) {
          contextText = directFr.slice(0, 140);
        } else if (contextText.includes(":")) {
          const [head, ...rest] = contextText.split(":");
          const headFr = findFr(head.trim());
          if (headFr) {
            const tail = rest.join(":").trim();
            const tailFr = tail ? findFr(tail) || tail : "";
            contextText = (tailFr ? `${headFr} : ${tailFr}` : headFr).slice(0, 140);
          }
        }
      }

      let id = el.getAttribute("data-nkap-id");
      if (!id) {
        id = "n_" + String(counter).padStart(2, "0");
        counter++;
        el.setAttribute("data-nkap-id", id);
      }
      const r = el.getBoundingClientRect();
      nodes.push({
        node_id: id,
        tag,
        text: contextText,
        clickable,
        bounds: [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)],
        tone: window.NKAP_RULES ? window.NKAP_RULES.detectTone(el) : "dark",
      });
    }
    window.__nkapIdCounter = counter;
    return {
      type: "screen_context",
      page: { url: location.href, title: document.title },
      screen_hint: state.step,
      nodes,
    };
  };

  window.NKAP_SETTINGS = {
    get langOn() {
      return langOn;
    },
    set langOn(v) {
      langOn = !!v;
      if (!langOn) restoreAll();
      else translateVisible();
    },
  };

  if (hasChrome) {
    chrome.runtime.onMessage.addListener((msg) => {
      if (msg.type === "settings") {
        langOn = !!msg.ewondoOn;
        if (!langOn) restoreAll();
        else translateVisible();
        if (msg.brainUrl !== undefined) window.NKAP_ASSISTANT?.setBrainUrl(msg.brainUrl);
      }
    });
  }

  function boot(cfg) {
    langOn = !!cfg.ewondoOn;
    lastStep = detectScreenState().step;
    if (langOn) translateVisible();
    mo.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["class", "style", "hidden"],
    });
    if (cfg.brainUrl) window.NKAP_ASSISTANT?.setBrainUrl(cfg.brainUrl);
    window.NKAP_OVERLAY?.bubble?.(() => window.NKAP_ASSISTANT?.next());
    console.log("[nkap] prêt sur", location.href, "— écran actif:", lastStep);
  }

  function start() {
    if (hasChrome && chrome.storage && chrome.storage.sync) {
      chrome.storage.sync.get({ ewondoOn: false, brainUrl: "" }, boot);
    } else {
      boot({ ewondoOn: false, brainUrl: "" });
    }
  }

  if (document.body) start();
  else document.addEventListener("DOMContentLoaded", start);
})();
