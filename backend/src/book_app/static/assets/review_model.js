// What a review card says and offers, as plain data (no DOM): plain labels, the one question,
// the answers that name their result, and who counts as having decided. The card in
// view_review.js draws this; tests/review_model.test.mjs checks it with node.

export const KIND = {
  alt_text: "Picture description", figure: "Picture", table: "Table", heading: "Heading", caption: "Caption",
  structure: "Part, chapter or section", character: "Character", author: "Author", index: "Index", settings: "Book setting",
  join: "Text break", list: "List", language: "Language", page_label: "Page number", hidden_text: "Hidden text",
  "adapter-inferred": "Index entry",
};
export const kindName = (k) => KIND[k] || k;

// "structure" items are about different things; the reason says which. A "unit" in the
// converter is one block of text (a paragraph or list entry), not a part or chapter.
export function structureSub(item) {
  const r = item.reason || "";
  if (item.kind !== "structure") return null;
  if (/unit boundary/.test(r)) return "boundary";        // where this paragraph starts and ends
  if (/line join inside the unit/.test(r)) return "lines"; // lines inside the paragraph
  if (/list or entry decision/.test(r)) return "entry";    // list item or entry split
  if (/list marker/.test(r)) return "marker";
  if (/part without chapters/.test(r)) return "part";
  if (/without a printed title/.test(r)) return "untitled";
  if (/without content/.test(r)) return "empty";
  return "outline";
}
// The label shown on the card and in the list: what the item is about, in plain words.
export function itemKindName(item) {
  const sub = structureSub(item);
  if (sub === "boundary" || sub === "lines") return "Paragraph";
  if (sub === "entry" || sub === "marker") return "List";
  return kindName(item.kind);
}
// What a decision did, in words.
export function decisionWords(d) {
  if (!d) return "";
  return d.action === "accept" ? "kept as it is" : d.action === "skip" ? "skipped" : d.fix?.note ? "noted for the production team" : "changed";
}
// Lines of the item's text as printed (the split edit cuts at one of these).
export const linesOf = (item) => String(item.current?.text || "").split("\n");

// icon and colour per kind (the colour is a CSS variable value, see style.css .k-*)
export const ICON = {
  alt_text: "✎", figure: "▣", table: "▦", heading: "H", caption: "❝", structure: "§", character: "–", author: "☺",
  index: "≡", settings: "⚙", join: "⇄", list: "•", language: "A", page_label: "#", hidden_text: "◌", "adapter-inferred": "≡",
};

// Who counts as a person. A decision by the tool's reviewing assistant stays open until someone confirms it.
export const isPerson = (d) => !!d && !/^claude desktop/i.test(String(d.who || ""));
export const confirmed = (item) => isPerson(item.decision);
export const assistantDecided = (item) => !!item.decision && !isPerson(item.decision);

// Several flags on the same block that ask the same question are one row for the reviewer
// (e.g. two reasons on one picture). The first item leads; the others ride along in `also`.
// Their decisions stay on their own keys. A row is open until every one of them is decided.
export function mergeItems(items) {
  const rows = [], byKey = new Map();
  for (const it of items) {
    const k = it.unit ? `${it.unit}|${it.kind}|${structureSub(it) || ""}|${question(it)}` : null;
    const lead = k && byKey.get(k);
    if (lead) { lead.also.push(it); continue; }
    const row = { ...it, also: [] };
    if (k) byKey.set(k, row);
    rows.push(row);
  }
  for (const r of rows) {
    if (!r.also.length) continue;
    const all = [r, ...r.also];
    if (!all.every((x) => isPerson(x.decision))) r.decision = all.find((x) => x.decision && !isPerson(x.decision))?.decision || (all.every((x) => x.decision) ? r.decision : null);
    if (all.some((x) => x.severity === "must_check")) r.severity = "must_check";
  }
  return rows;
}
export const membersOf = (row) => [row, ...(row.also || [])];

// Order: structure first, then must-check, then the rest.
export const GROUPS = ["Structure", "Must check", "The rest"];
export const groupOf = (item) => (item.kind === "structure" ? 0 : item.severity === "must_check" ? 1 : 2);
export const ordered = (items) => items.map((it, n) => [it, n]).sort((a, b) => groupOf(a[0]) - groupOf(b[0]) || a[1] - b[1]).map((x) => x[0]);

