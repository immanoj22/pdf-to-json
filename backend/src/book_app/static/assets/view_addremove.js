// Browse: "Remove from book" and "Add text here" (the Edit panel of a block).
//
// Remove: the block leaves the book text and goes to the page's "Left out on purpose" list
// (removed by <name>); "Restore" there brings it back. Add: new text before or after the block as
// a paragraph, a heading, a list item or any element of "Change element". PDF lines that the book
// leaves out are offered first (Restore); text is typed only where the PDF has none. Typed
// blocks are marked "added by <name>". Every change: check -> confirm -> Undo, in the audit log.
import { clear, errBox, get, h, me } from "./util.js";
import { CHANGES, buildEdit } from "./view_edit.js";

const clip = (s, n) => { const t = String(s || "").replace(/\s+/g, " ").trim(); return t.length <= n ? t : `${t.slice(0, n).replace(/[\s,;:]+$/, "")} …`; };
// The elements a new block can be: every "Change element" choice that makes an element of the
// block's own text (not a move, merge, unwrap or "not book content").
const NEW_AS = new Set(["list_bulleted", "list_numbered", "box", "box_plain", "quote", "pull_quote", "caption", "table_make", "table_title", "table_note", "footnote", "chapter_authors", "question", "bibliography", "index_entries", "glossary"]);
export const ADD_AS = [["paragraph", "Body paragraph"], ["heading", "Heading"], ["list_item", "List item (next to an item of the list)"],
  ...CHANGES.filter(([v]) => NEW_AS.has(v)).map(([v, t]) => [v, t.replace(/^Box \(sidebar\)/, "Box")])];

let policy = null;
async function addPolicy() { if (!policy) { try { policy = (await get("/api/health")).add_text_by || "managers"; } catch { policy = "managers"; } } return policy; }

// ctx: { id, S, B, rows, u, targets(type), check(edit, ids, label), perr }
export function removeControl(ctx) {
  const { u, check } = ctx;
  const count = h("input", { type: "number", min: "1", max: "40", value: "1", style: "width:60px", "aria-label": "How many blocks", dataset: { testid: "remove-count" } });
  const go = () => {
    const ids = ctx.run(Math.max(1, +count.value || 1));
    check({ op: "remove_block", units: ids }, ids, `removed ${ids.length} block${ids.length === 1 ? "" : "s"} from the book`);
  };
  count.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); go(); } });
  return h("div", { class: "ctl row" }, h("span", { class: "clabel" }, "Remove from book: this and the next"), count, h("span", {}, "block(s)"),
    h("button", { class: "small", dataset: { testid: "remove-check" }, onclick: go }, "Check"),
    h("span", { class: "muted small" }, "The text moves to “Left out on purpose” for this page; Restore brings it back."));
}

