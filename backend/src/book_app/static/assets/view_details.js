import { steps } from "./steps.js";
import { clear, errBox, get, h, put, spinner } from "./util.js";

function isbnOk(v) {
  const d = v.replace(/[\s\-‐‑–—]/g, "");
  if (!/^97[89]\d{10}$/.test(d)) return false;
  let t = 0;
  for (let i = 0; i < 12; i++) t += +d[i] * (i % 2 ? 3 : 1);
  return (10 - (t % 10)) % 10 === +d[12];
}

export async function detailsView({ app, id }) {
  const job = await get(`/api/jobs/${id}`);
  app.append(h("h1", {}, job.name), steps(job, "details"));
  if (job.state !== "converted") { app.append(h("div", { class: "banner warn" }, "Convert the book first."), h("a", { class: "btn", href: `#/job/${id}/convert` }, "Go to Convert")); return; }
  const wait = h("div", { class: "panel" }, spinner("Reading the title and copyright pages… (a long book can take half a minute)"));
  app.append(wait);
  const d = await get(`/api/jobs/${id}/details`);
  wait.remove();
  const v = structuredClone(d.details);
  v.authors ||= []; v.options ||= {};
  const errs = {};
  const field = (key, label, extra = {}) => {
    const input = h("input", { type: "text", value: v[key] || "", dataset: { testid: `d-${key}` }, "aria-label": label, ...extra, oninput: () => { v[key] = input.value; check(); } });
    const e = h("div", { class: "err", dataset: { err: key } });
    errs[key] = e;
    return h("label", { class: "field" }, h("span", {}, label), input, e, extra.hint && h("div", { class: "muted small" }, extra.hint));
  };
  const isbnHint = d.details.sources?.isbn ? `Read from the book: ${d.details.sources.isbn}` : "Copy it from the copyright page. It is never guessed.";
  const f = {
    isbn: field("isbn", "ISBN-13 (required)", { hint: isbnHint }),
    title: field("title", "Title"), edition: field("edition", "Edition"), year: field("year", "Year"),
  };
  function check() {
    const i = v.isbn.trim();
    errs.isbn.textContent = !i ? "The ISBN is required." : isbnOk(i) ? "" : "This ISBN-13 is not valid: check its digits against the book.";
    errs.title.textContent = v.title.trim() ? "" : "The title is required.";
    save.disabled = !!(errs.isbn.textContent || errs.title.textContent);
  }
  const authors = h("tbody");
  function authorRows() {
    clear(authors);
    v.authors.forEach((a, i) => {
      const cell = (k, ph) => h("td", {}, h("input", { type: "text", value: a[k] || "", placeholder: ph, "aria-label": `Author ${i + 1} ${ph}`, dataset: { testid: `a-${i}-${k}` }, oninput: (e) => (a[k] = e.target.value) }));
      authors.append(h("tr", {}, cell("role", "role (optional)"), cell("firstname", "first name"), cell("surname", "surname"), cell("degrees", "degrees"),
        h("td", {}, h("button", { class: "small", "aria-label": `Remove author ${i + 1}`, onclick: () => { v.authors.splice(i, 1); authorRows(); } }, "Remove"))));
    });
  }
  authorRows();
  const opts = Object.entries(d.options).map(([name, o]) => {
    const cb = h("input", { type: "checkbox", checked: !!v.options[name], dataset: { testid: `opt-${name}` }, onchange: () => (v.options[name] = cb.checked) });
    return h("label", { style: "display:block;margin-bottom:6px" }, cb, " ", h("b", {}, name.replaceAll("_", " ")), h("div", { class: "muted small", style: "margin-left:22px" }, o.description));
  });
  const save = h("button", { class: "primary", dataset: { testid: "details-save" } }, "Confirm and continue to review");
  const out = h("div");
  save.onclick = async () => {
    clear(out);
    try { await put(`/api/jobs/${id}/details`, v); location.hash = `#/job/${id}/review`; }
    catch (e) {
      out.append(errBox(e));
      for (const p of e.body.problems || []) { out.append(h("div", { class: "err" }, p.message)); if (errs[p.field]) errs[p.field].textContent = p.message; }
    }
  };
  app.append(
    h("div", { class: "banner info" }, d.confirmed ? "These details were confirmed earlier. Change anything that is wrong." : "This is a draft read from the book. Check every field against the printed pages."),
    h("div", { class: "panel" }, h("div", { class: "cols2" }, f.isbn, f.title), h("div", { class: "cols2" }, f.edition, f.year)),
    h("div", { class: "panel" }, h("h3", {}, "Authors"), h("p", { class: "muted small" }, "As printed on the title page. Check the split into first name, surname and degrees."),
      h("table", {}, h("thead", {}, h("tr", {}, ["Role", "First name", "Surname", "Degrees", ""].map((t) => h("th", {}, t)))), authors),
      h("button", { class: "small", style: "margin-top:8px", onclick: () => { v.authors.push({ role: "", firstname: "", surname: "", degrees: "" }); authorRows(); } }, "Add an author")),
    Object.keys(d.options).length ? h("div", { class: "panel" }, h("h3", {}, "Options for this profile"), opts) : null,
    out, h("div", { class: "row" }, save));
  check();
}
