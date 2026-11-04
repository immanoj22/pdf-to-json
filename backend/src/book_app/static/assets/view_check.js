import { badge, clear, errBox, get, h, spinner, upload, when } from "./util.js";
import { qcSections, verdictBanner } from "./qcview.js";

export async function checkView({ app }) {
  const [{ jobs }, { profiles }, { checks }] = await Promise.all([get("/api/jobs"), get("/api/profiles"), get("/api/checks")]);
  const book = h("select", { "aria-label": "Book", dataset: { testid: "check-book" } }, h("option", { value: "" }, "— none (DTD only) —"),
    jobs.filter((j) => j.state === "converted").map((j) => h("option", { value: j.id }, j.name)));
  const prof = h("select", { "aria-label": "Profile", dataset: { testid: "check-profile" } }, profiles.map((p) => h("option", { value: p.ref }, `${p.name} ${p.version}`)));
  const input = h("input", { type: "file", accept: ".zip,application/zip", dataset: { testid: "check-file" } });
  const out = h("div", { dataset: { testid: "check-result" } });
  const run = h("button", { class: "primary", dataset: { testid: "check-run" }, onclick: async () => {
    const f = input.files[0];
    clear(out);
    if (!f) { out.append(errBox({ message: "Choose the ZIP of the edited delivery first." })); return; }
    run.disabled = true; out.append(h("div", { class: "panel" }, spinner("Checking… (a long book can take a minute)")));
    try {
      const q = book.value ? `job=${book.value}` : `profile=${encodeURIComponent(prof.value)}`;
      const r = await upload(`/api/checks?filename=${encodeURIComponent(f.name)}&${q}`, f);
      clear(out).append(verdictBanner(r), h("div", { class: "panel", dataset: { testid: "check-qc" } }, qcSections(r)),
        h("a", { class: "btn", href: `/api/checks/${r.id}/report.html?download=true` }, "Download this report (HTML)"));
    } catch (e) { clear(out).append(errBox(e)); } finally { run.disabled = false; }
  } }, "Check the delivery");
  app.append(h("h1", {}, "Check an edited delivery"),
    h("p", { class: "muted" }, "You edited a delivery ZIP in your own XML editor? Upload it here. The app checks the DTD and the house rules, and compares the text with the book. ", h("b", {}, "Your files are only read, never changed.")),
    h("div", { class: "panel" },
      h("label", { class: "field" }, h("span", {}, "The book it was made from (for house rules and the text comparison)"), book),
      h("label", { class: "field" }, h("span", {}, "Or only the profile (DTD check without the book)"), prof),
      h("label", { class: "field" }, h("span", {}, "The delivery ZIP"), input), run), out,
    h("div", { class: "panel" }, h("h3", {}, "Earlier checks"), checks.length ? h("table", {}, h("tbody", {}, checks.map((c) => h("tr", {}, h("td", {}, c.name), h("td", { class: "small" }, when(c.checked_at || c.at)), h("td", {}, c.verdict ? badge(c.verdict, c.verdict.toUpperCase()) : ""),
      h("td", {}, h("a", { href: `/api/checks/${c.id}/report.html`, target: "_blank" }, "Report")))))) : h("p", { class: "muted" }, "None yet.")));
}
