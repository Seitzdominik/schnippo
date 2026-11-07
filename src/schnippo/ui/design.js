// Design setup view of the shared card (MCP App): style → font → colours → radius → final preview over a real frame.
// Live previews are the renderer's own HTML templates (server tool design_preview, autoplay), shown in srcdoc iframes.
(() => {
  const C = window.__card;
  const { h, show, callTool, sendChat } = C;
  const css = document.createElement("style");
  css.textContent = `
    .steps{display:flex;gap:6px;margin:4px 0 12px}.steps span{flex:1;height:4px;border-radius:2px;background:var(--color-background-tertiary)}
    .steps span.on{background:var(--color-text-primary);opacity:.7}
    .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px}
    .opt{padding:8px;border-radius:var(--border-radius-md);display:grid;gap:6px;text-align:left}
    .opt[aria-pressed="true"]{outline:2px solid var(--color-ring-primary);outline-offset:-1px;background:var(--color-background-tertiary)}
    .pv{position:relative;width:100%;aspect-ratio:9/16;border-radius:6px;overflow:hidden;background:#6f655c center/cover no-repeat}
    .pv iframe{position:absolute;left:0;top:0;width:540px;height:960px;border:0;transform-origin:0 0;pointer-events:none;background:transparent}
    .row{display:flex;align-items:center;gap:10px;margin:8px 0;flex-wrap:wrap}
    .row label{min-width:120px;font-size:var(--font-text-sm-size)}
    input[type=text]{font:inherit;font-size:var(--font-text-sm-size);padding:6px 8px;border-radius:6px;border:1px solid var(--color-border-primary);
      background:var(--color-background-primary);color:var(--color-text-primary);width:110px}
    input[type=color]{width:38px;height:30px;border:1px solid var(--color-border-primary);border-radius:6px;padding:0;background:none}
    .big{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
    .warn{color:var(--color-text-warning)}.okc{color:var(--color-text-success)}`;
  document.head.append(css);

  const STEP_NAMES = ["Stil", "Schrift", "Farben", "Radius", "Vorschau"];
  let d, step, prof, name;

  function preview(htmlStr, frame) {
    const box = h("div", { class: "pv", style: frame ? `background-image:url(${frame})` : "" });
    const f = h("iframe", { title: "Vorschau" });
    f.srcdoc = htmlStr || "";
    box.append(f);
    new ResizeObserver(() => { f.style.transform = `scale(${box.clientWidth / 540})`; }).observe(box);
    return box;
  }
  async function previews(profile, templates) {
    try {
      const r = await callTool("design_preview", { profile, templates });
      return (r && r.structuredContent && r.structuredContent.html) || {};
    } catch (e) { return {}; }
  }

  // WCAG contrast (alpha of rgba ignored = scrim assumed opaque, like the server)
  function rgb(c) {
    c = String(c).trim();
    if (c.startsWith("rgb")) return c.slice(c.indexOf("(") + 1, c.indexOf(")")).split(",").slice(0, 3).map(Number);
    c = c.replace("#", ""); if (c.length === 3) c = [...c].map((x) => x + x).join("");
    return [0, 2, 4].map((i) => parseInt(c.slice(i, i + 2), 16));
  }
  const lum = (c) => { const v = rgb(c).map((x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const hex = (v) => "#" + v.map((x) => Math.max(0, Math.min(255, Math.round(x))).toString(16).padStart(2, "0")).join("");
  function surfaceAndText() {
    const st = d.styles.find((s) => s.id === prof.style) || {};
    const mode = st.surface_mode || "dark";
    const bg = mode === "light" ? prof.surface_light : mode === "accent" ? prof.accent : prof.surface;
    const fg = mode === "light" ? prof.text_dark : prof.text;
    return { mode, bg, fg };
  }
  function fixAccent() {  // darken (or lighten) the accent until white/dark text reaches the minimum
    const { fg } = surfaceAndText();
    let c = rgb(prof.accent), k = 0;
    const darker = lum(fg) > 0.5;
    while (ratio(fg, hex(c)) < d.min_contrast && k++ < 40) c = c.map((x) => darker ? x * 0.92 : x + (255 - x) * 0.12);
    return hex(c);
  }

  function nav(canNext = true) {
    const back = h("button", { onclick: () => { step = Math.max(0, step - 1); draw(); }, disabled: step === 0 }, "Zurück");
    const next = step < STEP_NAMES.length - 1
      ? h("button", { class: "primary", disabled: !canNext, onclick: () => { step++; draw(); } }, "Weiter")
      : h("button", { class: "primary", onclick: save }, "Übernehmen");
    return h("footer", {}, h("span", { class: "muted" }, `Schritt ${step + 1} von ${STEP_NAMES.length}: ${STEP_NAMES[step]}`),
      h("span", { style: "display:flex;gap:8px" }, back, next));
  }
  const head = () => [h("header", {}, h("h1", {}, "Design für Grafiken"), h("span", { class: "pill" }, name)),
    h("div", { class: "steps" }, STEP_NAMES.map((_, i) => h("span", { class: i <= step ? "on" : "" })))];

  async function draw() {
    if (step === 0) {
      const grid = h("div", { class: "grid" });
      show(...head(), h("p", { class: "sub" }, "Designsprache wählen – Regeln (Bewegung, Kontrast, sichere Zone) gelten immer."), grid, nav());
      for (const st of d.styles) {
        const p = { ...prof, ...st.brand, style: st.id };
        const card = h("button", { class: "opt", "aria-pressed": String(prof.style === st.id), onclick: () => {
          prof = { ...prof, ...st.brand, style: st.id };
          for (const b of grid.children) b.setAttribute("aria-pressed", String(b === card));
        } }, h("span", { class: "pv" }), h("b", {}, st.label));
        grid.append(card);
        previews(p, ["callout"]).then((hs) => card.replaceChild(preview(hs.callout, d.frame), card.firstChild));
      }
    } else if (step === 1) {
      const pv = h("div", { style: "width:200px" }, h("div", { class: "pv" }));
      const list = h("div", { class: "grid" }, d.fonts.map((f) => h("button", { class: "opt", "aria-pressed": String(prof.font_family === f),
        onclick: (e) => { prof.font_family = f; for (const b of list.children) b.setAttribute("aria-pressed", String(b === e.currentTarget)); upd(); } },
        h("span", { style: "font-weight:600" }, f))));
      const own = h("input", { type: "text", placeholder: "Pfad zu TTF/OTF/WOFF2", style: "width:260px" });
      own.addEventListener("change", () => { if (own.value.trim()) { prof.font_family = own.value.trim(); upd(); } });
      async function upd() { const hs = await previews(prof, ["hook_text"]); pv.replaceChildren(preview(hs.hook_text, d.frame)); }
      show(...head(), h("p", { class: "sub" }, "Schrift (mitgelieferte OFL-Schriften, max. 2 Schnitte) oder eigene Datei."), list,
        h("div", { class: "row" }, h("label", {}, "Eigene Schrift"), own, h("span", { class: "muted" }, "Lizenz liegt bei dir")),
        h("div", { class: "row" }, pv), nav());
      upd();
    } else if (step === 2) {
      const info = h("div", { class: "row" });
      const pv = h("div", { style: "width:200px" }, h("div", { class: "pv" }));
      const field = (key, label) => {
        const col = h("input", { type: "color", value: prof[key].startsWith("#") ? prof[key].slice(0, 7) : "#111111" });
        const txt = h("input", { type: "text", value: prof[key] });
        col.addEventListener("input", () => { prof[key] = col.value.toUpperCase(); txt.value = prof[key]; check(); });
        txt.addEventListener("change", () => { prof[key] = txt.value.trim(); check(); });
        return h("div", { class: "row" }, h("label", {}, label), col, txt);
      };
      let timer;
      const msg = h("span");
      // persistent button: a rebuilt row would swallow the click (the colour field's change fires on mousedown first)
      const fixBtn = h("button", { class: "hidden", onclick: () => { prof.accent = fixAccent(); draw(); } }, "Vorschlag übernehmen");
      info.append(msg, fixBtn);
      function check() {
        const { bg, fg, mode } = surfaceAndText();
        const r = ratio(fg, bg.startsWith("rgba") ? hex(rgb(bg)) : bg);
        msg.className = r >= d.min_contrast ? "okc" : "warn";
        msg.textContent = `Kontrast Text/Fläche ${r.toFixed(1)}:1 ${r >= d.min_contrast ? "✓" : "– unter " + d.min_contrast + ":1"}`;
        fixBtn.classList.toggle("hidden", !(mode === "accent" && r < d.min_contrast));
        clearTimeout(timer);
        timer = setTimeout(async () => { const hs = await previews(prof, ["callout"]); pv.replaceChildren(preview(hs.callout, d.frame)); }, 350);
      }
      show(...head(), h("p", { class: "sub" }, "Eine Akzentfarbe plus Neutraltöne. Kontrast mindestens 4,5:1."),
        field("accent", "Akzent"), field("text", "Text hell"), field("text_dark", "Text dunkel"), field("surface", "Fläche (Scrim)"),
        info, h("p", { class: "muted" }, "Tipp: Nenne Claude im Chat deine Website – Claude schlägt Farben und Schrift vor und füllt das hier vor."),
        h("div", { class: "row" }, pv), nav());
      check();
    } else if (step === 3) {
      const grid = h("div", { class: "grid" });
      show(...head(), h("p", { class: "sub" }, "Ein Eckenradius für alle Boxen."), grid, nav());
      for (const r of d.radii) {
        const p = { ...prof, radius_px: r };
        const card = h("button", { class: "opt", "aria-pressed": String(+prof.radius_px === r), onclick: () => {
          prof.radius_px = r; for (const b of grid.children) b.setAttribute("aria-pressed", String(b === card)); } },
          h("span", { class: "pv" }), h("b", {}, r === 999 ? "Pille" : r + " px"));
        grid.append(card);
        previews(p, ["callout"]).then((hs) => card.replaceChild(preview(hs.callout, d.frame), card.firstChild));
      }
    } else {
      const big = h("div", { class: "big" }, [h("div", { class: "pv" }), h("div", { class: "pv" }), h("div", { class: "pv" })]);
      const nm = h("input", { type: "text", value: name, style: "width:180px" });
      nm.addEventListener("change", () => { name = nm.value.trim() || "Standard"; });
      show(...head(), h("p", { class: "sub" }, "So sieht es über deinem Video aus (Frame aus dem aktuellen Projekt)."), big,
        h("div", { class: "row" }, h("label", {}, "Name der Marke"), nm, h("span", { class: "muted" }, "mehrere Marken möglich, z. B. pro Kunde")),
        h("p", { class: "muted", id: "st" }), nav());
      const hs = await previews(prof, ["hook_text", "callout", "counter"]);
      ["hook_text", "callout", "counter"].forEach((t, i) => big.replaceChild(preview(hs[t], d.frame), big.children[i]));
    }
  }

  async function save() {
    const st = document.getElementById("st");
    try {
      const r = await callTool("save_brand", { name, profile: prof });
      const txt = (r && r.content && r.content[0] && r.content[0].text) || "gespeichert";
      if (st) st.textContent = txt;
      try { await sendChat(`Design „${name}“ übernommen (${(d.styles.find((s) => s.id === prof.style) || {}).label || prof.style}, ${prof.font_family}, Akzent ${prof.accent}, Radius ${prof.radius_px === 999 ? "Pille" : prof.radius_px + " px"}).`); }
      catch (e) { if (st) st.textContent += " – schreibe im Chat „weiter“."; }
    } catch (e) { if (st) st.textContent = "Speichern fehlgeschlagen: " + (e.message || e); }
  }

  window.renderDesign = (data) => { d = data; step = 0; prof = { ...data.current }; name = data.profile_name || "Standard"; draw(); };
})();