export function addControl(ctx) {
  const { u, id, S, check, perr } = ctx;
  const wrap = h("div", { class: "ctl addtext", dataset: { testid: "add-text" } });
  const open = h("button", { class: "small", dataset: { testid: "add-open" }, "aria-expanded": "false", onclick: () => (wrap.querySelector(".addform") ? close() : show()) }, "Add text here…");
  wrap.append(h("span", { class: "clabel" }, "Add text here"), open);
  const close = () => { wrap.querySelector(".addform")?.remove(); open.setAttribute("aria-expanded", "false"); };

  async function show() {
    open.setAttribute("aria-expanded", "true");
    const form = h("div", { class: "addform" });
    wrap.append(form);
    const who = me();
    if ((await addPolicy()) === "managers" && who.role !== "manager") {
      form.append(h("div", { class: "muted", dataset: { testid: "add-denied" } }, "Only a manager can add text to a book. Ask a manager, or restore a line from the PDF below."));
    }
    // PDF lines that are not in the book come first: restore them instead of typing.
    let d = S.restorable;
    try { d = await get(`/api/jobs/${id}/pages/${S.page}/restorable`); } catch { /* the page list shows the error */ }
    const lines = (d?.lines || []).filter((l) => l.status === "candidate" || l.status === "removed");
    if (lines.length) {
      form.append(h("div", { class: "addlines", dataset: { testid: "add-lines" } },
        h("b", {}, `${lines.length} line${lines.length === 1 ? "" : "s"} from the PDF ${lines.length === 1 ? "is" : "are"} not in the book`),
        h("div", { class: "muted small" }, "Restore the PDF's own text instead of typing it. Text is typed only where the PDF has none."),
        ...lines.map((l) => h("div", { class: "row" }, h("span", { class: "rtext" }, `“${clip(l.text, 90)}”`), h("div", { class: "grow" }),
          h("button", { class: "small", dataset: { testid: "add-restore" }, onclick: () => { close(); S.focusRestore?.(l.id); } }, l.status === "removed" ? "Restore" : "Restore as…")))));
      return;
    }
    if ((await addPolicy()) === "managers" && who.role !== "manager") return;
    const where = h("select", { "aria-label": "Where", dataset: { testid: "add-where" } }, h("option", { value: "after" }, "after this block"), h("option", { value: "before" }, "before this block"));
    const inList = u.type === "list" || u.type === "list_item";
    const kind = h("select", { "aria-label": "What it is", dataset: { testid: "add-kind" } },
      ADD_AS.filter(([v]) => v !== "list_item" || inList).map(([v, t]) => h("option", { value: v }, t)));
    const level = h("select", { "aria-label": "Heading level", dataset: { testid: "add-level" }, hidden: true }, [1, 2, 3, 4, 5, 6].map((n) => h("option", { value: n, selected: n === 2 }, `level ${n}`)));
    const cols = h("input", { type: "number", min: "1", max: "20", value: "1", style: "width:60px", "aria-label": "Columns", hidden: true, dataset: { testid: "add-columns" } });
    const target = h("select", { "aria-label": "Which one", hidden: true, dataset: { testid: "add-target" } });
    const text = h("textarea", { rows: "3", style: "width:min(520px,100%)", "aria-label": "The new text", placeholder: "Type the new text", dataset: { testid: "add-text-input" } });
    kind.onchange = () => {
      level.hidden = kind.value !== "heading"; cols.hidden = kind.value !== "table_make";
      const need = kind.value === "caption" ? "figure" : (kind.value === "table_title" || kind.value === "table_note") ? "table" : null;
      target.hidden = !need;
      if (need) { const t = ctx.targets(need); clear(target).append(...(t.length ? t : [["", `No ${need} on this page`]]).map(([v, x]) => h("option", { value: v }, x))); }
    };
    const go = () => {
      const value = text.value.trim();
      if (!value) { clear(perr).append(errBox({ message: "Type the text first." })); return; }
      const edit = { op: "add_block", anchor: u.id, where: where.value, page: S.page, text: value, as: ["heading", "list_item"].includes(kind.value) ? kind.value : "paragraph" };
      if (kind.value === "heading") edit.level = +level.value;
      if (!["paragraph", "heading", "list_item"].includes(kind.value)) {
        const then = buildEdit(kind.value, ["$new"], { level: 1, columns: cols.value, target: target.value });
        if (typeof then === "string") { clear(perr).append(errBox({ message: then })); return; }
        edit.then = then;
      }
      check(edit, [], `added text “${clip(value, 30)}”`);
    };
    form.append(h("div", { class: "row" }, "Insert", where, "as", kind, level, cols, target), text,
      h("div", { class: "row" }, h("button", { class: "small", dataset: { testid: "add-check" }, onclick: go }, "Check"), h("button", { class: "small", onclick: close }, "Close"),
        h("span", { class: "muted small" }, "It is marked “added by you” and listed in the QC report as words added by hand.")));
    text.focus();
  }
  return wrap;
}
