// Help: a "?" on each screen (3 lines of guidance), a first-time tour (once per user, can be
// skipped) and an in-app notice when a book becomes ready.
import { get, h, me, toast } from "./util.js";

const HELP = {
  books: ["Search by name, ISBN or person; narrow the list with the state, profile and reviewer filters.", "Each book shows how far its review is. “Continue where I left off” returns to the page you last worked on.", "Copy makes a new book from an old one (for training or testing); it is rebuilt from the PDF."],
  new: ["Drop one or many PDFs; each gets its own profile.", "Book parts are optional here; they are confirmed after conversion, before export.", "A warning appears if a book with the same ISBN or the same file is already in the list."],
  queue: ["Books are converted in this order; the time left is an estimate from this computer's speed.", "When a book is ready you get a notice here, whatever screen you are on.", "A book that stopped with an error can be tried again with Retry."],
};
const TOUR = [
  ["Books", "#/", "Your books, with search, filters and review progress. Start here each day."],
  ["New book", "#/new", "Drop PDFs here. Several at once are queued in order."],
  ["Queue", "#/queue", "See what is converting and how long is left. A notice appears when a book is ready."],
  ["The ? button", null, "Every screen has a ? beside its title with three lines of guidance. You can replay this tour from any ?."],
];

function seenKey() { return `tourSeen:${me().name.toLowerCase()}`; }
function tourSeen() { try { return !!localStorage.getItem(seenKey()); } catch { return true; } }
function markSeen() { try { localStorage.setItem(seenKey(), "1"); } catch { /* private window */ } }

function dialog(content) {
  const back = h("div", { class: "help-back", dataset: { testid: "help-dialog" }, onclick: (e) => { if (e.target === back) back.remove(); } },
    h("div", { class: "help-box", role: "dialog", "aria-modal": "true" }, content));
  document.body.append(back);
  return back;
}

export function startTour() {
  let i = 0;
  const body = h("div");
  let box;
  const close = () => { markSeen(); box?.remove(); };
  function paint() {
    const [title, link, text] = TOUR[i];
    body.replaceChildren(h("p", { class: "muted small" }, `Step ${i + 1} of ${TOUR.length}`), h("h3", {}, title), h("p", {}, text),
      h("div", { class: "row" },
        h("button", { dataset: { testid: "tour-skip" }, onclick: close }, "Skip the tour"),
        i > 0 && h("button", { onclick: () => { i--; paint(); } }, "Back"),
        h("button", { class: "primary", dataset: { testid: "tour-next" }, onclick: () => { if (i === TOUR.length - 1) close(); else { i++; paint(); } } }, i === TOUR.length - 1 ? "Done" : "Next")));
  }
  paint();
  box = dialog(body);
}

function key(parts) {
  if (parts.length === 0) return "books";
  return ["new", "queue"].includes(parts[0]) ? parts[0] : null;
}

// Adds the "?" after the first title of the screen; the first visit of a person opens the tour.
export function attachHelp(root, parts) {
  const k = key(parts);
  const title = root.querySelector("h1");
  if (!k || !title || title.querySelector(".help-btn")) return;
  title.append(h("button", { class: "help-btn", "aria-label": "Help for this screen", dataset: { testid: "help-btn" }, onclick: () => {
    const box = dialog(h("div", {}, h("h3", {}, "About this screen"), h("ol", {}, HELP[k].map((t) => h("li", {}, t))),
      h("div", { class: "row" }, h("button", { dataset: { testid: "help-tour" }, onclick: () => { box.remove(); startTour(); } }, "Show the tour"),
        h("button", { class: "primary", onclick: () => box.remove() }, "Close"))));
  } }, "?"));
}

export function maybeTour() { if (me().name && !tourSeen()) startTour(); }

// A notice when a book finishes: polls the list; the first poll only records what is known.
let known = null;
export function startNotices() {
  async function poll() {
    if (!me().name) return;
    try {
      const { queue } = await get("/api/queue");
      const now = Object.fromEntries(queue.map((r) => [r.id, r]));
      if (known) for (const [id, r] of Object.entries(now)) {
        const was = known[id]?.state;
        if (was && was !== r.state && ["queued", "converting"].includes(was)) {
          if (r.state === "converted") notice(r, `“${r.name}” is ready.`, `#/job/${id}/details`);
          else if (r.state === "failed") notice(r, `“${r.name}” stopped with an error.`, "#/queue");
        }
      }
      known = Object.fromEntries(Object.entries(now).map(([id, r]) => [id, { state: r.state }]));
    } catch { /* the screens show connection problems */ }
  }
  poll(); setInterval(poll, 4000);
}
function notice(r, text, href) {
  const box = document.getElementById("toast");
  const t = h("div", { role: "status", dataset: { testid: "ready-notice" } }, text, " ", h("a", { href }, r.state === "converted" ? "Open" : "See why"));
  box.append(t); setTimeout(() => t.remove(), 20000);
}
export { toast };
