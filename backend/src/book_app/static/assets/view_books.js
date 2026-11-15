import { FORMAT_SHORT, STATE, badge, bytes, confirmDialog, del, errBox, get, h, me, post, toast, when } from "./util.js";
import { assignPanel } from "./view_queue.js";

export async function booksView({ app }) {
  app.append(h("h1", {}, "Books"));
  const { jobs } = await get("/api/jobs");
  const bar = h("div", { class: "row", style: "margin-bottom:12px" },
    h("a", { class: "btn primary", href: "#/new", dataset: { testid: "new-book" } }, "New book"),
    h("a", { class: "btn", href: "#/check" }, "Check an edited delivery"),
    resumeLink() && h("a", { class: "btn", href: resumeLink(), dataset: { testid: "continue" } }, "Continue where I left off"));
  app.append(bar);
  if (!jobs.length) {
    app.append(h("div", { class: "panel" }, "No books yet. Press ", h("b", {}, "New book"), " and drop a PDF."));
    return;
  }
  // My books first: the books given to the person signed in, with their pages and progress.
  const who = me();
  const mine = jobs.filter((j) => (j.assigned_to || []).some((a) => a.name.toLowerCase() === who.name.toLowerCase()));
  if (mine.length) {
    app.append(h("h2", {}, "My books"), h("div", { class: "panel", dataset: { testid: "my-books" } }, h("table", {}, h("tbody", {}, mine.map((j) => {
      const a = j.assigned_to.find((x) => x.name.toLowerCase() === who.name.toLowerCase());
      const p = (j.review_progress?.reviewers || []).find((x) => x.name.toLowerCase() === who.name.toLowerCase());
      return h("tr", { dataset: { testid: "my-book", job: j.id } },
        h("td", {}, h("a", { href: `#/job/${j.id}/review` }, j.name)),
        h("td", { class: "small" }, a.first ? `pages ${a.first}–${a.last}` : "whole book"),
        h("td", { class: "small" }, p ? `${p.decided} of ${p.total} items decided` : "review list not prepared yet"),
        h("td", {}, h("a", { class: "btn small primary", href: `#/job/${j.id}/review` }, "Review")));
    }))))), h("h2", {}, "All books");
  }
  const body = h("tbody");
  const table = h("div", { class: "panel" }, h("table", { dataset: { testid: "books-table" } },
    h("thead", {}, h("tr", {}, ["Book", "Profile", "State", "Assigned to", "Review", "Last export", "Date", ""].map((t) => h("th", {}, t)))), body));
  const uniq = (xs) => [...new Set(xs.filter(Boolean))].sort();
  const sel = (label, tid, opts) => h("select", { "aria-label": label, dataset: { testid: tid }, onchange: draw },
    h("option", { value: "" }, label), opts.map(([v, t]) => h("option", { value: v }, t)));
  const search = h("input", { type: "search", placeholder: "Search name, ISBN, person…", "aria-label": "Search books", dataset: { testid: "books-search" }, oninput: draw });
  const fState = sel("Any state", "filter-state", uniq(jobs.map((j) => j.state)).map((s) => [s, STATE[s] || s]));
  const fProfile = sel("Any profile", "filter-profile", uniq(jobs.map((j) => j.profile)).map((p) => [p, p]));
  const fWho = sel("Any reviewer", "filter-reviewer", uniq(jobs.flatMap((j) => (j.assigned_to || []).map((a) => a.name))).map((n) => [n, n]));
  const sort = h("select", { "aria-label": "Sort", dataset: { testid: "books-sort" }, onchange: draw },
    [["new", "Newest first"], ["old", "Oldest first"], ["name", "Name A–Z"], ["progress", "Review progress"], ["state", "State"]].map(([v2, t]) => h("option", { value: v2 }, t)));
  const count = h("span", { class: "muted small", dataset: { testid: "books-count" } });
  const pct = (j) => (j.review_progress && j.review_progress.total ? j.review_progress.decided / j.review_progress.total : -1);
  function draw() {
    const q = search.value.trim().toLowerCase();
    let list = jobs.filter((j) => {
      if (fState.value && j.state !== fState.value) return false;
      if (fProfile.value && j.profile !== fProfile.value) return false;
      if (fWho.value && !(j.assigned_to || []).some((a) => a.name === fWho.value)) return false;
      if (!q) return true;
      const hay = [j.name, j.isbn, j.profile, j.uploaded_by, ...(j.assigned_to || []).map((a) => a.name)].join(" ").toLowerCase();
      return hay.includes(q);
    });
    const by = { new: (a, b) => (b.created_at || "").localeCompare(a.created_at || ""), old: (a, b) => (a.created_at || "").localeCompare(b.created_at || ""),
      name: (a, b) => a.name.localeCompare(b.name), progress: (a, b) => pct(b) - pct(a), state: (a, b) => a.state.localeCompare(b.state) }[sort.value];
    list = [...list].sort(by);
    body.replaceChildren(...list.map((j) => row(j, body)));
    count.textContent = `${list.length} of ${jobs.length} books`;
    if (!list.length) body.append(h("tr", {}, h("td", { colspan: 8, class: "muted", dataset: { testid: "books-none" } }, "No book matches. Clear the search or a filter.")));
  }
  app.append(h("div", { class: "filters", dataset: { testid: "books-filters" } }, search, fState, fProfile, fWho, sort, count), table);
  draw();
}

function resumeLink() {
  let hash = "";
  try { hash = localStorage.getItem(`lastBook:${me().name.toLowerCase()}`) || ""; } catch { /* private window */ }
  return /^#\/job\/[0-9a-f]{16}\//.test(hash) ? hash : "";
}

