import { steps } from "./steps.js";
import { badge, clear, errBox, get, h, me, post, put, spinner, upload, when } from "./util.js";
import { epubQcSections, qcSections, verdictBanner } from "./qcview.js";

const FORMAT_NAMES = { docbook: "DocBook XML (ZIP)", epub: "ePub 3", html: "HTML5", dtbook: "NIMAS / DTBook", daisy3: "DAISY 3 (text-only)", jats: "JATS", bits: "BITS" };

// A file whose lossless check is not 0/0 is refused by the server. A manager can download it
// anyway after a warning; the server records who did in the audit log.
async function guardedDownload(event) {
  const a = event.target.closest?.("a[href]");
  if (!a || !/\/exports\/\d+\/(book\.epub|delivery\.zip|formats\/[a-z0-9]+\/delivery\.zip)$/.test(a.getAttribute("href"))) return;
  event.preventDefault();
  const who = me();
  const headers = who.name ? { "X-User": encodeURIComponent(who.name), "X-Role": who.role || "reviewer" } : {};
  const href = a.getAttribute("href");
  let res = await fetch(href, { headers });
  if (res.status === 409) {
    const body = await res.json().catch(() => ({}));
    if (body.code !== "lossless_failed") { alert(body.detail || "The download failed."); return; }
    if (who.role !== "manager") { alert(`${body.detail}\n\nOnly a manager can download it anyway.`); return; }
    if (!confirm(`${body.detail}\n\nDownload it anyway? Your name is recorded in the audit log.`)) return;
    res = await fetch(`${href}?override=yes`, { headers });
  }
  if (!res.ok) { alert("The download failed."); return; }
  const url = URL.createObjectURL(await res.blob());
  const link = h("a", { href: url, download: href.split("/").pop() });
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export async function exportView({ app, id }) {
  app.addEventListener("click", guardedDownload);
  let job = await get(`/api/jobs/${id}`);
  app.append(h("h1", {}, job.name), steps(job, "export"));
  if (job.state !== "converted") { app.append(h("div", { class: "banner warn" }, "Convert the book first.")); return; }
  const [{ profiles }, { exports }] = await Promise.all([get("/api/profiles"), get(`/api/jobs/${id}/exports`)]);
  let details = null;
  try { details = (await get(`/api/jobs/${id}/details`)); } catch { /* shown below */ }
  const confirmed = details?.confirmed;
  const who = () => localStorage.getItem("reviewer") || "";
  const profSel = h("select", { "aria-label": "Profile", dataset: { testid: "export-profile" }, onchange: async () => {
    btn.disabled = true;  // no export until the new profile is saved
    try { job = await put(`/api/jobs/${id}/profile`, { ref: profSel.value }); box.prepend(h("div", { class: "banner info" }, `Profile changed to ${profSel.value}. The next export uses it.`)); } catch (e) { box.prepend(errBox(e)); }
    finally { btn.disabled = !confirmed; }
  } }, profiles.map((p) => h("option", { value: p.ref, selected: p.ref === job.profile }, `${p.name} ${p.version}${p.origin === "uploaded" ? ` (upload ${p.revision})` : ""} — ${p.standard ? "standard" : p.status}`)));
  const override = h("input", { type: "checkbox", dataset: { testid: "override" } });
  const overrideBox = h("label", { hidden: true, class: "banner warn", style: "display:none" }, override, " ", h("b", {}, "Export anyway with missing picture descriptions."), " The override is recorded in the QC report.");
  const out = h("div", { dataset: { testid: "export-result" } });
  const fmtSel = h("select", { "aria-label": "Format", dataset: { testid: "export-format" } });
  const supported = () => (profiles.find((p) => p.ref === profSel.value)?.formats) || ["docbook"];
  function fillFormats() {
    const keep = fmtSel.value;
    clear(fmtSel);
    const fs = supported();
    fs.forEach((f) => fmtSel.append(h("option", { value: f }, FORMAT_NAMES[f] || f)));
    if (fs.length > 1) fmtSel.append(h("option", { value: "all" }, "Every format of this profile"));
    fmtSel.value = [...fmtSel.options].some((o) => o.value === keep) ? keep : fs[0];
    coverField.hidden = !fs.includes("epub");  // the cover image is only for ePub
  }
  profSel.addEventListener("change", fillFormats);
  const cover = await get(`/api/jobs/${id}/cover`).catch(() => ({ cover: null }));
  const coverNote = h("span", { class: "muted small", dataset: { testid: "cover-note" } }, cover.cover ? `Cover image on file: ${cover.cover}` : "No cover image yet (the ePub then has no cover page and the review list asks for one).");
  const coverIn = h("input", { type: "file", accept: "image/jpeg,image/png", dataset: { testid: "cover-file" }, onchange: async () => {
    const f = coverIn.files[0]; if (!f) return;
    try { await upload(`/api/jobs/${id}/cover?filename=${encodeURIComponent(f.name)}`, f); coverNote.textContent = `Cover image on file: ${f.name}`; } catch (e) { box.prepend(errBox(e)); }
  } });
  const coverField = h("label", { class: "field", dataset: { testid: "cover-field" } }, h("span", {}, "Front cover image for the ePub (JPEG or PNG, optional)"), coverIn, coverNote);
  fillFormats();
  const btn = h("button", { class: "primary", dataset: { testid: "export-run" }, disabled: !confirmed }, "Export");
  const box = h("div", { class: "panel" },
    !confirmed ? h("div", { class: "banner warn" }, "Confirm the book details first. ", h("a", { href: `#/job/${id}/details` }, "Go to book details")) : null,
    h("label", { class: "field" }, h("span", {}, "Profile"), profSel),
    h("label", { class: "field" }, h("span", {}, "Format"), fmtSel),
    coverField,
    confirmed && h("p", { class: "muted" }, `${details.details.title} · ISBN ${details.details.isbn}`),
    overrideBox, h("div", { class: "row" }, btn, h("a", { class: "btn", href: `#/job/${id}/review` }, "Back to review")));
  btn.onclick = async () => {
    clear(out); btn.disabled = true;
    out.append(h("div", { class: "panel" }, spinner("Exporting and checking… (about half a minute for a long book)")));
    try {
      const r = await post(`/api/jobs/${id}/export`, { who: who() || "unknown", allow_alt_text_placeholders: override.checked, formats: fmtSel.value === "all" ? supported() : [fmtSel.value] });
      clear(out); out.append(...resultPanel(r, id));
      list((await get(`/api/jobs/${id}/exports`)).exports);
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
    history.append(h("table", {}, h("tbody", {}, [...rows].reverse().map((r) => h("tr", {}, h("td", {}, `#${r.n}`), h("td", { class: "small" }, when(r.at)), h("td", {}, r.profile), h("td", {}, Object.entries(r.verdicts || { docbook: r.verdict }).map(([f, v]) => [(FORMAT_NAMES[f] || f).replace(" (ZIP)", "") + " ", badge(v, v.toUpperCase()), " "]), r.override_alt_text ? " override" : ""),
      h("td", {}, r.zip ? [h("a", { href: `/api/jobs/${id}/exports/${r.n}/delivery.zip` }, "ZIP"), " · ", h("a", { href: `/api/jobs/${id}/exports/${r.n}/qc_report.html`, target: "_blank" }, "QC report")] : null,
        r.epub ? [r.zip ? " · " : "", h("a", { href: `/api/jobs/${id}/exports/${r.n}/book.epub` }, "ePub"), " · ", h("a", { href: `/api/jobs/${id}/exports/${r.n}/epub_qc_report.html`, target: "_blank" }, "ePub QC report")] : null,
        Object.entries(r.others || {}).map(([f, o]) => [" · ", h("a", { href: `/api/jobs/${id}/exports/${r.n}/formats/${f}/delivery.zip` }, `${o.label} ZIP`), " (", h("a", { href: `/api/jobs/${id}/exports/${r.n}/formats/${f}/qc_report.html`, target: "_blank" }, "QC"), ")"])))))));
  }
  list(exports);
  app.append(box, out, history);
}

function resultPanel(r, id) {
  const out = [];
  if (r.qc?.verdict && r.zip) {
    const q = r.qc;
    out.push(h("h2", {}, "DocBook"), verdictBanner({ verdict: q.verdict, reasons: q.reasons }),
      h("div", { class: "panel" }, h("div", { class: "row" },
        h("a", { class: "btn primary", href: `/api/jobs/${id}/exports/${r.n}/delivery.zip`, dataset: { testid: "download-zip" } }, `Download the delivery ZIP (${r.zip})`),
        h("a", { class: "btn", href: `/api/jobs/${id}/exports/${r.n}/qc_report.html?download=true`, dataset: { testid: "download-qc" } }, "Download the QC report (HTML)"),
        h("a", { class: "btn", href: `/api/jobs/${id}/exports/${r.n}/qc_report.html`, target: "_blank" }, "Open the QC report"),
        h("a", { class: "btn", href: `/api/jobs/${id}/exports/${r.n}/report/review_list.html`, target: "_blank" }, "Open the review list"))),
      h("div", { class: "panel", dataset: { testid: "qc" } }, qcSections(q)));
  }
  if (r.epub_qc && r.epub) {
    const q = r.epub_qc;
    out.push(h("h2", {}, "ePub 3"), verdictBanner({ verdict: q.verdict, reasons: q.reasons }),
      h("div", { class: "panel", dataset: { testid: "epub-result" } }, h("div", { class: "row" },
        h("a", { class: "btn primary", href: `/api/jobs/${id}/exports/${r.n}/book.epub`, dataset: { testid: "download-epub" } }, `Download the ePub (${r.epub})`),
        h("a", { class: "btn", href: `/api/jobs/${id}/exports/${r.n}/epub_qc_report.html?download=true`, dataset: { testid: "download-epub-qc" } }, "Download the ePub QC report (HTML)"),
        h("a", { class: "btn", href: `/api/jobs/${id}/exports/${r.n}/epub_qc_report.html`, target: "_blank" }, "Open the ePub QC report"),
        h("a", { class: "btn", href: `/api/jobs/${id}/exports/${r.n}/epub_report/review_list.html`, target: "_blank" }, "Open the ePub review list"))),
      h("div", { class: "panel", dataset: { testid: "epub-qc" } }, epubQcSections(q)));
  }
  for (const [f, o] of Object.entries(r.others || {})) {
    const q = r.other_qc?.[f];
    if (!q) continue;
    const base = `/api/jobs/${id}/exports/${r.n}/formats/${f}`;
    out.push(h("h2", {}, o.label), verdictBanner({ verdict: q.verdict, reasons: q.reasons }),
      h("div", { class: "panel", dataset: { testid: `result-${f}` } }, h("div", { class: "row" },
        h("a", { class: "btn primary", href: `${base}/delivery.zip`, dataset: { testid: `download-${f}` } }, `Download ${o.label} (${o.zip})`),
        h("a", { class: "btn", href: `${base}/qc_report.html?download=true`, dataset: { testid: `download-${f}-qc` } }, "Download the QC report (HTML)"),
        h("a", { class: "btn", href: `${base}/qc_report.html`, target: "_blank" }, "Open the QC report"),
        h("a", { class: "btn", href: `${base}/report/review_list.html`, target: "_blank" }, "Open the review list"))),
      h("div", { class: "panel", dataset: { testid: `qc-${f}` } }, qcSections(q)));
  }
  out.push(h("p", { class: "muted small" }, `Profile ${r.profile} (${r.profile_status}) · export #${r.n} · ${r.seconds ?? "?"} s`));
  return out;
}
