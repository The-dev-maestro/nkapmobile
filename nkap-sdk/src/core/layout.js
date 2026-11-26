/**
 * nkap-sdk/src/core/layout.js — Placeur anti-collision pur (0 DOM, inspiré de Roamies `nameSpot`)
 *
 * Teste des positions candidates autour d'une cible (droite, gauche, haut, bas, coins)
 * en pénalisant tout chevauchement avec :
 * - les bords du viewport / zone sûre (sous-titre bas, pilule haute, bulle bas-droite)
 * - les boîtes de texte / boutons existants de l'écran (`obstacles`)
 * - les marques et cartes déjà affichées (`occupied`)
 */

(function (global) {
  const NS = (global.__NKAP_SDK_MODULES__ = global.__NKAP_SDK_MODULES__ || {});

  function overlapArea(a, b) {
    const ix = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x));
    const iy = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
    return ix * iy;
  }

  function clampBox(box, viewport, margin = 12, safeTop = 52, safeBottom = 86) {
    const maxX = Math.max(margin, viewport.w - box.w - margin);
    const maxY = Math.max(safeTop, viewport.h - box.h - safeBottom);
    return {
      x: Math.min(maxX, Math.max(margin, box.x)),
      y: Math.min(maxY, Math.max(safeTop, box.y)),
      w: box.w,
      h: box.h,
    };
  }

  /**
   * Trouve le meilleur emplacement `(x, y, side)` pour une étiquette ou carte de taille `(w, h)`
   * près de `targetRect` sans recouvrir la cible ni les obstacles.
   */
  function findBestSpot(targetRect, size, opts = {}) {
    const viewport = opts.viewport || {
      w: typeof window !== "undefined" ? window.innerWidth : 1280,
      h: typeof window !== "undefined" ? window.innerHeight : 720,
    };
    const gap = opts.gap ?? 14;
    const obstacles = opts.obstacles || [];
    const occupied = opts.occupied || [];
    const safeTop = opts.safeTop ?? 54;
    const safeBottom = opts.safeBottom ?? 88;
    const w = size.w;
    const h = size.h;
    const t = targetRect || { x: viewport.w * 0.5, y: viewport.h * 0.35, w: 40, h: 24, cx: viewport.w * 0.5 + 20, cy: viewport.h * 0.35 + 12 };
    const cx = t.cx ?? t.x + t.w / 2;
    const cy = t.cy ?? t.y + t.h / 2;

    // Bulle flottante bas-droite réservée
    const bubbleObstacle = { x: viewport.w - 96, y: viewport.h - 96, w: 84, h: 84 };

    const candidates = [
      { side: "right", x: t.x + t.w + gap, y: cy - h / 2 },
      { side: "top", x: cx - w / 2, y: t.y - h - gap },
      { side: "bottom", x: cx - w / 2, y: t.y + t.h + gap },
      { side: "left", x: t.x - w - gap, y: cy - h / 2 },
      { side: "top-right", x: t.x + t.w + gap, y: t.y - h * 0.6 },
      { side: "top-left", x: t.x - w - gap, y: t.y - h * 0.6 },
      { side: "bottom-right", x: t.x + t.w + gap, y: t.y + t.h - h * 0.3 },
      { side: "bottom-left", x: t.x - w - gap, y: t.y + t.h - h * 0.3 },
    ];

    let best = null;
    let bestScore = Infinity;

    for (let idx = 0; idx < candidates.length; idx++) {
      const c = candidates[idx];
      const clamped = clampBox({ x: c.x, y: c.y, w, h }, viewport, 12, safeTop, safeBottom);
      const shiftPenalty = Math.hypot(clamped.x - c.x, clamped.y - c.y) * 4;
      const targetHit = overlapArea(clamped, t) * 40;
      const bubbleHit = overlapArea(clamped, bubbleObstacle) * 30;
      let occupiedHit = 0;
      for (const o of occupied) occupiedHit += overlapArea(clamped, o) * 25;
      let obsHit = 0;
      for (const o of obstacles) obsHit += overlapArea(clamped, o) * 3.5;

      const score = shiftPenalty + targetHit + bubbleHit + occupiedHit + obsHit + idx * 6;
      if (score < bestScore) {
        bestScore = score;
        best = { x: clamped.x, y: clamped.y, w, h, side: c.side, score };
      }
    }

    return best || clampBox({ x: viewport.w - w - 20, y: 92, w, h }, viewport, 12, safeTop, safeBottom);
  }

  /**
   * Calcule la meilleure zone libre pour une carte pédagogique (`notebook`)
   * en s'adaptant automatiquement aux layouts Web large, Mobile étroit, USSD ou GAB.
   */
  function findCardSpot(targetRect, cardSize, opts = {}) {
    const viewport = opts.viewport || {
      w: typeof window !== "undefined" ? window.innerWidth : 1280,
      h: typeof window !== "undefined" ? window.innerHeight : 720,
    };
    const w = Math.min(cardSize.w, Math.max(240, viewport.w - 28));
    const h = cardSize.h;
    const channel = opts.channel || "web";

    // Sur viewport mobile étroit ou fenêtre USSD centrée : éviter de couper sur les côtés
    if (viewport.w < 720 || channel === "mobile") {
      const topHalf = targetRect && targetRect.y > viewport.h * 0.45;
      const y = topHalf ? 64 : Math.max(64, viewport.h - h - 96);
      return clampBox({ x: (viewport.w - w) / 2, y, w, h }, viewport, 14, 58, 90);
    }

    // Sur grand écran : privilégier les marges calmes à droite ou à gauche hors du formulaire
    const outerRight = clampBox({ x: viewport.w - w - 18, y: targetRect ? targetRect.y - 40 : 88, w, h }, viewport, 12, 62, 94);
    const outerLeft = clampBox({ x: 18, y: targetRect ? targetRect.y - 40 : 88, w, h }, viewport, 12, 62, 94);
    const obs = opts.obstacles || [];
    const occ = opts.occupied || [];
    const scoreBox = (box) => {
      let s = targetRect ? overlapArea(box, targetRect) * 50 : 0;
      for (const o of occ) s += overlapArea(box, o) * 30;
      for (const o of obs) s += overlapArea(box, o) * 5;
      return s;
    };
    const rScore = scoreBox(outerRight);
    const lScore = scoreBox(outerLeft);
    if (rScore < 1200 || lScore < 1200) {
      return rScore <= lScore ? Object.assign(outerRight, { side: "outer-right" }) : Object.assign(outerLeft, { side: "outer-left" });
    }

    return findBestSpot(targetRect, { w, h }, {
      viewport,
      gap: 24,
      obstacles: obs,
      occupied: occ,
      safeTop: 62,
      safeBottom: 94,
    });
  }

  NS.layout = {
    overlapArea,
    clampBox,
    findBestSpot,
    findCardSpot,
  };
})(typeof window !== "undefined" ? window : globalThis);
