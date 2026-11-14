import { steps } from "./steps.js";
import { badge, clear, del, errBox, get, h, post, spinner, toast, when } from "./util.js";
import { changeDialog, similarPanel } from "./view_edit.js";

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
    who: localStorage.getItem("reviewer") || "", edits: [], stale: false, selected: new Set(), bulk: new Set(),
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
    const shown = list.slice(0, 400);
    const q = h("div", { class: "queue", dataset: { testid: "queue" } }, shown.map((it, n) => {
      const cb = h("input", { type: "checkbox", checked: S.bulk.has(it.key), "aria-label": "Select this item", dataset: { testid: "bulk-select" },
        onchange: () => { cb.checked ? S.bulk.add(it.key) : S.bulk.delete(it.key); paintBulk(); } });
      return h("div", { class: "qrow" }, cb,
        h("button", { class: `${n === S.idx ? "current" : ""} ${it.decision ? "done" : ""}`, dataset: { testid: "queue-item" }, onclick: () => { S.idx = n; paintRight(); } },
          it.severity === "must_check" ? h("b", {}, "must check") : "review", ` p.${it.page ?? "–"} `, kindName(it.kind), " ", h("span", { class: "muted" }, (it.reason || "").slice(0, 60))));
    }));
    right.append(bulkBar(shown), q);
    if (!list.length) { right.append(h("div", { class: "banner pass", dataset: { testid: "queue-empty" } }, S.total ? "Nothing open here. Change the filters or continue to export." : "Nothing flagged. You can browse pages to check the structure.")); return; }
    const item = list[S.idx];
    S.hl = item.box; if (item.page) S.page = item.page;
    right.append(card(item, list));
    paintPage();
  }

  // Select several queue items and accept or skip them together. A fix always needs its own detail.
  function bulkBar(shown) {
    const count = h("span", { class: "muted small", dataset: { testid: "bulk-count" } });
    const all = h("input", { type: "checkbox", "aria-label": "Select all shown", dataset: { testid: "bulk-all" },
      onchange: () => { shown.forEach((i) => (all.checked ? S.bulk.add(i.key) : S.bulk.delete(i.key))); paintRight(); } });
    const mkBtn = (action, label) => h("button", { class: "small", disabled: true, dataset: { testid: `bulk-${action}` }, onclick: () => bulkDecide(action) }, label);
    const acceptBtn = mkBtn("accept", "Accept selected"), skipBtn = mkBtn("skip", "Skip selected");
    const clearBtn = h("button", { class: "small", onclick: () => { S.bulk.clear(); paintRight(); } }, "Clear selection");
    const bar = h("div", { class: "row", style: "margin-bottom:6px" }, h("label", {}, all, " Select all shown"), count, h("div", { class: "grow" }), clearBtn, acceptBtn, skipBtn);
    bar.paint = () => {
      const n = shown.filter((i) => S.bulk.has(i.key)).length;
      count.textContent = n ? `${n} selected` : "";
      acceptBtn.disabled = skipBtn.disabled = !n;
      all.checked = n > 0 && n === shown.length;
    };
    bar.paint(); S.bulkBar = bar;
    return bar;
  }
  function paintBulk() { S.bulkBar?.paint(); }
  async function bulkDecide(action) {
    if (!S.who) { whoInput.focus(); toast("Enter your name first."); return; }
    const picked = S.items.filter((i) => S.bulk.has(i.key));
    if (!picked.length) return;
    try {
      const items = picked.map((it) => ({ key: it.key, item_kind: it.kind, item: { severity: it.severity, kind: it.kind, page: it.page, page_label: it.page_label, unit: it.unit, reason: it.reason, source: it.source, editor: it.editor, box: it.box } }));
      await post(`/api/jobs/${id}/decisions/bulk`, { who: S.who, action, items });
      const at = new Date().toISOString();
      picked.forEach((it) => { it.decision = { action, fix: null, note: "", who: S.who, at }; });
      S.bulk.clear();
      S.decided = S.items.filter((i) => i.decision).length;
      const dec = await get(`/api/jobs/${id}/decisions`); S.edits = dec.edits; paintHistory();
      toast(`${picked.length} item${picked.length === 1 ? "" : "s"} ${action === "skip" ? "skipped" : "accepted"}.`);
      paintRight();
    } catch (e) { toast(e.message); }
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
  // A change updates only the rows it touched (no reload): the PDF page, its zoom and the
  // scroll position stay where they are.
  async function paintBrowse() {
    right.append(h("div", { class: "row", style: "margin-bottom:8px" }, h("b", {}, `Page ${S.page}`), h("span", { class: "muted small" }, "Fix the structure of any page. Select items and change what they are; every change is previewed first and can be undone.")));
    const holder = h("div", { dataset: { testid: "browse-list" } }, spinner("Loading…"));
    right.append(holder);
    let data;
    try { data = await get(`/api/jobs/${id}/pages/${S.page}/units`); } catch (e) { clear(holder).append(errBox(e)); return; }
    clear(holder);
    const err = h("div"); S.selected = new Set();
    const mk = h("button", { dataset: { testid: "make-list" }, disabled: true, onclick: () => edit({ op: "make_list", units: [...S.selected] }) }, "Make a list from the selected paragraphs");
    const chg = h("button", { class: "primary", dataset: { testid: "change-element" }, disabled: true, onclick: () => openChange([...S.selected]) }, "Change element…");
    const selCount = h("span", { class: "muted small", dataset: { testid: "selected-count" } });
    const dialogBox = h("div", { dataset: { testid: "change-holder" } });
    const chaptersBox = h("div");
    const list = h("div", { dataset: { testid: "unit-list" } });
    holder.append(h("div", { class: "row", style: "margin-bottom:8px" }, chg, mk, selCount), err, dialogBox, chaptersBox, list);
    chaptersBox.append(await chapterPanel());
    const rowEls = new Map();
    const page = S.page;
    const syncSel = () => {
      const picked = S.rows.filter((r) => S.selected.has(r.id));
      selCount.textContent = picked.length ? `${picked.length} selected` : "";
      chg.disabled = !picked.length;
      mk.disabled = !picked.length || picked.some((r) => r.type !== "paragraph");
    };
    function renderRows(rows) {
      const y = window.scrollY;
      S.rows = rows;
      const ids = new Set(rows.map((r) => r.id));
      for (const k of [...S.selected]) if (!ids.has(k)) S.selected.delete(k);
      list.replaceChildren(...rows.map((r) => {
        const sig = JSON.stringify(r);
        const old = rowEls.get(r.id);
        if (old && old.sig === sig) return old.el;  // unchanged: the same element stays
        const el = unitRow(r, edit, syncSel, openChange);
        rowEls.set(r.id, { el, sig });
        return el;
      }));
      if (!rows.length) list.append(h("p", { class: "muted" }, "Nothing on this page."));
      syncSel();
      window.scrollTo(window.scrollX, y);
    }
    async function afterChange(res) {
      const mine = (res.pages || []).find((p) => p.page === page);
      if (mine && S.page === page && S.mode === "browse") renderRows(mine.after);
      if (res.chapters) chaptersBox.replaceChildren(chapterTable(res.chapters));
      S.stale = true; staleBanner.hidden = false;
      const dec = await get(`/api/jobs/${id}/decisions`); S.edits = dec.edits; paintHistory();
    }
    S.afterChange = afterChange;
    // Changes go to the server one after another, in the order they were made.
    function edit(e) {
      clear(err);
      if (!S.who) { whoInput.focus(); toast("Enter your name first."); return Promise.resolve(); }
      S.chain = (S.chain || Promise.resolve()).then(async () => {
        try { await afterChange(await post(`/api/jobs/${id}/edits`, { who: S.who, edit: e })); toast("Saved."); }
        catch (x) { err.append(errBox(x)); }
      });
      return S.chain;
    }
    function openChange(ids, initial) {
      const order = S.rows.map((r) => r.id);
      ids = [...ids].sort((a, b) => order.indexOf(a) - order.indexOf(b));
      dialogBox.replaceChildren(changeDialog({
        id, page, rows: S.rows, ids, initial, who: () => S.who,
        enqueue: (fn) => (S.chain = (S.chain || Promise.resolve()).then(fn, fn)),
        onSaved: async (res) => {
          S.selected.clear();
          list.querySelectorAll("[data-testid=select]").forEach((c) => { c.checked = false; });
          await afterChange(res);
          toast("Saved. Undo it from “Your changes”.");
          dialogBox.replaceChildren(similarPanel({
            id, event: res.event, who: () => S.who,
            onApplied: async (g) => {
              dialogBox.replaceChildren();
              await afterChange(g);
              toast(`Applied to ${g.applied} block${g.applied === 1 ? "" : "s"}${g.refused.length ? `; ${g.refused.length} could not be changed` : ""}. One Undo takes back the group.`);
            },
            onClose: () => dialogBox.replaceChildren(),
          }));
        },
        onClose: () => dialogBox.replaceChildren(),
      }));
      dialogBox.scrollIntoView?.({ block: "nearest" });
    }
    renderRows(data.units);
  }
  const KINDS = [["part", "Part"], ["chapter", "Chapter"], ["section", "Section"], ["front_matter", "Front matter"], ["back_matter", "Back matter"]];
  const kindOf = (u) => ({ part: "part", chapter: "chapter", front_section_title: "front_matter", rear_section_title: "back_matter" }[u.role] || "section");
  function chapterTable(rows) {
    const box = h("details", { class: "panel", open: true, dataset: { testid: "chapters-panel" } }, h("summary", {}, "Chapters and parts"));
    const chapters = rows.filter((r) => r.role === "chapter").length, parts = rows.filter((r) => r.role === "part").length;
    box.querySelector("summary").textContent = `Chapters and parts (${parts} parts, ${chapters} chapters)`;
    box.append(h("table", {}, h("thead", {}, h("tr", {}, ["", "Number", "Title", "Page"].map((t) => h("th", {}, t)))),
      h("tbody", {}, rows.map((r) => h("tr", { dataset: { testid: "chapter-row", role: r.role }, style: "cursor:pointer", onclick: () => { S.page = r.page; S.hl = null; paintPage(); paintRight(); } },
        h("td", {}, r.role === "part" ? "Part" : "Chapter"), h("td", {}, (r.number || "") + (r.set_by_reviewer ? " ✎" : "")), h("td", { style: r.role === "part" ? "font-weight:600" : "padding-left:16px" }, r.title), h("td", {}, String(r.page)))))));
    if (!rows.length) box.append(h("p", { class: "muted small" }, "No chapter or part yet."));
    return box;
  }
  async function chapterPanel() {
    try { return chapterTable((await get(`/api/jobs/${id}/chapters`)).chapters); }
    catch (e) { return h("details", { class: "panel", open: true, dataset: { testid: "chapters-panel" } }, h("summary", {}, "Chapters and parts"), errBox(e)); }
  }
  function unitRow(u, edit, syncSel, openChange) {
    const row = h("div", { class: "unitrow", dataset: { testid: "unit", unit: u.id, type: u.type }, style: `margin-left:${u.depth * 18}px`,
      onmouseenter: () => { S.hl = u.box; paintPage(); }, onclick: () => { S.hl = u.box; paintPage(); } });
    const what = u.type === "heading" ? `Heading · level ${u.level} · ${u.role}` : u.type === "box" ? (u.flags?.includes("pull_quote") ? "pull quote" : u.flags?.includes("quote") ? "quote" : "box")
      : u.type.replace("_", " ") + (u.type === "list" && u.list_type ? ` · ${u.list_type}` : "") + (u.type === "list_item" && u.item_level ? ` · level ${u.item_level}` : "")
      + (u.role && u.type === "paragraph" ? ` · ${u.flags?.includes("chapter_authors") ? "chapter authors" : u.role}` : "");
    const cb = h("input", { type: "checkbox", "aria-label": "Select", dataset: { testid: "select" }, onclick: (ev) => ev.stopPropagation(),
      onchange: () => { cb.checked ? S.selected.add(u.id) : S.selected.delete(u.id); syncSel(); } });
    row.append(h("div", { class: "row" }, h("label", {}, cb, " "), h("span", { class: "kind" }, what), u.reviewer_made && badge("warn", "changed by you"), h("div", { class: "grow" }),
      h("button", { class: "small", title: "Move up in the reading order", "aria-label": "Move up", dataset: { testid: "move-up" }, onclick: () => openChange([u.id], "move_up") }, "↑"),
      h("button", { class: "small", title: "Move down in the reading order", "aria-label": "Move down", dataset: { testid: "move-down" }, onclick: () => openChange([u.id], "move_down") }, "↓"),
      h("button", { class: "small", title: "This block starts the column that is read first on this page", dataset: { testid: "swap-columns" }, onclick: () => openChange([u.id], "swap_columns") }, "Read this column first"),
      h("button", { class: "small", dataset: { testid: "change-one" }, onclick: () => openChange([u.id]) }, "Change…")));
    if (u.type === "figure" || u.type === "equation") {
      const ta = h("input", { type: "text", value: u.alt_text || "", placeholder: "Description", "aria-label": "Description", style: "width:70%", dataset: { testid: "browse-alt" } });
      row.append(u.image && h("div", { class: "small muted" }, `Picture: ${u.image}`), h("div", { class: "row" }, ta,
        h("button", { class: "small", onclick: () => ta.value.trim() && edit({ op: "alt_text", unit: u.id, text: ta.value.trim() }) }, "Save description"),
        u.type === "figure" && h("button", { class: "small", onclick: () => edit({ op: "decorative", unit: u.id, value: !u.decorative }) }, u.decorative ? "It is a real figure" : "It is decoration")));
      return row;
    }
    row.append(h("div", { class: "txt" }, u.text || (u.type === "table" ? `${u.rows} rows` : "")));
    if (u.type === "paragraph") {
      const lvl = h("select", { "aria-label": "Heading level", dataset: { testid: "browse-level" } }, [1, 2, 3, 4].map((n) => h("option", { value: n }, `level ${n}`)));
      const splitBox = h("div", { class: "linesplit", hidden: true });
      row.append(h("div", { class: "row" },
        h("span", {}, "Make heading ", lvl, " ", h("button", { class: "small", dataset: { testid: "make-heading" }, onclick: () => edit({ op: "heading_set", unit: u.id, level: +lvl.value }) }, "Make heading")),
        h("span", {}, h("input", { type: "text", size: 4, placeholder: "Number", "aria-label": "Chapter number", dataset: { testid: "chapter-number" } }), " ", h("button", { class: "small", dataset: { testid: "new-chapter" }, onclick: (ev) => { const n = ev.target.parentNode.querySelector("input").value.trim(); edit({ op: "new_chapter", unit: u.id, ...(n ? { number: n } : {}) }); } }, "Start a new chapter here")),
        u.joined_to ? h("button", { class: "small", dataset: { testid: "unjoin" }, onclick: () => edit({ op: "unjoin", unit: u.id }) }, "Undo join with next") : u.can_join && h("button", { class: "small", dataset: { testid: "join-next" }, onclick: () => edit({ op: "join_next", unit: u.id }) }, "Join with next paragraph"),
        (u.lines?.length || 0) > 1 && h("button", { class: "small", dataset: { testid: "split-open" }, onclick: () => (splitBox.hidden = !splitBox.hidden) }, "Split here…")));
      (u.lines || []).forEach((line, n) => n > 0 && splitBox.append(h("div", {}, h("button", { class: "small", dataset: { testid: "split-line" }, onclick: () => edit({ op: "split", unit: u.id, line: n }) }, "New paragraph starts here ↓"), h("span", {}, line.slice(0, 70)))));
      row.append(splitBox);
    } else if (u.type === "heading") {
      const lvl = h("select", { "aria-label": "Heading level", dataset: { testid: "browse-level" } }, [1, 2, 3, 4, 5].map((n) => h("option", { value: n, selected: n === u.level }, `level ${n}`)));
      row.append(h("div", { class: "row" }, lvl, h("button", { class: "small", dataset: { testid: "set-level" }, onclick: () => edit({ op: "heading_set", unit: u.id, level: +lvl.value }) }, "Set level"),
        h("button", { class: "small", dataset: { testid: "not-heading" }, onclick: () => edit({ op: "heading_remove", unit: u.id }) }, "Not a heading"),
        u.role !== "chapter" && h("button", { class: "small", dataset: { testid: "new-chapter" }, onclick: () => edit({ op: "new_chapter", unit: u.id }) }, "Start a new chapter here")));
      const kind = h("select", { "aria-label": "Kind of heading", dataset: { testid: "heading-kind" } }, KINDS.map(([v, t]) => h("option", { value: v, selected: v === kindOf(u) }, t)));
      const num = h("input", { type: "text", size: 4, value: u.number || "", placeholder: "Number", "aria-label": "Number", dataset: { testid: "heading-number" } });
      const title = h("input", { type: "text", value: u.text || "", "aria-label": "Title text", style: "width:60%", dataset: { testid: "heading-text" } });
      row.append(
        h("div", { class: "row" }, kind, h("button", { class: "small", dataset: { testid: "set-kind" }, onclick: () => edit({ op: "heading_kind", unit: u.id, kind: kind.value }) }, "Set kind"),
          num, h("button", { class: "small", dataset: { testid: "set-number" }, onclick: () => num.value.trim() && edit({ op: "heading_number", unit: u.id, number: num.value.trim() }) }, "Set number"),
          h("button", { class: "small", dataset: { testid: "attach" }, onclick: () => edit({ op: "heading_attach", unit: u.id }) }, "Belongs to the chapter before")),
        h("div", { class: "row" }, title, h("button", { class: "small", dataset: { testid: "save-title" }, onclick: () => title.value.trim() && title.value !== u.text && edit({ op: "heading_text", unit: u.id, text: title.value }) }, "Save title"),
          h("span", { class: "muted small" }, "The title can only lose a stray number; the change is kept in your changes list.")));
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
    box.append(h("table", {}, h("tbody", {}, S.edits.map((e) => h("tr", { dataset: { testid: "edit-row", op: e.op } },
      h("td", {}, describe(e)), h("td", { class: "small" }, `${e.who}, ${when(e.at)}`),
      h("td", {}, e.group && h("button", { class: "small", dataset: { testid: "undo-group" }, onclick: async () => { try { const res = await del(`/api/jobs/${id}/groups/${e.group}?who=${encodeURIComponent(S.who || e.who)}`); S.stale = true;
        if (S.mode === "browse" && S.afterChange) { await S.afterChange(res); toast(`Undone: ${res.undone} changes.`); return; }
        const dec = await get(`/api/jobs/${id}/decisions`); S.edits = dec.edits; paintHistory(); paintRight(); } catch (x) { toast(x.message); } } }, "Undo the group"),
      h("button", { class: "small", onclick: async () => { try { const res = await del(`/api/jobs/${id}/decisions/${e.id}?who=${encodeURIComponent(S.who || e.who)}`); S.stale = true;
        if (S.mode === "browse" && res.pages && S.afterChange) { await S.afterChange(res); toast("Undone."); return; }
        const dec = await get(`/api/jobs/${id}/decisions`); S.edits = dec.edits; paintHistory(); paintRight(); } catch (x) { toast(x.message); } } }, "Undo")))))));
  }
  const NAMES = { heading_set: "Heading level", heading_remove: "Not a heading", new_chapter: "New chapter", join_next: "Join with next", unjoin: "Undo join", split: "Split paragraph", make_list: "Make a list", alt_text: "Picture description", decorative: "Decoration flag", char: "Character", heading_kind: "Kind of heading", heading_number: "Number", heading_text: "Title text", heading_attach: "Belongs to the chapter before",
    list_set: "List", list_level: "List level", box: "Box", caption: "Figure caption", table_make: "Table", table_text: "Table text", footnote: "Footnote",
    paragraph: "Body paragraph", chapter_authors: "Chapter authors", question: "MCQ question", bibliography: "Bibliography entries", index_entries: "Index entries",
    glossary: "Glossary entries", not_content: "Not book content", merge: "Merge", move: "Move", swap_columns: "Swap columns" };
  const describe = (e) => `${e.group ? "[same as another change] " : ""}${NAMES[e.op] || e.op}${e.op === "box" && e.kind !== "box" ? ` (${e.kind.replace("_", " ")})` : ""}${e.list_type ? ` (${e.list_type})` : ""}${e.direction ? ` ${e.direction}` : ""}${e.scope === "follow" ? " · and what follows" : ""}${e.level ? ` ${e.level}` : ""}${e.line ? ` (line ${e.line + 1})` : ""}${e.text ? `: ${e.text.slice(0, 40)}` : ""}${e.kind ? `: ${e.kind.replace("_", " ")}` : ""}${e.number ? ` (${e.number})` : ""}${e.before ? ` (was: ${e.before.replace(/\s+/g, " ").slice(0, 40)})` : ""}`;

  paintHistory();
  paintRight();
  paintPage();
  if (S.mode === "browse") paintRight();
  onLeave(() => {});
}
