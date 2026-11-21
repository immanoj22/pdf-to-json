// Browse: one clean line per block, one "Edit" per block, PDF and blocks linked both ways.
// Every save goes preview -> confirm (a one-line preview), with Undo; the server writes the
// audit log. The edits themselves are the same ops the book model already has (buildEdit).
import { clear, del, errBox, get, h, post, spinner, toast } from "./util.js";
import { restoreSection } from "./view_restore.js";
import { addControl, removeControl, textControl } from "./view_addremove.js";
import { buildEdit, similarPanel } from "./view_edit.js";

const BIG_ROLES = ["part", "chapter", "front_section_title", "rear_section_title"];
export function typeName(u) {
  switch (u.type) {
    case "heading": return BIG_ROLES.includes(u.role) ? "Heading" : "Section heading";
    case "paragraph": return "Paragraph";
    case "list": return "List";
    case "list_item": return "List item";
    case "table": return "Table";
    case "figure": case "equation": return "Picture";
    case "box": return "Box";
    case "caption": return "Caption";
    case "footnote": return "Footnote";
    default: return u.type.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
  }
}

// Text cut at a word (never mid-word), with "…" when cut.
export function wordClip(v, n) {
  const t = String(v || "").replace(/\s+/g, " ").trim();
  if (t.length <= n) return t;
  const cut = t.slice(0, n), at = cut.lastIndexOf(" ");
  return `${(at > n * 0.6 ? cut.slice(0, at) : cut).replace(/[\s,;:]+$/, "")} …`;
}

const listName = (u) => (u.list_type === "numbered" ? "Numbered list" : "Bulleted list");
function describe(r) {
  if (r.type === "list") return `${listName(r)} of ${(r.items || []).length} item${(r.items || []).length === 1 ? "" : "s"}`;
  if (r.type === "list_item") return `List item${r.item_level ? ` at level ${r.item_level}` : ""} “${wordClip(r.clean || r.text, 50)}”`;
  if (r.type === "table") return `Table, ${r.rows || 0} rows`;
  if (r.type === "figure" || r.type === "equation") return "Picture";
  const t = wordClip(r.clean || r.text, 60);
  return `${typeName(r)}${r.type === "heading" && r.level ? ` (level ${r.level})` : ""}${t ? ` “${t}”` : ""}`;
}
const visibleRows = (rows) => rows.filter((r) => !(r.type === "list_item" && rows.some((p) => p.id === r.parent && p.type === "list")));

// "Before … → After …" in one line, from a preview response.
export function previewLine(p, ids) {
  const pg = p.pages.find((x) => x.before.some((r) => ids.includes(r.id))) || p.pages[0];
  let line = "No visible change on the page.";
  if (pg) {
    const sig = new Map(pg.before.map((r) => [r.id, JSON.stringify(r)]));
    const after = new Set(pg.after.map((r) => r.id));
    const items = pg.after.filter((r) => r.type === "list_item" && ids.includes(r.id) && sig.get(r.id) !== JSON.stringify(r));
    const changed = [...items, ...visibleRows(pg.after.filter((r) => sig.get(r.id) !== JSON.stringify(r)))].filter((r, i, a) => !(r.type === "list" && items.length && a.some((x) => x.type === "list_item")));
    const gone = visibleRows(pg.before.filter((r) => !after.has(r.id)));
    const before = pg.before.filter((r) => (ids.includes(r.id) && (r.type !== "list" || !items.length)) || gone.some((g) => g.id === r.id)).filter((r) => r.type === "list_item" || visibleRows([r]).length);
    const reordered = pg.before.map((r) => r.id).join() !== pg.after.map((r) => r.id).join();
    const result = changed.slice(0, 3).map(describe).join("  +  ")
      || (gone.length ? "taken out of the book" : reordered ? "moves to its new place in the reading order" : "same text, new settings");
    line = `${before.slice(0, 3).map(describe).join("  +  ")}  →  ${result}`;
  }
  if (p.headings?.length) line += `   ·   ${p.headings.length} heading${p.headings.length === 1 ? "" : "s"} after it change${p.headings.length === 1 ? "s" : ""} level`;
  return line;
}

const KINDS = [["part", "Part"], ["chapter", "Chapter"], ["section", "Section"], ["front_matter", "Front matter"], ["back_matter", "Back matter"]];
const kindOf = (u) => ({ part: "part", chapter: "chapter", front_section_title: "front_matter", rear_section_title: "back_matter" }[u.role] || "section");
// "Turn this and the next paragraphs into …": [value, label] (value is a change of view_edit.js)
const TURN = [
  ["to_paragraph", "Paragraph"],
  ["list_bulleted", "Bulleted list"], ["list_numbered", "Numbered list"], ["quote", "Quote"], ["pull_quote", "Pull quote"],
  ["box", "Box with a title"], ["box_plain", "Box without a title"], ["table_make", "Table"], ["footnote", "Footnote"],
  ["caption", "Figure caption"], ["table_title", "Table title"], ["table_note", "Table note"], ["chapter_authors", "Chapter authors"],
  ["question", "MCQ question"], ["bibliography", "Bibliography entry"], ["index_entries", "Index entry"], ["glossary", "Glossary term and definition"],
  ["not_running_head", "Not book content: running head"], ["not_running_foot", "Not book content: running foot"],
  ["not_folio", "Not book content: page number"], ["not_production_mark", "Not book content: printer mark"],
];
const PARA = ["to_paragraph"];
const SPLITTABLE = new Set(["paragraph", "list_item", "footnote"]);  // "Split here" and "join with previous" work on these
const SELECTABLE = new Set(["paragraph", "heading", "footnote", "caption", "list_item"]);  // Shift/Ctrl+click select these
const ONE_ONLY = new Set(["footnote", "caption", "table_title", "table_note"]);

