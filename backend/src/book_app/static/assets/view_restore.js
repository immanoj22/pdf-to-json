// Browse: PDF text lines that are not in the book text ("Restore as…").
//
// The list comes from the PDF's own text layer as the converter read it: lines the book keeps
// out of its text as page furniture. The ones shown first are running heads that the page
// before does not carry too (a title the converter took for a running head). Running heads that
// repeat, page numbers and printer's marks are listed below, left out on purpose. A line is only
// ever restored with its own PDF text, as a chapter title, a part title, a heading or a
// paragraph, at its place on the page. Every restore is checked first (one line says what it
// does), confirmed, saved in the audit log and can be undone.

import { clear, errBox, get, h, post, spinner, toast } from "./util.js";

const clip = (s, n) => {
  const t = String(s || "").replace(/\s+/g, " ").trim();
  if (t.length <= n) return t;
  const cut = t.slice(0, n), at = cut.lastIndexOf(" ");
  return `${(at > n * 0.6 ? cut.slice(0, at) : cut).replace(/[\s,;:]+$/, "")} …`;
};

export const RESTORE_AS = [
  ["chapter", "Chapter title", "Starts a new chapter."],
  ["part", "Part title", "Starts a new part."],
  ["heading", "Heading", "A heading inside the chapter."],
  ["paragraph", "Paragraph", "Ordinary text."],
];
const AS_NAME = { chapter: "chapter title", part: "part title", heading: "heading", paragraph: "paragraph" };

