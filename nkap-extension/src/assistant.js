/**
 * assistant.js — Chef d'orchestre intelligent par écran + Dock HeyClicky + Voix synchronisée (M2/I3)
 *
 * Résout les 3 points remontés :
 * 1. Plus de répétition en double : suppression de la tentative audio 404 qui déclenchait
 *    simultanément .catch() et .onerror. La synthèse vocale Web Speech est appelée UNE SEULE FOIS.
 * 2. Plus de phrases coupées :
 *    - File d'attente vocale séquentielle (speechQueue) : les phrases d'un même scénario
 *      s'enchaînent naturellement sans s'interrompre.
 *    - Rétention des instances d'Utterance pour contrer le bug de Garbage Collection de Chrome.
 *    - Garde sur `clear` : ne nettoie pas le tableau ni les sous-titres tant que la voix parle.
 * 3. Réponse instantanée sans délai (0 ms) :
 *    - Mise en cache en mémoire (`fixtureCache`) de toutes les fixtures dès le démarrage.
 *    - Préchauffage des voix Chrome au boot.
 *    - Feedback tactile immédiat au clic sur les chips.
 */

window.NKAP_ASSISTANT = (() => {
  let brainUrl = "";
  let stepTimers = [];
  let speechTimer = null;
  let clearGuardTimer = null;
  let audioEnabled = true;
  let recognition = null;
  let isListening = false;
  let activePanelEl = null;

  // File d'attente vocale séquentielle pour le scénario actif
  const speechQueue = [];
  let isSpeaking = false;
  const activeUtterances = []; // Rétention anti-Garbage Collection de Chrome
  const onSpeechDoneCallbacks = [];

  // Cache mémoire des fixtures pour une réactivité instantanée à 0 ms
  const fixtureCache = new Map();

  const FIXTURES_LIST = [
    "p1-solde",
    "p2-frais",
    "p3-transfert",
    "p4-recap",
    "p5-erreur",
    "p6-inedit",
    "s-erreur-active",
    "s-inedit-actif",
    "s1-historique",
    "s1-lancer-transfert",
    "s1-solde",
    "s2-continuer-transfert",
    "s2-frais-combien",
    "s2-total-et-reste",
    "s3-alerte-nouveau-benef",
    "s3-cocher-et-continuer",
    "s3-remplir-beneficiaire",
    "s4-confirmer-envoi",
    "s4-recap-destinataire",
    "s4-recap-montants",
    "s5-recu-succes",
  ];

  // Catalogue des scénarios par écran avec libellés de chips et mots-clés d'intention
  const SCENARIOS_META = {
    home: [
      {
        id: "s1-solde",
        icon: "💰",
        label: "Combien il me reste sur mon compte ?",
        keywords: ["solde", "reste", "combien", "compte", "argent", "disponible"],
      },
      {
        id: "s1-lancer-transfert",
        icon: "💸",
        label: "Comment envoyer de l'argent ?",
        keywords: ["envoyer", "transfert", "faire", "lancer", "bouton", "comment"],
      },
      {
        id: "s1-historique",
        icon: "📋",
        label: "Quelles sont mes dernières opérations ?",
        keywords: ["historique", "dernier", "operation", "transaction", "recu", "paiement", "salaire"],
      },
    ],
    fees: [
      {
        id: "s2-frais-combien",
        icon: "🏷️",
        label: "Combien coûtent les frais ?",
        keywords: ["frais", "combien", "coute", "gratuit", "tarif", "commission", "pourcentage"],
      },
      {
        id: "s2-total-et-reste",
        icon: "🧮",
        label: "Combien il me restera après l'envoi ?",
        keywords: ["reste", "apres", "total", "debiter", "calcul", "combien il va me rester", "solde apres"],
      },
      {
        id: "s2-continuer-transfert",
        icon: "➡️",
        label: "Comment passer à l'étape suivante ?",
        keywords: ["continuer", "suite", "suivant", "passer", "apres", "bouton"],
      },
    ],
    beneficiary: [
      {
        id: "s3-remplir-beneficiaire",
        icon: "👤",
        label: "Où vérifier le nom et le numéro ?",
        keywords: ["nom", "numero", "telephone", "beneficiaire", "destinataire", "remplir", "ou"],
      },
      {
        id: "s3-alerte-nouveau-benef",
        icon: "🛡️",
        label: "Pourquoi cet avertissement jaune ?",
        keywords: ["alerte", "jaune", "jamais", "utilise", "attention", "pourquoi", "avertissement", "risque"],
      },
      {
        id: "s3-cocher-et-continuer",
        icon: "☑️",
        label: "Que cocher avant de continuer ?",
        keywords: ["cocher", "case", "verifie", "continuer", "valider", "suite"],
      },
    ],
    recap: [
      {
        id: "s4-recap-montants",
        icon: "📊",
        label: "Résume-moi les montants et les frais",
        keywords: ["montant", "frais", "total", "debite", "combien", "resume", "recapitulatif"],
      },
      {
        id: "s4-recap-destinataire",
        icon: "📱",
        label: "À qui va partir l'argent ?",
        keywords: ["qui", "destinataire", "beneficiaire", "nom", "telephone", "numero"],
      },
      {
        id: "s4-confirmer-envoi",
        icon: "🔒",
        label: "Comment confirmer définitivement ?",
        keywords: ["confirmer", "valider", "envoyer", "case", "cocher", "bouton"],
      },
    ],
    receipt: [
      {
        id: "s5-recu-succes",
        icon: "✅",
        label: "Est-ce que l'argent est bien parti ?",
        keywords: ["parti", "reussi", "confirme", "recu", "reference", "nouveau solde", "preuve"],
      },
    ],
  };

  const STEP_TITLES = {
    home: "Étape 1 · Solde & Compte",
    fees: "Étape 2 · Frais de transfert",
    beneficiary: "Étape 3 · Bénéficiaire",
    recap: "Étape 4 · Récapitulatif",
    receipt: "Étape 5 · Confirmation",
  };

  const SCENARIOS_BY_SCREEN = Object.fromEntries(
    Object.entries(SCENARIOS_META).map(([k, list]) => [k, list.map((x) => x.id)])
  );

  const cursorByScreen = {
    home: 0,
    fees: 0,
    beneficiary: 0,
    recap: 0,
    receipt: 0,
  };

  let lastExplainedErrorText = "";
  let lastExplainedUnseenText = "";

  const O = () => window.NKAP_OVERLAY;
  const Q = (t) => window.NKAP_QUERY(t);
  const hasChrome =
    typeof chrome !== "undefined" && !!chrome.runtime && !!chrome.runtime.getURL;

  const norm = (s) =>
    String(s || "")
      .normalize("NFD")
      .replace(/\p{Diacritic}/gu, "")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();

  // ── 1. Gestionnaire vocal séquentiel sans coupure ni double lecture ──

  function stopVoice() {
    speechQueue.length = 0;
    onSpeechDoneCallbacks.length = 0;
    isSpeaking = false;
    if (speechTimer) {
      clearTimeout(speechTimer);
      speechTimer = null;
    }
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      try {
        window.speechSynthesis.cancel();
      } catch (_) {}
    }
    activeUtterances.length = 0;
    if (O() && O().setStatusPill) {
      O().setStatusPill(null);
    }
  }

  function onSpeechDoneOnce(cb) {
    if (!isSpeaking && speechQueue.length === 0) {
      cb();
    } else {
      onSpeechDoneCallbacks.push(cb);
    }
  }

  function processSpeechQueue() {
    if (!audioEnabled || isSpeaking || speechQueue.length === 0) {
      if (!isSpeaking && speechQueue.length === 0) {
        if (O() && O().setStatusPill) O().setStatusPill(null);
        while (onSpeechDoneCallbacks.length) {
          const cb = onSpeechDoneCallbacks.shift();
          try {
            cb();
          } catch (_) {}
        }
      }
      return;
    }

    const item = speechQueue.shift();
    if (!item || !item.text) {
      processSpeechQueue();
      return;
    }

    isSpeaking = true;
    if (O() && O().setStatusPill) {
      O().setStatusPill("speaking", "nkap parle…");
    }
    // Met à jour le sous-titre de façon parfaitement synchronisée avec la phrase en cours
    if (O() && O().caption) {
      O().caption(item.text, item.subFr || null);
    }

    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      isSpeaking = false;
      processSpeechQueue();
      return;
    }

    try {
      const utter = new SpeechSynthesisUtterance(item.text);
      utter.lang = "fr-FR";
      utter.rate = 1.0;
      utter.pitch = 1.0;

      const voices = window.speechSynthesis.getVoices
        ? window.speechSynthesis.getVoices()
        : [];
      const frVoice =
        voices.find(
          (v) =>
            /^fr/i.test(v.lang) &&
            /natural|google|microsoft|hortense|paul|denise|julie/i.test(v.name)
        ) || voices.find((v) => /^fr/i.test(v.lang));
      if (frVoice) utter.voice = frVoice;

      // Retient la référence en mémoire globale pour contrer le bug de Garbage Collection de Chrome
      activeUtterances.push(utter);

      const onFinish = () => {
        const idx = activeUtterances.indexOf(utter);
        if (idx !== -1) activeUtterances.splice(idx, 1);
        if (speechTimer) {
          clearTimeout(speechTimer);
          speechTimer = null;
        }
        isSpeaking = false;
        processSpeechQueue();
      };

      utter.onend = onFinish;
      utter.onerror = onFinish;

      // Timeout de sécurité au cas où un bug interne de navigateur n'émettrait pas onend
      const estMs = Math.max(2500, Math.min(12000, item.text.length * 85));
      speechTimer = setTimeout(() => {
        if (isSpeaking) onFinish();
      }, estMs);

      window.speechSynthesis.speak(utter);
    } catch (_) {
      isSpeaking = false;
      processSpeechQueue();
    }
  }

  function enqueueSpeech(text, subFr = null) {
    if (!audioEnabled || !text) return;
    speechQueue.push({ text, subFr });
    if (!isSpeaking) {
      processSpeechQueue();
    }
  }

  function cancelPendingSteps() {
    stepTimers.forEach((t) => clearTimeout(t));
    stepTimers = [];
    if (clearGuardTimer) {
      clearTimeout(clearGuardTimer);
      clearGuardTimer = null;
    }
    stopVoice();
  }

  // ── 2. Cache mémoire des fixtures (chargement instantané à 0 ms) ──

  async function loadFixture(id) {
    if (fixtureCache.has(id)) {
      return fixtureCache.get(id);
    }
    const url = hasChrome
      ? chrome.runtime.getURL(`fixtures/actions-${id}.json`)
      : `../fixtures/actions-${id}.json`;
    const res = await fetch(url);
    const data = await res.json();
    fixtureCache.set(id, data);
    return data;
  }

  function preloadFixtures() {
    FIXTURES_LIST.forEach((id) => {
      loadFixture(id).catch(() => {});
    });
    // Préchauffe la synthèse vocale de Chrome
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      try {
        window.speechSynthesis.getVoices();
        if (window.speechSynthesis.onvoiceschanged !== undefined) {
          window.speechSynthesis.onvoiceschanged = () => {
            try {
              window.speechSynthesis.getVoices();
            } catch (_) {}
          };
        }
      } catch (_) {}
    }
  }

  // Déclenche le pré-chargement en tâche de fond dès le boot
  setTimeout(preloadFixtures, 40);

  /**
   * Si un élément trouvé par match_text est un <label> de formulaire placé au-dessus
   * d'un champ (<input>, <select>, <textarea>), renvoie directement ce champ
   * pour qu'on entoure la valeur / le champ et jamais l'intitulé.
   */
  function unwrapFieldLabel(el, preferField = true) {
    if (!el || !preferField) return el;
    const tag = el.tagName ? el.tagName.toLowerCase() : "";
    const txtLen = (el.textContent || "").trim().length;
    const isFieldLabel =
      (tag === "label" || ((tag === "p" || tag === "span" || tag === "div") && txtLen > 0 && txtLen <= 64)) &&
      !el.closest("button, a") &&
      !el.querySelector("input, select, textarea");
    if (isFieldLabel) {
      const next = el.nextElementSibling;
      if (
        next &&
        (next.tagName?.toLowerCase() === "input" ||
          next.tagName?.toLowerCase() === "select" ||
          next.tagName?.toLowerCase() === "textarea" ||
          next.querySelector?.('input:not([type="checkbox"]):not([type="radio"]), select, textarea'))
      ) {
        return next;
      }
    }
    return el;
  }

  /**
   * Résout une cible du contrat / fixture vers un élément DOM réel :
   * 1. node_id (`data-nkap-id`)
   * 2. field_of (champ de saisie sous un `<label>`)
   * 3. value_of (`<dt>Montant</dt><dd>25 000 FCFA</dd>` ou `<span>Frais</span><span>0 FCFA</span>`)
   * 4. match_text (chaîne ou tableau de synonymes)
   * 5. match_regex (avec stratégie `pick`)
   */
  function resolveTarget(pos, preferField = true) {
    if (!pos) return null;
    if (pos.node_id && window.NKAP_QUERY_BY_ID) {
      const byId = window.NKAP_QUERY_BY_ID(pos.node_id);
      if (byId) return unwrapFieldLabel(byId, preferField);
    }
    if (pos.field_of && window.NKAP_QUERY_FIELD_OF) {
      const fieldEl = window.NKAP_QUERY_FIELD_OF(pos.field_of);
      if (fieldEl) return fieldEl;
    }
    if (pos.value_of && window.NKAP_QUERY_VALUE_OF) {
      const valEl = window.NKAP_QUERY_VALUE_OF(pos.value_of);
      if (valEl) return valEl;
    }
    if (Array.isArray(pos.match_text)) {
      for (const t of pos.match_text) {
        const el = Q(t);
        if (el) return unwrapFieldLabel(el, preferField);
      }
    } else if (pos.match_text) {
      const el = Q(pos.match_text);
      if (el) return unwrapFieldLabel(el, preferField);
    }
    if (pos.match_regex && window.NKAP_QUERY_REGEX) {
      return window.NKAP_QUERY_REGEX(pos.match_regex, pos.pick);
    }
    return null;
  }

  const verbatim = (el) =>
    ((el && (el.getAttribute("data-nkap-orig") || el.textContent)) || "").trim();

  /** Exécute une action unitaire du contrat I3. */
  function executeAction(action) {
    if (!action || !action.t) return;
    switch (action.t) {
      case "speak": {
        const spokenText = action.text || action.caption_fr || "";
        enqueueSpeech(spokenText, action.sub_fr || null);
        break;
      }
      case "caption":
        O().caption(action.text || "", action.sub_fr || null);
        break;
      case "circle": {
        const el = resolveTarget(action.target);
        if (el) {
          O().circle(el, action.color || "ink", action.duration_ms || 680, action.id, {
            shape: action.shape,
          });
        }
        break;
      }
      case "box": {
        const el = resolveTarget(action.target);
        if (el) {
          O().box(el, action.color || "ink", action.duration_ms || 680, action.id);
        }
        break;
      }
      case "underline": {
        const el = resolveTarget(action.target);
        if (el) {
          O().underline(el, action.color || "yellow", action.duration_ms || 450, action.id);
        }
        break;
      }
      case "arrow": {
        const a = resolveTarget(action.from);
        const b = resolveTarget(action.to);
        if (a && b) {
          O().arrow(a, b, action.color || "ink", action.duration_ms || 780, action.id);
        }
        break;
      }
      case "frame": {
        const el = resolveTarget(action.target);
        if (el) {
          O().frame(
            el,
            action.label !== undefined ? action.label : "Appuie ici",
            action.id
          );
        }
        break;
      }
      case "write": {
        const el = resolveTarget(action.target);
        let text = action.text;
        if (action.copy_from) {
          const src = resolveTarget(
            typeof action.copy_from === "object"
              ? action.copy_from
              : { match_text: action.copy_from }
          );
          if (src) text = verbatim(src);
        } else if (action.copy_from_target && el) {
          text = verbatim(el);
        }
        const dy =
          action.target && action.target.dy !== undefined
            ? action.target.dy
            : action.dy;
        const dx =
          action.target && action.target.dx !== undefined
            ? action.target.dx
            : action.dx;
        if (el && text) {
          O().write(
            text,
            el,
            {
              size: action.size,
              color: action.color || "ink",
              perLetterMs: action.per_letter_ms,
              dy,
              dx,
            },
            action.id
          );
        }
        break;
      }
      case "notebook": {
        let anchorEl = action.anchor ? resolveTarget(action.anchor) : null;
        const resolvedLines = (action.lines || []).map((line) => {
          if (line.value_from) {
            const src = resolveTarget(line.value_from);
            if (src && !anchorEl) anchorEl = src;
            const liveVal = src ? verbatim(src) : line.fallback_value || "";
            return {
              ...line,
              value: (line.prefix || "") + liveVal + (line.suffix || ""),
            };
          }
          return line;
        });
        O().notebook(
          {
            ...action,
            anchorEl,
            lines: resolvedLines,
          },
          action.id
        );
        break;
      }
      case "callout": {
        const el = resolveTarget(action.target);
        if (el && O().callout) {
          O().callout(el, action.label || action.text || "", action.color || "yellow", action.duration_ms || 520, action.id);
        }
        break;
      }
      case "num": {
        const el = resolveTarget(action.target);
        if (el && O().num) {
          O().num(el, action.step || 1, action.label || "", action.color || "yellow", action.id);
        }
        break;
      }
      case "highlight": {
        const el = resolveTarget(action.target);
        if (el && O().highlight) {
          O().highlight(el, action.color || "yellow", action.duration_ms || 420, action.id);
        }
        break;
      }
      case "strike": {
        const el = resolveTarget(action.target);
        if (el && O().strike) {
          O().strike(el, action.color || "red", action.duration_ms || 360, action.id);
        }
        break;
      }
      case "check": {
        const el = resolveTarget(action.target);
        if (el && O().check) {
          O().check(el, action.color || "green", action.duration_ms || 380, action.id);
        }
        break;
      }
      case "cross": {
        const el = resolveTarget(action.target);
        if (el && O().cross) {
          O().cross(el, action.color || "red", action.duration_ms || 380, action.id);
        }
        break;
      }
      case "edit": {
        if (action.id && O().edit) {
          O().edit(action.id, action);
        }
        break;
      }
      case "hide":
        O().hide(action.id);
        break;
      case "clear": {
        const runClear = () => {
          if (clearGuardTimer) {
            clearTimeout(clearGuardTimer);
            clearGuardTimer = null;
          }
          O().clear();
        };
        // Si l'assistant parle encore, attend la fin (plafonné à 3,5 s anti-blocage TTS) avant d'effacer
        if (isSpeaking || speechQueue.length > 0) {
          if (clearGuardTimer) clearTimeout(clearGuardTimer);
          clearGuardTimer = setTimeout(runClear, 3500);
          onSpeechDoneOnce(() => {
            const t = setTimeout(runClear, 500);
            stepTimers.push(t);
          });
        } else {
          runClear();
        }
        break;
      }
    }
  }

  async function playParcours(id) {
    closePanel();
    cancelPendingSteps();
    O().clear();
    try {
      const fixture = await loadFixture(id);
      const steps = fixture.steps || [];
      console.log(`[nkap] Lecture du scénario : ${id}`, fixture.question_examples || []);
      steps.forEach((step) => {
        const baseDelay = step.at || 0;
        let cumulativeDrawDelay = 0;

        (step.do || []).forEach((act) => {
          if (!act || !act.t) return;
          const isDraw = /^(circle|box|underline|arrow|frame|callout|num|highlight|strike|check|cross)$/.test(act.t);
          const actDelay = baseDelay + cumulativeDrawDelay;

          // Si deux gestes de tracé se trouvent dans la même étape, on les enchaîne
          // naturellement l'un après l'autre (+100 ms pour que le curseur vole avec élégance)
          if (isDraw) {
            const dur = act.duration_ms || 650;
            cumulativeDrawDelay += dur + 100;
          }

          if (actDelay === 0) {
            executeAction(act);
          } else {
            const timer = setTimeout(() => {
              executeAction(act);
            }, actDelay);
            stepTimers.push(timer);
          }
        });
      });
    } catch (e) {
      console.error("[nkap] Scénario introuvable:", id, e);
    }
  }

  /**
   * Associe une question libre (vocale ou écrite) au meilleur scénario de l'écran actif.
   */
  function matchQuestionToScenario(questionText, state) {
    const q = norm(questionText);
    if (!q) return null;

    if (
      state.hasError &&
      (q.includes("erreur") ||
        q.includes("probleme") ||
        q.includes("rouge") ||
        q.includes("bloque") ||
        q.includes("insuffisant") ||
        q.includes("pourquoi"))
    ) {
      return "s-erreur-active";
    }
    if (
      state.hasUnseen &&
      (q.includes("message") ||
        q.includes("important") ||
        q.includes("plafonne") ||
        q.includes("nouveau"))
    ) {
      return "s-inedit-actif";
    }

    const activeList = SCENARIOS_META[state.step] || SCENARIOS_META.home;
    let bestId = null;
    let bestScore = 0;

    // 1. Score sur les scénarios de l'écran actif (prioritaires)
    for (const item of activeList) {
      let score = 0;
      for (const kw of item.keywords) {
        if (q.includes(norm(kw))) score += 3;
      }
      if (score > bestScore) {
        bestScore = score;
        bestId = item.id;
      }
    }

    // 2. Sinon cherche dans tous les écrans
    if (!bestId) {
      for (const list of Object.values(SCENARIOS_META)) {
        for (const item of list) {
          let score = 0;
          for (const kw of item.keywords) {
            if (q.includes(norm(kw))) score += 1;
          }
          if (score > bestScore) {
            bestScore = score;
            bestId = item.id;
          }
        }
      }
    }

    return bestId || activeList[0].id;
  }

  function requestBrainAnswer(payload) {
    const base = String(brainUrl || "").trim().replace(/\/+$/, "");
    if (!base) return Promise.reject(new Error("no_brain_url"));
    if (hasChrome && chrome.runtime && chrome.runtime.sendMessage) {
      return new Promise((resolve, reject) => {
        try {
          chrome.runtime.sendMessage(
            { type: "nkap_brain_answer", url: base, payload },
            (resp) => {
              if (chrome.runtime.lastError) {
                reject(new Error(chrome.runtime.lastError.message));
                return;
              }
              if (resp && resp.ok && resp.data) {
                resolve(resp.data);
              } else {
                reject(new Error((resp && (resp.error || `HTTP ${resp.status}`)) || "brain_error"));
              }
            }
          );
        } catch (err) {
          reject(err);
        }
      });
    }
    return fetch(base + "/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    });
  }

  /**
   * Pose une question libre (voix ou texte) :
   * - Si `brainUrl` est configuré → POST /answer avec le ScreenContext (I5-web)
   * - Sinon (ou en cas d'erreur réseau) → routage d'intention local immédiat
   */
  function askQuestion(questionText, fallbackScenarioId = null) {
    const q = String(questionText || "").trim();
    if (!q) return;
    closePanel();

    const state = window.NKAP_DETECT_SCREEN
      ? window.NKAP_DETECT_SCREEN()
      : { step: "home", hasError: false, hasUnseen: false };

    if (brainUrl) {
      const ctx = window.NKAP_EXTRACT_CONTEXT
        ? window.NKAP_EXTRACT_CONTEXT()
        : { page: { url: location.href, title: document.title }, screen_hint: state.step, nodes: [] };

      if (O().setStatusPill) O().setStatusPill("speaking", "Cerveau M2…");
      requestBrainAnswer({
        transcript: q,
        lang_hint: "fr",
        context: ctx,
      })
        .then((res) => {
          if (!res || !Array.isArray(res.actions) || !res.actions.length) {
            const fallbackId = fallbackScenarioId || matchQuestionToScenario(q, state);
            if (fallbackId) playParcours(fallbackId);
            return;
          }
          cancelPendingSteps();
          O().clear();
          let nextAvailableDrawAt = 0;
          let hasClearAction = false;
          res.actions.forEach((item, idx) => {
            const act = item.action || item;
            const isDraw = /^(circle|box|underline|arrow|frame|callout|num|highlight|strike|check|cross)$/.test(act.t);
            const hasExplicitDelay = item.run_after_ms !== undefined && item.run_after_ms !== null;
            let actDelay = hasExplicitDelay ? item.run_after_ms : idx * 750;
            if (isDraw) {
              if (actDelay < nextAvailableDrawAt) {
                actDelay = nextAvailableDrawAt;
              }
              const dur = act.duration_ms || 600;
              nextAvailableDrawAt = actDelay + dur + 110;
            } else if (act.t === "clear") {
              hasClearAction = true;
              if (actDelay < nextAvailableDrawAt + 3500) {
                actDelay = nextAvailableDrawAt + 3500;
              }
            }
            if (actDelay === 0) {
              executeAction(act);
            } else {
              const timer = setTimeout(() => executeAction(act), actDelay);
              stepTimers.push(timer);
            }
          });
          if (!hasClearAction) {
            stepTimers.push(
              setTimeout(() => executeAction({ t: "clear" }), Math.max(nextAvailableDrawAt + 4000, 6500))
            );
          }
        })
        .catch((err) => {
          console.warn("[nkap] Repli local (serveur M2 indisponible) :", err);
          if (O().setStatusPill) O().setStatusPill(null);
          const fallbackId = fallbackScenarioId || matchQuestionToScenario(q, state);
          if (fallbackId) playParcours(fallbackId);
        });
      return;
    }

    const targetScenario = fallbackScenarioId || matchQuestionToScenario(q, state);
    if (targetScenario) {
      playParcours(targetScenario);
    }
  }

  /** Démarre / arrête l'écoute vocale Push-to-Talk via Web Speech API. */
  function toggleVoiceRecognition(micBtnEl) {
    const SpeechRec =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRec) {
      O().caption("Micro vocal non disponible sur ce navigateur — clique sur une question.", null);
      return;
    }

    if (isListening && recognition) {
      try {
        recognition.stop();
      } catch (_) {}
      isListening = false;
      if (O().setStatusPill) O().setStatusPill(null);
      return;
    }

    stopVoice();
    recognition = new SpeechRec();
    recognition.lang = "fr-FR";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      isListening = true;
      if (micBtnEl) {
        micBtnEl.textContent = "🛑 Écoute…";
        micBtnEl.style.background = "#FF3B5C";
        micBtnEl.style.color = "#FFFFFF";
      }
      if (O().setStatusPill) {
        O().setStatusPill("listening", "Écoute ta question…");
      }
    };

    recognition.onresult = (ev) => {
      const transcript =
        ev.results && ev.results[0] && ev.results[0][0]
          ? ev.results[0][0].transcript
          : "";
      if (transcript) {
        console.log("[nkap] Question vocale reconnue :", transcript);
        askQuestion(transcript);
      }
    };

    recognition.onerror = () => {
      isListening = false;
      if (O().setStatusPill) O().setStatusPill(null);
    };

    recognition.onend = () => {
      isListening = false;
      if (micBtnEl) {
        micBtnEl.textContent = "🎤 Parler";
        micBtnEl.style.background = "rgba(245,183,0,0.16)";
        micBtnEl.style.color = "#F5B700";
      }
      if (O().setStatusPill && !speechTimer) {
        O().setStatusPill(null);
      }
    };

    try {
      recognition.start();
    } catch (_) {}
  }

  function closePanel() {
    if (activePanelEl) {
      activePanelEl.style.display = "none";
    }
  }

  /** Construit et affiche / masque le dock de questions HeyClicky au-dessus de la bulle `nkap`. */
  function togglePanel(panelEl) {
    if (!panelEl) {
      next();
      return;
    }
    activePanelEl = panelEl;
    if (panelEl.style.display === "flex") {
      panelEl.style.display = "none";
      return;
    }

    const state = window.NKAP_DETECT_SCREEN
      ? window.NKAP_DETECT_SCREEN()
      : { step: "home", hasError: false, hasUnseen: false };

    panelEl.innerHTML = "";

    // 1. En-tête : Étape détectée + contrôles sobres (sans icônes) + Fermer
    const header = document.createElement("div");
    header.style.cssText =
      "display:flex;align-items:center;justify-content:space-between;gap:8px;" +
      "padding-bottom:8px;border-bottom:1px solid rgba(255,255,255,0.1);";

    const title = document.createElement("div");
    title.textContent = STEP_TITLES[state.step] || "Assistant nkap";
    title.style.cssText =
      "font-size:12.5px;font-weight:700;color:#F5B700;letter-spacing:0.02em;white-space:nowrap;";

    const controls = document.createElement("div");
    controls.style.cssText = "display:flex;align-items:center;gap:6px;flex-shrink:0;";

    const clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.textContent = "Effacer";
    clearBtn.title = "Effacer les tracés";
    clearBtn.style.cssText =
      "background:rgba(255,255,255,0.06);color:#94A3B8;border:1px solid rgba(255,255,255,0.12);" +
      "border-radius:999px;padding:3px 9px;font-size:11.5px;cursor:pointer;font-family:inherit;";
    clearBtn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      cancelPendingSteps();
      O().clear();
      closePanel();
    });

    const muteBtn = document.createElement("button");
    muteBtn.type = "button";
    muteBtn.textContent = audioEnabled ? "Voix" : "Muet";
    muteBtn.title = "Activer / couper la voix";
    muteBtn.style.cssText =
      "background:rgba(255,255,255,0.08);color:#E2E8F0;border:1px solid rgba(255,255,255,0.14);" +
      "border-radius:999px;padding:3px 9px;font-size:11.5px;cursor:pointer;font-family:inherit;";
    muteBtn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      audioEnabled = !audioEnabled;
      if (!audioEnabled) stopVoice();
      muteBtn.textContent = audioEnabled ? "Voix" : "Muet";
    });

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.textContent = "×";
    closeBtn.style.cssText =
      "background:transparent;border:none;color:#94A3B8;font-size:18px;line-height:1;cursor:pointer;padding:0 4px;";
    closeBtn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      closePanel();
    });

    controls.appendChild(clearBtn);
    controls.appendChild(muteBtn);
    controls.appendChild(closeBtn);
    header.appendChild(title);
    header.appendChild(controls);
    panelEl.appendChild(header);

    // 2. Chips prioritaires si Erreur ou Contenu Inédit Jury à l'écran
    const chipsBox = document.createElement("div");
    chipsBox.style.cssText = "display:flex;flex-direction:column;gap:7px;";

    if (state.hasError) {
      const errChip = document.createElement("button");
      errChip.type = "button";
      errChip.className = "nkap-chip-btn";
      errChip.style.cssText +=
        ";background:rgba(255,59,92,0.18);border-color:rgba(255,59,92,0.65);color:#FFE4E8;font-weight:700;";
      errChip.textContent = "Expliquer l'erreur affichée";
      errChip.addEventListener("click", () => {
        errChip.style.transform = "scale(0.96)";
        errChip.style.background = "rgba(255,59,92,0.32)";
        closePanel();
        if (!playKnownErrorOrFixture(getActiveErrorText())) {
          playParcours("s-erreur-active");
        }
      });
      chipsBox.appendChild(errChip);
    }

    if (state.hasUnseen) {
      const unseenChip = document.createElement("button");
      unseenChip.type = "button";
      unseenChip.className = "nkap-chip-btn";
      unseenChip.style.cssText +=
        ";background:rgba(245,183,0,0.2);border-color:rgba(245,183,0,0.7);color:#FEF08A;font-weight:700;";
      unseenChip.textContent = "Expliquer le nouveau message";
      unseenChip.addEventListener("click", () => {
        unseenChip.style.transform = "scale(0.96)";
        unseenChip.style.background = "rgba(245,183,0,0.34)";
        closePanel();
        const unseenText = getActiveUnseenText();
        if (unseenText && playKnownErrorOrFixture(unseenText)) {
          return;
        }
        showUnseenAttention(unseenText);
      });
      chipsBox.appendChild(unseenChip);
    }

    // 3. Chips des scénarios de l'écran actif (fixtures locales instantanées ; LLM réservé à l'inédit & au chat)
    const screenScenarios = SCENARIOS_META[state.step] || SCENARIOS_META.home;
    screenScenarios.forEach((sc) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "nkap-chip-btn";
      btn.textContent = sc.label;
      btn.addEventListener("click", () => {
        // Feedback tactile immédiat sans aucun temps mort
        btn.style.transform = "scale(0.96)";
        btn.style.background = "rgba(245,183,0,0.28)";
        playParcours(sc.id);
      });
      chipsBox.appendChild(btn);
    });
    panelEl.appendChild(chipsBox);

    // 4. Champ de chat sobre (sans icônes) pour poser des questions personnalisées au cerveau M2
    const chatForm = document.createElement("form");
    chatForm.style.cssText =
      "display:flex;align-items:center;gap:6px;padding-top:8px;" +
      "border-top:1px solid rgba(255,255,255,0.1);margin-top:2px;";

    const chatInput = document.createElement("input");
    chatInput.type = "text";
    chatInput.placeholder = "Poser une question personnalisée…";
    chatInput.autocomplete = "off";
    chatInput.style.cssText =
      "flex:1;min-width:0;background:rgba(255,255,255,0.06);color:#F8FAFC;" +
      "border:1px solid rgba(255,255,255,0.14);border-radius:10px;" +
      "padding:7px 10px;font-size:12.5px;font-family:inherit;outline:none;";
    chatInput.addEventListener("focus", () => {
      chatInput.style.borderColor = "rgba(245,183,0,0.65)";
    });
    chatInput.addEventListener("blur", () => {
      chatInput.style.borderColor = "rgba(255,255,255,0.14)";
    });

    const sendBtn = document.createElement("button");
    sendBtn.type = "submit";
    sendBtn.textContent = "Envoyer";
    sendBtn.style.cssText =
      "background:#F5B700;color:#0F172A;border:none;border-radius:10px;" +
      "padding:7px 12px;font-size:12px;font-weight:700;cursor:pointer;" +
      "font-family:inherit;flex-shrink:0;";

    chatForm.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const q = chatInput.value.trim();
      if (!q) return;
      chatInput.value = "";
      askQuestion(q);
    });

    chatForm.appendChild(chatInput);
    chatForm.appendChild(sendBtn);
    panelEl.appendChild(chatForm);

    panelEl.style.display = "flex";
  }

  /**
   * Choisit intelligemment le prochain scénario à jouer :
   * 1. Si une erreur/alerte vient d'apparaître à l'écran → `s-erreur-active`
   * 2. Si un message inédit vient d'être injecté → `s-inedit-actif`
   * 3. Sinon → fait défiler les scénarios de l'écran actif (1..5)
   */
  function next() {
    const state = window.NKAP_DETECT_SCREEN
      ? window.NKAP_DETECT_SCREEN()
      : { step: "home", hasError: false, hasUnseen: false };

    if (state.hasError) {
      const errEl =
        Q("Solde insuffisant") ||
        Q("Alerte de sécurité") ||
        Q("Une erreur est survenue") ||
        Q("Erreur réseau");
      const errTxt = errEl ? errEl.textContent.trim() : "error";
      if (lastExplainedErrorText !== errTxt) {
        lastExplainedErrorText = errTxt;
        playParcours("s-erreur-active");
        return;
      }
    } else {
      lastExplainedErrorText = "";
    }

    if (state.hasUnseen) {
      const unseenEl =
        document.querySelector('[id^="injected-"]') || Q("Message important");
      const unseenTxt = unseenEl ? unseenEl.textContent.trim() : "unseen";
      if (lastExplainedUnseenText !== unseenTxt) {
        lastExplainedUnseenText = unseenTxt;
        playParcours("s-inedit-actif");
        return;
      }
    } else {
      lastExplainedUnseenText = "";
    }

    const list = SCENARIOS_BY_SCREEN[state.step] || SCENARIOS_BY_SCREEN.home;
    const idx = cursorByScreen[state.step] || 0;
    const scenarioId = list[idx % list.length];
    cursorByScreen[state.step] = idx + 1;
    playParcours(scenarioId);
  }

  /** Appelé automatiquement quand l'utilisateur passe d'une étape à une autre (1→2→3→4→5). */
  function onScreenChanged(newStep) {
    closePanel();
    cancelPendingSteps();
    O().clear();
    cursorByScreen[newStep] = 0;
    console.log("[nkap] Changement d'étape détecté →", newStep);
  }

  function getActiveUnseenElement() {
    const injected = document.querySelector('[id^="injected-"]');
    if (injected) return injected;
    const heading = Q("Message important");
    return heading ? heading.closest("div, section, aside") || heading.parentElement || heading : null;
  }

  function getActiveUnseenText() {
    const el = getActiveUnseenElement();
    return el ? String(el.innerText || el.textContent || "").replace(/\s+/g, " ").trim() : "";
  }

  /** Attire l'attention sur un message inédit sans appeler le LLM ni analyser son contenu. */
  function showUnseenAttention(rawText = "") {
    const targetEl = getActiveUnseenElement();
    if (!targetEl) {
      playParcours("s-inedit-actif");
      return;
    }
    lastExplainedUnseenText = rawText || String(targetEl.textContent || "").trim();
    cancelPendingSteps();
    O().clear();
    executeAction({
      t: "speak",
      phrase_key: "unseen_attention",
      text: "Attention ! Un nouveau message vient d'apparaître. Regarde-le bien avant de continuer.",
      lang: "fr",
    });
    O().box(targetEl, "yellow", 680, "b-unseen-auto");
    stepTimers.push(setTimeout(() => executeAction({ t: "clear" }), 6200));
  }

  function getActiveErrorText() {
    const errEl =
      Q("Solde insuffisant") ||
      Q("Alerte de sécurité") ||
      Q("Une erreur est survenue") ||
      Q("Erreur réseau");
    if (!errEl) return "";
    const container =
      errEl.closest('[role="alert"], [class*="border-red"], [class*="bg-red"], [class*="border-amber"], .rounded-xl, .rounded-lg') ||
      errEl.parentElement ||
      errEl;
    return String(container.innerText || container.textContent || "").replace(/\s+/g, " ").trim();
  }

  /** Contenu inédit injecté par le jury : attire l'attention localement sans appeler le LLM. */
  function onUnseenContent(text) {
    const raw = String(text || "").trim();
    if (raw && playKnownErrorOrFixture(raw)) {
      return;
    }
    showUnseenAttention(raw);
  }

  const ERROR_ALERTS = [
    {
      match: (low) => low.includes("solde insuffisant") || low.includes("insufficient balance") || low.includes("amount_002"),
      voiceId: "err_solde",
      text: "Attention : ton solde est insuffisant pour envoyer cette somme. Aucun franc n'a été retiré : baisse le montant à l'étape 1.",
      targetText: () => "Une erreur est survenue",
      title: "Solde insuffisant",
      lines: [
        { id: "nb-e1", text: "• Le montant dépasse ton solde", color: "red" },
        { id: "nb-e2", text: "• Aucun franc n'a été débité", color: "ink" },
        { divider: true },
        { id: "nb-e3", text: "→ Baisse le montant pour envoyer", color: "yellow", bold: true, underline: true },
      ],
    },
    {
      match: (low) =>
        (low.includes("alerte de securite") || low.includes("security warning") || low.includes("security_00")) &&
        !low.includes("une erreur est survenue") &&
        !low.includes("an error occurred"),
      voiceId: "err_sec",
      text: "Attention : la banque affiche une alerte de sécurité. Vérifie bien chaque chiffre du numéro avant de continuer.",
      targetText: (low) =>
        low.includes("verify")
          ? "verify the beneficiary phone number"
          : low.includes("verifiez")
          ? "vérifiez le numéro du bénéficiaire"
          : "Alerte de sécurité",
      title: "Alerte de sécurité",
      lines: [
        { id: "nb-es1", text: "• Envoi sensible à vérifier", color: "red" },
        { id: "nb-es2", text: "• Un transfert validé est définitif", color: "ink" },
        { divider: true },
        { id: "nb-es3", text: "→ Contrôle le numéro du bénéficiaire", color: "yellow", bold: true, underline: true },
      ],
    },
    {
      match: (low) => low.includes("reseau") || low.includes("indisponible") || low.includes("network"),
      voiceId: "err_net",
      text: "Attention : le réseau ne répond pas pour l'instant. Ton argent n'est pas parti, patiente un moment puis réessaie.",
      targetText: () => "Une erreur est survenue",
      title: "Erreur réseau",
      lines: [
        { id: "nb-en1", text: "• Connexion coupée avec la banque", color: "red" },
        { id: "nb-en2", text: "• Aucun argent n'a été envoyé", color: "ink" },
        { divider: true },
        { id: "nb-en3", text: "→ Réessaie dans quelques secondes", color: "yellow", bold: true, underline: true },
      ],
    },
  ];

  function playKnownErrorOrFixture(errText) {
    const low = norm(errText);
    if (!low) return false;
    const matched = ERROR_ALERTS.find((cfg) => cfg.match(low));
    if (!matched) return false;
    showErrorAlert(matched, low);
    return true;
  }

  function showErrorAlert(cfg, low) {
    cancelPendingSteps();
    O().clear();
    const targetMatch = cfg.targetText(low);
    executeAction({ t: "speak", phrase_key: cfg.voiceId, text: cfg.text, lang: "fr" });
    executeAction({
      t: "box",
      id: "b-err-auto",
      color: "red",
      target: { match_text: targetMatch },
      duration_ms: 550,
    });
    executeAction({
      t: "notebook",
      id: "nb-err-auto",
      title: cfg.title,
      anchor: { match_text: targetMatch },
      lines: cfg.lines,
    });
    stepTimers.push(setTimeout(() => executeAction({ t: "clear" }), 6500));
  }

  /** Erreur ou alerte critique déclenchée dynamiquement : erreurs connues via fixtures locales, inconnues via LLM. */
  function onErrorDetected(errText) {
    closePanel();
    const raw = String(errText || "").trim();
    if (playKnownErrorOrFixture(raw)) {
      return;
    }
    if (brainUrl && raw) {
      askQuestion(raw, "s-erreur-active");
      return;
    }
    playParcours("s-erreur-active");
  }

  return {
    next,
    togglePanel,
    closePanel,
    askQuestion,
    playParcours,
    executeAction,
    onScreenChanged,
    onUnseenContent,
    onErrorDetected,
    SCENARIOS_BY_SCREEN,
    setBrainUrl(u) {
      brainUrl = String(u || "").trim().replace(/\/+$/, "");
    },
    get brainUrl() {
      return brainUrl;
    },
  };
})();
