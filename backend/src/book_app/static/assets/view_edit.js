// "Change element": give selected units of a page another element type, move them in the
// reading order, or take them out of the book. Every change is previewed first and applied to
// "this block only" or to "this block and what follows" (the headings after it re-levelled).
import { clear, errBox, get, h, post, spinner } from "./util.js";

// [value, label, what the change needs]
export const CHANGES = [
  ["paragraph", "Body paragraph", "one"],
  ["list_bulleted", "Bulleted list", "many"],
  ["list_numbered", "Numbered list", "many"],
  ["list_in", "List item: one level in", "item"],
  ["list_out", "List item: one level out", "item"],
  ["box", "Box (sidebar) with title", "many"],
  ["box_plain", "Box (sidebar) without title", "many"],
  ["quote", "Quote", "many"],
  ["pull_quote", "Pull quote", "many"],
  ["caption", "Figure caption", "one"],
  ["table_make", "Table", "many"],
  ["table_title", "Table title", "one"],
  ["table_note", "Table note", "one"],
  ["footnote", "Footnote", "one"],
  ["chapter_authors", "Chapter authors", "many"],
  ["question", "MCQ question (stem, options, answer)", "many"],
  ["bibliography", "Bibliography entry", "many"],
  ["index_entries", "Index entry", "many"],
  ["glossary", "Glossary term and definition", "many"],
  ["not_running_head", "Not book content: running head", "many"],
  ["not_running_foot", "Not book content: running foot", "many"],
  ["not_folio", "Not book content: page number (folio)", "many"],
  ["not_production_mark", "Not book content: printer mark", "many"],
  ["merge", "Merge into one", "many"],
  ["unwrap", "Unwrap: a table, figure or box becomes its text", "one"],
  ["table_split", "Split table here (before a row)", "one"],
  ["move_up", "Move up in the reading order", "one"],
  ["move_down", "Move down in the reading order", "one"],
  ["swap_columns", "Read this column first (swap columns)", "one"],
];

// The edit the server applies for a change, or an error message.
export function buildEdit(change, ids, extra) {
  const one = ids[0];
  switch (change) {
    case "paragraph": return { op: "paragraph", unit: one };
    case "list_bulleted": return { op: "list_set", units: ids, list_type: "bulleted", level: +extra.level || 1 };
    case "list_numbered": return { op: "list_set", units: ids, list_type: "numbered", level: +extra.level || 1 };
    case "list_in": return { op: "list_level", unit: one, direction: "in" };
    case "list_out": return { op: "list_level", unit: one, direction: "out" };
    case "box": return { op: "box", units: ids, kind: "box", title: true };
    case "box_plain": return { op: "box", units: ids, kind: "box", title: false };
    case "quote": return { op: "box", units: ids, kind: "quote" };
    case "pull_quote": return { op: "box", units: ids, kind: "pull_quote" };
    case "caption": return extra.target ? { op: "caption", unit: one, figure: extra.target } : "Choose the figure.";
    case "table_make": return { op: "table_make", units: ids, columns: +extra.columns || 1 };
    case "table_title": return extra.target ? { op: "table_text", unit: one, table: extra.target, role: "title" } : "Choose the table.";
    case "table_note": return extra.target ? { op: "table_text", unit: one, table: extra.target, role: "note" } : "Choose the table.";
    case "footnote": return { op: "footnote", unit: one };
    case "unwrap": return { op: "unwrap", unit: one };
    case "table_split": return +extra.row >= 2 ? { op: "table_split", unit: one, row: +extra.row } : "Give the row the second table starts with (2 or more).";
    case "chapter_authors": return { op: "chapter_authors", units: ids };
    case "question": return { op: "question", units: ids };
    case "bibliography": case "index_entries": case "glossary": case "merge": return { op: change, units: ids };
    case "move_up": return { op: "move", unit: one, direction: "up" };
    case "move_down": return { op: "move", unit: one, direction: "down" };
    case "swap_columns": return { op: "swap_columns", unit: one };
    default:
      if (change.startsWith("not_")) return { op: "not_content", units: ids, kind: change.slice(4) };
      return "Choose what it is.";
  }
}

const rowText = (r) => `${r.type.replace("_", " ")}${r.level && r.type === "heading" ? ` ${r.level}` : ""}${r.flags?.length ? ` (${r.flags.join(", ")})` : ""}: ${(r.clean || r.text || "").replace(/\s+/g, " ").slice(0, 90)}`;