// ctx: { id, S, B, saved(res, label) }  saved() records the undo step and redraws the page.
export function restoreSection(ctx) {
  const { id, S, B } = ctx;
  const el = h("div", { class: "restore", hidden: true, dataset: { testid: "restore-panel" } });
  let token = 0;

  function showLine(line) {
    if (line.box) { S.hl = line.box; B.paintPage(); }
  }

  // Where it will go, in words, from the page's blocks around it.
  const placeWords = (place) => {
    if (!place) return "at its place on the page";
    const q = (t) => (t.startsWith("the ") ? t : `“${clip(t, 30)}”`);
    if (place.before && place.after) return `between ${q(place.after)} and ${q(place.before)}`;
    if (place.before) return `at the top of the page, before ${q(place.before)}`;
    if (place.after) return `at the end of the page, after ${q(place.after)}`;
    return "on the page";
  };

  function rowFor(line, candidate) {
    const holder = h("div", { class: "restore-form" }), err = h("div");
    const row = h("div", { class: `rline${candidate ? " cand" : ""}`, dataset: { testid: "restore-line", line: line.id, status: line.status } },
      h("div", { class: "row" },
        h("span", { class: "rtext", title: "This is the PDF's own text" }, `“${line.text}”`),
        h("div", { class: "grow" }),
        line.can_restore && h("button", { class: candidate ? "primary small" : "small", dataset: { testid: "restore-open" }, "aria-expanded": "false",
          onclick: () => (holder.firstChild ? close() : open()) }, candidate ? "Restore as…" : "Restore anyway…")),
      h("div", { class: "muted small" }, candidate ? `${line.why} It would go ${placeWords(line.place)}.` : line.why),
      holder, err);
    row.addEventListener("mouseenter", () => showLine(line));
    row.addEventListener("click", () => showLine(line));
    const btn = () => row.querySelector("[data-testid=restore-open]");
    function close() { clear(holder); clear(err); btn()?.setAttribute("aria-expanded", "false"); }
    function open() {
      btn()?.setAttribute("aria-expanded", "true");
      showLine(line);
      let as = candidate ? "chapter" : "paragraph";
      const level = h("select", { "aria-label": "Heading level", dataset: { testid: "restore-level" } },
        [1, 2, 3, 4, 5, 6].map((n) => h("option", { value: n, selected: n === Math.min(line.level_default || 2, 6) }, `level ${n}`)));
      const pv = h("div", { class: "pv", dataset: { testid: "restore-preview" } });
      const edit = () => ({ op: "restore_line", line: line.id, as, ...(as === "heading" ? { level: +level.value } : {}) });
      const choices = RESTORE_AS.map(([v, label, hint]) => h("label", { class: "rchoice" },
        h("input", { type: "radio", name: `as-${line.id}`, value: v, checked: v === as, dataset: { testid: `restore-as-${v}` },
          onchange: () => { as = v; clear(pv); } }), " ", h("b", {}, label), " ", h("span", { class: "muted small" }, hint), v === "heading" && [" ", level]));
      const check = h("button", { class: "small", dataset: { testid: "restore-check" }, onclick: async () => {
        clear(err); clear(pv).append(spinner("Checking what it would do…"));
        try {
          const e = edit(), p = await post(`/api/jobs/${id}/edits/preview`, { edit: e });
          const pg = (p.pages || []).find((x) => x.page === S.page) || (p.pages || [])[0];
          const after = (pg?.after || []).filter((r) => r.type !== "list_item" && r.type !== "page_marker");
          const at = after.findIndex((r) => r.id === line.id);
          const near = (r) => (!r ? null : (r.clean || r.text) ? `“${clip(r.clean || r.text, 28)}”` : `the ${String(r.type).replace("_", " ")}`);
          const prev = at > 0 ? near(after[at - 1]) : null, next = at >= 0 ? near(after[at + 1]) : null;
          const where = prev && next ? `between ${prev} and ${next}` : next ? `at the top of the page, before ${next}` : prev ? `at the end of the page, after ${prev}` : "on the page";
          let text = `“${clip(line.text, 50)}” becomes a ${AS_NAME[as]}${as === "heading" ? ` (level ${level.value})` : ""}, ${where}.`;
          if (p.headings?.length) text += `  ·  ${p.headings.length} heading${p.headings.length === 1 ? "" : "s"} after it change${p.headings.length === 1 ? "s" : ""} level.`;
          const go = h("button", { class: "primary small", dataset: { testid: "restore-confirm" }, onclick: () => save(e, go) }, "Confirm");
          clear(pv).append(h("div", { class: "pvline", dataset: { testid: "restore-preview-line" } }, text),
            h("div", { class: "row" }, go, h("button", { class: "small", dataset: { testid: "restore-cancel" }, onclick: () => clear(pv) }, "Cancel")));
          go.focus();
        } catch (x) { clear(pv); err.append(errBox(x)); }
      } }, "Check");
      async function save(e, go) {
        if (!S.who) { B.whoInput.focus(); toast("Enter your name first (top of the page)."); return; }
        go.disabled = true;
        S.chain = (S.chain || Promise.resolve()).then(async () => {
          try {
            const res = await post(`/api/jobs/${id}/edits`, { who: S.who, edit: e });
            await ctx.saved(res, `restored “${clip(line.text, 30)}” as a ${AS_NAME[e.as]}`);
          } catch (x) { go.disabled = false; clear(err).append(errBox(x)); }
        });
      }
      clear(holder).append(h("div", { class: "rform" }, h("div", { class: "muted small" }, "What is this line in the book?"), ...choices,
        h("div", { class: "row" }, check, h("button", { class: "small", onclick: close }, "Close")), pv));
      holder.querySelector("input[type=radio]:checked")?.focus();
    }
    return row;
  }

  async function load(page = S.page) {
    const mine = ++token;
    let d;
    try { d = await get(`/api/jobs/${id}/pages/${page}/restorable`); }
    catch (e) { if (mine === token) { clear(el).append(errBox(e)); el.hidden = false; } return; }
    if (mine !== token || page !== S.page) return;
    const cands = d.lines.filter((l) => l.status === "candidate"), left = d.lines.filter((l) => l.status !== "candidate");
    clear(el);
    el.hidden = !d.lines.length;
    if (cands.length) {
      el.append(h("div", { class: "rhead", dataset: { testid: "restore-head" } }, h("b", {}, `${cands.length} line${cands.length === 1 ? "" : "s"} from the PDF ${cands.length === 1 ? "is" : "are"} not in the book text`),
        h("div", { class: "muted small" }, "Printed on this page but kept out of the text as a running head. A title that opens a chapter or part is often read this way. Restore it if it belongs in the book.")),
        ...cands.map((l) => rowFor(l, true)));
    }
    if (left.length) {
      el.append(h("details", { class: "restore-left", dataset: { testid: "restore-leftout" } },
        h("summary", { class: "muted small" }, `Left out of the book on purpose (${left.length}): ${[...new Set(left.map((l) => l.kind_name.toLowerCase()))].join(", ")}`),
        ...left.map((l) => rowFor(l, false))));
    }
  }
  return { el, load };
}
