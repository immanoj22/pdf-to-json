import { steps } from "./steps.js";
import { append, badge, clear, del, errBox, get, h, post, spinner, toast, when } from "./util.js";
import { changeDialog, similarPanel } from "./view_edit.js";
import { GROUPS, ICON, answersFor, assistantDecided, confirmed, decisionWords, groupOf, helpFor, itemKindName, kindName, linesOf, ordered, question, similarKey, why } from "./review_model.js";


export async function reviewView({ app, id, params, onLeave }) {
  const job = await get(`/api/jobs/${id}`);
  app.append(h("h1", {}, job.name), steps(job, "review"));
  if (job.state !== "converted") { app.append(h("div", { class: "banner warn" }, "Convert the book first.")); return; }
  const S = {
    items: [], total: 0, decided: 0, idx: 0, mode: params.get("mode") === "browse" ? "browse" : "queue",
    kind: "", pageFilter: "", status: "open", page: +params.get("page") || 1, zoom: 1, hl: null, pages: [],
    who: localStorage.getItem("reviewer") || "", undo: [], keys: null, edits: [], stale: false, selected: new Set(), bulk: new Set(),
    pageTo: "", reviewer: "", decidedBy: "", mine: false, assigned: [], offer: null, focusUnit: null,
  };
  const wait = h("div", { class: "panel" }, spinner("Preparing the review list… (a long book can take half a minute)"));
  app.append(wait);
  const [pagesInfo, asg] = await Promise.all([get(`/api/jobs/${id}/pages`), get(`/api/jobs/${id}/assignments`).catch(() => ({ reviewers: [] })), load()]);
  S.pages = pagesInfo.pages; S.assigned = asg.reviewers || [];
  wait.remove();

  async function load(refresh = false) {
    const d = refresh ? await post(`/api/jobs/${id}/review/refresh`) : await get(`/api/jobs/${id}/review`);
    Object.assign(S, { items: d.items, total: d.total, decided: d.decided, stale: d.stale, placeholders: d.alt_text_placeholders, failed: d.failed_edits });
    const dec = await get(`/api/jobs/${id}/decisions`);
    S.edits = dec.edits;
  }

  // ------------------------------------------------------------------ layout
  const whoInput = h("input", { type: "text", value: S.who, placeholder: "Your name", "aria-label": "Your name", dataset: { testid: "who" },
    oninput: () => { S.who = whoInput.value.trim(); localStorage.setItem("reviewer", S.who); if (S.mine) { S.idx = 0; paintRight(); } } });
  const progText = h("span", { dataset: { testid: "progress" } });
  const progBar = h("div", { style: "width:0" });
  const groupBars = h("div", { class: "row groupbars", dataset: { testid: "groups" } });
  const kindSel = h("select", { "aria-label": "Filter by kind", dataset: { testid: "filter-kind" }, onchange: () => { S.kind = kindSel.value; S.idx = 0; paintRight(); } });
  const pageFilter = h("input", { type: "number", min: "1", placeholder: "from page", "aria-label": "From page", style: "width:90px", dataset: { testid: "filter-page" },
    oninput: () => { S.pageFilter = pageFilter.value; S.idx = 0; paintRight(); } });
  const pageTo = h("input", { type: "number", min: "1", placeholder: "to page", "aria-label": "To page", style: "width:90px", dataset: { testid: "filter-page-to" },
    oninput: () => { S.pageTo = pageTo.value; S.idx = 0; paintRight(); } });
  const reviewerSel = h("select", { "aria-label": "Filter by reviewer", dataset: { testid: "filter-reviewer" }, onchange: () => { S.reviewer = reviewerSel.value; S.idx = 0; paintRight(); } },
    h("option", { value: "" }, "Any reviewer"), S.assigned.map((r) => h("option", { value: r.name }, `${r.name}${r.first ? ` (p.${r.first}–${r.last})` : ""}`)));
  const byDecided = h("select", { "aria-label": "Filter by who decided", dataset: { testid: "filter-decided-by" }, onchange: () => { S.decidedBy = byDecided.value; S.idx = 0; paintRight(); } },
    h("option", { value: "" }, "Decided by anyone"), h("option", { value: "person" }, "Decided by a person"), h("option", { value: "claude" }, "Decided by Claude Desktop"));
  const myBox = h("input", { type: "checkbox", dataset: { testid: "filter-mine" }, onchange: () => { S.mine = myBox.checked; S.idx = 0; paintRight(); } });
  const myLabel = h("label", { class: "small", title: "Only the pages assigned to you (the name in Reviewer)" }, myBox, " My items");
  const statusSel = h("select", { "aria-label": "Show", dataset: { testid: "filter-status" }, onchange: () => { S.status = statusSel.value; S.idx = 0; paintRight(); } },
    h("option", { value: "open" }, "Open items"), h("option", { value: "all" }, "All items"), h("option", { value: "done" }, "Decided items"));
  const modeQueue = h("button", { dataset: { testid: "mode-queue" }, onclick: () => setMode("queue") }, "Flagged items");
  const modeBrowse = h("button", { dataset: { testid: "mode-browse" }, onclick: () => setMode("browse") }, "Browse pages");
  // Shown only while the list is being brought up to date in the background.
  const staleBanner = h("div", { class: "banner info small", hidden: true, dataset: { testid: "stale" } }, spinner("Updating the list with the latest changes… You can keep working."));
  const bar = h("div", { class: "panel" },
    h("div", { class: "row" }, h("label", {}, "Reviewer ", whoInput), h("div", { class: "grow" }), progText, h("div", { class: "bar", style: "width:160px" }, progBar),
      h("div", { class: "row" }, modeQueue, modeBrowse)),
    groupBars,
    h("div", { class: "row", style: "margin-top:8px" }, kindSel, pageFilter, "–", pageTo, reviewerSel, byDecided, statusSel, myLabel,
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
      centerOn(hl);
    } else hl.hidden = true;
  }
  // Scroll the PDF pane (not the window) so the highlight sits in the middle of the part of
  // the pane that is on screen.
  // The pane is as tall as the space left on screen below its top, so it always scrolls by
  // itself and its bottom is never below the window.
  function fitPane() {
    if (getComputedStyle(left).position !== "sticky") { left.style.maxHeight = ""; return; }
    left.style.maxHeight = `${Math.max(300, window.innerHeight - Math.max(left.getBoundingClientRect().top, 56) - 12)}px`;
  }
  window.addEventListener("scroll", fitPane, { passive: true });
  window.addEventListener("resize", fitPane);
  function centerOn(el) {
    fitPane();
    const pane = left, pr = pane.getBoundingClientRect(), er = el.getBoundingClientRect();
    const visTop = Math.max(pr.top, 0), visBottom = Math.min(pr.bottom, window.innerHeight);
    const visH = Math.max(120, visBottom - visTop - tools.offsetHeight);
    const elTop = er.top - pr.top + pane.scrollTop, elLeft = er.left - pr.left + pane.scrollLeft;
    pane.scrollTop = Math.max(0, elTop - tools.offsetHeight - (visH - er.height) / 2);
    pane.scrollLeft = Math.max(0, elLeft - (pane.clientWidth - er.width) / 2);
  }
  function openInBrowse(item) {
    if (item.page) S.page = item.page;
    S.focusUnit = item.unit || null; S.hl = item.box || null;
    setMode("browse");
  }
  async function setMode(m) {
    S.mode = m; paintRight();
    if (m === "browse") { const item = visible()[S.idx]; if (item?.page) S.page = item.page; paintPage(); }
  }
  // The list goes out of date after a change; it is rebuilt in the background a few seconds
  // after the last change. The card being answered is never redrawn under the reviewer.
  let refreshTimer = null, refreshing = false, alive = true;
  function scheduleRefresh(delay = 4000) {
    S.stale = true;
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(refreshList, delay);
  }
  async function refreshList() {
    if (!alive) return;
    if (refreshing) { scheduleRefresh(); return; }
    refreshing = true; staleBanner.hidden = false;
    const keep = S.mode === "queue" ? visible()[S.idx]?.key : null;
    try { await load(true); } catch (e) { toast(`The list could not be updated: ${e.message}`); }
    finally { refreshing = false; }
    if (!alive) return;
    staleBanner.hidden = true;
    const busy = right.contains(document.activeElement) && /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    if (S.mode === "queue" && !busy && !right.querySelector(".formbox")) {
      const at = visible().findIndex((i) => i.key === keep);
      if (at >= 0) S.idx = at;
      paintRight();
    } else paintHeader();
  }

  // ------------------------------------------------------------------ queue
  function visible() {
    const from = +S.pageFilter || 0, to = +S.pageTo || (from || Infinity);
    const inRanges = (page, name) => { const mine = S.assigned.filter((r) => String(r.name).toLowerCase() === name.toLowerCase()); return mine.some((r) => r.first == null || (page != null && page >= r.first && page <= r.last)); };
    return ordered(S.items.filter((i) => (!S.kind || i.kind === S.kind) && (!from || (i.page != null && i.page >= from && i.page <= to))
      && (S.status === "all" || (S.status === "open" ? !confirmed(i) : confirmed(i)))
      && (!S.reviewer || inRanges(i.page, S.reviewer))
      && (!S.mine || (S.who && inRanges(i.page, S.who)))
      && (!S.decidedBy || (S.decidedBy === "person" ? confirmed(i) : assistantDecided(i)))));
  }
  function paintHeader() {
    const kinds = [...new Set(S.items.map((i) => i.kind))].sort();
    const cur = kindSel.value;
    clear(kindSel).append(h("option", { value: "" }, "All kinds"), ...kinds.map((k) => h("option", { value: k, selected: k === cur }, kindName(k))));
    S.decided = S.items.filter(confirmed).length;
    progText.textContent = `${S.decided} of ${S.total} confirmed`;
    progBar.style.width = S.total ? `${(100 * S.decided) / S.total}%` : "0";
    clear(groupBars).append(...GROUPS.map((name, g) => {
      const all = S.items.filter((i) => groupOf(i) === g), done = all.filter(confirmed).length;
      return all.length ? h("div", { class: "gbar", dataset: { testid: `group-${g}` } }, h("span", { class: "small" }, `${name}: ${done} of ${all.length}`), h("div", { class: "bar" }, h("div", { style: `width:${(100 * done) / all.length}%` }))) : null;
    }));
    modeQueue.className = S.mode === "queue" ? "primary" : ""; modeBrowse.className = S.mode === "browse" ? "primary" : "";
    staleBanner.hidden = !refreshing;
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
        h("button", { class: `${n === S.idx ? "current" : ""} ${confirmed(it) ? "done" : ""}`, dataset: { testid: "queue-item" }, onclick: () => { S.idx = n; paintRight(); } },
          confirmed(it) ? h("span", { class: "muted" }, "done ✓") : it.severity === "must_check" ? h("b", {}, "must check") : "review", ` p.${it.page ?? "–"} `, kindName(it.kind), " ", h("span", { class: "muted" }, (it.reason || "").slice(0, 60))));
    }));
    right.append(...(S.offer ? [offerPanel()] : []), groupBar() || "", bulkBar(shown), q);
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
  const bulkDecide = (action) => bulkDecideItems(S.items.filter((i) => S.bulk.has(i.key)), action);
  async function bulkDecideItems(picked, action) {
    if (!S.who) { whoInput.focus(); toast("Enter your name first."); return; }
    if (!picked.length) return;
    try {
      const items = picked.map((it) => ({ key: it.key, item_kind: it.kind, item: { severity: it.severity, kind: it.kind, page: it.page, page_label: it.page_label, unit: it.unit, reason: it.reason, source: it.source, editor: it.editor, box: it.box } }));
      await post(`/api/jobs/${id}/decisions/bulk`, { who: S.who, action, items });
      const at = new Date().toISOString();
      picked.forEach((it) => { it.decision = { action, fix: null, note: "", who: S.who, at }; });
      S.bulk.clear();
      S.decided = S.items.filter(confirmed).length;
      const dec = await get(`/api/jobs/${id}/decisions`); S.edits = dec.edits; paintHistory();
      toast(`${picked.length} item${picked.length === 1 ? "" : "s"} ${action === "skip" ? "skipped" : "accepted"}.`);
      paintRight();
    } catch (e) { toast(e.message); }
  }

  // ------------------------------------------------------------------ the review card
  const doneCount = () => S.items.filter(confirmed).length;
  const snapOf = (item) => ({ severity: item.severity, kind: item.kind, page: item.page, page_label: item.page_label, unit: item.unit, reason: item.reason, source: item.source, editor: item.editor, box: item.box });

  // Save one answer. Nothing is saved before this is called.
  async function decide(item, a, note = "") {
    if (!S.who) { whoInput.focus(); toast("Enter your name first."); return false; }
    const action = a.action, fix = action === "fix" ? a.fix : null;
    const res = await post(`/api/jobs/${id}/decisions`, { who: S.who, key: item.key, item_kind: item.kind, action, fix, note, item: snapOf(item) });
    item.decision = { action, fix, note, who: S.who, at: new Date().toISOString() };
    S.undo.push({ key: item.key, id: res?.event?.id });
    S.decided = doneCount();
    if (fix?.op) scheduleRefresh();
    const dec = await get(`/api/jobs/${id}/decisions`); S.edits = dec.edits; paintHistory();
    return true;
  }
  function afterDecision(list) {
    if (S.status === "open") S.idx = Math.min(S.idx, Math.max(0, visible().length - 1));
    else S.idx = Math.min(S.idx + 1, list.length - 1);
    paintRight();
  }
  // U: take back the last answer of this session (its decision and the change it made).
  async function undoLast() {
    const last = S.undo.pop();
    if (!last) { toast("Nothing to undo."); return; }
    if (last.group) { await undoGroupDecisions(last.group); return; }
    try {
      const who = encodeURIComponent(S.who || "");
      if (last.id) await del(`/api/jobs/${id}/decisions/${last.id}?who=${who}`);
      for (const e of S.edits.filter((x) => x.source === last.key)) await del(`/api/jobs/${id}/decisions/${e.id}?who=${who}`);
      const dec = await get(`/api/jobs/${id}/decisions`); S.edits = dec.edits;
      const it = S.items.find((i) => i.key === last.key);
      if (it) it.decision = dec.decisions[last.key] || null;
      S.decided = doneCount(); scheduleRefresh(); paintHistory();
      const at = visible().findIndex((i) => i.key === last.key);
      if (at >= 0) S.idx = at;
      paintRight(); toast("Undone.");
    } catch (e) { toast(e.message); }
  }

  function renderOut(s = {}) {
    const t = wordClip(s.text, 600);
    switch (s.kind) {
      case "heading": return h("div", { class: `out-h lv${Math.min(s.level || 2, 5)}` }, t || "(heading)");
      case "para": return h("p", { class: "out-p" }, t || "(body text)");
      case "picture": return h("div", { class: "out-pic" }, "▣ Picture", s.text ? h("div", { class: "muted small" }, `Description: ${s.text}`) : "");
      case "decor": return h("div", { class: "out-decor" }, "Left out of the book (decoration)");
      case "char": return h("div", {}, h("span", { class: "out-char" }, s.text), h("span", { class: "muted small" }, ` ${s.label || ""}`));
      case "split": {
        const lines = String(s.text || "").split("\n");
        return h("div", {}, h("p", { class: "out-p" }, wordClip(lines.slice(0, s.line).join(" "), 300)), h("p", { class: "out-p" }, wordClip(lines.slice(s.line).join(" "), 300)));
      }
      case "join": return h("p", { class: "out-p" }, t ? `${t} …` : "One paragraph (the next one is added to it)");
      case "table": return h("div", { class: "out-pic" }, "▦ Table", s.text ? h("span", { class: "muted small" }, ` · ${s.text}`) : "");
      default: return t ? h("p", { class: "out-p" }, t) : h("div", { class: "muted small" }, "No visible change in the book.");
    }
  }

  // Text on one line, cut at a word (never mid-word), with "…" when cut.
  function wordClip(v, n) {
    const t = String(v || "").replace(/\s+/g, " ").trim();
    if (t.length <= n) return t;
    const cut = t.slice(0, n), at = cut.lastIndexOf(" ");
    return `${(at > n * 0.6 ? cut.slice(0, at) : cut).replace(/[\s,;:]+$/, "")} …`;
  }

  // The problem area with some of the page around it, cut from the sharp page picture and
  // outlined. Sized with percentages, so it fills the card at any width.
  function cropView(item) {
    const b = item.box, pg = b && S.pages[b.page - 1];
    if (!b || !pg) return item.crop && h("img", { class: "cropimg", src: `/api/jobs/${id}/crops/${item.crop.split("/").pop()}`, alt: "The problem area, cut from the page", dataset: { testid: "crop" } });
    const padX = 24, padY = 28;
    const rx0 = Math.max(0, Math.min(b.x0 - padX, pg.width * 0.08)), rx1 = Math.min(pg.width, Math.max(b.x1 + padX, pg.width * 0.92));
    const ry0 = Math.max(0, b.y0 - padY), ry1 = Math.min(pg.height, Math.max(b.y1 + padY, b.y0 + 90));
    const rw = rx1 - rx0, rh = ry1 - ry0, pc = (v, of) => `${(100 * v) / of}%`;
    return h("figure", { class: "crop", dataset: { testid: "crop" } },
      h("div", { class: "cropwin", style: `aspect-ratio:${rw} / ${rh}` },
        h("img", { src: `/api/jobs/${id}/pages/${b.page}/image?scale=3`, alt: "The problem area on the page", style: `width:${pc(pg.width, rw)};left:${pc(-rx0, rw)};top:${pc(-ry0, rh)}` }),
        h("div", { class: "cropmark", style: `left:${pc(b.x0 - rx0, rw)};top:${pc(b.y0 - ry0, rh)};width:${pc(b.x1 - b.x0, rw)};height:${pc(b.y1 - b.y0, rh)}` })),
      h("figcaption", { class: "muted small" }, `Page ${item.page_label || item.page}: the outlined area. The whole page is on the left.`));
  }

  // The little form a few answers need (a description, a level, new names). Returns {el, getFix}.
  function formFor(item, a) {
    const u = item.unit, cur = item.current || {};
    if (a.form === "alt") {
      const ta = h("textarea", { placeholder: "What does the picture show? Write it for a reader who cannot see it.", "aria-label": "Description", dataset: { testid: "alt-text" } }, cur.alt_text || "");
      return { el: ta, getFix: () => (ta.value.trim() ? { op: "alt_text", unit: u, text: ta.value.trim() } : null) };
    }
    if (a.form === "heading") {
      const sel = h("select", { "aria-label": "Heading level", dataset: { testid: "heading-level" } },
        h("option", { value: "none" }, "Not a heading"), [1, 2, 3, 4, 5].map((n) => h("option", { value: n, selected: cur.type === "heading" ? cur.level === n : n === 2 }, `Heading, level ${n}`)), h("option", { value: "chapter" }, "Start of a new chapter"));
      return { el: h("label", { class: "field" }, h("span", {}, "What is it?"), sel), getFix: () => (sel.value === "none" ? { op: "heading_remove", unit: u } : sel.value === "chapter" ? { op: "new_chapter", unit: u } : { op: "heading_set", unit: u, level: +sel.value }) };
    }
    if (a.form === "role") {
      const isHead = cur.type === "heading", isPara = cur.type === "paragraph";
      const sel = h("select", { "aria-label": "Role", dataset: { testid: "role-select" } }, h("option", { value: "" }, "— choose —"),
        isHead && h("option", { value: "body" }, "Body paragraph (not a heading)"), [1, 2, 3, 4].map((n) => h("option", { value: `h${n}` }, `Heading, level ${n}`)),
        h("option", { value: "chapter" }, "Start of a new chapter"), isPara && h("option", { value: "join" }, "Join with the next paragraph"));
      return { el: h("label", { class: "field" }, h("span", {}, "Change it to"), sel), getFix: () => { const v = sel.value; return !v ? null : v === "body" ? { op: "heading_remove", unit: u } : v === "chapter" ? { op: "new_chapter", unit: u } : v === "join" ? { op: "join_next", unit: u } : { op: "heading_set", unit: u, level: +v[1] }; } };
    }
    if (a.form === "split") {
      const lines = linesOf(item);
      let at = 1;
      const rows = lines.map((line, n) => n === 0 ? h("div", { class: "splitline muted" }, line) :
        h("label", { class: "splitline" }, h("input", { type: "radio", name: "split-at", value: n, checked: n === 1, dataset: { testid: "split-at" },
          onchange: () => { at = n; S.showOut?.({ kind: "split", text: item.current.text, line: n }); } }), " ", h("span", {}, "New paragraph starts here: "), h("b", {}, line)));
      return { el: h("div", { class: "field" }, h("span", {}, "Where does the new paragraph start?"), rows),
        getFix: () => ({ op: "split", unit: u, line: at }) };
    }
    if (a.form === "author") return authorEditor(item);
    return { el: h("span"), getFix: () => null };
  }

  function card(item, list) {
    const err = h("div"), formHolder = h("div");
    const note = h("textarea", { placeholder: "Note (optional)", "aria-label": "Note", dataset: { testid: "note" }, style: "min-height:44px" }, item.decision?.note || "");
    const answers = answersFor(item);
    const suggested = answers.find((a) => a.suggested);
    const outBox = h("div", { class: "outbox", dataset: { testid: "outbox" } });
    const showOut = (spec) => clear(outBox).append(h("div", { class: "kind" }, "How it will look in the book"), renderOut(spec));
    S.showOut = showOut;
    showOut((suggested || answers[0])?.preview);
    const d = item.decision, byAssistant = assistantDecided(item);
    const help = helpFor(item);
    let busy = false;

    async function save(a) {
      if (busy) return; busy = true; clear(err);
      try { if (await decide(item, a, note.value)) { S.lastGroup = null; S.offer = makeOffer(item, a); afterDecision(list); } } catch (e) { err.append(errBox(e)); } finally { busy = false; }
    }
    function open(a) {
      const f = formFor(item, a);
      clear(formHolder).append(h("div", { class: "formbox" }, f.el, h("div", { class: "row", style: "margin-top:8px" },
        h("button", { class: "primary", dataset: { testid: "confirm-fix" }, onclick: () => { const fx = f.getFix(); if (!fx) { clear(err).append(errBox({ message: "Fill in the answer first." })); return; } save({ action: "fix", fix: fx }); } }, "Confirm"),
        h("button", { class: "small", dataset: { testid: "cancel-fix" }, onclick: () => clear(formHolder) }, "Cancel"))));
    }
    const run = (a) => (a.form ? open(a) : save(a));
    const answerBtns = answers.map((a, n) => h("button", {
      class: `answer${a.suggested ? " suggested" : ""}`, title: a.hint,
      dataset: { testid: a.form ? `fix-${a.form}` : a.action === "accept" ? "accept" : `answer-${n + 1}` },
      onmouseenter: () => showOut(a.preview), onfocus: () => showOut(a.preview), onmouseleave: () => showOut((suggested || answers[0])?.preview),
      onclick: () => run(a),
    }, h("span", { class: "key" }, String(n + 1)), h("span", { class: "alabel" }, a.label), h("span", { class: "ahint" }, a.hint), a.suggested && !byAssistant && h("span", { class: "tag" }, "Suggested")));
    const skipBtn = h("button", { class: "small", dataset: { testid: "skip" }, title: "Leave it for now (recorded as skipped).", onclick: () => save({ action: "skip" }) }, h("span", { class: "key" }, "S"), " Not sure, skip");
    const confirmBtn = byAssistant && h("button", { class: "primary big", dataset: { testid: "confirm" }, onclick: () => save({ action: d.action, fix: d.fix }) },
      h("span", { class: "key" }, "↵"), ` Confirm: ${d.action === "fix" ? "keep the change" : d.action === "skip" ? "keep skipped" : "yes, as it is"}`);
    S.keys = { answers, run, suggested, confirm: byAssistant ? () => save({ action: d.action, fix: d.fix }) : null, skip: () => save({ action: "skip" }) };
    if (!byAssistant && answers[0]?.openAtStart && !d) open(answers[0]);

    const cur = item.current;
    const raw = h("div", { class: "small muted" },
      h("div", {}, `Kind: ${item.kind} · Reason from the tool: ${item.reason}`), h("div", {}, `Where from: ${item.source} · page ${item.page ?? "–"}${item.page_label ? ` (printed ${item.page_label})` : ""} · ${item.severity === "must_check" ? "must check" : "to review"}`),
      cur && h("div", {}, `Current result: ${cur.type}${cur.role ? ` · ${cur.role}` : ""}${cur.level ? ` · level ${cur.level}` : ""}${cur.decorative ? " · decoration" : ""}`));
    return h("div", { class: `panel qcard k-${String(item.kind).replace(/[^a-z_]/g, "")}`, dataset: { testid: "item-card", key: item.key, kind: item.kind } },
      h("div", { class: "row" }, h("span", { class: "kicon", "aria-hidden": "true" }, itemKindName(item) === "Paragraph" ? "¶" : ICON[item.kind] || "•"), h("span", { class: "kind" }, itemKindName(item)),
        confirmed(item) ? badge("pass", "done") : byAssistant ? badge("warn", "needs your confirm") : item.severity === "must_check" ? badge("fail", "must check") : badge("warn", "to review"), h("div", { class: "grow" }), h("span", { class: "muted small" }, `page ${item.page ?? "–"}`)),
      h("h2", { class: "question", dataset: { testid: "question" } }, question(item)),
      help && h("div", { class: "checkline", dataset: { testid: "what-to-check" } }, help[0]),
      cropView(item),
      outBox,
      d && h("div", { class: `banner ${byAssistant ? "warn" : "info"} small`, dataset: { testid: "decided" } },
        `${byAssistant ? "Suggested by" : "Answered by"} ${d.who}: ${decisionWords(d)} · ${when(d.at)}.`, byAssistant ? " Please confirm or change it." : "", d.note ? ` Note: ${d.note}` : ""),
      confirmBtn,
      h("div", { class: "answers" }, answerBtns),
      suggested && h("div", { class: "muted small", dataset: { testid: "why" } }, `Why this is suggested: ${why(item)}`),
      formHolder, err,
      h("div", { class: "row", style: "margin-top:8px" }, skipBtn, h("div", { class: "grow" }),
        h("button", { class: "small", dataset: { testid: "prev-item" }, onclick: () => { S.idx = Math.max(0, S.idx - 1); paintRight(); } }, "◀ Previous"),
        h("button", { class: "small", dataset: { testid: "open-browse" }, title: "Show this page and block in Browse pages (B)", onclick: () => openInBrowse(item) }, h("span", { class: "key" }, "B"), " Open in Browse"),
        h("button", { class: "small", dataset: { testid: "next-item" }, onclick: () => { S.idx = Math.min(list.length - 1, S.idx + 1); paintRight(); } }, "Next ▶")),
      h("div", { class: "helpline" }, help && h("div", {}, h("b", {}, "What happens: "), help[1])),
      h("details", { class: "small" }, h("summary", {}, "Add a note"), note),
      h("details", { class: "small", dataset: { testid: "details" } }, h("summary", {}, "Details"), raw),
      h("div", { class: "muted small keyhint" }, `Keys: 1–${answers.length} answer · Enter = suggested or Confirm · S skip · ← → move · U undo · B open in Browse`));
  }

  // After an answer: the same answer for the open items of the same kind and pattern, with the
  // list to untick. A change is repeated only where it names the answered block alone (heading level,
  // not a heading, new chapter, join); anything else is offered as Looks right / Skip only.
  const REPEATABLE = new Set(["heading_set", "heading_remove", "new_chapter", "join_next"]);
  function makeOffer(item, a) {
    const fix = a.action === "fix" ? a.fix : null;
    if (a.action === "fix" && !(fix?.op && REPEATABLE.has(fix.op) && fix.unit === item.unit && !fix.units)) return null;
    const key = similarKey(item);
    const same = S.items.filter((i) => i.key !== item.key && !confirmed(i) && similarKey(i) === key && (a.action !== "fix" || i.unit));
    if (!same.length) return null;
    return { action: a.action, fix, label: a.label || (a.action === "skip" ? "Skip" : "Looks right"), kind: item.kind, same, ticked: new Set(same.map((i) => i.key)) };
  }
  const OFFER_WORDS = { accept: "kept as it is", skip: "skipped", fix: "changed the same way" };
  function offerPanel() {
    const o = S.offer;
    const apply = async () => {
      const picked = o.same.filter((i) => o.ticked.has(i.key));
      if (!picked.length) { S.offer = null; paintRight(); return; }
      if (!S.who) { whoInput.focus(); toast("Enter your name first."); return; }
      try {
        const items = picked.map((it) => ({ key: it.key, item_kind: it.kind, item: snapOf(it), ...(o.fix ? { fix: { ...o.fix, unit: it.unit } } : {}) }));
        const res = await post(`/api/jobs/${id}/decisions/bulk`, { who: S.who, action: o.action, items, group: true });
        const at = new Date().toISOString();
        picked.forEach((it) => { it.decision = { action: o.action, fix: o.fix ? { ...o.fix, unit: it.unit } : null, note: "", who: S.who, at }; });
        S.undo.push({ group: res.group, count: picked.length });
        S.offer = null; S.decided = doneCount();
        if (o.fix) scheduleRefresh();
        const dec = await get(`/api/jobs/${id}/decisions`); S.edits = dec.edits; paintHistory();
        toast(`The same answer was saved for ${picked.length} item${picked.length === 1 ? "" : "s"}. Press U or “Undo the group” to take them all back.`);
        S.lastGroup = { group: res.group, count: picked.length };
        paintRight();
      } catch (e) { toast(e.message); }
    };
    o.apply = apply;
    const n = () => o.same.filter((i) => o.ticked.has(i.key)).length;
    const applyBtn = h("button", { class: "primary small", dataset: { testid: "offer-apply" }, onclick: apply });
    const sync = () => { applyBtn.textContent = `Do the same for ${n()} ticked (A)`; applyBtn.disabled = !n(); };
    sync();
    return h("div", { class: "panel similar-offer", dataset: { testid: "offer" } },
      h("div", {}, h("b", {}, `${o.same.length} open item${o.same.length === 1 ? "" : "s"} of the same kind and pattern.`), ` Give them the same answer (${OFFER_WORDS[o.action]})? Untick the ones that differ.`),
      h("div", { class: "simlist" }, o.same.slice(0, 200).map((i) => h("label", { class: "row" },
        h("input", { type: "checkbox", checked: true, "aria-label": `Item on page ${i.page}`, dataset: { testid: "offer-pick" }, onchange: (ev) => { ev.target.checked ? o.ticked.add(i.key) : o.ticked.delete(i.key); sync(); } }),
        ` p.${i.page ?? "–"} `, h("span", { class: "muted small" }, clipText(i.current?.text || i.reason || "", 70))))),
      h("div", { class: "row", style: "margin-top:6px" }, applyBtn, h("button", { class: "small", dataset: { testid: "offer-dismiss" }, onclick: () => { S.offer = null; paintRight(); } }, "No thanks (Esc)")));
  }
  function groupBar() {
    const g = S.lastGroup;
    if (!g) return null;
    return h("div", { class: "banner info small row", dataset: { testid: "group-bar" } }, `Saved for ${g.count} similar item${g.count === 1 ? "" : "s"}.`, h("div", { class: "grow" }),
      h("button", { class: "small", dataset: { testid: "undo-answer-group" }, onclick: () => undoGroupDecisions(g.group) }, "Undo the group (U)"));
  }
  async function undoGroupDecisions(group) {
    try {
      await del(`/api/jobs/${id}/decision-groups/${group}?who=${encodeURIComponent(S.who || "")}`);
      S.undo = S.undo.filter((u) => u.group !== group); S.lastGroup = null;
      const d = await get(`/api/jobs/${id}/review`); Object.assign(S, { items: d.items, total: d.total, stale: d.stale });
      const dec = await get(`/api/jobs/${id}/decisions`); S.edits = dec.edits;
      S.decided = doneCount(); scheduleRefresh(); paintHistory(); paintRight(); toast("The group was undone.");
    } catch (e) { toast(e.message); }
  }
  const clipText = (s, n) => { s = String(s).replace(/\s+/g, " "); return s.length > n ? `${s.slice(0, n - 1)}…` : s; };

  function authorEditor(item) {
    const m = (k) => (item.reason.match(new RegExp(`${k}='([^']*)'`)) || [])[1] || "";
    const box = { first: h("input", { type: "text", value: m("firstname"), "aria-label": "First name", dataset: { testid: "au-first" } }), sur: h("input", { type: "text", value: m("surname"), "aria-label": "Surname", dataset: { testid: "au-sur" } }), deg: h("input", { type: "text", value: m("degrees"), "aria-label": "Degrees", dataset: { testid: "au-deg" } }) };
    let index = null;
    get(`/api/jobs/${id}/details`).then((d) => { index = d.details.authors.findIndex((a) => a.firstname === m("firstname") && a.surname === m("surname")); }).catch(() => {});
    return { el: h("div", { class: "row" }, h("label", {}, "First name ", box.first), h("label", {}, "Surname ", box.sur), h("label", {}, "Degrees ", box.deg)),
      getFix: () => (box.sur.value.trim() ? { author: index ?? -1, firstname: box.first.value, surname: box.sur.value, degrees: box.deg.value } : null) };
  }

  // Keyboard: 1-3 answer, Enter = suggested / Confirm, S skip, arrows move, U undo.
  const onKey = (ev) => {
    if (S.mode !== "queue" || ev.ctrlKey || ev.metaKey || ev.altKey) return;
    const t = ev.target, tag = t?.tagName;
    const typing = tag === "TEXTAREA" || tag === "SELECT" || (tag === "INPUT" && t.type !== "checkbox");
    if (S.offer && !typing) {
      if (ev.key === "a" || ev.key === "A") { ev.preventDefault(); S.offer.apply?.(); return; }
      if (ev.key === "Escape") { ev.preventDefault(); S.offer = null; paintRight(); return; }
    }
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    const K = S.keys; if (!K) return;
    const list = visible();
    if (/^[1-4]$/.test(ev.key)) { const a = K.answers[+ev.key - 1]; if (a) { ev.preventDefault(); K.run(a); } }
    else if (ev.key === "Enter" && tag !== "BUTTON" && tag !== "A") { ev.preventDefault(); if (K.confirm) K.confirm(); else if (K.suggested) K.run(K.suggested); }
    else if (ev.key === "s" || ev.key === "S") { ev.preventDefault(); K.skip(); }
    else if (ev.key === "ArrowLeft") { ev.preventDefault(); S.idx = Math.max(0, S.idx - 1); paintRight(); }
    else if (ev.key === "ArrowRight") { ev.preventDefault(); S.idx = Math.min(list.length - 1, S.idx + 1); paintRight(); }
    else if (ev.key === "u" || ev.key === "U") { ev.preventDefault(); undoLast(); }
    else if (ev.key === "b" || ev.key === "B") { ev.preventDefault(); const it = list[S.idx]; if (it) openInBrowse(it); }
  };
  document.addEventListener("keydown", onKey);

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
      scheduleRefresh();
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
    if (S.focusUnit) {
      const row = rowEls.get(S.focusUnit);
      S.focusUnit = null;
      if (row) {
        row.el.classList.add("focused");
        const u = data.units.find((x) => rowEls.get(x.id) === row);
        if (u?.box) { S.hl = u.box; paintPage(); }
        row.el.scrollIntoView?.({ block: "center" });
      }
    }
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
      append(row, u.image && h("div", { class: "small muted" }, `Picture: ${u.image}`), h("div", { class: "row" }, ta,
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
        h("span", {}, h("input", { type: "text", style: "width:90px", placeholder: "Number", "aria-label": "Chapter number", dataset: { testid: "chapter-number" } }), " ", h("button", { class: "small", dataset: { testid: "new-chapter" }, onclick: (ev) => { const n = ev.target.parentNode.querySelector("input").value.trim(); edit({ op: "new_chapter", unit: u.id, ...(n ? { number: n } : {}) }); } }, "Start a new chapter here")),
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
      const num = h("input", { type: "text", style: "width:90px", value: u.number || "", placeholder: "Number", "aria-label": "Number", dataset: { testid: "heading-number" } });
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
      h("td", {}, e.group && h("button", { class: "small", dataset: { testid: "undo-group" }, onclick: async () => { try { const res = await del(`/api/jobs/${id}/groups/${e.group}?who=${encodeURIComponent(S.who || e.who)}`); scheduleRefresh();
        if (S.mode === "browse" && S.afterChange) { await S.afterChange(res); toast(`Undone: ${res.undone} changes.`); return; }
        const dec = await get(`/api/jobs/${id}/decisions`); S.edits = dec.edits; paintHistory(); paintRight(); } catch (x) { toast(x.message); } } }, "Undo the group"),
      h("button", { class: "small", onclick: async () => { try { const res = await del(`/api/jobs/${id}/decisions/${e.id}?who=${encodeURIComponent(S.who || e.who)}`); scheduleRefresh();
        if (S.mode === "browse" && res.pages && S.afterChange) { await S.afterChange(res); toast("Undone."); return; }
        const dec = await get(`/api/jobs/${id}/decisions`); S.edits = dec.edits; paintHistory(); paintRight(); } catch (x) { toast(x.message); } } }, "Undo")))))));
  }
  const NAMES = { heading_set: "Heading level", heading_remove: "Not a heading", new_chapter: "New chapter", join_next: "Join with next", unjoin: "Undo join", split: "Split paragraph", make_list: "Make a list", alt_text: "Picture description", decorative: "Decoration flag", char: "Character", heading_kind: "Kind of heading", heading_number: "Number", heading_text: "Title text", heading_attach: "Belongs to the chapter before",
    list_set: "List", list_level: "List level", box: "Box", caption: "Figure caption", table_make: "Table", table_text: "Table text", footnote: "Footnote",
    paragraph: "Body paragraph", chapter_authors: "Chapter authors", question: "MCQ question", bibliography: "Bibliography entries", index_entries: "Index entries",
    glossary: "Glossary entries", not_content: "Not book content", merge: "Merge", move: "Move", swap_columns: "Swap columns", unwrap: "Unwrap", table_split: "Split table" };
  const describe = (e) => `${e.group ? "[same as another change] " : ""}${NAMES[e.op] || e.op}${e.op === "box" && e.kind !== "box" ? ` (${e.kind.replace("_", " ")})` : ""}${e.list_type ? ` (${e.list_type})` : ""}${e.direction ? ` ${e.direction}` : ""}${e.scope === "follow" ? " · and what follows" : ""}${e.level ? ` ${e.level}` : ""}${e.line ? ` (line ${e.line + 1})` : ""}${e.text ? `: ${e.text.slice(0, 40)}` : ""}${e.kind ? `: ${e.kind.replace("_", " ")}` : ""}${e.number ? ` (${e.number})` : ""}${e.before ? ` (was: ${e.before.replace(/\s+/g, " ").slice(0, 40)})` : ""}`;

  paintHistory();
  paintRight();
  paintPage();
  if (S.mode === "browse") paintRight();
  if (S.stale) scheduleRefresh(0);
  onLeave(() => { alive = false; window.removeEventListener("scroll", fitPane); window.removeEventListener("resize", fitPane); clearTimeout(refreshTimer); document.removeEventListener("keydown", onKey); });
}