// The dialog. ``rows``: the page's browse rows; ``ids``: the selected unit ids (page order).
export function changeDialog({ id, page, rows, ids, who, onSaved, onClose, initial, enqueue = (fn) => fn() }) {
  const err = h("div");
  const out = h("div", { class: "preview", dataset: { testid: "change-preview" } });
  const kind = h("select", { "aria-label": "Change to", dataset: { testid: "change-kind" } },
    h("option", { value: "" }, "— choose what it is —"),
    CHANGES.filter(([, , need]) => need !== "one" || ids.length === 1).map(([v, t]) => h("option", { value: v, selected: v === initial }, t)));
  const level = h("select", { "aria-label": "List level", dataset: { testid: "change-level" } }, [1, 2, 3, 4].map((n) => h("option", { value: n }, `level ${n}`)));
  const columns = h("input", { type: "number", min: "1", max: "20", value: "1", style: "width:60px", "aria-label": "Columns", dataset: { testid: "change-columns" } });
  const splitRow = h("input", { type: "number", min: "2", value: "2", style: "width:60px", "aria-label": "Row", dataset: { testid: "change-row" } });
  const target = h("select", { "aria-label": "Which one", dataset: { testid: "change-target" } });
  const extras = h("span");
  const scope = (v, label, help) => h("label", { style: "display:block;margin:4px 0" },
    h("input", { type: "radio", name: "change-scope", value: v, checked: v === "block", dataset: { testid: `scope-${v}` } }), ` ${label} `, h("span", { class: "muted small" }, help));
  const scopes = h("div", { dataset: { testid: "change-scope" } },
    scope("block", "This block only", "— change just the selected block; nothing else moves."),
    scope("follow", "This block and what follows", "— also re-level the headings after it (no level skips) and rebuild the nesting."));
  const save = h("button", { class: "primary", disabled: true, dataset: { testid: "change-save" }, onclick: () => apply(true) }, "Save the change");
  const preview = h("button", { dataset: { testid: "change-preview-btn" }, onclick: () => apply(false) }, "Preview");
  let previewed = null;

  async function targets(type) {
    const seen = rows.filter((r) => r.type === type).map((r) => [r.id, `page ${page}: ${r.clean || r.text || r.image || r.id}`]);
    for (const p of [page - 1, page + 1]) {
      if (p < 1) continue;
      try { (await get(`/api/jobs/${id}/pages/${p}/units`)).units.filter((r) => r.type === type).forEach((r) => seen.push([r.id, `page ${p}: ${r.clean || r.text || r.image || r.id}`])); } catch { /* past the last page */ }
    }
    clear(target).append(...(seen.length ? seen.map(([v, t]) => h("option", { value: v }, t.slice(0, 70))) : [h("option", { value: "" }, `No ${type} on this page or the pages beside it`)]));
  }
  function paintExtras() {
    clear(extras); previewed = null; save.disabled = true; clear(out);
    const v = kind.value;
    if (v.startsWith("list_") && !v.endsWith("in") && !v.endsWith("out")) extras.append(" ", level);
    if (v === "table_make") extras.append(" columns ", columns);
    if (v === "table_split") extras.append(" second table starts at row ", splitRow);
    if (v === "caption") { extras.append(" of ", target); targets("figure"); }
    if (v === "table_title" || v === "table_note") { extras.append(" of ", target); targets("table"); }
  }
  kind.onchange = paintExtras;
  const scopeValue = () => box.querySelector("input[name=change-scope]:checked")?.value || "block";

  async function apply(saving) {
    clear(err);
    const edit = buildEdit(kind.value, ids, { level: level.value, columns: columns.value, row: splitRow.value, target: target.value });
    if (typeof edit === "string") { err.append(errBox({ message: edit })); return; }
    edit.scope = scopeValue();
    if (saving) {
      if (!who()) { err.append(errBox({ message: "Enter your name first (top of the page)." })); return; }
      if (!previewed || JSON.stringify(previewed) !== JSON.stringify(edit)) { err.append(errBox({ message: "Preview the change first." })); return; }
      save.disabled = true;
      await enqueue(async () => {  // after any change still on its way to the server
        try { onSaved(await post(`/api/jobs/${id}/edits`, { who: who(), edit })); }
        catch (e) { err.append(errBox(e)); save.disabled = false; }
      });
      return;
    }
    clear(out).append(spinner("Preparing the preview…"));
    try {
      const p = await post(`/api/jobs/${id}/edits/preview`, { edit });
      previewed = edit; save.disabled = false;
      clear(out).append(...renderPreview(p));
    } catch (e) { clear(out); err.append(errBox(e)); }
  }

  const box = h("div", { class: "panel changebox", dataset: { testid: "change-dialog" } },
    h("div", { class: "row" }, h("b", {}, `Change ${ids.length} selected item${ids.length === 1 ? "" : "s"} to`), kind, extras),
    scopes, h("div", { class: "row", style: "margin-top:6px" }, preview, save,
      h("button", { dataset: { testid: "change-cancel" }, onclick: onClose }, "Cancel")), err, out);
  for (const input of box.querySelectorAll("input[name=change-scope]")) input.onchange = () => { previewed = null; save.disabled = true; };
  if (initial) paintExtras();
  return box;
}

