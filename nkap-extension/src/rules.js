/**
 * rules.js — La discipline de composition et de sécurité (contrat v1.1 §5 & §6)
 *
 * 1. Budget visuel strict : ≤ 3 marques simultanées à l'écran (FIFO).
 * 2. AmountGuard : tout montant écrit doit exister à l'identique à l'écran.
 * 3. Détection du ton de fond (light / dark) : permet d'adapter l'encre
 *    (#12233A sur fond clair, #F5B700 jaune feutre sur fond sombre).
 */

window.NKAP_RULES = (() => {
  const MAX_MARKS = 3;
  const visibleIds = []; // file FIFO des marques actives à l'écran

  const AMOUNT_RE = /[\d][\d\s.,]*\s*(?:FCFA|francs?|fr\.?|%)/giu;

  /** Enregistre une nouvelle marque et renvoie les IDs à effacer si > 3. */
  function onMarkAdded(id) {
    const idx = visibleIds.indexOf(id);
    if (idx !== -1) visibleIds.splice(idx, 1);
    visibleIds.push(id);

    const evicted = [];
    while (visibleIds.length > MAX_MARKS) {
      evicted.push(visibleIds.shift());
    }
    return evicted;
  }

  function onMarkRemoved(id) {
    const idx = visibleIds.indexOf(id);
    if (idx !== -1) visibleIds.splice(idx, 1);
  }

  function onCleared() {
    visibleIds.length = 0;
  }

  function getVisibleCount() {
    return visibleIds.length;
  }

  /**
   * AmountGuard : vérifie qu'aucun montant ou pourcentage dans `text`
   * n'est inventé ou altéré par rapport aux textes visibles de la page.
   */
  function amountsPreserved(text) {
    if (!text) return true;
    const matches = String(text).match(AMOUNT_RE);
    if (!matches || matches.length === 0) return true;

    const bodyDigits = (document.body ? document.body.innerText : "").replace(/\D+/g, "");
    for (const raw of matches) {
      const digits = raw.replace(/\D+/g, "");
      if (digits.length > 0 && !bodyDigits.includes(digits)) {
        console.warn("[nkap/AmountGuard] Action rejetée — montant absent de l'écran :", raw);
        return false;
      }
    }
    return true;
  }

  /**
   * Calcule le ton effectif ("light" | "dark") du fond derrière `el`
   * en remontant la chaîne des ancêtres jusqu'au premier fond opaque.
   */
  function detectTone(el) {
    let cur = el;
    for (let depth = 0; depth < 10 && cur && cur !== document.documentElement; depth++, cur = cur.parentElement) {
      const bg = window.getComputedStyle(cur).backgroundColor;
      if (!bg || bg === "transparent") continue;
      const m = bg.match(/rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)/);
      if (!m) continue;
      const alpha = m[4] !== undefined ? parseFloat(m[4]) : 1;
      if (alpha < 0.35) continue;
      const r = parseFloat(m[1]);
      const g = parseFloat(m[2]);
      const b = parseFloat(m[3]);
      // Luminance relative perçue (sRGB)
      const lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
      return lum < 0.45 ? "dark" : "light";
    }
    return "light";
  }

  return {
    MAX_MARKS,
    onMarkAdded,
    onMarkRemoved,
    onCleared,
    getVisibleCount,
    amountsPreserved,
    detectTone,
  };
})();