// B: {id, S, right, left, wrap, rail, root, whoInput, paintPage, goPage, scheduleRefresh, paintHistory}
export function initBrowse(B) {
  const { id, S } = B;
  const STAMP = (n, scale) => `/api/jobs/${id}/pages/${n}/image?scale=${scale}`;
  let rows = [], token = 0, activeId = null, openId = null, hotId = null, searchTimer = null;
  const undoStack = [];
  const rowEls = new Map();
  // Blocks picked with Shift/Ctrl+click (id -> page): the pick stays when the page turns, so a
  // paragraph cut by a page break can be picked on both pages; M merges them.
  const sel = new Map();
  let anchorSel = null, splitMode = false, splitFor = null;
  // Full text: a global switch (remembered per user in this browser), the block that is selected or
  // being edited, and a Show full text / Collapse toggle on each card (which wins over the other two).
  const fullKey = () => `browseFullText:${(S.who || "").toLowerCase()}`;
  const readFull = () => { try { return localStorage.getItem(fullKey()) === "1"; } catch { return false; } };
  let fullOn = readFull();
  const cardFull = new Map();
  const isFull = (uid) => (cardFull.has(uid) ? cardFull.get(uid) : fullOn || uid === activeId || uid === openId);
  const refreshCard = (uid) => rowEls.get(uid)?.refresh();

  // ---------------------------------------------------------------- toolbar
  const pageNo = h("input", { type: "number", min: "1", max: String(S.pages.length), "aria-label": "Page number", style: "width:64px", dataset: { testid: "browse-page-no" },
    onchange: () => B.goPage(+pageNo.value) });
  const ofText = h("span", { class: "muted small" });
  const search = h("input", { type: "search", placeholder: "Search the book…  ( / )", "aria-label": "Search the book", style: "width:230px", dataset: { testid: "search" },
    oninput: () => { clearTimeout(searchTimer); searchTimer = setTimeout(runSearch, 350); },
    onkeydown: (ev) => { if (ev.key === "Enter") { clearTimeout(searchTimer); runSearch(); } if (ev.key === "Escape") { results.hidden = true; search.blur(); } } });
  const results = h("div", { class: "searchres", hidden: true, dataset: { testid: "search-results" } });
  const fullBtn = h("button", { class: "small", title: "Show the whole text of every block instead of cutting it with …", dataset: { testid: "browse-full-toggle" },
    onclick: () => {
      fullOn = !fullOn; cardFull.clear();
      try { localStorage.setItem(fullKey(), fullOn ? "1" : "0"); } catch { /* private window */ }
      paintFullBtn(); for (const k of rowEls.keys()) refreshCard(k);
    } });
  const selText = h("span", { dataset: { testid: "sel-count" } });
  const selBar = h("div", { class: "selbar", hidden: true, dataset: { testid: "selbar" } }, selText,
    h("button", { class: "small primary", title: "Merge the picked blocks into one paragraph (M)", dataset: { testid: "merge-selected" }, onclick: () => mergeSelected() }, "Merge into one paragraph (M)"),
    h("button", { class: "small", title: "Pick nothing (Esc)", dataset: { testid: "sel-clear" }, onclick: () => clearSel() }, "Clear"),
    h("span", { class: "muted small" }, "Shift+click = range · Ctrl+click = add or remove"));
  function paintSel() {
    selBar.hidden = !sel.size;
    const pages = [...new Set(sel.values())].sort((a, b) => a - b);
    selText.textContent = `${sel.size} selected${pages.length > 1 ? ` (pages ${pages[0]}–${pages[pages.length - 1]})` : ""}`;
    for (const [k, v] of rowEls) v.el.classList.toggle("sel", sel.has(k));
  }
  function clearSel() { sel.clear(); anchorSel = null; paintSel(); }
  function toggleSel(u) {
    if (!SELECTABLE.has(u.type)) return;
    if (sel.has(u.id)) sel.delete(u.id); else sel.set(u.id, S.page);
    anchorSel = u.id; paintSel();
  }
  function rangeSel(u) {
    if (!SELECTABLE.has(u.type)) return;
    const vis = visibleRows(rows).filter((r) => SELECTABLE.has(r.type));
    const from = vis.findIndex((r) => r.id === (anchorSel && rowEls.has(anchorSel) ? anchorSel : activeId)), to = vis.findIndex((r) => r.id === u.id);
    if (from < 0 || to < 0) { toggleSel(u); return; }
    for (const r of vis.slice(Math.min(from, to), Math.max(from, to) + 1)) sel.set(r.id, S.page);
    anchorSel = u.id; paintSel();
  }
  async function mergeSelected() {
    if (sel.size < 2) { toast("Pick at least two blocks first: Shift+click or Ctrl+click."); return; }
    const ok = await quickSave({ op: "merge", units: [...sel.keys()] }, `${sel.size} blocks merged into one paragraph`);
    if (ok) clearSel();
  }
  const paintFullBtn = () => { fullBtn.textContent = `Full text: ${fullOn ? "on" : "off"}`; fullBtn.setAttribute("aria-pressed", String(fullOn)); };
  paintFullBtn();
  const undoBtn = h("button", { class: "small", disabled: true, dataset: { testid: "undo-last" }, onclick: () => undoLast() }, "Undo");
  const status = h("div", { class: "bstatus", hidden: true, dataset: { testid: "status" } });
  const fitBtn = h("button", { class: "small", title: "Fit the page to the width of this pane", dataset: { testid: "browse-zoom-fit" }, onclick: () => { S.fit = true; B.paintPage(); } }, "Fit width");
  const toolbar = h("div", { class: "btool", dataset: { testid: "browse-toolbar" } },
    h("button", { title: "Previous page (←)", "aria-label": "Previous page", dataset: { testid: "browse-prev" }, onclick: () => B.goPage(S.page - 1) }, "◀"),
    pageNo, ofText,
    h("button", { title: "Next page (→)", "aria-label": "Next page", dataset: { testid: "browse-next" }, onclick: () => B.goPage(S.page + 1) }, "▶"),
    h("span", { class: "sep" }), fitBtn,
    h("button", { class: "small", "aria-label": "Zoom out", dataset: { testid: "browse-zoom-out" }, onclick: () => B.zoomBy(-0.2) }, "−"),
    h("button", { class: "small", "aria-label": "Zoom in", dataset: { testid: "browse-zoom-in" }, onclick: () => B.zoomBy(0.2) }, "+"),
    h("span", { class: "sep" }), h("span", { class: "searchbox" }, search, results), h("div", { class: "grow" }), fullBtn, undoBtn);

  async function runSearch() {
    const q = search.value.trim();
    if (q.length < 2) { results.hidden = true; return; }
    results.hidden = false; clear(results).append(h("div", { class: "muted small pad" }, spinner("Searching…")));
    let d;
    try { d = await get(`/api/jobs/${id}/search?q=${encodeURIComponent(q)}`); } catch (e) { clear(results).append(errBox(e)); return; }
    if (search.value.trim() !== q) return;
    clear(results);
    if (!d.hits.length) { results.append(h("div", { class: "muted small pad" }, `“${q}” is not in this book.`)); return; }
    const at = (s) => { const i = s.toLowerCase().indexOf(q.toLowerCase()); return i < 0 ? [s] : [s.slice(0, i), h("b", {}, s.slice(i, i + q.length)), s.slice(i + q.length)]; };
    results.append(h("div", { class: "muted small pad" }, `${d.hits.length}${d.more ? "+" : ""} place${d.hits.length === 1 ? "" : "s"}`),
      ...d.hits.slice(0, 60).map((x) => h("button", { class: "hit", dataset: { testid: "search-hit", page: x.page, unit: x.unit },
        onclick: () => { results.hidden = true; S.focusUnit = x.unit; if (x.page === S.page) focusUnit(); else B.goPage(x.page); } },
        h("span", { class: "muted" }, `p.${x.page}`), " ", ...at(x.snippet))));
  }
  document.addEventListener("click", (ev) => { if (!results.contains(ev.target) && ev.target !== search) results.hidden = true; });

  // ---------------------------------------------------------------- thumbnails
  const thumbs = new Map();
  S.pages.forEach((p, i) => {
    const n = i + 1, w = 62, hgt = Math.round((w * p.height) / p.width);
    const b = h("button", { class: "thumb", title: `Page ${n}${p.label ? ` (printed ${p.label})` : ""}`, "aria-label": `Go to page ${n}`, dataset: { testid: "thumb", page: n }, onclick: () => B.goPage(n) },
      h("img", { src: STAMP(n, 0.5), loading: "lazy", alt: "", width: w, height: hgt }), h("span", {}, p.label || String(n)));
    thumbs.set(n, b);
  });
  B.rail.append(...thumbs.values());

  // ---------------------------------------------------------------- PDF overlay (blocks clickable on the page)
  const overlay = h("div", { class: "blkover", dataset: { testid: "overlay" } });
  B.wrap.append(overlay);
  function drawOverlay() {
    clear(overlay);
    if (S.mode !== "browse") return;
    const z = S.z || 1;
    for (const r of visibleRows(rows)) {
      const b = r.box; if (!b || b.page !== S.page) continue;
      overlay.append(h("div", { class: `blk${r.id === activeId ? " active" : ""}${r.id === hotId ? " hot" : ""}`, title: `${typeName(r)} — click to find it in the list`, dataset: { testid: "blk", unit: r.id },
        style: `left:${b.x0 * z}px;top:${b.y0 * z}px;width:${(b.x1 - b.x0) * z}px;height:${(b.y1 - b.y0) * z}px`,
        onmouseenter: () => hot(r.id, false), onmouseleave: () => hot(null), onclick: () => activate(r.id, true) }));
    }
  }
  function hot(unitId, scroll) {
    hotId = unitId;
    for (const [k, v] of rowEls) v.el.classList.toggle("hot", k === unitId);
    overlay.querySelectorAll(".blk").forEach((e) => e.classList.toggle("hot", e.dataset.unit === unitId));
    if (scroll && unitId) rowEls.get(unitId)?.el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  function activate(unitId, scrollList) {
    const was = activeId;
    activeId = unitId;
    if (was !== unitId) {  // a newly selected block is shown whole, whatever its toggle said before
      if (unitId) cardFull.delete(unitId);
      if (was) refreshCard(was);
      if (unitId) refreshCard(unitId);
    }
    for (const [k, v] of rowEls) v.el.classList.toggle("active", k === unitId);
    overlay.querySelectorAll(".blk").forEach((e) => e.classList.toggle("active", e.dataset.unit === unitId));
    if (scrollList) rowEls.get(unitId)?.el.scrollIntoView({ block: "center", behavior: "smooth" });
  }
  function focusUnit() {
    const u = S.focusUnit; S.focusUnit = null;
    if (!u || !rowEls.has(u)) return;
    const r = rows.find((x) => x.id === u);
    activate(u, true);
    if (r?.box) { S.hl = r.box; B.paintPage(); }
  }

  // ---------------------------------------------------------------- the list
  const holder = h("div", { dataset: { testid: "browse-list" } });
  const list = h("div", { dataset: { testid: "unit-list" } });
  const err = h("div");
  const chapters = h("details", { class: "chapters", dataset: { testid: "chapters-panel" } }, h("summary", {}, "Chapters and parts"));
  chapters.addEventListener("toggle", () => chapters.open && loadChapters());
  async function loadChapters(data) {
    clear(chapters).append(h("summary", {}, "Chapters and parts"));
    try { data = data || (await get(`/api/jobs/${id}/chapters`)).chapters; } catch (e) { chapters.append(errBox(e)); return; }
    const n = data.filter((r) => r.role === "chapter").length, p = data.filter((r) => r.role === "part").length;
    chapters.querySelector("summary").textContent = `Chapters and parts (${p} parts, ${n} chapters)`;
    chapters.append(h("table", {}, h("thead", {}, h("tr", {}, ["", "Number", "Title", "Page"].map((t) => h("th", {}, t)))),
      h("tbody", {}, data.map((r) => h("tr", { dataset: { testid: "chapter-row", role: r.role }, style: "cursor:pointer", onclick: () => B.goPage(r.page) },
        h("td", {}, r.role === "part" ? "Part" : "Chapter"), h("td", {}, (r.number || "") + (r.set_by_reviewer ? " ✎" : "")),
        h("td", { style: r.role === "part" ? "font-weight:600" : "padding-left:16px" }, r.title), h("td", {}, String(r.page)))))));
    if (!data.length) chapters.append(h("p", { class: "muted small" }, "No chapter or part yet."));
  }

  // The card text: cut at a word with "…" (collapsed) or whole (full). ``cutSeen``: something was cut.
  let cutSeen = false;
  function bodyOf(u, full) { cutSeen = false; return bodyInner(u, full); }
  function bodyInner(u, full) {
    const text = u.clean || u.text || "";
    const clip = (v, n) => {
      const t = String(v || "").replace(/\s+/g, " ").trim();
      if (full || t.length <= n) return t;
      cutSeen = true;
      return wordClip(t, n);
    };
    if (u.type === "list") {
      const items = u.items || [];
      const tag = u.list_type === "numbered" ? "ol" : "ul";
      const shown = full ? items : items.slice(0, 8);
      if (items.length > shown.length) cutSeen = true;
      return h(tag, { class: "blist" }, shown.map((i) => h("li", { style: `margin-left:${((i.level || 1) - 1) * 18}px`, dataset: { item: i.id } }, clip(i.text, 160), " ",
        h("button", { class: "small linkish", title: "Split this item: click the word where the new item starts", dataset: { testid: "split-item", item: i.id },
          onclick: (ev) => { ev.stopPropagation(); toggleSplit(u.id, i.id); } }, "Split"))),
        items.length > shown.length && h("li", { class: "muted" }, `… and ${items.length - shown.length} more item${items.length - shown.length === 1 ? "" : "s"}`));
    }
    if (u.type === "table") {
      const g = u.grid || [];
      if (g.length > 4 || g.some((r) => r.length > 5)) cutSeen = true;
      return h("div", {}, h("div", { class: "muted small" }, `${u.rows || 0} rows × ${u.cols || 0} columns`),
        h("table", { class: "mini" }, h("tbody", {}, (full ? g : g.slice(0, 4)).map((r) => h("tr", {}, (full ? r : r.slice(0, 5)).map((c) => h("td", {}, clip(c, 28))))))));
    }
    if (u.type === "figure" || u.type === "equation") {
      return h("div", {}, u.decorative ? h("span", { class: "muted" }, "Decoration — left out of the book") : u.alt_text ? clip(u.alt_text, 200) : h("span", { class: "muted" }, "No description yet"));
    }
    if (u.type === "box") return h("span", { class: "muted" }, `${u.flags?.includes("pull_quote") ? "Pull quote" : u.flags?.includes("quote") ? "Quote" : "Box"} — the blocks inside follow`);
    return h("span", { class: "btext", dataset: { testid: "btext" } }, u.number ? h("span", { class: "muted" }, `${u.number} `) : "", clip(text, 240));
  }

  function rowEl(u) {
    const holderEdit = h("div", { class: "blk-edit" });
    const edited = u.added_by ? h("span", { class: "mini added", title: "Typed in the app: this text is not in the PDF", dataset: { testid: "added-badge" } }, `added by ${u.added_by}`)
      : u.reviewer_made && h("span", { class: "mini", title: "You changed this block" }, "edited");
    const body = h("div", { class: "bbody" });
    const fullBtnCard = h("button", { class: "small", dataset: { testid: "toggle-full" }, "aria-expanded": "false",
      onclick: (ev) => { ev.stopPropagation(); cardFull.set(u.id, !isFull(u.id)); refresh(); } });
    bodyOf(u, false);
    const cuttable = cutSeen;  // is there anything to cut in the collapsed card?
    const refresh = () => {
      const full = isFull(u.id);
      body.replaceChildren(bodyOf(u, full));
      fullBtnCard.hidden = !cuttable;
      fullBtnCard.textContent = full ? "Collapse" : "Show full text";
      fullBtnCard.setAttribute("aria-expanded", String(full));
    };
    refresh();
    const editBtn = h("button", { class: "small editbtn", dataset: { testid: "edit-block" }, "aria-expanded": "false", onclick: (ev) => { ev.stopPropagation(); toggleEdit(u.id); } }, "Edit");
    const splittable = SPLITTABLE.has(u.type);
    const splitBtn = splittable && h("button", { class: "small splitbtn", title: "Cut this block in two: click the word where the new one starts (Alt+click on a word does it at once)", "aria-expanded": "false",
      dataset: { testid: "split-block" }, onclick: (ev) => { ev.stopPropagation(); toggleSplit(u.id, u.id); } }, "Split");
    const joinBtn = splittable && h("button", { class: "small joinbtn", title: "Join this block with the one before it, across a page break too (J)",
      dataset: { testid: "join-prev" }, onclick: (ev) => { ev.stopPropagation(); joinPrev(u); } }, "⤒ join with previous");
    const el = h("div", { class: `brow${sel.has(u.id) ? " sel" : ""}`, dataset: { testid: "unit", unit: u.id, type: u.type }, style: `margin-left:${Math.min(u.depth, 3) * 18}px`, tabindex: "0",
      onmouseenter: () => hot(u.id), onmouseleave: () => hot(null),
      onmousedown: (ev) => { if ((ev.shiftKey || ev.ctrlKey || ev.metaKey || ev.altKey) && !ev.target.closest("button, input, select, textarea, a, .blk-edit")) ev.preventDefault(); },  // no text selection while picking
      onclick: (ev) => {
        const inside = ev.target.closest("button, input, select, textarea, a, .blk-edit");
        if (!inside && ev.altKey) { altSplit(ev, u); return; }
        if (!inside && ev.shiftKey) { rangeSel(u); return; }
        if (!inside && (ev.ctrlKey || ev.metaKey)) { toggleSel(u); return; }
        anchorSel = u.id;
        activate(u.id, false); if (u.box) { S.hl = u.box; B.paintPage(); }
      } },
      h("div", { class: "bline" }, h("span", { class: `tbadge t-${u.type}` }, typeName(u)), body, edited, fullBtnCard, joinBtn, splitBtn, editBtn), holderEdit);
    return { el, sig: JSON.stringify(u), holderEdit, editBtn, splitBtn, refresh };
  }

  function renderRows(data) {
    const y = window.scrollY;
    rows = data;
    const shown = visibleRows(rows);
    const keep = new Set(shown.map((r) => r.id));
    for (const k of [...rowEls.keys()]) if (!keep.has(k)) rowEls.delete(k);
    list.replaceChildren(...shown.map((r) => {
      const old = rowEls.get(r.id), sig = JSON.stringify(r);
      if (old && old.sig === sig) return old.el;
      const made = rowEl(r); rowEls.set(r.id, made);
      return made.el;
    }));
    if (!shown.length) list.append(h("p", { class: "muted" }, "Nothing on this page."));
    if (openId && !rowEls.has(openId)) openId = null;
    if (openId) openPanel(openId);
    if (activeId && !rowEls.has(activeId)) activeId = null;
    activate(activeId, false);
    drawOverlay();
    window.scrollTo(window.scrollX, y);
  }

  // ---------------------------------------------------------------- the edit panel
  function toggleEdit(unitId) {
    if (openId === unitId && !splitMode) { closePanel(); return; }
    closePanel(); openId = unitId; openPanel(unitId);
    rowEls.get(unitId)?.el.scrollIntoView({ block: "nearest" });
  }
  function closePanel() {
    if (openId) { const r = rowEls.get(openId); if (r) { clear(r.holderEdit); r.editBtn.textContent = "Edit"; r.editBtn.setAttribute("aria-expanded", "false"); r.el.classList.remove("editing"); if (r.splitBtn) { r.splitBtn.textContent = "Split"; r.splitBtn.setAttribute("aria-expanded", "false"); } } }
    const was = openId;
    openId = null; splitMode = false; splitFor = null;
    if (was) refreshCard(was);
  }
  function openPanel(unitId) {
    const r = rowEls.get(unitId), u = rows.find((x) => x.id === unitId);
    if (!r || !u) return;
    r.holderEdit.replaceChildren(splitMode ? splitPanel(u) : panelFor(u));
    if (splitMode) { if (r.splitBtn) { r.splitBtn.textContent = "Close"; r.splitBtn.setAttribute("aria-expanded", "true"); } r.el.classList.add("editing"); }
    else { r.editBtn.textContent = "Close"; r.editBtn.setAttribute("aria-expanded", "true"); r.el.classList.add("editing"); }
    cardFull.delete(unitId);
    r.refresh();
  }

  // ---------------------------------------------------------------- split here, quick join, save without a panel
  // One save for the actions that have no panel (J, M, Alt+click): the same request, Undo and
  // audit log as the panel's Confirm. Resolves true when saved.
  function quickSave(edit, label) {
    if (!S.who) { B.whoInput.focus(); toast("Enter your name first (top of the page)."); return Promise.resolve(false); }
    S.chain = (S.chain || Promise.resolve()).then(async () => {
      try {
        const res = await post(`/api/jobs/${id}/edits`, { who: S.who, edit });
        const y = window.scrollY;
        closePanel();
        undoStack.push({ event: res.event, label });
        await afterChange(res);
        window.scrollTo(window.scrollX, y);
        showSaved(label, res);
        return true;
      } catch (e) { toast(e.message); return false; }
    });
    return S.chain;
  }
  // "Split": the block's words; a click on one starts the new block there (preview, Confirm).
  function toggleSplit(hostId, targetId) {
    if (openId === hostId && splitMode && splitFor === targetId) { closePanel(); return; }
    closePanel(); openId = hostId; splitMode = true; splitFor = targetId; openPanel(hostId);
    rowEls.get(hostId)?.el.scrollIntoView({ block: "nearest" });
  }
  function splitPanel(host) {
    const target = splitFor || host.id;
    const box = h("div", { class: "splitpanel", dataset: { testid: "split-panel" } }, spinner("Reading the words…"));
    const pv = h("div", { class: "pv", dataset: { testid: "preview" } });
    const perr = h("div");
    const label = (w) => `split before “${wordClip(w, 30)}”`;
    (async () => {
      let data;
      try { data = await get(`/api/jobs/${id}/units/${target}/words`); } catch (e) { clear(box).append(errBox(e)); return; }
      if (splitFor !== target) return;
      const words = data.words;
      const chosen = (w, el) => {
        box.querySelectorAll(".wsplit.chosen").forEach((x) => x.classList.remove("chosen"));
        el.classList.add("chosen");
        const edit = { op: "split_word", unit: target, offset: w.at, text: w.t };
        clear(perr); clear(pv).append(spinner("Checking what it would do…"));
        post(`/api/jobs/${id}/edits/preview`, { edit }).then((p) => {
          const go = h("button", { class: "primary small", dataset: { testid: "confirm-save" }, onclick: () => { go.disabled = true; quickSave(edit, label(w.t)).then((ok) => { if (!ok) go.disabled = false; }); } }, "Confirm");
          clear(pv).append(h("div", { class: "pvline", dataset: { testid: "preview-line" } }, previewLine(p, [target])),
            h("div", { class: "row" }, go, h("button", { class: "small", dataset: { testid: "cancel-save" }, onclick: () => { clear(pv); el.classList.remove("chosen"); } }, "Cancel")));
          go.focus();
        }).catch((e) => { clear(pv); perr.append(errBox(e)); });
      };
      const spans = words.map((w, n) => {
        const el = h("span", { class: `wsplit${n === 0 ? " first" : ""}`, title: n === 0 ? "The first word cannot start a new block" : `The new block starts with “${w.t}”`, dataset: { testid: "split-word", at: w.at } }, w.t);
        if (n) el.addEventListener("click", (ev) => { ev.stopPropagation(); chosen(w, el); });
        return el;
      });
      clear(box).append(h("div", { class: "muted small" }, "Click the word where the new block starts."),
        h("div", { class: "splitwords" }, spans.flatMap((x, n) => (n ? [" ", x] : [x]))), pv, perr);
    })();
    return box;
  }
  // Alt+click on a word of a block: split there at once (Undo is in the bar under the list).
  async function altSplit(ev, u) {
    const li = ev.target.closest("[data-item]");
    const target = li ? li.dataset.item : u.id;
    const holder_ = li || ev.target.closest("[data-testid=btext]");
    if (!holder_ || (!li && !SPLITTABLE.has(u.type))) { toast("Alt+click a word of a paragraph, list item or footnote to split it there."); return; }
    const pos = document.caretPositionFromPoint?.(ev.clientX, ev.clientY);
    const range = pos ? null : document.caretRangeFromPoint?.(ev.clientX, ev.clientY);
    const node = pos ? pos.offsetNode : range?.startContainer, off = pos ? pos.offset : range?.startOffset;
    if (!node || !holder_.contains(node)) return;
    const walker = document.createTreeWalker(holder_, NodeFilter.SHOW_TEXT);
    let before = "", shown = "", n;
    while ((n = walker.nextNode())) {
      if (n.parentElement.closest("button, .muted")) continue;  // the Split button, the printed number
      if (n === node) before = shown + n.textContent.slice(0, off);
      shown += n.textContent;
    }
    const tokens = [...shown.matchAll(/\S+/g)];
    const at = before.length;
    const k = tokens.findIndex((m) => m.index + m[0].length > at);
    if (k < 1) { toast(k === 0 ? "The first word cannot start a new block." : "Click on a word."); return; }
    let words;
    try { words = (await get(`/api/jobs/${id}/units/${target}/words`)).words; } catch (e) { toast(e.message); return; }
    const w = words[k];
    if (!w || w.t !== tokens[k][0]) { toast("Could not tell which word that is (the text is cut). Use the Split button."); return; }
    quickSave({ op: "split_word", unit: target, offset: w.at, text: w.t }, `split before “${wordClip(w.t, 30)}”`);
  }
  // "⤒ join with previous" (J): this block and the block before it become one, no preview. The block
  // before may be on the page before.
  async function joinPrev(u) {
    const vis = visibleRows(rows).filter((r) => r.type !== "page_marker");
    const at = vis.findIndex((r) => r.id === u.id);
    let prev = at > 0 ? vis[at - 1] : null;
    if (!prev && S.page > 1) {
      try {
        const back = await get(`/api/jobs/${id}/pages/${S.page - 1}/units`);
        prev = visibleRows(back.units).filter((r) => r.type !== "page_marker").pop() || null;
      } catch (e) { toast(e.message); return; }
    }
    if (!prev || prev.id === u.id) { toast("There is no block before this one to join with."); return; }
    if (prev.type !== u.type || prev.depth !== u.depth) { toast(`The block before is a ${typeName(prev).toLowerCase()}, not a ${typeName(u).toLowerCase()}: use Edit › Merge or Change element.`); return; }
    quickSave({ op: "merge", units: [prev.id, u.id] }, "joined with the block before");
  }

  function panelFor(u) {
    const pv = h("div", { class: "pv", dataset: { testid: "preview" } });
    const perr = h("div");
    const idx = rows.findIndex((x) => x.id === u.id);
    // Paragraphs of the page from this one on (for "this and the next n").
    // Consecutive blocks of the same level (a list counts as one block, its items are inside it).
    const run = (n) => { const out = []; for (let i = idx; i < rows.length && out.length < n; i++) { if (rows[i].type === "list_item" || rows[i].depth !== u.depth) continue; if (rows[i].type === "page_marker") break; out.push(rows[i].id); } return out; };
    const targets = (type) => rows.filter((r) => r.type === type).map((r) => [r.id, wordClip(r.clean || r.text || r.image || type, 40)]);
    const nextRow = rows.slice(idx + 1).find((x) => x.depth === u.depth && x.type !== "list_item");

    // ---- preview -> confirm
    async function check(edit, ids, label) {
      clear(perr); clear(pv);
      if (typeof edit === "string") { perr.append(errBox({ message: edit })); return; }
      pv.append(spinner("Checking what it would do…"));
      try {
        const p = await post(`/api/jobs/${id}/edits/preview`, { edit });
        const go = h("button", { class: "primary small", dataset: { testid: "confirm-save" }, onclick: () => save(edit, label, go) }, "Confirm");
        clear(pv).append(h("div", { class: "pvline", dataset: { testid: "preview-line" } }, previewLine(p, ids)),
          h("div", { class: "row" }, go, h("button", { class: "small", dataset: { testid: "cancel-save" }, onclick: () => clear(pv) }, "Cancel")));
        go.focus();
      } catch (e) { clear(pv); perr.append(errBox(e)); }
    }
    function save(edit, label, btn) {
      if (!S.who) { B.whoInput.focus(); toast("Enter your name first (top of the page)."); return; }
      btn.disabled = true;
      S.chain = (S.chain || Promise.resolve()).then(async () => {
        try {
          const res = await post(`/api/jobs/${id}/edits`, { who: S.who, edit });
          // The panel closes in the same moment the rows are redrawn, so the page does not jump.
          const y = window.scrollY, was = openId; openId = null;
          undoStack.push({ event: res.event, label });
          await afterChange(res);
          if (was && rowEls.get(was)) { const r = rowEls.get(was); clear(r.holderEdit); r.editBtn.textContent = "Edit"; r.editBtn.setAttribute("aria-expanded", "false"); r.el.classList.remove("editing"); }
          window.scrollTo(window.scrollX, y);
          showSaved(label, res);
        } catch (e) { btn.disabled = false; clear(perr).append(errBox(e)); }
      });
    }

    // ---- controls: a label, some fields, a "Check" button (Enter in a field does the same)
    const ctl = (label, fields, build, testid) => {
      const els = fields.map((f) => f.type === "select"
        ? h("select", { "aria-label": f.label || label, dataset: { testid: f.id } }, f.options.map(([v, t]) => h("option", { value: v, selected: String(v) === String(f.value) }, t)))
        : h("input", { type: f.type || "text", value: f.value ?? "", placeholder: f.placeholder || "", "aria-label": f.label || label, min: f.min, style: f.style || "width:120px", dataset: { testid: f.id } }));
      const go = () => { const vals = Object.fromEntries(fields.map((f, i) => [f.id, els[i].value])); const r = build(vals); check(r.edit ?? r, r.ids || [u.id], label); };
      for (const e of els) e.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); go(); } });
      return h("div", { class: "ctl row" }, h("span", { class: "clabel" }, label), els, h("button", { class: "small", dataset: { testid: testid || "check" }, onclick: go }, "Check"));
    };
    const btn = (label, edit, testid, ids) => h("button", { class: "small act", dataset: { testid }, onclick: () => check(edit, ids || [u.id], label) }, label);
    const mv = [btn("Move up in the reading order", { op: "move", unit: u.id, direction: "up" }, "move-up"), btn("Move down in the reading order", { op: "move", unit: u.id, direction: "down" }, "move-down")];
    const levels = (max) => Array.from({ length: max }, (_, i) => [i + 1, `Level ${i + 1}`]);
    const groups = { what: [], number: [], title: [], addremove: [], move: [] };
    // ``only``: the kinds a block can turn into (default: all); ``siblings``: the next blocks are items of the same list
    const turn = (only, siblings) => {
      const choices = only ? TURN.filter(([v]) => only.includes(v)) : TURN;
      const kind = h("select", { "aria-label": "Turn into", dataset: { testid: "turn-kind" } }, h("option", { value: "" }, "— choose —"), choices.map(([v, t]) => h("option", { value: v }, t)));
      const perItem = h("input", { type: "checkbox", dataset: { testid: "turn-per-item" }, "aria-label": "One paragraph per item" });
      const perItemLabel = h("label", { class: "small", hidden: true }, perItem, " one paragraph per item");
      const count = h("input", { type: "number", min: "1", max: "40", value: "1", style: "width:60px", "aria-label": "How many blocks", dataset: { testid: "turn-count" } });
      const cols = h("input", { type: "number", min: "1", max: "20", value: "2", style: "width:60px", "aria-label": "Columns", dataset: { testid: "turn-columns" } });
      const tsel = h("select", { "aria-label": "Which one", dataset: { testid: "turn-target" } });
      const extra = h("span", { class: "row" });
      const scopeSel = h("select", { "aria-label": "Apply to", dataset: { testid: "turn-scope" } }, h("option", { value: "block" }, "this change only"), h("option", { value: "follow" }, "and re-level the headings after it"));
      kind.onchange = () => {
        clear(extra);
        perItemLabel.hidden = kind.value !== "to_paragraph";
        if (kind.value === "table_make") extra.append(" columns ", cols);
        const need = kind.value === "caption" ? "figure" : (kind.value === "table_title" || kind.value === "table_note") ? "table" : null;
        if (need) { const t = targets(need); clear(tsel).append(...(t.length ? t : [["", `No ${need} on this page`]]).map(([v, x]) => h("option", { value: v }, x))); extra.append(" of ", tsel); }
        count.disabled = ONE_ONLY.has(kind.value);
      };
      const go = () => {
        if (!kind.value) return check("Choose what it should become.");
        const n = Math.max(1, +count.value || 1);
        const ids = ONE_ONLY.has(kind.value) ? [u.id] : siblings ? siblings(n) : run(n);
        const e = buildEdit(kind.value, ids, { level: 1, columns: cols.value, target: tsel.value, perItem: perItem.checked });
        if (typeof e !== "string") e.scope = scopeSel.value;
        check(e, ids, TURN.find(([v]) => v === kind.value)[1]);
      };
      return h("div", { class: "ctl row" }, h("span", { class: "clabel" }, "Turn this and the next"), count, h("span", {}, siblings ? "item(s) into" : "block(s) into"), kind, extra, perItemLabel, scopeSel,
        h("button", { class: "small", dataset: { testid: "turn-check" }, onclick: go }, "Check"));
    };


    if (u.type === "heading") {
      groups.what.push(
        ctl("Heading level", [{ id: "level", type: "select", options: levels(5), value: u.level }, { id: "scope", type: "select", options: [["block", "this heading only"], ["follow", "this and the headings after it"]], value: "block" }],
          (v) => ({ edit: { op: "heading_set", unit: u.id, level: +v.level, scope: v.scope } }), "set-level"),
        ctl("Kind", [{ id: "kind", type: "select", options: KINDS, value: kindOf(u) }], (v) => ({ edit: { op: "heading_kind", unit: u.id, kind: v.kind } }), "set-kind"),
        btn("Not a heading — make it a paragraph", { op: "heading_remove", unit: u.id }, "not-heading"), turn(),
        u.role !== "chapter" && btn("Start a new chapter here", { op: "new_chapter", unit: u.id }, "new-chapter"));
      groups.number.push(ctl("Number", [{ id: "number", value: u.number || "", placeholder: "e.g. 2.1" }], (v) => (v.number.trim() ? { edit: { op: "heading_number", unit: u.id, number: v.number.trim() } } : "Type the number first."), "set-number"));
      groups.title.push(ctl("Title text", [{ id: "text", value: u.text || "", style: "width:min(420px,100%)" }], (v) => (v.text.trim() && v.text !== u.text ? { edit: { op: "heading_text", unit: u.id, text: v.text } } : "Change the title first."), "save-title"),
        h("div", { class: "muted small" }, "The title can only lose a stray number."));
      groups.move.push(btn("Belongs to the chapter before", { op: "heading_attach", unit: u.id }, "attach"), ...mv);
    } else if (u.type === "paragraph") {
      groups.what.push(
        ctl("Make it a heading", [{ id: "level", type: "select", options: levels(4), value: 2 }], (v) => ({ edit: { op: "heading_set", unit: u.id, level: +v.level, scope: "block" } }), "make-heading"),
        turn());
      groups.number.push(ctl("Start a new chapter here — number", [{ id: "number", placeholder: "optional", style: "width:90px" }], (v) => ({ edit: { op: "new_chapter", unit: u.id, ...(v.number.trim() ? { number: v.number.trim() } : {}) } }), "new-chapter"));
      groups.move.push(
        u.joined_to ? btn("Undo join with the next paragraph", { op: "unjoin", unit: u.id }, "unjoin") : u.can_join && btn("Join with the next paragraph", { op: "join_next", unit: u.id }, "join-next"),
        nextRow?.type === "paragraph" && btn("Merge with the next paragraph into one", { op: "merge", units: [u.id, nextRow.id] }, "merge", [u.id, nextRow.id]),
        (u.lines?.length || 0) > 1 && ctl("Split", [{ id: "line", type: "select", label: "Where the new paragraph starts", options: u.lines.map((l, n) => [n, `starts at: ${wordClip(l, 50)}`]).slice(1), value: 1 }],
          (v) => ({ edit: { op: "split", unit: u.id, line: +v.line } }), "split-line"),
        ...mv, btn("Read this column first", { op: "swap_columns", unit: u.id }, "swap-columns"));
    } else if (u.type === "list") {
      const ids = u.item_ids || [];
      groups.what.push(turn(),
        u.list_type !== "bulleted" && btn("Make it a bulleted list", { op: "list_set", units: ids, list_type: "bulleted", level: 1 }, "list-bulleted", [u.id, ...ids]),
        u.list_type !== "numbered" && btn("Make it a numbered list", { op: "list_set", units: ids, list_type: "numbered", level: 1 }, "list-numbered", [u.id, ...ids]));
      groups.what.push(ctl("Indent or outdent one item", [
        { id: "item", type: "select", label: "Which item", options: (u.items || []).map((i, n) => [i.id, `${n + 1}. ${wordClip(i.text, 40)} (level ${i.level})`]), value: ids[0] },
        { id: "dir", type: "select", label: "Direction", options: [["in", "one level in (indent)"], ["out", "one level out (outdent)"]], value: "in" }],
      (v) => ({ edit: { op: "list_level", unit: v.item, direction: v.dir }, ids: [v.item] }), "list-level"));
      groups.move.push(...mv);
    } else if (u.type === "table") {
      groups.what.push(btn("Unwrap — a table becomes its plain text", { op: "unwrap", unit: u.id }, "unwrap"), turn(PARA));
      groups.move.push(ctl("Split the table before row", [{ id: "row", type: "number", value: 2, min: "2", style: "width:70px" }], (v) => (+v.row >= 2 ? { edit: { op: "table_split", unit: u.id, row: +v.row } } : "Give a row of 2 or more."), "table-split"), ...mv);
    } else if (u.type === "figure" || u.type === "equation") {
      groups.what.push(u.type === "figure" && btn(u.decorative ? "It is a real picture" : "It is decoration (leave it out)", { op: "decorative", unit: u.id, value: !u.decorative }, "decorative"),
        u.type === "figure" && btn("Unwrap — its text becomes paragraphs", { op: "unwrap", unit: u.id }, "unwrap"), u.type === "figure" && turn(PARA));
      groups.title.push(ctl("Description", [{ id: "text", value: u.alt_text || "", placeholder: "What does the picture show?", style: "width:min(420px,100%)" }], (v) => (v.text.trim() ? { edit: { op: "alt_text", unit: u.id, text: v.text.trim() } } : "Write the description first."), "save-alt"));
      groups.move.push(...mv);
    } else if (u.type === "box") {
      groups.what.push(btn("Unwrap — the box becomes its text", { op: "unwrap", unit: u.id }, "unwrap"), turn(PARA));
      groups.move.push(...mv);
    } else {
      if (u.type === "caption" || u.type === "footnote") groups.what.push(btn("Make it a body paragraph", { op: "paragraph", unit: u.id }, "to-paragraph"));
      if (u.type === "caption" || u.type === "footnote") groups.what.push(turn(PARA));
      if (u.type === "list_item") groups.what.push(turn(PARA, (n) => rows.slice(idx).filter((r) => r.type === "list_item" && r.parent === u.parent).slice(0, n).map((r) => r.id)));
      groups.move.push(...mv);
    }

    const actx = { u, id, S, check, perr, run, targets };
    if (u.type !== "figure" && u.type !== "equation") groups.addremove.push(removeControl(actx));
    if (["paragraph", "heading", "list_item", "caption", "footnote", "bibliography_entry"].includes(u.type)) groups.addremove.push(textControl(actx));
    groups.addremove.push(addControl(actx));
    const NAMES = { what: "What is it?", number: "Number", title: "Title", addremove: "Add / remove", move: "Move / merge / split" };
    return h("div", { class: "epanel", dataset: { testid: "edit-panel", type: u.type } },
      Object.keys(NAMES).filter((k) => groups[k].filter(Boolean).length).map((k) =>
        h("section", { class: "egroup", dataset: { testid: `group-${k}` } }, h("h4", {}, NAMES[k]), h("div", { class: "eitems" }, groups[k].filter(Boolean)))),
      h("div", { class: "muted small" }, "Esc closes. Nothing is saved until you press Confirm."), pv, perr);
  }

  // ---------------------------------------------------------------- after a save, undo
  async function afterChange(res) {
    const mine = (res.pages || []).find((p) => p.page === S.page);
    if (mine && S.mode === "browse") renderRows(mine.after);
    if (res.chapters && chapters.open) loadChapters(res.chapters);
    restore.load(S.page);
    B.scheduleRefresh();
    const dec = await get(`/api/jobs/${id}/decisions`); S.edits = dec.edits; B.paintHistory();
    undoBtn.disabled = !undoStack.length;
  }
  S.afterChange = afterChange;
  // PDF lines that are not in the book text ("Restore as…"): the same save, undo and redraw path.
  async function revokeEvent(eventId, label) {
    const res = await del(`/api/jobs/${id}/decisions/${eventId}?who=${encodeURIComponent(S.who || "")}`);
    const at = undoStack.findIndex((x) => x.event?.id === eventId);
    if (at >= 0) undoStack.splice(at, 1);
    await afterChange(res);
    status.hidden = false; clear(status).append(`Restored: ${label}.`);
    undoBtn.disabled = !undoStack.length;
  }
  S.focusRestore = (lineId) => { restore.el.scrollIntoView({ block: "center", behavior: "smooth" }); restore.el.querySelector(`[data-line="${lineId}"] [data-testid=restore-open], [data-line="${lineId}"] [data-testid=restore-removed]`)?.focus(); };
  const restore = restoreSection({ id, S, B, revoke: revokeEvent, saved: async (res, label) => {
    const y = window.scrollY;
    undoStack.push({ event: res.event, label });
    await afterChange(res);
    window.scrollTo(window.scrollX, y);
    showSaved(label, res);
  } });
  function showSaved(label, res) {
    status.hidden = false;
    clear(status).append(h("span", {}, `Saved: ${label}. `),
      h("button", { class: "small", dataset: { testid: "status-undo" }, onclick: () => undoLast() }, "Undo"),
      " ", h("button", { class: "small", dataset: { testid: "similar-open" }, onclick: () => {
        clear(status).append(similarPanel({ id, event: res.event, who: () => S.who,
          onApplied: async (g) => { clear(status); status.hidden = true; undoStack.push({ group: g.group, label: "same change to similar blocks" }); await afterChange(g); toast(`Applied to ${g.applied} block${g.applied === 1 ? "" : "s"}. One Undo takes back the group.`); },
          onClose: () => { clear(status); status.hidden = true; } }));
      } }, "Same change to similar blocks…"));
    undoBtn.disabled = false;
  }
  async function undoLast() {
    const last = undoStack.pop();
    if (!last) { toast("Nothing to undo on this screen. Older changes: “Your changes” at the bottom."); return; }
    const who = encodeURIComponent(S.who || "");
    try {
      const res = last.group ? await del(`/api/jobs/${id}/groups/${last.group}?who=${who}`) : await del(`/api/jobs/${id}/decisions/${last.event.id}?who=${who}`);
      if (res.pages) await afterChange(res); else await paint();
      status.hidden = false; clear(status).append(`Undone: ${last.label}.`);
      undoBtn.disabled = !undoStack.length;
    } catch (e) { toast(e.message); }
  }

  // ---------------------------------------------------------------- keyboard
  const onKey = (ev) => {
    if (S.mode !== "browse" || ev.altKey) return;
    const t = ev.target, tag = t?.tagName, typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
    if (ev.key === "Escape") { if (openId) { const r = rowEls.get(openId); closePanel(); r?.editBtn.focus(); } else if (sel.size) clearSel(); return; }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "z" && !typing) { ev.preventDefault(); undoLast(); return; }
    if (ev.ctrlKey || ev.metaKey || typing) return;
    if (ev.key === "/") { ev.preventDefault(); search.focus(); search.select(); }
    else if (ev.key === "m" || ev.key === "M") { if (sel.size) { ev.preventDefault(); mergeSelected(); } }
    else if (ev.key === "j" || ev.key === "J") { const u = rows.find((x) => x.id === activeId); if (u && SPLITTABLE.has(u.type)) { ev.preventDefault(); joinPrev(u); } }
    else if (ev.key === "u" || ev.key === "U") { ev.preventDefault(); undoLast(); }
    else if (ev.key === "ArrowLeft") { ev.preventDefault(); B.goPage(S.page - 1); }
    else if (ev.key === "ArrowRight") { ev.preventDefault(); B.goPage(S.page + 1); }
  };
  document.addEventListener("keydown", onKey);

  // ---------------------------------------------------------------- paint
  async function paint() {
    const mine = ++token;
    B.rail.hidden = false;
    pageNo.value = S.page; ofText.textContent = `of ${S.pages.length}`;
    const p = S.pages[S.page - 1];
    for (const [n, b] of thumbs) b.classList.toggle("current", n === S.page);
    thumbs.get(S.page)?.scrollIntoView({ block: "nearest" });
    pageNo.title = p?.label ? `Printed page ${p.label}` : "";
    closePanel(); rowEls.clear(); clear(list); activeId = null;
    clear(holder).append(spinner("Loading…"));
    B.right.append(toolbar, selBar, err, chapters, restore.el, holder, status);
    let data;
    try { data = await get(`/api/jobs/${id}/pages/${S.page}/units`); } catch (e) { if (mine === token) clear(holder).append(errBox(e)); return; }
    if (mine !== token) return;
    clear(holder).append(list);
    renderRows(data.units);
    restore.load(S.page);
    if (S.focusUnit) focusUnit();
  }
  return {
    paint,
    afterPaint: drawOverlay,
    destroy() { document.removeEventListener("keydown", onKey); clearTimeout(searchTimer); },
  };
}