export function renderPreview(p) {
  const parts = [];
  for (const pg of p.pages) {
    const before = new Map(pg.before.map((r) => [r.id, JSON.stringify(r)]));
    const after = new Map(pg.after.map((r) => [r.id, JSON.stringify(r)]));
    const gone = pg.before.filter((r) => !after.has(r.id));
    const changed = pg.after.filter((r) => before.get(r.id) !== after.get(r.id));
    parts.push(h("div", { class: "small", dataset: { testid: "preview-page" } }, h("b", {}, `Page ${pg.page}`),
      changed.map((r) => h("div", { class: "prev-after", dataset: { testid: "preview-after" } }, "→ ", rowText(r))),
      gone.map((r) => h("div", { class: "prev-gone muted" }, "✕ ", rowText(r)))));
  }
  if (p.headings.length) {
    parts.push(h("div", { class: "small", dataset: { testid: "preview-headings" } }, h("b", {}, "Headings that change"),
      p.headings.map((x) => h("div", { dataset: { testid: "preview-heading" } }, `p.${x.page} ${x.text.slice(0, 60)}: `,
        `${x.before.role} level ${x.before.level} → `, x.after ? `${x.after.role} level ${x.after.level}` : "no longer a heading"))));
  } else parts.push(h("div", { class: "small muted" }, "No heading changes level."));
  return parts;
}

// "Apply to all similar": after a change, the blocks of the book printed like the changed one
// (same style, same element) are listed with their pages; the reviewer unticks any and applies
// the same change (same scope) to the rest. One Undo takes back the whole group.
export function similarPanel({ id, event, who, onApplied, onClose }) {
  const box = h("div", { class: "panel changebox", dataset: { testid: "similar-panel" } });
  const err = h("div");
  const find = h("button", { dataset: { testid: "similar-find" }, onclick: load }, "Apply to all similar…");
  box.append(h("div", { class: "row" }, h("b", {}, "Saved."), h("span", { class: "muted small" }, "Make the same change to every block printed like this one?"), find,
    h("button", { class: "small", dataset: { testid: "similar-close" }, onclick: onClose }, "Close")), err);
  async function load() {
    find.disabled = true;
    const list = h("div", { dataset: { testid: "similar-list" } }, spinner("Looking for blocks printed the same way…"));
    box.append(list);
    let d;
    try { d = await post(`/api/jobs/${id}/edits/similar`, { event: event.id }); } catch (e) { clear(list); err.append(errBox(e)); return; }
    clear(list);
    if (!d.repeatable) { list.append(h("p", { class: "muted small" }, "This change belongs to its own block (its text or its figure/table); it is not repeated.")); return; }
    const usable = d.matches.filter((m) => m.edit);
    if (!d.matches.length) { list.append(h("p", { class: "muted small", dataset: { testid: "similar-none" } }, "No other block is printed like this one.")); return; }
    list.append(h("p", { class: "small" }, `${usable.length} similar block${usable.length === 1 ? "" : "s"} (${d.style ? d.style.slice(4, 8).join(", ") : ""}). Untick any that should stay as they are.`));
    const boxes = [];
    const table = h("table", {}, h("tbody", {}, d.matches.map((m) => {
      const cb = m.edit && h("input", { type: "checkbox", checked: true, dataset: { testid: "similar-pick", page: m.page } });
      if (cb) boxes.push([cb, m]);
      return h("tr", { dataset: { testid: "similar-row" } }, h("td", {}, cb || ""), h("td", {}, `p.${m.page}`), h("td", {}, m.text),
        h("td", { class: "muted small" }, m.reason || ""));
    })));
    const apply = h("button", { class: "primary", dataset: { testid: "similar-apply" }, onclick: async () => {
      clear(err);
      const picked = boxes.filter(([cb]) => cb.checked).map(([, m]) => m.edit);
      if (!picked.length) { err.append(errBox({ message: "Tick at least one block." })); return; }
      apply.disabled = true;
      try { onApplied(await post(`/api/jobs/${id}/edits/group`, { who: who(), event: event.id, edits: picked })); }
      catch (e) { err.append(errBox(e)); apply.disabled = false; }
    } }, `Apply to the ticked blocks`);
    list.append(table, h("div", { class: "row", style: "margin-top:6px" }, apply));
  }
  return box;
}