// "The dash the tool kept": the reason says "kept en dash" or "kept minus".
export function keptDash(item) {
  const m = /kept (en dash|minus)/.exec(item.reason || "");
  return m ? (m[1] === "minus" ? "−" : "–") : null;
}
const clip = (s, n) => { s = String(s || "").replace(/\s+/g, " ").trim(); return s.length > n ? `${s.slice(0, n - 1)}…` : s; };

// The one plain question (about ten words).
export function question(item) {
  const cur = item.current || {}, r = item.reason || "";
  switch (item.kind) {
    case "figure": return "Is this a picture?";
    case "alt_text": return "What does this picture show?";
    case "heading": return (cur.clean ?? cur.text) ? `Is “${clip(cur.clean ?? cur.text, 28)}” a heading?` : "Is this a heading?";
    case "structure":
      switch (structureSub(item)) {
        case "boundary": return cur.type === "heading" ? `Is “${clip(cur.clean ?? cur.text, 28)}” one whole heading?` : "Is this one whole paragraph?";
        case "lines": return "Do these lines belong to the same paragraph?";
        case "entry": return "Is this list or entry split correctly?";
        case "marker": return "Is the symbol at the start a list marker?";
        case "part": return "Should this part be a chapter?";
        case "untitled": return "What is the title of this section?";
        case "empty": return "Is this section really empty?";
        default: return "Is this part, chapter or section right?";
      }
    case "list": return "Is this symbol a bullet?";
    case "table": return "Does this table look right?";
    case "character":
      if (item.editor === "hyphen_space") return "Hyphen followed by a space — remove the space?";
      return item.editor === "dash" ? "Is this a range (–) or a minus (−)?" : "Does this character match the page?";
    case "join": return "Does this text continue after the break?";
    case "reference": return "Is this reference read correctly?";
    case "language": return "Is the language of this text right?";
    case "caption": return "Does this caption belong to a picture or table?";
    case "page_label": return "Is the page number right?";
    case "settings": return /ISBN/.test(r) ? "What is the ISBN of this book?" : "What is the title of this book?";
    case "author": return "Are these names right?";
    case "index": return "Is this index entry right?";
    case "adapter-inferred": return "Is this index entry read correctly?";
    case "hidden_text": return "Is this text really hidden on the page?";
    default: return "Is this right?";
  }
}

// "What to check" / "What happens if you choose…" (one line each).
export const HELP = {
  figure: ["Look at the highlighted area on the page.", "A picture stays in the book; a decoration is left out."],
  alt_text: ["Describe the picture for a reader who cannot see it.", "The description is read aloud in the finished book."],
  heading: ["Does the text name the part that follows?", "A heading starts a section and appears in the contents."],
  structure: ["Look at the highlighted block on the page.", "The book's outline follows your answer."],
  list: ["Is the symbol printed as a list bullet?", "A bullet starts a list item; the symbol is removed from the text."],
  table: ["Compare the rows and columns with the page.", "“Needs fixing” leaves a note for the production team; the table is not changed here."],
  character: ["Compare the character with the page.", "The chosen character is written into the text."],
  join: ["Does the sentence carry on after the page or column break?", "Joining makes one paragraph; keeping them apart leaves two."],
  language: ["Read the text and decide its language.", "The language is used for hyphenation and reading aloud."],
  caption: ["Is the caption next to a picture or a table?", "It is attached to that picture or table."],
  page_label: ["Look for the printed number on the page.", "It is used as the page number in the contents."],
  settings: ["This is needed for the file name and the cover data.", "Fill it in on Book details."],
  author: ["Compare the names with the title page.", "The names go into the book's front matter."],
  index: ["Does the page number point to a real page?", "The entry is kept or left out of the index."],
  "adapter-inferred": ["Check the entry against the page.", "The entry is kept as shown."],
  hidden_text: ["Is the text covered or invisible on the page?", "Hidden text stays out of the book."],
  reference: ["Compare the reference with the page: authors, title, journal, year, pages, address.", "The reference is written as it is read. If a character is wrong or missing (for example the full stop between the title and the journal), correct the text."],
};

// Items that look alike: same kind, same reason once numbers are ignored.
export const HELP_SUB = {
  boundary: ["Does the highlighted block start and end where the paragraph does on the page?", "Splitting makes two paragraphs; joining adds the next paragraph to this one."],
  lines: ["Read the lines: is it one paragraph on the page?", "Splitting starts a new paragraph at the line you choose."],
  entry: ["Compare the list items or entries with the page.", "Changing it re-reads this block as you choose."],
};
export const HELP_EDITOR = {
  hyphen_space: ["Look at the hyphen and the space after it on the page.", "The space is taken out of the book text and the hyphen stays; the change is in the audit log and can be undone."],
};
export const helpFor = (item) => HELP_SUB[structureSub(item)] || HELP_EDITOR[item.editor] || HELP[item.kind];

