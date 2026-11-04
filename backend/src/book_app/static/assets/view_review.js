import { steps } from "./steps.js";
import { badge, clear, del, errBox, get, h, post, spinner, toast, when } from "./util.js";

const KIND = {
  alt_text: "Picture description", figure: "Figure", table: "Table", heading: "Heading", caption: "Caption",
  join: "Text break", structure: "Structure", character: "Character", author: "Author", index: "Index", settings: "Book setting",
};
const kindName = (k) => KIND[k] || k;

export async function reviewView({ app, id, params, onLeave }) {
  const job = await get(`/api/jobs/${id}`);
  app.append(h("h1", {}, job.name), steps(job, "review"));
  if (job.state !== "converted") { app.append(h("div", { class: "banner warn" }, "Convert the book first.")); return; }
  const S = {
    items: [], total: 0, decided: 0, idx: 0, mode: params.get("mode") === "browse" ? "browse" : "queue",
    kind: "", pageFilter: "", status: "open", page: +params.get("page") || 1, zoom: 1, hl: null, pages: [],
    who: localStorage.getItem("reviewer") || "", edits: [], stale: false, selected: new Set(),
  };
  const wait = h("div", { class: "panel" }, spinner("Preparing the review list… (a long book can take half a minute)"));
  app.append(wait);
  const [pagesInfo] = await Promise.all([get(`/api/jobs/${id}/pages`), load()]);
  S.pages = pagesInfo.pages;
  wait.remove();

  async function load(refresh = false) {
    const d = refresh ? await post(`/api/jobs/${id}/review/refresh`) : await get(`/api/jobs/${id}/review`);
    Object.assign(S, { items: d.items, total: d.total, decided: d.decided, stale: d.stale, placeholders: d.alt_text_placeholders, failed: d.failed_edits });
    const dec = await get(`/api/jobs/${id}/decisions`);
    S.edits = dec.edits;
  }

  // ------------------------------------------------------------------ layout
  const whoInput = h("input", { type: "text", value: S.who, placeholder: "Your name", "aria-label": "Your name", dataset: { testid: "who" },
    oninput: () => { S.who = whoInput.value.trim(); localStorage.setItem("reviewer", S.who); } });
  const progText = h("span", { dataset: { testid: "progress" } });
  const progBar = h("div", { style: "width:0" });
  const kindSel = h("select", { "aria-label": "Filter by kind", dataset: { testid: "filter-kind" }, onchange: () => { S.kind = kindSel.value; S.idx = 0; paintRight(); } });
  const pageFilter = h("input", { type: "number", min: "1", placeholder: "page", "aria-label": "Filter by page", style: "width:80px", dataset: { testid: "filter-page" },
    oninput: () => { S.pageFilter = pageFilter.value; S.idx = 0; paintRight(); } });
  const statusSel = h("select", { "aria-label": "Show", dataset: { testid: "filter-status" }, onchange: () => { S.status = statusSel.value; S.idx = 0; paintRight(); } },
    h("option", { value: "open" }, "Open items"), h("option", { value: "all" }, "All items"), h("option", { value: "done" }, "Decided items"));
  const modeQueue = h("button", { dataset: { testid: "mode-queue" }, onclick: () => setMode("queue") }, "Flagged items");
  const modeBrowse = h("button", { dataset: { testid: "mode-browse" }, onclick: () => setMode("browse") }, "Browse pages");
  const staleBanner = h("div", { class: "banner warn", hidden: true, dataset: { testid: "stale" } }, "You made changes since this list was prepared. ",
    h("button", { class: "small", onclick: refreshList }, "Refresh the list"), " (takes up to half a minute)");
  const bar = h("div", { class: "panel" },
    h("div", { class: "row" }, h("label", {}, "Reviewer ", whoInput), h("div", { class: "grow" }), progText, h("div", { class: "bar", style: "width:160px" }, progBar),
      h("div", { class: "row" }, modeQueue, modeBrowse)),
    h("div", { class: "row", style: "margin-top:8px" }, kindSel, pageFilter, statusSel,
      h("a", { class: "btn primary", href: `#/job/${id}/export`, dataset: { testid: "to-export" } }, "Continue to export")));
  const img = h("img", { alt: "PDF page", dataset: { testid: "page-image" } });
  const hl = h("div", { class: "hl", hidden: true, dataset: { testid: "highlight" } });
  const wrap = h("div", { class: "pagewrap" }, img, hl);
  const pageNo = h("input", { type: "number", min: "1", max: String(S.pages.length), style: "width:70px", "aria-label": "Page number", dataset: { testid: "page-no" }, onchange: () => goPage(+pageNo.value) });
  const pageLabel = h("span", { class: "muted small" });
  const tools = h("div", { class: "pdftools" },
    h("button", { dataset: { testid: "prev-page" }, onclick: () => goPage(S.page - 1) }, "◀ Previous page"), pageNo, pageLabel,
    h("button", { dataset: { testid: "next-page" }, onclick: () => goPage(S.page + 1) }, "Next page ▶"),
    h("button", { "aria-label": "Zoom out", dataset: { testid: "zoom-out" }, onclick: () => zoom(-0.2) }, "−"),
    h("button", { "aria-label": "Zoom in", dataset: { testid: "zoom-in" }, onclick: () => zoom(0.2) }, "+"));
  const left = h("div", { class: "pdfpane" }, tools, wrap);
  const right = h("div", { dataset: { testid: "right-pane" } });
  app.append(bar, staleBanner, h("div", { class: "split" }, left, right), historyPanel());
  const histBox = app.querySelector("[data-testid=history]");

  function zoom(d) { S.zoom = Math.min(2.4, Math.max(0.4, +(S.zoom + d).toFixed(1))); paintPage(); }
  function goPage(n) {
    n = Math.max(1, Math.min(S.pages.length, n || 1));
    S.page = n; S.hl = null;
    if (S.mode === "browse") paintRight();
    paintPage();
  }
  function paintPage() {
    const p = S.pages[S.page - 1];
    const scale = S.zoom <= 1.2 ? 2 : 3;
    const w = p.width * S.zoom, hh = p.height * S.zoom;
    img.style.width = `${w}px`; img.style.height = `${hh}px`;
    img.src = `/api/jobs/${id}/pages/${S.page}/image?scale=${scale}`;
    pageNo.value = S.page; pageLabel.textContent = `of ${S.pages.length}` + (p.label ? ` (printed ${p.label})` : "");
    const b = S.hl;
    if (b && b.page === S.page) {
      hl.hidden = false;
      Object.assign(hl.style, { left: `${b.x0 * S.zoom}px`, top: `${b.y0 * S.zoom}px`, width: `${(b.x1 - b.x0) * S.zoom}px`, height: `${(b.y1 - b.y0) * S.zoom}px` });
      hl.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    } else hl.hidden = true;
  }
  async function setMode(m) {
    S.mode = m; paintRight();
    if (m === "browse") { const item = visible()[S.idx]; if (item?.page) S.page = item.page; paintPage(); }
  }
  async function refreshList() {
    staleBanner.hidden = true;
    right.replaceChildren(spinner("Preparing the review list…"));
    await load(true); paintRight();
  }

  // ------------------------------------------------------------------ queue
  function visible() {
    return S.items.filter((i) => (!S.kind || i.kind === S.kind) && (!S.pageFilter || String(i.page) === S.pageFilter)
      && (S.status === "all" || (S.status === "open" ? !i.decision : !!i.decision)));
  }
  function paintHeader() {
    const kinds = [...new Set(S.items.map((i) => i.kind))].sort();
    const cur = kindSel.value;
    clear(kindSel).append(h("option", { value: "" }, "All kinds"), ...kinds.map((k) => h("option", { value: k, selected: k === cur }, kindName(k))));
    progText.textContent = `${S.decided} of ${S.total} decided`;
    progBar.style.width = S.total ? `${(100 * S.decided) / S.total}%` : "0";
    modeQueue.className = S.mode === "queue" ? "primary" : ""; modeBrowse.className = S.mode === "browse" ? "primary" : "";
    staleBanner.hidden = !S.stale;
  }
  function paintRight() {
    paintHeader();
    clear(right);
    if (S.mode === "browse") return paintBrowse();
    const list = visible();
    if (S.idx >= list.length) S.idx = Math.max(0, list.length - 1);
    const q = h("div", { class: "queue", dataset: { testid: "queue" } }, list.slice(0, 400).map((it, n) =>
      h("button", { class: `${n === S.idx ? "current" : ""} ${it.decision ? "done" : ""}`, dataset: { testid: "queue-item" }, onclick: () => { S.idx = n; paintRight(); } },
        it.severity === "must_check" ? h("b", {}, "must check") : "review", ` p.${it.page ?? "–"} `, kindName(it.kind), " ", h("span", { class: "muted" }, (it.reason || "").slice(0, 60)))));
    right.append(q);
    if (!list.length) { right.append(h("div", { class: "banner pass", dataset: { testid: "queue-empty" } }, S.total ? "Nothing open here. Change the filters or continue to export." : "Nothing flagged. You can browse pages to check the structure.")); return; }
    const item = list[S.idx];
    S.hl = item.box; if (item.page) S.page = item.page;
    right.append(card(item, list));
    paintPage();
  }

  function card(item, list) {
    const err = h("div"); const note = h("textarea", { placeholder: "Note (optional)", "aria-label": "Note", dataset: { testid: "note" }, style: "min-height:50px" }, item.decision?.note || "");
    const ed = editor(item);
    async function decide(action) {
      clear(err);
      if (!S.who) { whoInput.focus(); toast("Enter your name first."); return; }
      let fix = null;
      if (action === "fix") { fix = ed.getFix(); if (!fix) { err.append(errBox({ message: "Fill in the fix first." })); return; } }
      try {
        const snap = { severity: item.severity, kind: item.kind, page: item.page, page_label: item.page_label, unit: item.unit, reason: item.reason, source: item.source, editor: item.editor, box: item.box };
        await post(`/api/jobs/${id}/decisions`, { who: S.who, key: item.key, item_kind: item.kind, action, fix, note: note.value, item: snap });
        item.decision = { action, fix, note: note.value, who: S.who, at: new Date().toISOString() };
        S.decided = S.items.filter((i) => i.decision).length;
        if (fix?.op) S.stale = true;
        const dec = await get(`/api/jobs/${id}/decisions`); S.edits = dec.edits; paintHistory();
        const open = visible();
        if (S.status === "open") { S.idx = Math.min(S.idx, Math.max(0, open.length - 1)); } else S.idx = Math.min(S.idx + 1, list.length - 1);
        paintRight();
      } catch (e) { err.append(errBox(e)); }
    }
    const d = item.decision;
    return h("div", { class: "panel", dataset: { testid: "item-card", key: item.key } },
      h("div", { class: "row" }, h("span", { class: "kind" }, kindName(item.kind)), item.severity === "must_check" ? badge("fail", "must check") : badge("warn", "to review"),
        h("span", { class: "muted small" }, `page ${item.page ?? "–"}${item.page_label ? ` (printed ${item.page_label})` : ""} · ${item.source}`)),
      h("p", { dataset: { testid: "reason" } }, item.reason),
      item.current && h("div", { class: "unitrow" }, h("div", { class: "kind" }, "Our current result"),
        h("div", {}, item.current.type + (item.current.role ? ` · ${item.current.role}` : "") + (item.current.level ? ` · level ${item.current.level}` : "") + (item.current.decorative ? " · decorative" : "")),
        item.current.text && h("div", { class: "txt" }, item.current.text), item.current.alt_text && h("div", {}, h("b", {}, "Description: "), item.current.alt_text)),
      item.crop && h("img", { src: `/api/jobs/${id}/crops/${item.crop.split("/").pop()}`, alt: "Crop from the book", style: "max-width:100%;max-height:140px;border:1px solid var(--line);margin-bottom:8px" }),
      d && h("div", { class: "banner info small", dataset: { testid: "decided" } }, `Decided: ${d.action} by ${d.who}, ${when(d.at)}.`, d.note ? ` Note: ${d.note}` : ""),
      ed.el, note, err,
      h("div", { class: "row", style: "margin-top:10px" },
        h("button", { class: "primary", dataset: { testid: "accept" }, onclick: () => decide("accept") }, "Accept"),
        h("button", { dataset: { testid: "fix" }, onclick: () => decide("fix") }, "Fix"),
        h("button", { dataset: { testid: "skip" }, onclick: () => decide("skip") }, "Skip"),
        h("div", { class: "grow" }),
        h("button", { class: "small", dataset: { testid: "prev-item" }, onclick: () => { S.idx = Math.max(0, S.idx - 1); paintRight(); } }, "◀ Previous item"),
        h("button", { class: "small", dataset: { testid: "next-item" }, onclick: () => { S.idx = Math.min(list.length - 1, S.idx + 1); paintRight(); } }, "Next item ▶")));
  }

  // ------------------------------------------------------------------ editors by kind
  function editor(item) {
    const u = item.unit, cur = item.current || {};
    const radio = (name, opts, init) => {
      const els = opts.map(([val, label]) => { const r = h("input", { type: "radio", name, value: val, checked: val === init, dataset: { testid: `${name}-${val}` } }); return [r, h("label", { style: "margin-right:14px" }, r, " ", label)]; });
      return { el: h("div", { style: "margin:6px 0" }, els.map((e) => e[1])), value: () => els.find((e) => e[0].checked)?.[0].value };
    };
    switch (item.editor) {
      case "alt_text": {
        const mode = radio("alt", [["describe", "Describe the picture"], ["decorative", "It is decoration (no description)"]], cur.decorative ? "decorative" : "describe");
        const ta = h("textarea", { placeholder: "What does the picture show? Write it for a reader who cannot see it.", "aria-label": "Description", dataset: { testid: "alt-text" } }, cur.alt_text || "");
        return { el: h("div", {}, mode.el, ta), getFix: () => mode.value() === "decorative" ? { op: "decorative", unit: u, value: true } : (ta.value.trim() ? { op: "alt_text", unit: u, text: ta.value.trim() } : null) };
      }
      case "figure": {
        const mode = radio("fig", [["content", "A real figure (keep)"], ["decorative", "Decoration (leave out)"]], cur.decorative ? "decorative" : "content");
        return { el: mode.el, getFix: () => ({ op: "decorative", unit: u, value: mode.value() === "decorative" }) };
      }
      case "heading": {
        const sel = h("select", { "aria-label": "Heading level", dataset: { testid: "heading-level" } },
          h("option", { value: "none" }, "Not a heading"), [1, 2, 3, 4, 5].map((n) => h("option", { value: n, selected: cur.level === n && cur.type === "heading" }, `Heading, level ${n}`)), h("option", { value: "chapter" }, "Start of a new chapter"));
        return { el: h("label", { class: "field" }, h("span", {}, "What is it?"), sel), getFix: () => sel.value === "none" ? { op: "heading_remove", unit: u } : sel.value === "chapter" ? { op: "new_chapter", unit: u } : { op: "heading_set", unit: u, level: +sel.value } };
      }
      case "role": {
        const isHead = cur.type === "heading", isPara = cur.type === "paragraph";
        if (!isHead && !isPara) return { el: h("p", { class: "muted small" }, "Accept it if it is right, or skip it."), getFix: () => null };
        const sel = h("select", { "aria-label": "Role", dataset: { testid: "role-select" } }, h("option", { value: "" }, "— choose —"),
          isHead && h("option", { value: "body" }, "Body paragraph (not a heading)"), [1, 2, 3, 4].map((n) => h("option", { value: `h${n}` }, `Heading, level ${n}`)),
          h("option", { value: "chapter" }, "Start of a new chapter"), isPara && h("option", { value: "join" }, "Join with the next paragraph"));
        return { el: h("label", { class: "field" }, h("span", {}, "Change it to"), sel), getFix: () => { const v = sel.value; return !v ? null : v === "body" ? { op: "heading_remove", unit: u } : v === "chapter" ? { op: "new_chapter", unit: u } : v === "join" ? { op: "join_next", unit: u } : { op: "heading_set", unit: u, level: +v[1] }; } };
      }
      case "join": {
        if (cur.type !== "paragraph") return { el: h("p", { class: "muted small" }, "This break is in a list or table. Accept to keep as it is."), getFix: () => null };
        return { el: h("p", { class: "muted small" }, "Fix = join this paragraph with the next one."), getFix: () => ({ op: "join_next", unit: u }) };
      }
      case "dash": {
        const mode = radio("dash", [["−", "Minus sign (−)"], ["–", "En dash (–)"]], "−");
        return { el: mode.el, getFix: () => (item.offset === null ? null : { op: "char", unit: u, offset: item.offset, char: mode.value() }) };
      }
      case "author": return authorEditor(item);
      case "table": {
        const mode = radio("tbl", [["ok", "Looks right"], ["bad", "Needs fixing"]], "ok");
        return { el: h("div", {}, mode.el, h("p", { class: "muted small" }, "Table fixes are recorded as a note for the production team; the table text is not changed here.")), getFix: () => (mode.value() === "bad" ? { note: "table needs fixing" } : null) };
      }
      default: return { el: h("p", { class: "muted small" }, "Accept it if it is right, or skip it."), getFix: () => null };
    }
  }
  function authorEditor(item) {
    const m = (k) => (item.reason.match(new RegExp(`${k}='([^']*)'`)) || [])[1] || "";
    const box = { first: h("input", { type: "text", value: m("firstname"), "aria-label": "First name", dataset: { testid: "au-first" } }), sur: h("input", { type: "text", value: m("surname"), "aria-label": "Surname", dataset: { testid: "au-sur" } }), deg: h("input", { type: "text", value: m("degrees"), "aria-label": "Degrees", dataset: { testid: "au-deg" } }) };
    let index = null;
    get(`/api/jobs/${id}/details`).then((d) => { index = d.details.authors.findIndex((a) => a.firstname === m("firstname") && a.surname === m("surname")); }).catch(() => {});
    return { el: h("div", { class: "row" }, h("label", {}, "First name ", box.first), h("label", {}, "Surname ", box.sur), h("label", {}, "Degrees ", box.deg)),
      getFix: () => (box.sur.value.trim() ? { author: index ?? -1, firstname: box.first.value, surname: box.sur.value, degrees: box.deg.value } : null) };
  }

  // ------------------------------------------------------------------ browse a page
  async function paintBrowse() {
    right.append(h("div", { class: "row", style: "margin-bottom:8px" }, h("b", {}, `Page ${S.page}`), h("span", { class: "muted small" }, "Fix the structure of any page. Changes are saved as review decisions.")));
    const holder = h("div", { dataset: { testid: "browse-list" } }, spinner("Loading…"));
    right.append(holder);
    let data;
    try { data = await get(`/api/jobs/${id}/pages/${S.page}/units`); } catch (e) { clear(holder).append(errBox(e)); return; }
    clear(holder);
    const err = h("div"); S.selected = new Set();
    const mk = h("button", { dataset: { testid: "make-list" }, disabled: true, onclick: () => edit({ op: "make_list", units: [...S.selected] }) }, "Make a list from the selected paragraphs");
    holder.append(h("div", { class: "row", style: "margin-bottom:8px" }, mk), err);
    async function edit(e) {
      clear(err);
      if (!S.who) { whoInput.focus(); toast("Enter your name first."); return; }
      try { await post(`/api/jobs/${id}/edits`, { who: S.who, edit: e }); S.stale = true; const dec = await get(`/api/jobs/${id}/decisions`); S.edits = dec.edits; paintHistory(); paintRight(); toast("Saved."); }
      catch (x) { err.append(errBox(x)); }
    }
    for (const u of data.units) holder.append(unitRow(u, edit, mk));
    if (!data.units.length) holder.append(h("p", { class: "muted" }, "Nothing on this page."));
  }
  function unitRow(u, edit, mk) {
    const row = h("div", { class: "unitrow", dataset: { testid: "unit", unit: u.id, type: u.type }, style: `margin-left:${u.depth * 18}px`,
      onmouseenter: () => { S.hl = u.box; paintPage(); }, onclick: () => { S.hl = u.box; paintPage(); } });
    const label = u.type === "heading" ? `Heading · level ${u.level} · ${u.role}` : u.type.replace("_", " ") + (u.role && u.type === "paragraph" ? ` · ${u.role}` : "");
    row.append(h("div", { class: "row" }, h("span", { class: "kind" }, label), u.reviewer_made && badge("warn", "changed by you")));
    if (u.type === "figure" || u.type === "equation") {
      const ta = h("input", { type: "text", value: u.alt_text || "", placeholder: "Description", "aria-label": "Description", style: "width:70%", dataset: { testid: "browse-alt" } });
      row.append(u.image && h("div", { class: "small muted" }, `Picture: ${u.image}`), h("div", { class: "row" }, ta,
        h("button", { class: "small", onclick: () => ta.value.trim() && edit({ op: "alt_text", unit: u.id, text: ta.value.trim() }) }, "Save description"),
        u.type === "figure" && h("button", { class: "small", onclick: () => edit({ op: "decorative", unit: u.id, value: !u.decorative }) }, u.decorative ? "It is a real figure" : "It is decoration")));
      return row;
    }
    row.append(h("div", { class: "txt" }, u.text || (u.type === "table" ? `${u.rows} rows` : "")));
    if (u.type === "paragraph") {
      const cb = h("input", { type: "checkbox", "aria-label": "Select for a list", dataset: { testid: "select" }, onchange: () => { cb.checked ? S.selected.add(u.id) : S.selected.delete(u.id); mk.disabled = !S.selected.size; } });
      const lvl = h("select", { "aria-label": "Heading level", dataset: { testid: "browse-level" } }, [1, 2, 3, 4].map((n) => h("option", { value: n }, `level ${n}`)));
      const splitBox = h("div", { class: "linesplit", hidden: true });
      row.append(h("div", { class: "row" }, h("label", {}, cb, " select"),
        h("span", {}, "Make heading ", lvl, " ", h("button", { class: "small", dataset: { testid: "make-heading" }, onclick: () => edit({ op: "heading_set", unit: u.id, level: +lvl.value }) }, "Make heading")),
        h("button", { class: "small", dataset: { testid: "new-chapter" }, onclick: () => edit({ op: "new_chapter", unit: u.id }) }, "Start a new chapter here"),
        u.joined_to ? h("button", { class: "small", dataset: { testid: "unjoin" }, onclick: () => edit({ op: "unjoin", unit: u.id }) }, "Undo join with next") : u.can_join && h("button", { class: "small", dataset: { testid: "join-next" }, onclick: () => edit({ op: "join_next", unit: u.id }) }, "Join with next paragraph"),
        (u.lines?.length || 0) > 1 && h("button", { class: "small", dataset: { testid: "split-open" }, onclick: () => (splitBox.hidden = !splitBox.hidden) }, "Split here…")));
      (u.lines || []).forEach((line, n) => n > 0 && splitBox.append(h("div", {}, h("button", { class: "small", dataset: { testid: "split-line" }, onclick: () => edit({ op: "split", unit: u.id, line: n }) }, "New paragraph starts here ↓"), h("span", {}, line.slice(0, 70)))));
      row.append(splitBox);
    } else if (u.type === "heading") {
      const lvl = h("select", { "aria-label": "Heading level", dataset: { testid: "browse-level" } }, [1, 2, 3, 4, 5].map((n) => h("option", { value: n, selected: n === u.level }, `level ${n}`)));
      row.append(h("div", { class: "row" }, lvl, h("button", { class: "small", dataset: { testid: "set-level" }, onclick: () => edit({ op: "heading_set", unit: u.id, level: +lvl.value }) }, "Set level"),
        h("button", { class: "small", dataset: { testid: "not-heading" }, onclick: () => edit({ op: "heading_remove", unit: u.id }) }, "Not a heading"),
        u.role !== "chapter" && h("button", { class: "small", dataset: { testid: "new-chapter" }, onclick: () => edit({ op: "new_chapter", unit: u.id }) }, "Start a new chapter here")));
    }
    return row;
  }

  // ------------------------------------------------------------------ your changes
  function historyPanel() {
    return h("details", { class: "panel", dataset: { testid: "history" } }, h("summary", {}, "Your changes"), h("div", { class: "hist" }));
  }
  function paintHistory() {
    const box = histBox.querySelector(".hist");
    histBox.querySelector("summary").textContent = `Your changes (${S.edits.length})`;
    clear(box);
    if (!S.edits.length) { box.append(h("p", { class: "muted small" }, "None yet.")); return; }
    box.append(h("table", {}, h("tbody", {}, S.edits.map((e) => h("tr", { dataset: { testid: "edit-row" } },
      h("td", {}, describe(e)), h("td", { class: "small" }, `${e.who}, ${when(e.at)}`),
      h("td", {}, h("button", { class: "small", onclick: async () => { try { await del(`/api/jobs/${id}/decisions/${e.id}?who=${encodeURIComponent(S.who || e.who)}`); S.stale = true; const dec = await get(`/api/jobs/${id}/decisions`); S.edits = dec.edits; paintHistory(); paintRight(); } catch (x) { toast(x.message); } } }, "Undo")))))));
  }
  const NAMES = { heading_set: "Heading level", heading_remove: "Not a heading", new_chapter: "New chapter", join_next: "Join with next", unjoin: "Undo join", split: "Split paragraph", make_list: "Make a list", alt_text: "Picture description", decorative: "Decoration flag", char: "Character" };
  const describe = (e) => `${NAMES[e.op] || e.op}${e.level ? ` ${e.level}` : ""}${e.line ? ` (line ${e.line + 1})` : ""}${e.text ? `: ${e.text.slice(0, 40)}` : ""}`;

  paintHistory();
  paintRight();
  paintPage();
  if (S.mode === "browse") paintRight();
  onLeave(() => {});
}
