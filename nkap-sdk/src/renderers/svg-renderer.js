/**
 * nkap-sdk/src/renderers/svg-renderer.js — SurfaceRenderer Web v1.2 (HeyClicky + Roamies)
 *
 * Gestes écran supportés :
 *   v1.1 : circle, box, underline, arrow, frame, write, caption, hide, clear, bubble
 *   v1.2 : callout (anti-collision nameSpot), num (① ② ③), highlight (stabilo),
 *          strike (rature correction), check (✓), cross (✗), edit (maj par id)
 *
 * Ardoise modulaire `notebook` (5 modes) :
 *   lines | flow | bars | table | choices (cliquable pour Requête ambiguë)
 */

(function (global) {
  const NS = (global.__NKAP_SDK_MODULES__ = global.__NKAP_SDK_MODULES__ || {});

  function createSVGRenderer(opts = {}) {
    let hostEl = null;
    let svg = null;
    let capLayer = null;
    let cursorEl = null;
    let cursorPathEl = null;
    let statusPillEl = null;
    let bubbleEl = null;
    let panelEl = null;
    let orbState = "idle"; // idle | thinking | speaking | listening
    let orbRaf = null;
    let orbRippleEl = null;
    let wordTimer = null;
    let raf = null;
    let activeCursorMarkId = null;
    let clearGen = 0;

    const marks = new Map();
    const pendingTimers = new Set();
    let onChoiceCb = typeof opts.onChoice === "function" ? opts.onChoice : null;
    let getObstaclesCb = typeof opts.getObstacles === "function" ? opts.getObstacles : () => [];
    let getChannelCb = typeof opts.getChannel === "function" ? opts.getChannel : () => "web";

    const PALETTE = {
      inkLight: "#12233A",
      inkDark: "#F5B700",
      yellow: "#F5B700",
      red: "#FF3B5C",
      green: "#34D399",
      cyan: "#38BDF8",
      chalk: "#F8FAFC",
      coral: "#FF6B8B",
    };

    const CHALK = {
      ink: "#F8FAFC",
      white: "#F8FAFC",
      yellow: "#F5B700",
      red: "#FF6B8B",
      green: "#34D399",
      cyan: "#38BDF8",
    };

    const geom = () => NS.geometry;
    const rules = () => NS.rules;
    const layout = () => NS.layout;

    function getAssetUrl(relPath) {
      if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.getURL) {
        return chrome.runtime.getURL(relPath);
      }
      return opts.assetBaseUrl ? `${opts.assetBaseUrl.replace(/\/$/, "")}/${relPath}` : relPath;
    }

    function injectStyles() {
      if (document.getElementById("nkap-sdk-styles")) return;
      const style = document.createElement("style");
      style.id = "nkap-sdk-styles";
      const regUrl = getAssetUrl("fonts/Andika-Regular.ttf");
      const boldUrl = getAssetUrl("fonts/Andika-Bold.ttf");
      const fontBlock =
        typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.getURL
          ? `@font-face{font-family:'Andika';src:url('${regUrl}') format('truetype');font-weight:400;font-display:swap;}
             @font-face{font-family:'Andika';src:url('${boldUrl}') format('truetype');font-weight:700;font-display:swap;}`
          : "";
      style.textContent = `
        ${fontBlock}
        @keyframes nkapPopIn { 0%{opacity:0;transform:scale(0.94);} 100%{opacity:1;transform:scale(1);} }
        @keyframes nkapSlideDown { 0%{opacity:0;transform:translateY(-16px) scale(0.96);} 100%{opacity:1;transform:translateY(0) scale(1);} }
        @keyframes nkapChipIn { 0%{opacity:0;transform:translateY(-6px);} 100%{opacity:1;transform:translateY(0);} }
        @keyframes nkapOrbBreath { 0%,100%{box-shadow:0 8px 26px rgba(245,183,0,0.28),0 0 0 1px rgba(255,196,77,0.35);} 50%{box-shadow:0 10px 34px rgba(255,152,48,0.44),0 0 0 2px rgba(245,183,0,0.58);} }
        @keyframes nkapOrbRipple { 0%{transform:scale(1);opacity:0.62;} 100%{transform:scale(1.62);opacity:0;} }
        @keyframes nkapMarqueeDrag { 0%{transform:scale(0.08,0.08);opacity:0.4;} 100%{transform:scale(1,1);opacity:1;} }
        @keyframes nkapPulseWave { 0%,100%{transform:scaleY(0.45);} 50%{transform:scaleY(1.15);} }
        @keyframes nkapBarGrow { 0%{transform:scaleX(0);} 100%{transform:scaleX(1);} }
        .nkap-write-char { display:inline-block;opacity:0;transition:opacity 0.08s ease-out;white-space:pre; }
        .nkap-write-char.visible { opacity:1; }
        .nkap-word { display:inline-block;opacity:0;transform:translateY(3px);transition:opacity 0.13s ease-out,transform 0.13s ease-out;margin-right:0.28em; }
        .nkap-word.visible { opacity:1;transform:translateY(0); }
        #nkap-bubble:hover { transform:scale(1.09); }
        #nkap-bubble[data-state="speaking"] { filter:drop-shadow(0 0 16px rgba(245,183,0,0.65)) drop-shadow(0 2px 8px rgba(15,23,42,0.35)); }
        #nkap-bubble[data-state="thinking"] { filter:drop-shadow(0 0 14px rgba(255,159,28,0.55)) drop-shadow(0 2px 6px rgba(15,23,42,0.3)); }
        #nkap-bubble[data-state="listening"] { filter:drop-shadow(0 0 16px rgba(255,92,119,0.7)) drop-shadow(0 2px 8px rgba(15,23,42,0.35)); }
        .nkap-choice-btn {
          display:flex;align-items:center;gap:10px;width:100%;text-align:left;
          background:rgba(255,255,255,0.07);color:#F8FAFC;border:1.5px solid rgba(245,183,0,0.45);
          border-radius:12px;padding:9px 13px;font-family:'Andika',system-ui,sans-serif;font-size:14px;
          font-weight:700;cursor:pointer;transition:background 0.14s ease,transform 0.12s ease;
        }
        .nkap-choice-btn:hover { background:rgba(245,183,0,0.22);transform:translateX(3px); }
        .nkap-chip-btn {
          display:flex;align-items:center;gap:9px;width:100%;text-align:left;
          background:linear-gradient(135deg,rgba(255,214,130,0.08),rgba(255,255,255,0.04));
          color:#FEF3C7;border:1px solid rgba(245,183,0,0.2);
          border-radius:12px;padding:9px 12px;font-family:'Andika',system-ui,sans-serif;font-size:13px;
          cursor:pointer;transition:background 0.16s ease,border-color 0.16s ease,transform 0.14s ease,box-shadow 0.16s ease;
          animation:nkapChipIn 0.24s cubic-bezier(0.22,1,0.36,1) both;
        }
        .nkap-chip-btn:hover {
          background:linear-gradient(135deg,rgba(245,183,0,0.22),rgba(255,140,66,0.14));
          border-color:rgba(245,183,0,0.62);transform:translateX(3px);
          box-shadow:0 4px 16px rgba(245,183,0,0.16);
        }
        .nkap-quick-pill {
          background:rgba(245,183,0,0.1);color:#FDE68A;border:1px solid rgba(245,183,0,0.28);
          border-radius:999px;padding:4px 10px;font-size:11.5px;font-family:'Andika',system-ui,sans-serif;
          cursor:pointer;transition:background 0.15s ease,border-color 0.15s ease,transform 0.12s ease;
          white-space:nowrap;
        }
        .nkap-quick-pill:hover { background:rgba(245,183,0,0.24);border-color:rgba(245,183,0,0.68);transform:translateY(-1px); }
      `;
      document.head.appendChild(style);
    }

    function svgEl(tag, attrs) {
      const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
      for (const k in attrs) n.setAttribute(k, attrs[k]);
      return n;
    }

    function ensureLayers() {
      injectStyles();
      if (svg && capLayer && cursorEl && hostEl && hostEl.isConnected) return;

      hostEl = document.createElement("div");
      hostEl.id = "nkap-overlay-host";
      hostEl.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:2147483646;overflow:hidden;";

      const NS_SVG = "http://www.w3.org/2000/svg";
      svg = document.createElementNS(NS_SVG, "svg");
      svg.setAttribute("width", "100%");
      svg.setAttribute("height", "100%");
      svg.style.cssText = "display:block;width:100%;height:100%;overflow:visible;";
      hostEl.appendChild(svg);

      cursorEl = document.createElement("div");
      cursorEl.id = "nkap-cursor-buddy";
      cursorEl.style.cssText =
        "position:fixed;left:0;top:0;width:24px;height:24px;pointer-events:none;z-index:2147483647;" +
        "opacity:0;transform:translate(-40px,-40px);transition:opacity 0.18s ease,transform 0.2s cubic-bezier(0.22,1,0.36,1);" +
        "filter:drop-shadow(0 3px 8px rgba(0,0,0,0.55));";
      const curSvg = document.createElementNS(NS_SVG, "svg");
      curSvg.setAttribute("viewBox", "0 0 24 24");
      curSvg.setAttribute("width", "24");
      curSvg.setAttribute("height", "24");
      cursorPathEl = document.createElementNS(NS_SVG, "path");
      cursorPathEl.setAttribute("d", "M2.5 2.5 L20.5 10.2 L12.2 13.4 L9.2 21.2 Z");
      cursorPathEl.setAttribute("fill", "#F5B700");
      cursorPathEl.setAttribute("stroke", "#FFFFFF");
      cursorPathEl.setAttribute("stroke-width", "1.8");
      cursorPathEl.setAttribute("stroke-linejoin", "round");
      curSvg.appendChild(cursorPathEl);
      cursorEl.appendChild(curSvg);
      hostEl.appendChild(cursorEl);

      statusPillEl = document.createElement("div");
      statusPillEl.id = "nkap-status-pill";
      statusPillEl.style.cssText =
        "position:fixed;top:12px;left:50%;transform:translateX(-50%);background:rgba(10,14,22,0.92);" +
        "color:#F8FAFC;border:1px solid rgba(255,255,255,0.14);border-radius:999px;padding:5px 15px;" +
        "font-family:'Andika',system-ui,sans-serif;font-size:12.5px;font-weight:700;display:none;" +
        "align-items:center;gap:10px;box-shadow:0 8px 24px rgba(0,0,0,0.45);z-index:2147483647;" +
        "pointer-events:none;backdrop-filter:blur(8px);";
      hostEl.appendChild(statusPillEl);

      capLayer = document.createElement("div");
      capLayer.id = "nkap-caption";
      capLayer.style.cssText =
        "position:fixed;left:50%;bottom:12px;transform:translateX(-50%);max-width:min(680px,calc(100vw - 140px));" +
        "z-index:2147483647;background:rgba(10,14,22,0.78);backdrop-filter:blur(6px);" +
        "border:1px solid rgba(255,255,255,0.12);color:#FFFFFF;border-radius:999px;padding:7px 22px;" +
        "font-family:'Andika',system-ui,sans-serif;font-size:18px;line-height:1.35;text-align:center;" +
        "text-shadow:0 2px 8px rgba(0,0,0,0.95);box-shadow:0 6px 20px rgba(0,0,0,0.35);" +
        "pointer-events:none;display:none;opacity:0;transition:opacity 0.16s ease;";

      document.documentElement.appendChild(hostEl);
      document.documentElement.appendChild(capLayer);

      window.addEventListener("scroll", repositionAll, { passive: true, capture: true });
      window.addEventListener("resize", repositionAll, { passive: true });
    }

    function moveCursor(x, y, color = "#F5B700", instant = false) {
      ensureLayers();
      if (!cursorEl) return;
      if (cursorPathEl && color) cursorPathEl.setAttribute("fill", color);
      cursorEl.style.transition = instant
        ? "opacity 0.14s ease"
        : "opacity 0.16s ease, transform 0.2s cubic-bezier(0.22,1,0.36,1)";
      cursorEl.style.opacity = "1";
      cursorEl.style.transform = `translate(${(x - 2).toFixed(1)}px, ${(y - 2).toFixed(1)}px)`;
    }

    function hideCursor() {
      if (cursorEl) cursorEl.style.opacity = "0";
    }

    function setOrbState(mode) {
      orbState = mode || "idle";
      if (bubbleEl) {
        bubbleEl.setAttribute("data-state", orbState);
      }
    }

    function setStatusPill(mode, labelText) {
      ensureLayers();
      // Synchronise automatiquement la pulsation de l'orbe neuronal Jarvis avec l'état vocal/cerveau !
      if (!mode) {
        setOrbState("idle");
      } else if (mode === "listening") {
        setOrbState("listening");
      } else if (labelText && /cerveau|réfléch|en cours/i.test(labelText)) {
        setOrbState("thinking");
      } else {
        setOrbState("speaking");
      }
      if (!statusPillEl) return;
      if (!mode) {
        statusPillEl.style.display = "none";
        statusPillEl.innerHTML = "";
        return;
      }
      const accent = mode === "listening" ? "#FF5C77" : "#F5B700";
      statusPillEl.style.display = "inline-flex";
      statusPillEl.innerHTML = `
        <span style="width:7px;height:7px;border-radius:50%;background:${accent};box-shadow:0 0 10px ${accent};"></span>
        <span>${labelText || (mode === "listening" ? "Écoute…" : "Parle…")}</span>
        <span style="display:inline-flex;align-items:center;gap:2.5px;height:12px;">
          <span style="width:2.5px;height:10px;background:${accent};border-radius:2px;animation:nkapPulseWave 0.55s infinite ease-in-out;"></span>
          <span style="width:2.5px;height:13px;background:${accent};border-radius:2px;animation:nkapPulseWave 0.55s infinite 0.15s ease-in-out;"></span>
          <span style="width:2.5px;height:8px;background:${accent};border-radius:2px;animation:nkapPulseWave 0.55s infinite 0.3s ease-in-out;"></span>
        </span>`;
    }

    function resolveInk(colorName, targetEl) {
      if (colorName === "red") return PALETTE.red;
      if (colorName === "yellow") return PALETTE.yellow;
      if (colorName === "green") return PALETTE.green;
      if (colorName === "cyan") return PALETTE.cyan;
      const tone = rules() ? rules().detectTone(targetEl) : "light";
      return tone === "dark" ? PALETTE.inkDark : PALETTE.inkLight;
    }

    function rectOf(el) {
      if (!el) return { x: 80, y: 120, w: 120, h: 32, cx: 140, cy: 136 };
      const r = el.getBoundingClientRect();
      return { x: r.left, y: r.top, w: r.width, h: r.height, cx: r.left + r.width / 2, cy: r.top + r.height / 2 };
    }

    function getOccupiedBoxes() {
      const boxes = [];
      for (const [, m] of marks) {
        if (m.dom && m.node) {
          for (const n of m.node) {
            if (n && n.getBoundingClientRect) {
              const r = n.getBoundingClientRect();
              if (r.width > 4 && r.height > 4) boxes.push({ x: r.left, y: r.top, w: r.width, h: r.height });
            }
          }
        }
      }
      return boxes;
    }

    function removeMarkImmediate(id) {
      const m = marks.get(id);
      if (!m) return;
      if (m.timers) m.timers.forEach((t) => clearTimeout(t));
      if (m.node) m.node.forEach((n) => n && n.remove && n.remove());
      marks.delete(id);
      if (activeCursorMarkId === id) activeCursorMarkId = null;
      if (rules()) rules().onMarkRemoved(id);
    }

    function enforceMarkBudget(id) {
      if (marks.has(id)) removeMarkImmediate(id);
      if (!rules()) return;
      const evicted = rules().onMarkAdded(id);
      evicted.forEach((oldId) => removeMarkImmediate(oldId));
    }

    function addStroke(id, main, head, strokeColor, drawMs, anchorEl, baseRect, strokeWidth = 4.0, opacity = 0.96, extraNodes = []) {
      ensureLayers();
      enforceMarkBudget(id);
      const created = [...extraNodes];

      const makePath = (pathObj, w, col, op, delay = 0) => {
        const len = Math.max(1, pathObj.len || 1);
        const outline = svgEl("path", {
          d: pathObj.d,
          fill: "none",
          stroke: "rgba(255,255,255,0.45)",
          "stroke-width": String(w + 3),
          "stroke-linecap": "round",
          "stroke-linejoin": "round",
          "stroke-dasharray": `${len} ${len + 12}`,
          "stroke-dashoffset": String(len),
          opacity: "0",
          "data-nkap": id,
        });
        const p = svgEl("path", {
          d: pathObj.d,
          fill: "none",
          stroke: col,
          "stroke-width": String(w),
          "stroke-linecap": "round",
          "stroke-linejoin": "round",
          "stroke-dasharray": `${len} ${len + 12}`,
          "stroke-dashoffset": String(len),
          opacity: "0",
          "data-nkap": id,
        });
        svg.appendChild(outline);
        svg.appendChild(p);
        created.push(outline, p);
        return { p, outline, len, delay, targetOp: op };
      };

      const mainObj = makePath(main, strokeWidth, strokeColor, opacity, 0);
      marks.set(id, {
        node: created,
        mainPath: mainObj.p,
        strokePairs: [mainObj],
        strokeColor,
        startedAt: performance.now(),
        drawMs: Math.max(120, drawMs),
        len: mainObj.len,
        dom: false,
        anchorEl,
        baseRect,
        dx: 0,
        dy: 0,
      });

      if (head && head.d) {
        const headObj = makePath(head, strokeWidth * 0.92, strokeColor, opacity, drawMs * 0.78);
        marks.get(id).strokePairs.push(headObj);
      }

      animate();
    }

    function animate() {
      if (raf) return;
      const step = () => {
        const now = performance.now();
        let live = false;
        let latestCursorPt = null;
        let latestColor = "#F5B700";

        let activeCursorMark = null;
        if (activeCursorMarkId && marks.has(activeCursorMarkId)) {
          const m = marks.get(activeCursorMarkId);
          const rawT = (now - m.startedAt) / (m.drawMs || 1);
          if (rawT >= 0 && rawT <= 1.02) activeCursorMark = m;
          else activeCursorMarkId = null;
        }

        for (const [id, m] of marks) {
          if (!m.strokePairs) continue;
          for (const sp of m.strokePairs) {
            const rawT = (now - (m.startedAt + sp.delay)) / (sp.delay > 0 ? Math.max(160, m.drawMs * 0.35) : m.drawMs);
            const t = Math.min(1, Math.max(0, rawT));
            const eased = 1 - Math.pow(1 - t, 1.65);
            const offset = (1 - eased) * sp.len;
            sp.p.setAttribute("stroke-dashoffset", offset.toFixed(1));
            sp.outline.setAttribute("stroke-dashoffset", offset.toFixed(1));
            if (rawT >= 0) {
              sp.p.setAttribute("opacity", String(sp.targetOp));
              sp.outline.setAttribute("opacity", String(sp.targetOp * 0.55));
            }
          }
          const rawT = (now - m.startedAt) / (m.drawMs || 1);
          if (!activeCursorMarkId && m.mainPath && rawT >= 0 && rawT <= 1.02) {
            activeCursorMarkId = id;
            activeCursorMark = m;
          }
          if (now < m.startedAt + m.drawMs + 280) live = true;
        }

        if (activeCursorMark && activeCursorMark.mainPath) {
          const rawT = (now - activeCursorMark.startedAt) / (activeCursorMark.drawMs || 1);
          const t = Math.min(1, Math.max(0, rawT));
          const eased = 1 - Math.pow(1 - t, 1.65);
          try {
            const pt = activeCursorMark.mainPath.getPointAtLength(
              Math.max(0, Math.min(activeCursorMark.len, eased * activeCursorMark.len))
            );
            latestCursorPt = { x: pt.x + (activeCursorMark.dx || 0), y: pt.y + (activeCursorMark.dy || 0) };
            latestColor = activeCursorMark.strokeColor || "#F5B700";
          } catch (_) {}
        }

        if (latestCursorPt) moveCursor(latestCursorPt.x, latestCursorPt.y, latestColor, true);
        if (live) raf = requestAnimationFrame(step);
        else raf = null;
      };
      raf = requestAnimationFrame(step);
    }

    function repositionAll() {
      for (const [, m] of marks) {
        if (!m.anchorEl || !m.baseRect || !m.anchorEl.isConnected) continue;
        const cur = m.anchorEl.getBoundingClientRect();
        const dx = cur.left - m.baseRect.left;
        const dy = cur.top - m.baseRect.top;
        m.dx = dx;
        m.dy = dy;
        if (m.dom) {
          m.node.forEach((n) => {
            if (n && n.style && n.getAttribute("data-nkap-reposition") !== "none") {
              n.style.left = `${(m.baseX + dx).toFixed(1)}px`;
              n.style.top = `${(m.baseY + dy).toFixed(1)}px`;
            }
          });
        } else {
          m.node.forEach((n) => {
            if (n && n.setAttribute && n.namespaceURI === "http://www.w3.org/2000/svg") {
              n.setAttribute("transform", `translate(${dx.toFixed(1)}, ${dy.toFixed(1)})`);
            }
          });
        }
      }
    }

    function anchored(el, fn) {
      if (!el || !el.isConnected) return;
      const r = el.getBoundingClientRect();
      if (r.top < 40 || r.bottom > window.innerHeight - 60) {
        try {
          el.scrollIntoView({ behavior: "smooth", block: "center" });
        } catch (_) {}
        const gen = clearGen;
        const tid = setTimeout(() => {
          pendingTimers.delete(tid);
          if (gen === clearGen && el.isConnected) fn();
        }, 260);
        pendingTimers.add(tid);
      } else {
        fn();
      }
    }

    // ---- API publique des gestes (v1.1 + v1.2) -----------------------------

    const api = {
      rectOf,
      moveCursor,
      hideCursor,
      setStatusPill,
      setOnChoice(cb) {
        onChoiceCb = typeof cb === "function" ? cb : null;
      },
      setObstaclesProvider(cb) {
        getObstaclesCb = typeof cb === "function" ? cb : () => [];
      },
      setChannelProvider(cb) {
        getChannelCb = typeof cb === "function" ? cb : () => "web";
      },

      circle(el, color = "ink", drawMs = 680, id = "c_" + Date.now(), opts = {}) {
        if (opts && opts.shape === "box") return api.box(el, color, drawMs, id);
        anchored(el, () => {
          const r = rectOf(el);
          const col = resolveInk(color, el);
          const p = geom().handCircle(r.cx, r.cy, r.w / 2 + 14, r.h / 2 + 11, id);
          addStroke(id, p, null, col, drawMs, el, el.getBoundingClientRect(), 4.2);
        });
      },

      box(el, color = "ink", drawMs = 680, id = "b_" + Date.now()) {
        anchored(el, () => {
          const r = rectOf(el);
          const col = resolveInk(color, el);
          const p = geom().handBox(r.x - 10, r.y - 6, r.w + 20, r.h + 12, id);
          addStroke(id, p, null, col, drawMs, el, el.getBoundingClientRect(), 4.2);
        });
      },

      underline(el, color = "yellow", drawMs = 450, id = "u_" + Date.now()) {
        anchored(el, () => {
          const r = rectOf(el);
          const col = resolveInk(color, el);
          const p = geom().handUnderline(r.x - 4, r.y + r.h + 5, r.w + 8, id);
          addStroke(id, p, null, col, drawMs, el, el.getBoundingClientRect(), 4.8);
        });
      },

      /** NEW v1.2 : Surligneur fluo translucide (`highlight`). */
      highlight(el, color = "yellow", drawMs = 420, id = "hl_" + Date.now()) {
        anchored(el, () => {
          const r = rectOf(el);
          const col = resolveInk(color, el);
          const p = geom().handHighlight(r.x, r.y, r.w, r.h, id);
          addStroke(id, p, null, col, drawMs, el, el.getBoundingClientRect(), Math.max(18, Math.min(34, r.h + 4)), 0.34);
        });
      },

      /** NEW v1.2 : Rature manuscrite rouge (`strike`, scénario Correction). */
      strike(el, color = "red", drawMs = 360, id = "st_" + Date.now()) {
        anchored(el, () => {
          const r = rectOf(el);
          const col = resolveInk(color || "red", el);
          const p = geom().handStrike(r.x, r.y, r.w, r.h, id);
          addStroke(id, p, null, col, drawMs, el, el.getBoundingClientRect(), 4.4);
        });
      },

      /** NEW v1.2 : Coche verte ✓ tracée à côté d'une cible (`check`). */
      check(el, color = "green", drawMs = 380, id = "chk_" + Date.now()) {
        anchored(el, () => {
          const r = rectOf(el);
          const col = resolveInk(color || "green", el);
          const p = geom().handCheck(r.x + r.w + 20, r.cy, 24, id);
          addStroke(id, p, null, col, drawMs, el, el.getBoundingClientRect(), 4.6);
        });
      },

      /** NEW v1.2 : Croix rouge ✗ tracée à côté d'une cible (`cross`). */
      cross(el, color = "red", drawMs = 380, id = "crs_" + Date.now()) {
        anchored(el, () => {
          const r = rectOf(el);
          const col = resolveInk(color || "red", el);
          const p = geom().handCross(r.x + r.w + 20, r.cy, 22, id);
          addStroke(id, p.main, p.head, col, drawMs, el, el.getBoundingClientRect(), 4.4);
        });
      },

      /** NEW v1.2 : Étiquette pilule anti-collision (`nameSpot`) + flèche fine + Pointer Buddy (`callout`). */
      callout(el, label = "", color = "yellow", drawMs = 520, id = "co_" + Date.now()) {
        if (!label || (rules() && !rules().amountsPreserved(label))) return;
        ensureLayers();
        anchored(el, () => {
          const r = rectOf(el);
          const col = resolveInk(color || "yellow", el);
          const estW = Math.min(260, Math.max(90, label.length * 8.6 + 26));
          const estH = 34;
          const spot = layout().findBestSpot(r, { w: estW, h: estH }, {
            gap: 28,
            obstacles: getObstaclesCb(),
            occupied: getOccupiedBoxes(),
          });

          const pill = document.createElement("div");
          pill.setAttribute("data-nkap", id);
          pill.style.cssText =
            `position:fixed;left:${spot.x.toFixed(1)}px;top:${spot.y.toFixed(1)}px;max-width:260px;` +
            `background:rgba(12,17,28,0.94);color:#F8FAFC;border:2px solid ${col};border-radius:999px;` +
            `padding:5px 14px;font-family:'Andika',system-ui,sans-serif;font-weight:700;font-size:13.5px;` +
            `box-shadow:0 10px 24px rgba(0,0,0,0.48);z-index:2147483647;pointer-events:none;` +
            `white-space:nowrap;overflow:hidden;text-overflow:ellipsis;animation:nkapPopIn 0.16s ease-out both;`;
          pill.textContent = label;
          document.documentElement.appendChild(pill);

          const pr = pill.getBoundingClientRect();
          const pillRect = { x: pr.left, y: pr.top, w: pr.width, h: pr.height, cx: pr.left + pr.width / 2, cy: pr.top + pr.height / 2 };
          const arrowPath = geom().handArrowBetweenRects(pillRect, r, id + "::arr", 0.16);
          addStroke(id, arrowPath.main, arrowPath.head, col, drawMs, el, el.getBoundingClientRect(), 3.2, 0.96, [pill]);
          const rec = marks.get(id);
          if (rec) {
            rec.baseX = spot.x;
            rec.baseY = spot.y;
            rec.calloutPill = pill;
          }
        });
      },

      /** NEW v1.2 : Pastille numérotée ① ② ③ (`num`) pour parcours guidé & menus USSD/GAB. */
      num(el, step = 1, label = "", color = "yellow", id = "num_" + Date.now()) {
        if (label && rules() && !rules().amountsPreserved(label)) return;
        ensureLayers();
        anchored(el, () => {
          enforceMarkBudget(id);
          const r = rectOf(el);
          const col = resolveInk(color || "yellow", el);
          const estW = label ? Math.min(180, 42 + label.length * 8) : 32;
          const bx = Math.max(10, r.x - estW - 10);
          const by = Math.max(46, r.cy - 14);

          const wrap = document.createElement("div");
          wrap.setAttribute("data-nkap", id);
          wrap.style.cssText =
            `position:fixed;left:${bx.toFixed(1)}px;top:${by.toFixed(1)}px;display:inline-flex;` +
            `align-items:center;gap:6px;z-index:2147483647;pointer-events:none;animation:nkapPopIn 0.16s ease-out both;`;
          const badge = document.createElement("span");
          badge.textContent = String(step);
          badge.style.cssText =
            `width:28px;height:28px;border-radius:50%;background:${col};color:#0B1220;` +
            `display:inline-flex;align-items:center;justify-content:center;font-family:'Andika',system-ui,sans-serif;` +
            `font-weight:700;font-size:15px;border:2px solid #FFFFFF;box-shadow:0 4px 12px rgba(0,0,0,0.45);`;
          wrap.appendChild(badge);
          if (label) {
            const tag = document.createElement("span");
            tag.textContent = label;
            tag.style.cssText =
              `background:rgba(12,17,28,0.92);color:#F8FAFC;border:1.5px solid ${col};border-radius:999px;` +
              `padding:3px 10px;font-family:'Andika',system-ui,sans-serif;font-weight:700;font-size:12.5px;`;
            wrap.appendChild(tag);
          }
          document.documentElement.appendChild(wrap);
          moveCursor(bx + 14, by + 14, col, false);

          marks.set(id, {
            node: [wrap],
            startedAt: performance.now(),
            drawMs: 180,
            dom: true,
            anchorEl: el,
            baseRect: el.getBoundingClientRect(),
            baseX: bx,
            baseY: by,
          });
        });
      },

      /** NEW v1.2 : Met à jour une marque existante par son ID sans effacer la scène (`edit`). */
      edit(id, patch = {}) {
        const m = marks.get(id);
        if (!m) return false;
        const newText = patch.label || patch.text;
        if (newText && rules() && !rules().amountsPreserved(newText)) return false;
        if (m.calloutPill && newText) {
          m.calloutPill.textContent = newText;
          if (patch.color) m.calloutPill.style.borderColor = resolveInk(patch.color, m.anchorEl);
          return true;
        }
        if (m.dom && m.node[0] && newText) {
          m.node[0].textContent = newText;
          return true;
        }
        return false;
      },

      arrow(elFrom, elTo, color = "ink", drawMs = 760, id = "a_" + Date.now()) {
        anchored(elFrom, () =>
          anchored(elTo, () => {
            const a = rectOf(elFrom);
            const b = rectOf(elTo);
            const col = resolveInk(color, elFrom);
            const pageAnchor = elFrom.closest && elFrom.closest("#nkap-notebook") ? elTo : elFrom;
            const p = geom().handArrowBetweenRects(a, b, id, 0.14);
            addStroke(id, p.main, p.head, col, drawMs, pageAnchor, pageAnchor.getBoundingClientRect(), 3.8);
          })
        );
      },

      frame(el, label = "Appuie ici", id = "f_" + Date.now()) {
        ensureLayers();
        anchored(el, () => {
          enforceMarkBudget(id);
          const r = rectOf(el);
          const pad = 6;
          const baseX = r.x - pad;
          const baseY = r.y - pad;
          const boxW = r.w + pad * 2;
          const boxH = r.h + pad * 2;

          const div = document.createElement("div");
          div.setAttribute("data-nkap", id);
          div.style.cssText =
            `position:fixed;left:${baseX}px;top:${baseY}px;width:${boxW}px;height:${boxH}px;` +
            `border:2px dashed #FF3B5C;outline:1px solid rgba(255,59,92,0.38);border-radius:6px;` +
            `transform-origin:top left;pointer-events:none;z-index:2147483646;` +
            `box-shadow:0 0 0 3px rgba(255,59,92,0.12);animation:nkapMarqueeDrag 0.18s cubic-bezier(0.16,1,0.3,1) both;`;

          for (const [sx, sy] of [[0, 0], [1, 0], [0, 1], [1, 1]]) {
            const h = document.createElement("div");
            h.style.cssText =
              `position:absolute;width:7px;height:7px;background:#FFFFFF;border:2px solid #FF3B5C;border-radius:1.5px;box-sizing:border-box;` +
              `${sx ? "right:-4.5px" : "left:-4.5px"};${sy ? "bottom:-4.5px" : "top:-4.5px"};`;
            div.appendChild(h);
          }

          if (label) {
            const chip = document.createElement("div");
            chip.textContent = label;
            const placeTop = baseX < 140;
            chip.style.cssText =
              (placeTop
                ? "position:absolute;left:50%;top:-10px;transform:translate(-50%,-100%);"
                : "position:absolute;left:-10px;top:50%;transform:translate(-100%,-50%);") +
              "background:#FF3B5C;color:#FFFFFF;border-radius:999px;padding:3px 11px;" +
              "font-family:'Andika',system-ui,sans-serif;font-weight:700;font-size:13px;white-space:nowrap;" +
              "box-shadow:0 4px 12px rgba(255,59,92,0.4);";
            div.appendChild(chip);
          }

          document.documentElement.appendChild(div);
          moveCursor(baseX + boxW, baseY + boxH, "#FF3B5C", false);

          marks.set(id, {
            node: [div],
            startedAt: performance.now(),
            drawMs: 180,
            dom: true,
            anchorEl: el,
            baseRect: el.getBoundingClientRect(),
            baseX,
            baseY,
          });
        });
      },

      write(text, el, opts = {}, id = "w_" + Date.now()) {
        if (!text || (rules() && !rules().amountsPreserved(text))) return;
        ensureLayers();
        anchored(el, () => {
          enforceMarkBudget(id);
          const r = rectOf(el);
          const baseX = r.cx + (opts.dx ?? 0);
          const baseY = r.y + (opts.dy ?? -44);
          const strokeColor = resolveInk(opts.color || "ink", el);
          const perLetterMs = opts.perLetterMs || 48;

          const container = document.createElement("div");
          container.setAttribute("data-nkap", id);
          container.style.cssText =
            `position:fixed;left:${baseX}px;top:${baseY}px;transform:translate(-50%,0);` +
            `font-family:'Andika',system-ui,sans-serif;font-weight:700;color:${strokeColor};` +
            `font-size:${opts.size || 24}px;white-space:nowrap;z-index:2147483647;pointer-events:none;` +
            `text-shadow:0 2px 6px rgba(0,0,0,0.75);`;

          const rand = geom().seeded(id + "::" + text);
          const timers = [];
          Array.from(String(text)).forEach((ch, idx) => {
            const s = document.createElement("span");
            s.className = "nkap-write-char";
            s.textContent = ch;
            s.style.transform = `translateY(${((rand() - 0.5) * 2.2).toFixed(1)}px) rotate(${((rand() - 0.5) * 5.8).toFixed(2)}deg)`;
            container.appendChild(s);
            timers.push(setTimeout(() => s.classList.add("visible"), idx * perLetterMs));
          });

          document.documentElement.appendChild(container);
          moveCursor(baseX, baseY, strokeColor, false);

          marks.set(id, {
            node: [container],
            timers,
            startedAt: performance.now(),
            drawMs: text.length * perLetterMs,
            dom: true,
            anchorEl: el,
            baseRect: el.getBoundingClientRect(),
            baseX,
            baseY,
          });
        });
      },

      /**
       * Ardoise vitrée modulaire v1.2 (`notebook`) :
       * Modes : `lines` (défaut) | `flow` | `bars` | `table` | `choices`
       */
      notebook(config = {}, id = config.id || "nb_" + Date.now()) {
        ensureLayers();
        if (rules() && !rules().validateActionAmounts(config)) return;

        const mode = config.mode || (config.flow_steps ? "flow" : config.bars ? "bars" : config.columns ? "table" : config.choices ? "choices" : "lines");
        const pageAnchor = config.anchorEl || null;

        const renderCard = () => {
          enforceMarkBudget(id);
          const timers = [];
          const width = Math.min(config.width || 400, Math.max(250, window.innerWidth - 28));
          const targetRect = pageAnchor ? rectOf(pageAnchor) : null;
          const spot = layout().findCardSpot(targetRect, { w: width, h: 240 }, {
            channel: getChannelCb(),
            obstacles: getObstaclesCb(),
            occupied: getOccupiedBoxes(),
          });

          const card = document.createElement("div");
          card.id = "nkap-notebook";
          card.setAttribute("data-nkap", id);
          card.setAttribute("data-nkap-mode", mode);
          card.style.cssText =
            `position:fixed;left:${spot.x.toFixed(1)}px;top:${spot.y.toFixed(1)}px;width:${spot.w}px;` +
            `background:rgba(12,17,28,0.90);backdrop-filter:blur(12px);color:#F8FAFC;border-radius:16px;` +
            `padding:22px 22px 20px 22px;box-sizing:border-box;font-family:'Andika',system-ui,sans-serif;` +
            `box-shadow:0 22px 50px rgba(0,0,0,0.62);z-index:2147483646;pointer-events:auto;` +
            `animation:nkapPopIn 0.16s ease-out both;`;

          const closeBtn = document.createElement("div");
          closeBtn.style.cssText = "position:absolute;top:12px;right:14px;display:flex;gap:6px;cursor:pointer;";
          closeBtn.innerHTML =
            '<span style="width:9px;height:9px;border:1.6px solid rgba(248,250,252,0.55);border-radius:2px;"></span>' +
            '<span style="width:9px;height:9px;border:1.6px solid rgba(255,107,139,0.8);border-radius:2px;"></span>';
          closeBtn.addEventListener("click", () => api.hide(id));
          card.appendChild(closeBtn);

          const noteSvg = svgEl("svg", { width: "100%", height: "100%" });
          noteSvg.style.cssText = "position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none;";
          card.appendChild(noteSvg);

          if (config.title) {
            const titleEl = document.createElement("div");
            titleEl.style.cssText = "font-weight:700;font-size:16.5px;color:#F5B700;margin-bottom:14px;padding-right:34px;";
            titleEl.textContent = config.title;
            card.appendChild(titleEl);
          }

          const body = document.createElement("div");
          body.style.cssText = "display:flex;flex-direction:column;gap:10px;position:relative;z-index:1;";
          card.appendChild(body);

          if (mode === "flow" && Array.isArray(config.flow_steps)) {
            config.flow_steps.forEach((st, idx) => {
              const col = CHALK[st.tone] || "#F8FAFC";
              const node = document.createElement("div");
              node.setAttribute("data-nkap-id", `${id}_f${idx + 1}`);
              node.style.cssText =
                `display:flex;justify-content:space-between;align-items:center;gap:10px;` +
                `background:rgba(255,255,255,0.05);border:1.5px solid ${col};border-radius:11px;padding:9px 13px;` +
                `opacity:0;transform:translateY(6px);transition:opacity 0.22s ease,transform 0.22s ease;`;
              node.innerHTML = `<span style="color:#CBD5E1;font-size:13.5px;">${st.label || ""}</span>` +
                `<span style="font-weight:700;color:${col};font-size:15px;">${st.value || ""}</span>`;
              body.appendChild(node);
              timers.push(setTimeout(() => { node.style.opacity = "1"; node.style.transform = "translateY(0)"; }, idx * 240));
              if (idx < config.flow_steps.length - 1) {
                const sep = document.createElement("div");
                sep.textContent = "↓";
                sep.style.cssText = "text-align:center;color:#F5B700;font-weight:700;font-size:15px;line-height:1;";
                body.appendChild(sep);
              }
            });
          } else if (mode === "bars" && Array.isArray(config.bars)) {
            const maxVal = Math.max(1, ...config.bars.map((b) => Math.abs(Number(b.value) || 0)));
            config.bars.forEach((b, idx) => {
              const col = CHALK[b.tone] || (idx === 0 ? "#F5B700" : "#34D399");
              const pct = Math.max(6, Math.min(100, (Math.abs(Number(b.value) || 0) / maxVal) * 100));
              const wrap = document.createElement("div");
              wrap.style.cssText = "display:flex;flex-direction:column;gap:4px;";
              wrap.innerHTML =
                `<div style="display:flex;justify-content:space-between;font-size:13.5px;">` +
                `<span style="color:#CBD5E1;">${b.label || ""}</span>` +
                `<span style="font-weight:700;color:${col};">${b.amount_text || b.value}</span></div>` +
                `<div style="height:10px;background:rgba(255,255,255,0.1);border-radius:999px;overflow:hidden;">` +
                `<div style="height:100%;width:${pct.toFixed(1)}%;background:${col};border-radius:999px;transform-origin:left;animation:nkapBarGrow 0.45s ${idx * 0.14}s ease-out both;"></div></div>`;
              body.appendChild(wrap);
            });
          } else if (mode === "table" && Array.isArray(config.columns)) {
            const tbl = document.createElement("table");
            tbl.style.cssText = "width:100%;border-collapse:collapse;font-size:13.5px;";
            const thead = document.createElement("tr");
            config.columns.forEach((c) => {
              const th = document.createElement("th");
              th.textContent = c;
              th.style.cssText = "text-align:left;padding:5px 6px;color:#F5B700;border-bottom:1.5px solid rgba(248,250,252,0.28);";
              thead.appendChild(th);
            });
            tbl.appendChild(thead);
            (config.rows || []).forEach((r) => {
              const tr = document.createElement("tr");
              (Array.isArray(r) ? r : []).forEach((cell) => {
                const td = document.createElement("td");
                td.textContent = cell;
                td.style.cssText = "padding:6px;border-bottom:1px solid rgba(255,255,255,0.08);color:#F8FAFC;";
                tr.appendChild(td);
              });
              tbl.appendChild(tr);
            });
            body.appendChild(tbl);
          } else if (mode === "choices" && Array.isArray(config.choices)) {
            config.choices.forEach((ch, idx) => {
              const btn = document.createElement("button");
              btn.type = "button";
              btn.className = "nkap-choice-btn";
              btn.innerHTML =
                `<span style="width:24px;height:24px;border-radius:50%;background:#F5B700;color:#0B1220;display:inline-flex;align-items:center;justify-content:center;font-size:13px;flex-shrink:0;">${ch.key || idx + 1}</span>` +
                `<span>${ch.label}</span>`;
              btn.addEventListener("click", () => {
                if (onChoiceCb) onChoiceCb(ch);
              });
              body.appendChild(btn);
            });
          } else {
            // Mode `lines` (rétro-compatible v1.1)
            (config.lines || []).forEach((line, idx) => {
              const lineId = line.id || `${id}_l${idx + 1}`;
              if (line.divider) {
                const hr = document.createElement("div");
                hr.style.cssText = "height:1px;background:rgba(248,250,252,0.25);margin:2px 0;";
                body.appendChild(hr);
                return;
              }
              const col = CHALK[line.color] || "#F8FAFC";
              const row = document.createElement("div");
              row.setAttribute("data-nkap-id", lineId);
              row.style.cssText = `display:flex;justify-content:space-between;gap:12px;font-size:${line.bold ? "15.5px" : "14px"};font-weight:${line.bold ? "700" : "400"};color:${col};line-height:1.4;`;
              if (line.label != null && line.value != null) {
                row.innerHTML = `<span style="color:#CBD5E1;">${line.label}</span><span data-nkap-id="${lineId}-val" style="font-weight:700;color:${col};text-align:right;">${line.value}</span>`;
              } else {
                row.textContent = line.text || "";
              }
              body.appendChild(row);
            });
          }

          document.documentElement.appendChild(card);

          // Cadre wireframe esquissé à la craie
          const gen = clearGen;
          requestAnimationFrame(() => {
            if (gen !== clearGen || !card.isConnected) return;
            const wire = geom().handBox(3, 3, card.offsetWidth - 6, card.offsetHeight - 6, id + "::wire");
            const p = svgEl("path", {
              d: wire.d,
              fill: "none",
              stroke: "rgba(248,250,252,0.5)",
              "stroke-width": "2",
              "stroke-linecap": "round",
            });
            noteSvg.appendChild(p);
          });

          marks.set(id, {
            node: [card],
            timers,
            startedAt: performance.now(),
            drawMs: 360,
            dom: true,
            anchorEl: pageAnchor,
            baseRect: pageAnchor ? pageAnchor.getBoundingClientRect() : null,
            baseX: spot.x,
            baseY: spot.y,
          });
        };

        if (pageAnchor) anchored(pageAnchor, renderCard);
        else renderCard();
      },

      caption(text, subFr = null, wordDelayMs = 70) {
        ensureLayers();
        if (wordTimer) {
          clearInterval(wordTimer);
          wordTimer = null;
        }
        if (!text || !String(text).trim()) {
          capLayer.style.opacity = "0";
          setStatusPill(null);
          setTimeout(() => {
            if (capLayer && capLayer.style.opacity === "0") {
              capLayer.style.display = "none";
              capLayer.innerHTML = "";
            }
          }, 160);
          return;
        }
        capLayer.innerHTML = "";
        capLayer.style.display = "block";
        requestAnimationFrame(() => (capLayer.style.opacity = "1"));
        const mainLine = document.createElement("div");
        mainLine.style.fontWeight = "700";
        const spans = String(text).trim().split(/\s+/).map((w) => {
          const s = document.createElement("span");
          s.className = "nkap-word";
          s.textContent = w;
          mainLine.appendChild(s);
          return s;
        });
        capLayer.appendChild(mainLine);
        if (subFr) {
          const sub = document.createElement("div");
          sub.textContent = subFr;
          sub.style.cssText = "font-size:13px;color:#CBD5E1;margin-top:2px;";
          capLayer.appendChild(sub);
        }
        let idx = 0;
        const next = () => {
          if (idx < spans.length) spans[idx++].classList.add("visible");
          else if (wordTimer) { clearInterval(wordTimer); wordTimer = null; }
        };
        next();
        wordTimer = setInterval(next, wordDelayMs);
      },

      hide(id) {
        removeMarkImmediate(id);
      },

      clear() {
        clearGen++;
        pendingTimers.forEach((tid) => clearTimeout(tid));
        pendingTimers.clear();
        ensureLayers();
        if (wordTimer) { clearInterval(wordTimer); wordTimer = null; }
        for (const [, m] of marks) {
          if (m.timers) m.timers.forEach((t) => clearTimeout(t));
        }
        if (svg) svg.innerHTML = "";
        marks.clear();
        activeCursorMarkId = null;
        hideCursor();
        setStatusPill(null);
        if (rules()) rules().onCleared();
        api.caption("");
        document.querySelectorAll("[data-nkap]").forEach((n) => n.remove());
      },

      bubble(onTap) {
        ensureLayers();
        if (bubbleEl && bubbleEl.isConnected) {
          if (onTap) bubbleEl.__nkapTap = onTap;
          return bubbleEl;
        }
        // Panneau Jarvis chaleureux qui glisse VERS LE BAS depuis l'orbe neuronal (ancré en haut à droite)
        panelEl = document.createElement("div");
        panelEl.id = "nkap-question-panel";
        panelEl.style.cssText =
          "position:fixed;right:20px;top:150px;width:352px;max-width:calc(100vw - 32px);" +
          "max-height:calc(100vh - 176px);overflow-y:auto;" +
          "background:linear-gradient(160deg,rgba(26,20,15,0.95) 0%,rgba(12,17,30,0.96) 100%);" +
          "backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);" +
          "border:1px solid rgba(245,183,0,0.34);border-radius:20px;" +
          "padding:15px 15px 14px;color:#FEF9EE;font-family:'Andika',system-ui,sans-serif;" +
          "box-shadow:0 24px 60px rgba(0,0,0,0.62),0 0 32px rgba(245,183,0,0.12),inset 0 1px 0 rgba(255,220,130,0.24);" +
          "z-index:2147483647;display:none;flex-direction:column;gap:11px;pointer-events:auto;" +
          "transform-origin:top right;animation:nkapSlideDown 0.24s cubic-bezier(0.22,1,0.36,1) both;";
        document.documentElement.appendChild(panelEl);

        // Constellation neuronale holographique sans contour circulaire (flotte librement façon Jarvis)
        bubbleEl = document.createElement("div");
        bubbleEl.id = "nkap-bubble";
        bubbleEl.setAttribute("data-state", orbState);
        bubbleEl.title = "Nkap — clique pour ouvrir ton assistant";
        bubbleEl.style.cssText =
          "position:fixed;right:18px;top:64px;width:78px;height:78px;" +
          "background:transparent;border:none;box-shadow:none;" +
          "display:flex;align-items:center;justify-content:center;" +
          "filter:drop-shadow(0 0 11px rgba(245,183,0,0.48)) drop-shadow(0 2px 6px rgba(15,23,42,0.32));" +
          "z-index:2147483647;pointer-events:auto;cursor:pointer;user-select:none;" +
          "transition:transform 0.18s cubic-bezier(0.22,1,0.36,1),filter 0.25s ease;overflow:visible;";

        // Canvas 60fps : réseau de neurones flottant librement + impulsions lumineuses organiques
        const canvas = document.createElement("canvas");
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const size = 78;
        canvas.width = size * dpr;
        canvas.height = size * dpr;
        canvas.style.cssText = `width:${size}px;height:${size}px;display:block;pointer-events:none;`;
        bubbleEl.appendChild(canvas);

        // Micro-pastille discrète "nkap" sous la constellation
        const tag = document.createElement("span");
        tag.textContent = "nkap";
        tag.style.cssText =
          "position:absolute;bottom:-4px;left:50%;transform:translateX(-50%);" +
          "background:linear-gradient(135deg,#F5B700,#FF8C42);color:#140E07;" +
          "font-family:'Andika',system-ui,sans-serif;font-weight:700;font-size:10px;letter-spacing:0.06em;" +
          "padding:1px 7px;border-radius:999px;box-shadow:0 2px 10px rgba(0,0,0,0.35);pointer-events:none;";
        bubbleEl.appendChild(tag);

        const ctx = canvas.getContext("2d");
        if (ctx) {
          ctx.scale(dpr, dpr);
          const N = 16;
          const nodes = Array.from({ length: N }, (_, i) => {
            const phi = Math.acos(1 - (2 * (i + 0.5)) / N);
            const theta = Math.PI * (1 + Math.sqrt(5)) * i;
            return {
              phi,
              theta,
              r: 15 + (i % 3) * 5.2,
              speed: 0.45 + (i % 4) * 0.16,
              phase: i * 0.7,
            };
          });

          const drawOrb = (tMs) => {
            if (!bubbleEl || !bubbleEl.isConnected) {
              orbRaf = null;
              return;
            }
            const t = tMs * 0.001;
            const cx = size / 2;
            const cy = size / 2;
            ctx.clearRect(0, 0, size, size);

            const isSpeak = orbState === "speaking";
            const isListen = orbState === "listening";
            const isThink = orbState === "thinking";
            const speedMul = isSpeak ? 2.5 : isListen ? 2.1 : isThink ? 3.2 : 0.9;
            const pulse = isSpeak
              ? 1 + 0.16 * Math.sin(t * 9.5) + 0.07 * Math.sin(t * 17)
              : isListen
              ? 1 + 0.13 * Math.sin(t * 7.2)
              : isThink
              ? 1 + 0.1 * Math.sin(t * 5.5)
              : 1 + 0.05 * Math.sin(t * 2.1);

            const coreHue = isListen ? "255, 92, 119" : "245, 183, 0";
            const warmHue = isListen ? "255, 130, 80" : "234, 118, 28";

            // Lueur solaire diffuse sans aucun bord net (fond 100% transparent)
            const coreGrad = ctx.createRadialGradient(cx, cy, 1, cx, cy, 31 * pulse);
            coreGrad.addColorStop(0, `rgba(255, 244, 196, ${isSpeak ? 0.85 : 0.62})`);
            coreGrad.addColorStop(0.32, `rgba(${coreHue}, ${isSpeak ? 0.46 : 0.28})`);
            coreGrad.addColorStop(0.68, `rgba(${warmHue}, ${isSpeak ? 0.16 : 0.08})`);
            coreGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
            ctx.fillStyle = coreGrad;
            ctx.beginPath();
            ctx.arc(cx, cy, 34 * pulse, 0, Math.PI * 2);
            ctx.fill();

            // Onde organique diffuse quand Nkap parle ou écoute (sans bord circulaire dur)
            if (isSpeak || isListen || isThink) {
              const waveP = (t * (isSpeak ? 1.15 : isListen ? 1.35 : 0.85)) % 1;
              const waveR = 12 + waveP * 25;
              const waveAlpha = (1 - waveP) * 0.45;
              ctx.strokeStyle = `rgba(${coreHue}, ${waveAlpha.toFixed(2)})`;
              ctx.lineWidth = 1.6 * (1 - waveP * 0.6);
              ctx.beginPath();
              ctx.arc(cx, cy, waveR, 0, Math.PI * 2);
              ctx.stroke();
            }

            // Projection 3D des neurones en orbite libre
            const pts = nodes.map((n) => {
              const a = n.theta + t * n.speed * speedMul;
              const b = n.phi + Math.sin(t * 0.7 + n.phase) * 0.24;
              const rad = n.r * pulse;
              const x3 = rad * Math.sin(b) * Math.cos(a);
              const y3 = rad * Math.cos(b);
              const z3 = rad * Math.sin(b) * Math.sin(a);
              const scale = (z3 + 46) / 64;
              return { x: cx + x3, y: cy + y3, z: z3, s: scale, p: n.phase };
            });

            // Filaments synaptiques chaleureux (lisibles sur fond clair et foncé)
            ctx.lineWidth = isSpeak ? 1.35 : 1.05;
            for (let i = 0; i < pts.length; i++) {
              for (let j = i + 1; j < pts.length; j++) {
                const dx = pts[i].x - pts[j].x;
                const dy = pts[i].y - pts[j].y;
                const dist = Math.hypot(dx, dy);
                const maxD = isSpeak ? 30 : 26;
                if (dist < maxD) {
                  const alpha = (1 - dist / maxD) * (isSpeak ? 0.88 : isThink ? 0.76 : 0.62);
                  ctx.strokeStyle = `rgba(${i % 2 === 0 ? coreHue : warmHue}, ${alpha.toFixed(2)})`;
                  ctx.beginPath();
                  ctx.moveTo(pts[i].x, pts[i].y);
                  ctx.lineTo(pts[j].x, pts[j].y);
                  ctx.stroke();
                }
              }
            }

            // Neurones lumineux à cœur crème + halo doré
            pts.sort((a, b) => a.z - b.z);
            for (const p of pts) {
              const glow = 0.55 + 0.45 * Math.sin(t * (isSpeak ? 8.5 : 3.2) + p.p);
              const rNode = (1.7 + p.s * 1.55) * (isSpeak ? 1.12 : 1);
              ctx.fillStyle = `rgba(${coreHue}, ${(0.38 + glow * 0.35).toFixed(2)})`;
              ctx.beginPath();
              ctx.arc(p.x, p.y, rNode * 1.65, 0, Math.PI * 2);
              ctx.fill();
              ctx.fillStyle = `rgba(255, 248, 220, ${(0.72 + glow * 0.28).toFixed(2)})`;
              ctx.beginPath();
              ctx.arc(p.x, p.y, rNode * 0.85, 0, Math.PI * 2);
              ctx.fill();
            }

            orbRaf = requestAnimationFrame(drawOrb);
          };
          orbRaf = requestAnimationFrame(drawOrb);
        }

        bubbleEl.__nkapTap = onTap || (() => {});
        bubbleEl.addEventListener("click", () => {
          bubbleEl.style.transform = "scale(0.9)";
          setTimeout(() => (bubbleEl.style.transform = ""), 150);
          if (global.NKAP_ASSISTANT && global.NKAP_ASSISTANT.togglePanel) {
            global.NKAP_ASSISTANT.togglePanel(panelEl);
          } else {
            bubbleEl.__nkapTap();
          }
        });
        document.documentElement.appendChild(bubbleEl);
        return bubbleEl;
      },

      setOrbState,

      destroy() {
        if (orbRaf) { cancelAnimationFrame(orbRaf); orbRaf = null; }
        api.clear();
        window.removeEventListener("scroll", repositionAll, true);
        window.removeEventListener("resize", repositionAll);
        [hostEl, capLayer, bubbleEl, panelEl].forEach((el) => el && el.remove());
        hostEl = svg = capLayer = cursorEl = statusPillEl = bubbleEl = panelEl = null;
      },
    };

    return api;
  }

  NS.svgRenderer = { createSVGRenderer };
})(typeof window !== "undefined" ? window : globalThis);
