// Shortcuts made visible: a thin strip at the bottom of Browse and Review (can be hidden, remembered
// per person), a "?" panel with every shortcut and when to use it, and three tips on a person's first
// three visits. The key lists here are the only place the app names its shortcuts (help.js and the
// tooltips use the same wording).
import { h, me } from "./util.js";

// [keys, what it does, when to use it]
export const SHORTCUTS = [
  ["Browse", [
    ["Click a word, then S", "Split the block there", "One paragraph that should be two: the new block starts with the word you clicked."],
    ["J", "Join with previous", "A paragraph cut by a page break, or a block the PDF cut in two."],
    ["Shift+click", "Pick a range of blocks", "Several blocks in a row that belong together."],
    ["Ctrl+click", "Add or remove one block from the pick", "Blocks that are not next to each other on the screen, or on another page (the pick stays when you turn the page)."],
    ["M", "Merge the picked blocks into one paragraph", "After Shift/Ctrl+click: a paragraph cut into several blocks, also across pages."],
    ["Alt+click on a word", "Split there at once", "Same as Click + S in one step (some systems keep Alt+click for the window: use S)."],
    ["U or Ctrl+Z", "Undo the last change", "You saved something by mistake: the whole action is taken back."],
    ["Esc", "Clear the pick or close the open panel", "When you picked the wrong blocks."],
    ["/", "Search the book", "Find a word or a sentence anywhere in the book."],
  ]],
  ["Review: flagged items", [
    ["1 2 3 4", "Choose answer 1 to 4", "The answer you want is listed on the card."],
    ["Enter", "The suggested answer, or Confirm", "You agree with what the converter or the assistant suggests."],
    ["S", "Not sure, skip", "Leave the item for later; it is recorded as skipped."],
    ["← →", "Previous or next item", "Move through the list without answering."],
    ["B", "Open this item in Browse", "You need to see the whole page and the blocks around the item."],
    ["A", "Apply the same answer to the similar items", "After an answer, when the app offers the same answer for the others."],
    ["U", "Undo the last answer", "You answered by mistake."],
  ]],
  ["Navigation", [
    ["← →", "Previous or next page (Browse)", "Turn the page without the mouse."],
    ["?", "This list of shortcuts", "Any time on Browse or Review."],
    ["Tab", "Next control", "Move through buttons and fields with the keyboard."],
  ]],
];

const BAR = {
  browse: [["Click a word + S", "split"], ["J", "join with previous"], ["Shift/Ctrl+click + M", "merge"], ["U", "undo"], ["?", "all shortcuts"]],
  queue: [["1–4", "answer"], ["Enter", "suggested"], ["S", "skip"], ["← →", "move"], ["B", "open in Browse"], ["U", "undo"], ["?", "all shortcuts"]],
};
const TIPS = {
  browse: [["Click a word, then S", "cuts a paragraph in two right there."],
    ["J", "joins a block with the one before it, even across a page break."],
    ["Shift/Ctrl+click, then M", "merges several blocks into one paragraph. U undoes."]],
  queue: [["1–4 or Enter", "answers the item: Enter takes the suggested answer."],
    ["S", "skips what you are unsure about, ← → move, U undoes."],
    ["B", "opens the item in Browse to see the whole page."]],
};

const who = () => (me().name || "anyone").toLowerCase();
const read = (k, d = "") => { try { return localStorage.getItem(k) ?? d; } catch { return d; } };
const write = (k, v) => { try { localStorage.setItem(k, v); } catch { /* private window */ } };
const chips = (pairs) => pairs.flatMap(([k, t], i) => [i ? h("span", { class: "kbsep" }, "·") : null, h("span", { class: "kbitem" }, h("kbd", {}, k), " ", t)]);

