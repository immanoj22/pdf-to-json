import { STATE, badge, bytes, confirmDialog, del, errBox, get, h, toast, when } from "./util.js";

export async function booksView({ app }) {
  app.append(h("h1", {}, "Books"));
  const { jobs } = await get("/api/jobs");
  const bar = h("div", { class: "row", style: "margin-bottom:12px" },
    h("a", { class: "btn primary", href: "#/new", dataset: { testid: "new-book" } }, "New book"),
    h("a", { class: "btn", href: "#/check" }, "Check an edited delivery"));
  app.append(bar);
  if (!jobs.length) {
    app.append(h("div", { class: "panel" }, "No books yet. Press ", h("b", {}, "New book"), " and drop a PDF."));
    return;
  }
  const body = h("tbody");
  for (const j of jobs) body.append(row(j, body));
  app.append(h("div", { class: "panel" }, h("table", { dataset: { testid: "books-table" } },
    h("thead", {}, h("tr", {}, ["Book", "Profile", "State", "Last export", "Date", ""].map((t) => h("th", {}, t)))), body)));
}

function nextStep(j) {
  if (!j.profile) return "profile";
  if (j.state === "converted") return j.exports ? "export" : "details";
  return "convert";
}
function row(j, body) {
  const last = j.last_export;
  const tr = h("tr", { dataset: { job: j.id } },
    h("td", {}, h("a", { href: `#/job/${j.id}/${nextStep(j)}` }, j.name), h("div", { class: "muted small" }, `${j.pages} pages · ${bytes(j.size)}`)),
    h("td", {}, j.profile || h("span", { class: "muted" }, "not chosen")),
    h("td", {}, badge(j.state, STATE[j.state] || j.state)),
    h("td", {}, last ? [Object.entries(last.verdicts || { docbook: last.verdict }).map(([f, v]) => [f === "epub" ? "ePub " : "DocBook ", badge(v, v.toUpperCase()), " "]), h("span", { class: "muted small" }, `#${last.n}`)] : h("span", { class: "muted" }, "none yet")),
    h("td", { class: "small" }, when(j.created_at)),
    h("td", { class: "row" },
      h("a", { class: "btn small", href: `#/job/${j.id}/${nextStep(j)}`, dataset: { testid: "open" } }, "Open"),
      j.state === "converted" && h("a", { class: "btn small", href: `#/job/${j.id}/export`, dataset: { testid: "reexport" } }, "Re-export"),
      h("button", { class: "small danger", dataset: { testid: "delete" }, disabled: ["queued", "converting"].includes(j.state), onclick: async () => {
        if (!confirmDialog(`Delete “${j.name}”?\n\nThis removes the uploaded PDF, the converted book, the review decisions and every export of this book. Other books are not touched.`)) return;
        try { await del(`/api/jobs/${j.id}?confirm=yes`); tr.remove(); toast("Book deleted."); }
        catch (e) { body.closest(".panel").prepend(errBox(e)); }
      } }, "Delete")));
  return tr;
}