function progressCell(j) {
  const p = j.review_progress;
  if (!p || !p.total) return h("span", { class: "muted small" }, j.state === "converted" ? "not started" : "");
  const f = p.decided / p.total;
  return h("div", { class: "small", dataset: { testid: "book-progress" } }, h("span", { class: "minibar" }, h("i", { style: `width:${Math.round(100 * f)}%` })), ` ${Math.round(100 * f)}%`,
    h("div", { class: "muted" }, `${p.decided} of ${p.total} decided`));
}

function assigned(j) {
  if (!(j.assigned_to || []).length) return h("span", { class: "muted small" }, j.state === "converted" ? "nobody yet" : "");
  const prog = j.review_progress;
  return h("div", { class: "small", dataset: { testid: "assigned" } },
    j.assigned_to.map((a) => h("div", {}, `${a.name}${a.first ? ` (pp. ${a.first}–${a.last})` : ""}`)),
    prog && h("div", { class: "muted", dataset: { testid: "progress" } }, `${prog.decided} of ${prog.total} decided`));
}

function nextStep(j) {
  if (!j.profile) return "profile";
  if (j.state === "converted") return j.exports ? "export" : "details";
  return "convert";
}
function row(j, body) {
  const manager = me().role === "manager";
  const last = j.last_export;
  const tr = h("tr", { dataset: { job: j.id } },
    h("td", {}, h("a", { href: `#/job/${j.id}/${nextStep(j)}` }, j.name), j.is_copy && badge("warn", "COPY"), h("div", { class: "muted small" }, `${j.pages} pages · ${bytes(j.size)}`)),
    h("td", {}, j.profile || h("span", { class: "muted" }, "not chosen")),
    h("td", {}, badge(j.state, STATE[j.state] || j.state), j.uploaded_by && h("div", { class: "muted small" }, `uploaded by ${j.uploaded_by}`)),
    h("td", {}, assigned(j)),
    h("td", {}, progressCell(j)),
    h("td", {}, last ? [Object.entries(last.verdicts || { docbook: last.verdict }).map(([f, v]) => [`${FORMAT_SHORT[f] || f} `, badge(v, v.toUpperCase()), " "]), h("span", { class: "muted small" }, `#${last.n}`)] : h("span", { class: "muted" }, "none yet")),
    h("td", { class: "small" }, when(j.created_at)),
    h("td", { class: "row" },
      h("a", { class: "btn small", href: `#/job/${j.id}/${nextStep(j)}`, dataset: { testid: "open" } }, "Open"),
      manager && j.state === "converted" && h("a", { class: "btn small", href: `#/job/${j.id}/export`, dataset: { testid: "reexport" } }, "Re-export"),
      manager && j.state === "converted" && h("button", { class: "small", dataset: { testid: "assign" }, onclick: () => {
        const panel = assignPanel(j, () => { location.reload(); });
        tr.after(h("tr", {}, h("td", { colspan: 8 }, panel)));
      } }, "Assign…"),
      manager && h("button", { class: "small", dataset: { testid: "copy" }, title: "A new book marked COPY, for training or testing", onclick: async () => {
        const mode = await copyDialog(j);
        if (!mode) return;
        try {
          const c = await post(`/api/jobs/${j.id}/copy`, { decisions: mode });
          toast(c.state === "converted" ? "Copied. The COPY is ready to review." : "Copied. Press Start on the COPY when you want it converted.");
          location.reload();
        } catch (e) { body.closest(".panel").prepend(errBox(e)); }
      } }, "Copy"),
      manager && h("button", { class: "small danger", dataset: { testid: "delete" }, disabled: ["queued", "converting"].includes(j.state), onclick: async () => {
        if (!confirmDialog(`Delete “${j.name}”?\n\nThis removes the uploaded PDF, the converted book, the review decisions and every export of this book. Other books are not touched.`)) return;
        try { await del(`/api/jobs/${j.id}?confirm=yes`); tr.remove(); toast("Book deleted."); }
        catch (e) { body.closest(".panel").prepend(errBox(e)); }
      } }, "Delete")));
  return tr;
}

// Copy asks one thing: keep the review decisions or start clean. Resolves to "with", "clean" or null.
function copyDialog(j) {
  return new Promise((resolve) => {
    const close = (v) => { back.remove(); resolve(v); };
    const converted = j.state === "converted";
    const back = h("div", { class: "help-back", dataset: { testid: "copy-dialog" }, onclick: (e) => { if (e.target === back) close(null); } },
      h("div", { class: "help-box", role: "dialog", "aria-label": "Copy this book" },
        h("h2", {}, `Copy “${j.name}”`),
        h("p", {}, converted ? "The copy is marked COPY and is ready at once: it shares the converted pages with the original, so nothing is converted again and no disk space is used."
          : "This book is not converted yet. The copy is marked COPY and waits: press Start on it when you want it converted."),
        h("div", { class: "row" },
          h("button", { class: "primary", dataset: { testid: "copy-with" }, onclick: () => close("with") }, "With review decisions"),
          h("button", { dataset: { testid: "copy-clean" }, onclick: () => close("clean") }, "Clean (no decisions)"),
          h("button", { class: "small", dataset: { testid: "copy-cancel" }, onclick: () => close(null) }, "Cancel"))));
    document.body.append(back);
    back.querySelector("[data-testid=copy-clean]").focus();
    back.addEventListener("keydown", (e) => { if (e.key === "Escape") close(null); });
  });
}
