import { steps } from "./steps.js";
import { clear, errBox, get, h, put, spinner } from "./util.js";

function isbnOk(v) {
  const d = v.replace(/[\s\-‐‑–—]/g, "");
  if (!/^97[89]\d{10}$/.test(d)) return false;
  let t = 0;
  for (let i = 0; i < 12; i++) t += +d[i] * (i % 2 ? 3 : 1);
  return (10 - (t % 10)) % 10 === +d[12];
}

const PART_LABELS = {
  front: ["Front matter", "Everything before the first chapter: title pages, preface, contents."],
  body: ["Body", "From the first chapter to the end of the last chapter."],
  bibliography: ["Bibliography / references", "A reference list after the last chapter."],
  glossary: ["Glossary", "A list of terms after the last chapter."],
  appendix: ["Appendix", "Appendices, answer keys, tables and other back matter."],
  index: ["Index", "The alphabetical index."],
};

// Book parts: every part a page range or explicitly none; the person must confirm them.
async function partsPanel(id, who) {
  const d = await get(`/api/jobs/${id}/parts`);
  const v = structuredClone(d.parts);
  const rows = {}, box = h("div"), out = h("div");
  const num = (part, k) => {
    const input = h("input", { type: "number", min: 1, max: d.pages, value: v[part]?.[k] ?? "", "aria-label": `${PART_LABELS[part][0]} ${k} page`, dataset: { testid: `part-${part}-${k}` },
      style: "width:90px", oninput: () => { v[part] = { ...(v[part] || {}), [k]: input.value === "" ? null : +input.value }; showProblems(); } });
    return input;
  };
  const table = h("tbody");
  for (const part of d.keys) {
    const none = h("input", { type: "checkbox", checked: v[part] === null, dataset: { testid: `part-${part}-none` },
      onchange: () => { v[part] = none.checked ? null : (d.guess[part] || { first: null, last: null }); first.disabled = last.disabled = none.checked; if (!none.checked) { first.value = v[part].first ?? ""; last.value = v[part].last ?? ""; } showProblems(); } });
    const first = num(part, "first"), last = num(part, "last");
    first.disabled = last.disabled = v[part] === null;
    rows[part] = h("div", { class: "err", dataset: { err: `part-${part}` } });
    table.append(h("tr", {}, h("td", {}, h("b", {}, PART_LABELS[part][0]), h("div", { class: "muted small" }, PART_LABELS[part][1])),
      h("td", {}, first), h("td", {}, last), h("td", {}, h("label", {}, none, " none")), h("td", {}, rows[part])));
  }
  const confirm = h("button", { class: "primary", dataset: { testid: "parts-confirm" } }, d.confirmed ? "Confirm again" : "Confirm book parts");
  const whoInput = h("input", { type: "text", value: who(), placeholder: "Your name", "aria-label": "Your name", dataset: { testid: "parts-who" },
    oninput: () => localStorage.setItem("reviewer", whoInput.value.trim()) });
  // Client-side check mirrors the server's (which decides): no overlap, no gap, full coverage.
  function problems() {
    const list = [], spans = [];
    for (const part of d.keys) {
      if (v[part] === null) continue;
      const { first, last } = v[part] || {};
      if (!Number.isInteger(first) || !Number.isInteger(last) || first < 1 || last < first || last > d.pages) { list.push([part, `Pages run from 1 to ${d.pages}; the first page is no later than the last.`]); continue; }
      spans.push([first, last, part]);
    }
    if (!v.body) list.push(["body", "A book has a body: give its page range."]);
    spans.sort((a, b) => a[0] - b[0]);
    spans.forEach((s, i) => {
      const prev = spans[i - 1];
      if (prev && s[0] <= prev[1]) list.push([s[2], `Overlaps ${prev[2]}.`]);
      else if (prev && s[0] > prev[1] + 1) list.push([s[2], `Pages ${prev[1] + 1}-${s[0] - 1} are in no part.`]);
    });
    if (spans.length && spans[0][0] > 1) list.push([spans[0][2], `Pages 1-${spans[0][0] - 1} are in no part.`]);
    if (spans.length && spans[spans.length - 1][1] < d.pages) list.push([spans[spans.length - 1][2], `Pages ${spans[spans.length - 1][1] + 1}-${d.pages} are in no part.`]);
    return list;
  }
  function showProblems() {
    const list = problems();
    for (const part of d.keys) rows[part].textContent = list.filter((p) => p[0] === part).map((p) => p[1]).join(" ");
    confirm.disabled = list.length > 0;
  }
  confirm.onclick = async () => {
    clear(out);
    const name = whoInput.value.trim();
    if (!name) { whoInput.focus(); out.append(h("div", { class: "err" }, "Enter your name first.")); return; }
    try {
      const r = await put(`/api/jobs/${id}/parts`, { parts: v, who: name });
      if (r.rerun) { location.hash = `#/job/${id}/convert`; return; }
      location.reload();
    } catch (e) {
      out.append(errBox(e));
      for (const p of e.body.problems || []) out.append(h("div", { class: "err" }, p.message));
    }
  };
  const status = d.confirmed
    ? h("div", { class: "banner info" }, `Confirmed by ${d.confirmed_by} on ${(d.confirmed_at || "").slice(0, 10)}. Change a range and confirm again if it is wrong.`)
    : h("div", { class: "banner warn" }, "Confirm the book parts before exporting. These page ranges are the converter's guess: check each one against the printed book (the book has " + d.pages + " pages).");
  box.append(status, h("div", { class: "panel" }, h("h3", {}, "Book parts (physical pages)"),
    h("p", { class: "muted small" }, "Every part is a range of pages or none. The parts must not overlap or leave pages out: front matter, then the body, then the back matter. A bibliography, glossary or index range is read as that kind of page."),
    h("table", {}, h("thead", {}, h("tr", {}, ["Part", "First page", "Last page", "", ""].map((t) => h("th", {}, t)))), table),
    h("div", { class: "row", style: "margin-top:8px" }, h("label", {}, "Confirmed by ", whoInput), confirm), out));
  showProblems();
  return box;
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
    publisher: field("publisher", "Publisher (optional)", { hint: "Needed by NIMAS, DAISY, JATS and BITS; listed as to supply when empty." }),
    publication_date: field("publication_date", "Publication date (optional)", { hint: "2026, 2026-03 or 2026-03-01. The year above is used when empty." }),
    rights: field("rights", "Rights statement (optional)"),
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
  const whoNow = () => localStorage.getItem("reviewer") || "";
  app.append(await partsPanel(id, whoNow));
  app.append(
    h("div", { class: "banner info" }, d.confirmed ? "These details were confirmed earlier. Change anything that is wrong." : "This is a draft read from the book. Check every field against the printed pages."),
    h("div", { class: "panel" }, h("div", { class: "cols2" }, f.isbn, f.title), h("div", { class: "cols2" }, f.edition, f.year), h("div", { class: "cols2" }, f.publisher, f.publication_date), h("div", {}, f.rights)),
    h("div", { class: "panel" }, h("h3", {}, "Authors"), h("p", { class: "muted small" }, "As printed on the title page. Check the split into first name, surname and degrees."),
      h("table", {}, h("thead", {}, h("tr", {}, ["Role", "First name", "Surname", "Degrees", ""].map((t) => h("th", {}, t)))), authors),
      h("button", { class: "small", style: "margin-top:8px", onclick: () => { v.authors.push({ role: "", firstname: "", surname: "", degrees: "" }); authorRows(); } }, "Add an author")),
    Object.keys(d.options).length ? h("div", { class: "panel" }, h("h3", {}, "Options for this profile"), opts) : "",
    out, h("div", { class: "row" }, save));
  check();
}
