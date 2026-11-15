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

// icon and colour per kind (the colour is a CSS variable value, see style.css .k-*)
export const ICON = {
  alt_text: "✎", figure: "▣", table: "▦", heading: "H", caption: "❝", structure: "§", character: "–", author: "☺",
  index: "≡", settings: "⚙", join: "⇄", list: "•", language: "A", page_label: "#", hidden_text: "◌", "adapter-inferred": "≡",
};

// Who counts as a person. A decision by the tool's reviewing assistant stays open until someone confirms it.
export const isPerson = (d) => !!d && !/^claude desktop/i.test(String(d.who || ""));
export const confirmed = (item) => isPerson(item.decision);
export const assistantDecided = (item) => !!item.decision && !isPerson(item.decision);

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
    case "heading": return cur.text ? `Is “${clip(cur.text, 28)}” a heading?` : "Is this a heading?";
    case "structure":
      if (/list marker/.test(r)) return "Is the symbol at the start a list marker?";
      if (/part without chapters/.test(r)) return "Should this part be a chapter?";
      if (/without a printed title/.test(r)) return "What is the title of this section?";
      if (/without content/.test(r)) return "Is this section really empty?";
      return "Where does this part, chapter or section start?";
    case "list": return "Is this symbol a bullet?";
    case "table": return "Does this table look right?";
    case "character": return item.editor === "dash" ? "Is this a range (–) or a minus (−)?" : "Does this character match the page?";
    case "join": return "Does this text continue after the break?";
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
  structure: ["Look at where the part, chapter or section starts.", "The book's outline follows your answer."],
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
};

// Items that look alike: same kind, same reason once numbers are ignored.
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
  const cur = item.current || {}, u = item.unit, text = cur.text || "";
  const A = (label, hint, action, fix, preview, extra = {}) => ({ label, hint, action, fix: fix || null, preview, ...extra });
  const same = { kind: "same", text: clip(text, 160) };
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
      if (item.kind === "language" || (!isHead && !isPara)) return [A("Looks right", "Keeps it as it is.", "accept", null, same, { suggested: true })];
      return [
        A("Looks right", "Keeps it as it is.", "accept", null, same, { suggested: true }),
        A("Change it…", "Choose what it should be, then confirm.", "fix", null, same, { form: "role" }),
      ];
    }
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
    case "author":
      return [A("Names are right", "Keeps the names.", "accept", null, same, { suggested: true }), A("Edit the names…", "Type the names, then confirm.", "fix", null, same, { form: "author" })];
    case "table":
      return [A("Looks right", "Keeps the table.", "accept", null, { kind: "table", text: cur.rows ? `${cur.rows} rows` : "" }, { suggested: true }),
              A("Needs fixing", "Leaves a note for the production team.", "fix", { note: "table needs fixing" }, { kind: "table", text: cur.rows ? `${cur.rows} rows` : "" })];
    default: {
      const label = { settings: "Use the placeholder", caption: "It stands alone", page_label: "The number is right", list: "Yes, it's a bullet",
        hidden_text: "Yes, it's hidden", structure: "Looks right" }[item.kind] || "Looks right";
      const hint = item.kind === "settings" ? "Fill it in on Book details later." : "Keeps it as it is.";
      return [A(label, hint, "accept", null, same, { suggested: true })];
    }
  }
}
