import { steps } from "./steps.js";
import { badge, clear, errBox, get, h, post, put, spinner, when } from "./util.js";
import { qcSections, verdictBanner } from "./qcview.js";

export async function exportView({ app, id }) {
  let job = await get(`/api/jobs/${id}`);
  app.append(h("h1", {}, job.name), steps(job, "export"));
  if (job.state !== "converted") { app.append(h("div", { class: "banner warn" }, "Convert the book first.")); return; }
  const [{ profiles }, { exports }] = await Promise.all([get("/api/profiles"), get(`/api/jobs/${id}/exports`)]);
  let details = null;
  try { details = (await get(`/api/jobs/${id}/details`)); } catch { /* shown below */ }
  const confirmed = details?.confirmed;
  const who = () => localStorage.getItem("reviewer") || "";
  const profSel = h("select", { "aria-label": "Profile", dataset: { testid: "export-profile" }, onchange: async () => {
    try { job = await put(`/api/jobs/${id}/profile`, { ref: profSel.value }); box.prepend(h("div", { class: "banner info" }, `Profile changed to ${profSel.value}. The next export uses it.`)); } catch (e) { box.prepend(errBox(e)); }
  } }, profiles.map((p) => h("option", { value: p.ref, selected: p.ref === job.profile }, `${p.name} ${p.version}${p.origin === "uploaded" ? ` (upload ${p.revision})` : ""} — ${p.status}`)));
  const override = h("input", { type: "checkbox", dataset: { testid: "override" } });
  const overrideBox = h("label", { hidden: true, class: "banner warn", style: "display:none" }, override, " ", h("b", {}, "Export anyway with missing picture descriptions."), " The override is recorded in the QC report.");
  const out = h("div", { dataset: { testid: "export-result" } });
  const btn = h("button", { class: "primary", dataset: { testid: "export-run" }, disabled: !confirmed }, "Export DocBook");
  const box = h("div", { class: "panel" },
    !confirmed ? h("div", { class: "banner warn" }, "Confirm the book details first. ", h("a", { href: `#/job/${id}/details` }, "Go to book details")) : null,
    h("label", { class: "field" }, h("span", {}, "Profile"), profSel),
    confirmed && h("p", { class: "muted" }, `${details.details.title} · ISBN ${details.details.isbn}`),
    overrideBox, h("div", { class: "row" }, btn, h("a", { class: "btn", href: `#/job/${id}/review` }, "Back to review")));
  btn.onclick = async () => {
    clear(out); btn.disabled = true;
    out.append(h("div", { class: "panel" }, spinner("Exporting and checking… (about half a minute for a long book)")));
    try {
      const r = await post(`/api/jobs/${id}/export`, { who: who() || "unknown", allow_alt_text_placeholders: override.checked });
      clear(out); out.append(...resultPanel(r, id));
      list(await get(`/api/jobs/${id}/exports`));
    } catch (e) {
      clear(out); out.append(errBox(e));
      if (e.code === "alt_text_placeholders") {
        overrideBox.hidden = false; overrideBox.style.display = "block";
        out.append(h("div", { class: "banner warn", dataset: { testid: "blocked" } }, `Export is blocked: ${e.body.placeholders} picture/equation description(s) are still missing. Write them in the review, or tick the override above.`,
          h("div", {}, h("a", { class: "btn small", href: `#/job/${id}/review` }, "Go to review"))));
      }
    } finally { btn.disabled = !confirmed; }
  };
  const history = h("div", { class: "panel", dataset: { testid: "export-history" } });
  function list(rows) {
    clear(history).append(h("h3", {}, "Earlier exports"));
    if (!rows.length) { history.append(h("p", { class: "muted" }, "None yet.")); return; }
    history.append(h("table", {}, h("tbody", {}, [...rows].reverse().map((r) => h("tr", {}, h("td", {}, `#${r.n}`), h("td", { class: "small" }, when(r.at)), h("td", {}, r.profile), h("td", {}, badge(r.verdict, r.verdict.toUpperCase()), r.override_alt_text ? " override" : ""),
      h("td", {}, h("a", { href: `/api/jobs/${id}/exports/${r.n}/delivery.zip` }, "ZIP"), " · ", h("a", { href: `/api/jobs/${id}/exports/${r.n}/qc_report.html`, target: "_blank" }, "QC report")))))));
  }
  list(exports);
  app.append(box, out, history);
}

function resultPanel(r, id) {
  const q = r.qc;
  return [
    verdictBanner({ verdict: q.verdict, reasons: q.reasons }),
    h("div", { class: "panel" }, h("div", { class: "row" },
      h("a", { class: "btn primary", href: `/api/jobs/${id}/exports/${r.n}/delivery.zip`, dataset: { testid: "download-zip" } }, `Download the delivery ZIP (${r.zip})`),
      h("a", { class: "btn", href: `/api/jobs/${id}/exports/${r.n}/qc_report.html?download=true`, dataset: { testid: "download-qc" } }, "Download the QC report (HTML)"),
      h("a", { class: "btn", href: `/api/jobs/${id}/exports/${r.n}/qc_report.html`, target: "_blank" }, "Open the QC report"),
      h("a", { class: "btn", href: `/api/jobs/${id}/exports/${r.n}/report/review_list.html`, target: "_blank" }, "Open the review list")),
      h("p", { class: "muted small" }, `Profile ${r.profile} (${r.profile_status}) · export #${r.n} · ${r.seconds ?? "?"} s`)),
    h("div", { class: "panel", dataset: { testid: "qc" } }, qcSections(q)),
  ];
}
