// In-page WCAG 2.2 AA audit for the HUNTX dashboard.
//
// This function is passed straight to page.evaluate(), so it must be fully
// self-contained: no closure over module scope, no imports, only what the
// browser provides. It returns { findings, checked }.
//
// Checks: 1.1.1 non-text content, 1.3.1 heading hierarchy, 1.4.3 text
// contrast, 1.4.10 reflow, 1.4.11 non-text contrast, 2.4.7 focus visible,
// 2.5.8 target size, 3.3.2 labels, 4.1.1 duplicate ids, 4.1.2 name/role/value.
//
// Two deliberate interpretations, both grounded in the W3C understanding
// documents:
//
//  * 1.4.11 does NOT require a boundary on a control that already shows a
//    visible text label or an icon glyph meeting 3:1 -- the text is then
//    assessed under 1.4.3. A boundary, fill or glyph only needs 3:1 where it
//    is the sole way to identify the control.
//  * Text sitting on a gradient is measured against every stop of that
//    gradient, taking the least-contrasting area, which is the prescribed way
//    to test a multi-colour surface.
export function wcagAuditInPage() {
  const findings = [];
  const seen = new Set();
  const stats = { text: 0, controls: 0, headings: 0 };

  // Thousands of descendants share the same ancestors: memoising the
  // per-element background resolution turns a computed-style walk per text
  // node into one per element, which is what makes a 1k-card tab auditable.
  const bgCandidateMemo = new WeakMap();
  const bgEffectiveMemo = new WeakMap();
  const add = (level, criterion, el, message) => {
    const selector = describe(el);
    const key = level + "|" + criterion + "|" + selector + "|" + message;
    if (seen.has(key)) return;
    seen.add(key);
    findings.push({ level, criterion, selector, message });
  };
  const describe = (el) => {
    if (!el || !el.tagName) return "<root>";
    const parts = [el.tagName.toLowerCase()];
    if (el.id) parts.push("#" + el.id);
    const cls = (el.getAttribute && el.getAttribute("class")) || "";
    if (cls) parts.push("." + cls.trim().split(/\s+/).slice(0, 3).join("."));
    const text = (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 40);
    return parts.join("") + (text ? " [" + text + "]" : "");
  };
  const isVisible = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || cs.opacity === "0") return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 || r.height > 0;
  };
  const parseRGBA = (str) => {
    if (!str) return null;
    const m = /^rgba?\(\s*(\d+)[ ,]+(\d+)[ ,]+(\d+)(?:[ ,]+([\d.]+))?\)$/.exec(str.replace(/\s/g, ""));
    if (!m) return null;
    return [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]];
  };
  const blend = (top, bottom) => {
    const a = top[3];
    return [top[0] * a + bottom[0] * (1 - a), top[1] * a + bottom[1] * (1 - a), top[2] * a + bottom[2] * (1 - a), 1];
  };
  const effectiveBackground = (el) => {
    const hit = bgEffectiveMemo.get(el);
    if (hit) return hit;
    const chain = [];
    let node = el;
    while (node && node.nodeType === 1) {
      const bg = parseRGBA(getComputedStyle(node).backgroundColor);
      if (bg) chain.unshift(bg);
      node = node.parentElement;
    }
    let acc = chain[0] || [255, 255, 255, 1];
    for (let i = 1; i < chain.length; i++) acc = blend(chain[i], acc);
    bgEffectiveMemo.set(el, acc);
    return acc;
  };
  // Gradient stops are real backgrounds. Chromium serializes computed
  // gradients as comma-separated rgb()/rgba() stops.
  const parseGradient = (img) => {
    if (!img || img === "none") return [];
    const out = [];
    const re = /rgba?\(\s*\d[^)]*\)/g;
    let m;
    while ((m = re.exec(img))) {
      const c = parseRGBA(m[0]);
      if (c) out.push(c);
    }
    return out;
  };
  // Text sits on the NEAREST ancestor (or self) that actually paints a
  // background -- a solid or a gradient; anything beyond that first painter is
  // hidden behind it. A translucent layer is blended over what shows through.
  const backgroundCandidates = (el) => {
    const cached = bgCandidateMemo.get(el);
    if (cached) return cached;
    let node = el;
    while (node && node.nodeType === 1) {
      const cs = getComputedStyle(node);
      const solid = parseRGBA(cs.backgroundColor);
      const grads = parseGradient(cs.backgroundImage);
      const hasSolid = !!(solid && solid[3] !== 0);
      if (hasSolid || grads.length) {
        const behind = effectiveBackground(node.parentElement || document.body);
        const out = [];
        for (const g of grads) out.push(g[3] < 1 ? blend(g, behind) : g);
        if (hasSolid) out.push(solid[3] < 1 ? blend(solid, behind) : solid);
        bgCandidateMemo.set(el, out);
        return out;
      }
      node = node.parentElement;
    }
    const fallback = [effectiveBackground(el)];
    bgCandidateMemo.set(el, fallback);
    return fallback;
  };
  const srgbLin = (c) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  };
  const luminance = (rgb) => 0.2126 * srgbLin(rgb[0]) + 0.7152 * srgbLin(rgb[1]) + 0.0722 * srgbLin(rgb[2]);
  const contrastRatio = (a, b) => {
    const la = luminance(a), lb = luminance(b);
    const hi = Math.max(la, lb), lo = Math.min(la, lb);
    return (hi + 0.05) / (lo + 0.05);
  };
  const accessibleName = (el) =>
    (el.getAttribute && (el.getAttribute("aria-label") || el.getAttribute("aria-labelledby") || el.getAttribute("title"))) ||
    (el.textContent || "").trim();

  const INTERACTIVE = 'a[href], button:not([disabled]), input, select, textarea, [role="button"], [role="tab"], [role="link"], summary, [tabindex]';

  // ---- 1.3.1 / 4.1.2 names and roles -------------------------------------
  for (const el of document.querySelectorAll(INTERACTIVE)) {
    if (!isVisible(el)) continue;
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (tag === "input" && (type === "hidden" || type === "submit" || type === "button")) continue;
    if (!accessibleName(el)) add("serious", "4.1.2 Name, Role, Value", el, "interactive element has no accessible name");
  }
  for (const el of document.querySelectorAll("img, canvas")) {
    if (!isVisible(el)) continue;
    if (!accessibleName(el) && !el.getAttribute("role")) add("serious", "1.1.1 Non-text Content", el, "no alt / aria-label / role");
  }
  for (const el of document.querySelectorAll("input, select, textarea")) {
    if (!isVisible(el)) continue;
    const id = el.getAttribute("id");
    const labelled = el.getAttribute("aria-label") || el.getAttribute("aria-labelledby") ||
      (id && document.querySelector('label[for="' + CSS.escape(id) + '"]')) ||
      (el.closest("label") && el.closest("label").textContent.trim());
    if (!labelled) add("serious", "3.3.2 Labels or Instructions", el, "form control without an associated label");
    else if (el.getAttribute("placeholder") && !(el.getAttribute("aria-label") || el.getAttribute("aria-labelledby")))
      add("moderate", "3.3.2 Labels or Instructions", el, "placeholder is the only visible label text");
  }

  // ---- 1.3.1 heading hierarchy ------------------------------------------
  const headings = [...document.querySelectorAll("h1,h2,h3,h4,h5,h6")].filter(isVisible);
  stats.headings = headings.length;
  let lastLevel = 0;
  for (const h of headings) {
    const lvl = +h.tagName[1];
    if (lastLevel && lvl > lastLevel + 1) add("moderate", "1.3.1 Info and Relationships", h, "heading level skips from h" + lastLevel + " to h" + lvl);
    lastLevel = Math.max(lastLevel, lvl);
  }
  if (!document.querySelector("h1")) add("serious", "1.3.1 / 2.4.6 Headings", document.body, "no h1 on the page");

  // ---- 1.4.3 text contrast ---------------------------------------------
  const textEls = [...document.querySelectorAll("body *")].filter((el) => {
    if (!isVisible(el) || /^(script|style|svg|path|circle|rect|line)$/.test(el.tagName.toLowerCase())) return false;
    return [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
  });
  stats.text = textEls.length;
  for (const el of textEls) {
    const cs = getComputedStyle(el);
    const fg = parseRGBA(cs.color);
    if (!fg) continue;
    const cands = backgroundCandidates(el);
    let bg = cands[0];
    let ratio = contrastRatio(fg, bg);
    for (const b of cands) {
      const r = contrastRatio(fg, b);
      if (r < ratio) { ratio = r; bg = b; }
    }
    const size = parseFloat(cs.fontSize);
    const bold = parseInt(cs.fontWeight, 10) >= 700;
    const large = size >= 24 || (bold && size >= 18.66);
    const threshold = large ? 3.0 : 4.5;
    if (ratio < threshold) {
      add("serious", "1.4.3 Contrast (Minimum)", el,
        ratio.toFixed(2) + ":1 " + cs.color + " on rgb(" + bg.map((v) => Math.round(v)).join(",") + ") " +
        size.toFixed(1) + "px" + (bold ? " bold" : "") + " (needs " + threshold + ":1)");
    }
  }

  // ---- 1.4.11 non-text contrast ----------------------------------------
  // A control that shows a visible text label, placeholder, or option is
  // already identifiable and needs no boundary. Otherwise one of its border,
  // fill or icon glyph must contrast >= 3:1 against the adjacent background.
  const identifyingText = (el) => {
    if ((el.textContent || "").replace(/\s+/g, "")) return true;
    if (el.placeholder || el.value) return true;
    if (el.tagName === "SELECT" && el.options && el.options.length) return true;
    return false;
  };
  const controls = [...document.querySelectorAll("button, input, select, textarea, [role='tab'], a[href]")].filter(isVisible);
  stats.controls = controls.length;
  for (const el of controls) {
    if (identifyingText(el)) continue;
    const cs = getComputedStyle(el);
    const parentBg = effectiveBackground(el.parentElement || document.body);
    const border = parseRGBA(cs.borderTopColor);
    const fill = parseRGBA(cs.backgroundColor);
    const hasBorder = !!(border && border[3] !== 0 && cs.borderTopWidth !== "0px" && cs.borderTopStyle !== "none");
    const borderOK = hasBorder && contrastRatio(border, parentBg) >= 3.0;
    const fillOK = !!(fill && fill[3] !== 0) && contrastRatio(fill, parentBg) >= 3.0;
    // Icon glyphs inherit currentColor, but may carry their own color class.
    const glyphColors = [parseRGBA(cs.color)];
    for (const svg of el.querySelectorAll("svg")) {
      const sc = parseRGBA(getComputedStyle(svg).color);
      if (sc) glyphColors.push(sc);
    }
    const glyphOK = glyphColors.some((c) => c && contrastRatio(c, parentBg) >= 3.0);
    if (!(borderOK || fillOK || glyphOK)) {
      const bRatio = hasBorder ? contrastRatio(border, parentBg).toFixed(2) : "none";
      const fRatio = fill && fill[3] !== 0 ? contrastRatio(fill, parentBg).toFixed(2) : "none";
      const g = glyphColors.find((c) => c);
      const gRatio = g ? contrastRatio(g, parentBg).toFixed(2) : "none";
      add("serious", "1.4.11 Non-text Contrast", el, "no identifying label and no 3:1 indicator: border " + bRatio + ":1, fill " + fRatio + ":1, glyph " + gRatio + ":1 (needs 3:1)");
    }
  }

  // ---- 2.4.7 focus visible ---------------------------------------------
  for (const el of document.querySelectorAll(INTERACTIVE)) {
    if (!isVisible(el)) continue;
    el.focus({ preventScroll: true });
    const cs = getComputedStyle(el);
    if ((cs.outlineWidth === "0px" || cs.outlineStyle === "none") && cs.boxShadow === "none") {
      add("serious", "2.4.7 Focus Visible", el, "no outline or box-shadow when focused");
    } else if (cs.outlineStyle !== "none" && cs.outlineWidth !== "0px" && cs.outlineColor === "rgba(0, 0, 0, 0)") {
      add("serious", "2.4.7 Focus Visible", el, "focused outline is transparent");
    }
    el.blur();
  }

  // ---- 2.5.8 target size (minimum, AA in 2.2) ---------------------------
  for (const el of document.querySelectorAll(INTERACTIVE)) {
    if (!isVisible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0) continue;
    if (r.width < 24 || r.height < 24) {
      add("moderate", "2.5.8 Target Size (Minimum)", el, "target " + Math.round(r.width) + "x" + Math.round(r.height) + "px (needs 24x24)");
    }
  }

  // ---- 4.1.1 duplicate ids (breaks aria references) --------------------
  const ids = new Map();
  for (const el of document.querySelectorAll("[id]")) {
    const id = el.getAttribute("id");
    ids.set(id, (ids.get(id) || 0) + 1);
  }
  for (const [id, n] of ids) if (n > 1) add("moderate", "4.1.1 Parsing (duplicate id)", document.body, 'id "' + id + '" used ' + n + " times");

  // ---- 1.4.10 reflow ----------------------------------------------------
  const vw = window.innerWidth;
  if (document.documentElement.scrollWidth > vw + 1) {
    add("serious", "1.4.10 Reflow", document.documentElement, "page scrollWidth " + document.documentElement.scrollWidth + "px > viewport " + vw + "px");
  }

  // ---- 4.1.2 aria reference / state sanity -----------------------------
  for (const el of document.querySelectorAll("[aria-expanded]")) {
    if (!isVisible(el)) continue;
    const expanded = el.getAttribute("aria-expanded");
    if (expanded !== "true" && expanded !== "false") add("moderate", "4.1.2 Name, Role, Value", el, "aria-expanded is neither true nor false");
  }
  for (const el of document.querySelectorAll("[aria-labelledby]")) {
    if (!document.getElementById(el.getAttribute("aria-labelledby"))) add("moderate", "4.1.2 Name, Role, Value", el, "aria-labelledby points at nothing");
  }
  for (const el of document.querySelectorAll("[aria-controls]")) {
    if (!document.getElementById(el.getAttribute("aria-controls"))) add("moderate", "4.1.2 Name, Role, Value", el, "aria-controls points at nothing");
  }

  return {
    findings: findings.map((f) => ({
      ...f,
      tab: (location.hash || "#radar"),
      theme: document.documentElement.className,
      viewport: vw
    })),
    checked: stats
  };
}