export const similarKey = (item) => `${item.kind}|${String(item.reason || "").replace(/\d+/g, "N").replace(/\s+/g, " ")}`;

// One short line on why an answer is suggested.
export function why(item) {
  const cur = item.current || {};
  if (item.editor === "dash" && keptDash(item)) return `The tool kept the ${keptDash(item) === "−" ? "minus sign" : "en dash"}.`;
  if (item.kind === "figure") return cur.decorative ? "The tool treats it as a decoration." : "The tool treats it as a picture.";
  if (item.kind === "heading") return cur.type === "heading" ? `The tool made it a level ${cur.level ?? "?"} heading.` : "The tool left it as body text.";
  return "This is what the tool produced.";
}

// The answers for one item. Each says its result. action: accept (what the tool produced stays),
// fix (with `fix`, or `form` when the reviewer must type or choose first). `preview` is how it
// will look in the book. Skip is separate (always there).
export function answersFor(item) {
  const cur = item.current || {}, u = item.unit, text = cur.clean ?? cur.text ?? "";  // clean: as the book reads it
  const A = (label, hint, action, fix, preview, extra = {}) => ({ label, hint, action, fix: fix || null, preview, ...extra });
  const same = { kind: "same", text: clip(text, 160) };
  const sub = structureSub(item);
  if ((sub === "boundary" || sub === "lines") && (cur.type === "paragraph" || cur.type === "heading")) {
    const lines = linesOf(item), para = cur.type === "paragraph";
    const out = [A(para ? "Yes, one paragraph" : "Yes, one heading", "Keeps it as it is.", "accept", null, { kind: para ? "para" : "heading", level: cur.level, text }, { suggested: true })];
    if (para && lines.length > 1) out.push(A("No, split it…", "Choose the line where the new paragraph starts.", "fix", null, { kind: "split", text, line: 1 }, { form: "split" }));
    if (para && sub === "boundary") out.push(A("It continues in the next one", "Joins it with the next paragraph.", "fix", { op: "join_next", unit: u }, { kind: "join", text }));
    out.push(A("Something else…", "Make it a heading or a new chapter, then confirm.", "fix", null, same, { form: "role" }));
    return out;
  }
  switch (item.editor) {
    case "figure": {
      const dec = !!cur.decorative;
      return [
        dec ? A("Yes, it's a picture", "Keeps it in the book.", "fix", { op: "decorative", unit: u, value: false }, { kind: "picture", text: cur.alt_text })
            : A("Yes, it's a picture", "Keeps it in the book.", "accept", null, { kind: "picture", text: cur.alt_text }, { suggested: true }),
        dec ? A("No, it's decoration", "Leaves it out of the book.", "accept", null, { kind: "decor" }, { suggested: true })
            : A("No, it's decoration", "Leaves it out of the book.", "fix", { op: "decorative", unit: u, value: true }, { kind: "decor" }),
      ];
    }
    case "alt_text":
      return [
        A("Write a description", "Saves the text you type.", "fix", null, { kind: "picture", text: cur.alt_text }, { form: "alt", openAtStart: true }),
        cur.decorative ? A("It's a decoration", "Already left out of the book.", "accept", null, { kind: "decor" }, { suggested: true })
                       : A("It's a decoration", "Leaves it out of the book; no description needed.", "fix", { op: "decorative", unit: u, value: true }, { kind: "decor" }),
      ];
    case "heading": {
      const isHead = cur.type === "heading";
      return isHead ? [
        A("Yes, it's a heading", `Keeps level ${cur.level ?? "?"}.`, "accept", null, { kind: "heading", level: cur.level, text }, { suggested: true }),
        A("No, it's body text", "Becomes a normal paragraph.", "fix", { op: "heading_remove", unit: u }, { kind: "para", text }),
        A("Another level…", "Choose the level, then confirm.", "fix", null, { kind: "heading", level: 2, text }, { form: "heading" }),
      ] : [
        A("No, it's body text", "Stays a normal paragraph.", "accept", null, { kind: "para", text }, { suggested: true }),
        A("Yes, make it a heading…", "Choose the level, then confirm.", "fix", null, { kind: "heading", level: 2, text }, { form: "heading" }),
      ];
    }
    case "role": {
      const isHead = cur.type === "heading", isPara = cur.type === "paragraph";
      if (item.kind === "list") return [A("Yes, it's a bullet", "Keeps the list as it is.", "accept", null, same, { suggested: true })];
      if (item.kind === "language") return [A("Yes, the language is right", "Keeps it as it is.", "accept", null, same, { suggested: true })];
      if (!isHead && !isPara) return [A("Yes, it's right", "Keeps it as it is.", "accept", null, same, { suggested: true })];
      return [
        A(isHead ? "Yes, keep the heading" : "Yes, keep the paragraph", "Keeps it as it is.", "accept", null, isHead ? { kind: "heading", level: cur.level, text } : same, { suggested: true }),
        A("No, change it…", "Choose what it should be, then confirm.", "fix", null, same, { form: "role" }),
      ];
    }
    case "reference":
      return [
        A("Yes, it's right", "Writes the reference as it is read.", "accept", null, same, { suggested: true }),
        A("Correct the text…", "Fix a wrong or missing character, then confirm.", "fix", null, same, { form: "text" }),
      ];
    case "join":
      if (cur.type !== "paragraph") return [A("Keep as it is", "Nothing is joined.", "accept", null, same, { suggested: true })];
      return [
        A("No, keep them apart", "Two paragraphs stay.", "accept", null, same, { suggested: true }),
        A("Yes, join them", "Makes one paragraph.", "fix", { op: "join_next", unit: u }, { kind: "join", text }),
      ];
    case "dash": {
      const kept = keptDash(item), canFix = item.offset !== null && item.offset !== undefined;
      const mk = (ch, label) => (!canFix || ch === kept
        ? A(label, "Keeps the character the tool chose.", "accept", null, { kind: "char", text: ch, label: ch === "−" ? "minus sign" : "en dash" }, { suggested: ch === kept })
        : A(label, "Writes this character into the text.", "fix", { op: "char", unit: u, offset: item.offset, char: ch }, { kind: "char", text: ch, label: ch === "−" ? "minus sign" : "en dash" }));
      return canFix ? [mk("–", "Range (–)"), mk("−", "Minus (−)")] : [A("Looks right", "Keeps it as it is.", "accept", null, same, { suggested: true })];
    }
    case "hyphen_space": {
      // The space is in the PDF's own text, so it is never removed by itself: one click does it.
      const raw = String(cur.text || ""), at = item.offset;
      const ok = Number.isInteger(at) && raw[at] === " ";
      const fixed = ok ? raw.slice(0, at) + raw.slice(at + 1) : raw;
      const from = Math.max(0, (ok ? at : 0) - 60), shown = (s) => `${from ? "… " : ""}${s.slice(from, from + 150).replace(/\s+/g, " ").trim()}${s.length > from + 150 ? " …" : ""}`;
      const known = /written “[^”]+” elsewhere/.test(item.reason || "");
      return [
        A("Yes, remove the space", "Writes it as one word with its hyphen.", "fix", { op: "remove_char", unit: u, offset: at }, { kind: "para", text: shown(fixed) }, known ? { suggested: true } : {}),
        A("No, keep the space", "Keeps it as printed (for example “pre- and post-operative”).", "accept", null, { kind: "para", text: shown(raw) }, known ? {} : { suggested: true }),
      ];
    }
    case "author":
      return [A("Names are right", "Keeps the names.", "accept", null, same, { suggested: true }), A("Edit the names…", "Type the names, then confirm.", "fix", null, same, { form: "author" })];
    case "table":
      return [A("Looks right", "Keeps the table.", "accept", null, { kind: "table", text: cur.rows ? `${cur.rows} rows` : "" }, { suggested: true }),
              A("Needs fixing", "Leaves a note for the production team.", "fix", { note: "table needs fixing" }, { kind: "table", text: cur.rows ? `${cur.rows} rows` : "" })];
    default: {
      const label = { settings: "Use the placeholder", caption: "It stands alone", page_label: "The number is right", list: "Yes, it's a bullet",
        hidden_text: "Yes, it's hidden", structure: "Yes, it's right" }[item.kind] || "Looks right";
      const hint = item.kind === "settings" ? "Fill it in on Book details later." : "Keeps it as it is.";
      return [A(label, hint, "accept", null, same, { suggested: true })];
    }
  }
}