export function openShortcuts() {
  if (document.querySelector("[data-testid=shortcuts-panel]")) return;
  const close = () => { back.remove(); document.removeEventListener("keydown", onEsc, true); };
  const onEsc = (ev) => { if (ev.key === "Escape" || ev.key === "?") { ev.preventDefault(); ev.stopPropagation(); close(); } };
  const back = h("div", { class: "help-back", dataset: { testid: "shortcuts-panel" }, onclick: (e) => { if (e.target === back) close(); } },
    h("div", { class: "help-box shortcuts-box", role: "dialog", "aria-modal": "true", "aria-label": "All shortcuts" },
      h("h3", {}, "Shortcuts"),
      ...SHORTCUTS.map(([group, rows]) => h("section", { dataset: { group } }, h("h4", {}, group),
        h("table", { class: "kbtable" }, h("tbody", {}, rows.map(([k, what, when]) => h("tr", { dataset: { testid: "shortcut-row" } },
          h("td", {}, h("kbd", {}, k)), h("td", {}, h("b", {}, what), h("div", { class: "muted small" }, when))))))),
      ),
      h("div", { class: "row" }, h("button", { class: "primary", dataset: { testid: "shortcuts-close" }, onclick: close }, "Close (Esc)"))));
  document.body.append(back);
  document.addEventListener("keydown", onEsc, true);
  back.querySelector("button").focus();
}

// Mounts the strip, the "?" key and the first-time tips on Browse / Review. Returns {setMode, destroy}.
export function mountShortcuts({ app }) {
  let mode = "queue";
  const barKey = () => `shortcutBar:${who()}`;
  const hidden = () => read(barKey()) === "hidden";
  const strip = h("div", { class: "kbar", role: "note", dataset: { testid: "shortcut-bar" } });
  const tab = h("button", { class: "kbtab small", title: "Show the shortcut strip", dataset: { testid: "shortcut-tab" }, onclick: () => { write(barKey(), ""); paint(); } }, "⌨ Shortcuts");
  let card = null;

  function paint() {
    const off = hidden();
    strip.hidden = off; tab.hidden = !off;
    document.body.classList.toggle("has-kbar", !off);
    strip.replaceChildren(h("span", { class: "kbitems" }, ...chips(BAR[mode])),
      h("span", { class: "grow" }),
      h("button", { class: "small", title: "Every shortcut and when to use it (?)", dataset: { testid: "shortcuts-open" }, onclick: openShortcuts }, "? All shortcuts"),
      h("button", { class: "small", title: "Hide this strip (you can bring it back with the ⌨ button)", dataset: { testid: "shortcut-hide" }, onclick: () => { write(barKey(), "hidden"); paint(); } }, "Hide"));
  }
  // First three visits of each screen: three tricks, dismissible.
  const visits = new Set();
  function tips() {
    card?.remove(); card = null;
    const key = `tipVisits:${who()}:${mode}`;
    if (!visits.has(mode)) { visits.add(mode); write(key, String(+read(key, "0") + 1)); }
    if (+read(key, "0") > 3) return;
    card = h("div", { class: "kbtips panel", dataset: { testid: "first-tips" } },
      h("b", {}, mode === "browse" ? "Three tricks for Browse" : "Three tricks for the flagged items"),
      h("ul", {}, TIPS[mode].map(([k, t]) => h("li", {}, h("kbd", {}, k), " ", t))),
      h("div", { class: "row" },
        h("button", { class: "small primary", dataset: { testid: "tips-ok" }, onclick: () => { card.remove(); card = null; } }, "Got it"),
        h("button", { class: "small", dataset: { testid: "tips-never" }, onclick: () => { write(key, "99"); card.remove(); card = null; } }, "Do not show again"),
        h("button", { class: "small", onclick: openShortcuts }, "All shortcuts (?)")));
    (app.querySelector(".split") || app).before(card);
  }
  const onKey = (ev) => {
    if (ev.key !== "?" || ev.ctrlKey || ev.metaKey || ev.altKey) return;
    const t = ev.target, tag = t?.tagName;
    if (tag === "TEXTAREA" || tag === "SELECT" || (tag === "INPUT" && t.type !== "checkbox")) return;
    ev.preventDefault(); openShortcuts();
  };
  document.addEventListener("keydown", onKey);
  document.body.append(strip, tab);
  paint();
  return {
    setMode(m) { mode = m === "browse" ? "browse" : "queue"; paint(); tips(); },
    destroy() { document.removeEventListener("keydown", onKey); strip.remove(); tab.remove(); card?.remove(); document.body.classList.remove("has-kbar"); document.querySelector("[data-testid=shortcuts-panel]")?.remove(); },
  };
}
