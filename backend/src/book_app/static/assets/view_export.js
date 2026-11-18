import { steps } from "./steps.js";
import { FORMAT_NAMES, FORMAT_SHORT, badge, clear, errBox, get, h, me, post, put, spinner, upload, when } from "./util.js";
import { epubQcSections, qcSections, verdictBanner, problemList, losslessBlock, summaryBanner } from "./qcview.js";


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
  const btn = h("button", { dataset: { testid: "export-run" }, disabled: !confirmed }, "Export the chosen format");
  const allBtn = h("button", { class: "primary", dataset: { testid: "export-all" }, disabled: !confirmed }, "Export all formats");
  const box = h("div", { class: "panel" },
    !confirmed ? h("div", { class: "banner warn" }, "Confirm the book details first. ", h("a", { href: `#/job/${id}/details` }, "Go to book details")) : null,
    h("label", { class: "field" }, h("span", {}, "Profile"), profSel),
    h("label", { class: "field" }, h("span", {}, "Only one format (the big button exports every format of this profile)"), fmtSel),
    coverField,
    confirmed && h("p", { class: "muted" }, `${details.details.title} · ISBN ${details.details.isbn}`),
    overrideBox, h("div", { class: "row" }, allBtn, btn, h("a", { class: "btn", href: `#/job/${id}/review` }, "Back to review")));
  const progress = h("div", { dataset: { testid: "export-progress" } });
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  async function runExport(formats) {
    clear(out); clear(progress); btn.disabled = true; allBtn.disabled = true;
    const rows = Object.fromEntries(formats.map((f) => [f, h("li", { dataset: { testid: `progress-${f}` } })]));
    const paint = (st) => formats.forEach((f) => {
      const s = st[f] || "waiting";
      clear(rows[f]).append(s === "done" ? "✔ " : s === "running" ? h("span", { class: "spinner" }) : "· ", `${FORMAT_NAMES[f] || f} — ${s === "done" ? "done" : s === "running" ? "working…" : "waiting"}`);
    });
    paint({});
    progress.append(h("div", { class: "panel" }, h("b", {}, "Exporting and checking…"), h("ul", {}, formats.map((f) => rows[f])), h("p", { class: "muted small" }, "About half a minute per format for a long book. You can leave this page open.")));
    try {
      await post(`/api/jobs/${id}/export/start`, { who: who() || "unknown", allow_alt_text_placeholders: override.checked, formats });
      for (;;) {
        await sleep(1500);
        const run = await get(`/api/jobs/${id}/export/progress`);
        paint(run.formats || {});
        if (run.state === "done") {
          clear(progress);
          const r = await get(`/api/jobs/${id}/exports/${run.n}`);
          out.append(...await resultPanel(r, id));
          await refresh();
          return;
        }
        if (run.state === "error") {
          clear(progress); out.append(errBox({ message: run.error }));
          if (run.code === "alt_text_placeholders") {
            overrideBox.hidden = false; overrideBox.style.display = "block";
            out.append(h("div", { class: "banner warn", dataset: { testid: "blocked" } }, `Export is blocked: ${run.extra?.placeholders ?? "some"} picture/equation description(s) are still missing. Write them in the review, or tick the override above.`,
              h("div", {}, h("a", { class: "btn small", href: `#/job/${id}/review` }, "Go to review"))));
          }
          return;
        }
      }
    } catch (e) { clear(progress); out.append(errBox(e)); }
    finally { btn.disabled = !confirmed; allBtn.disabled = !confirmed; }
  }
  btn.onclick = () => runExport(fmtSel.value === "all" ? supported() : [fmtSel.value]);
  allBtn.onclick = () => runExport(supported());
  const history = h("div", { class: "panel", dataset: { testid: "export-history" } });
  const summary = h("div", { dataset: { testid: "export-summary" } });
  async function refresh() {
    const [{ exports: rows, events }, ] = await Promise.all([get(`/api/jobs/${id}/export-history`)]);
    await paintSummary(rows); list(rows, events);
  }
  async function paintSummary(rows) {
    clear(summary);
    const last = rows[rows.length - 1];
    if (!last) return;
    try { summary.append(await summaryBanner(await get(`/api/jobs/${id}/exports/${last.n}`), id)); } catch { /* the result panel shows errors */ }
  }
  function list(rows, events) {
    clear(history).append(h("h3", {}, "Download history"));
    if (!rows.length) { history.append(h("p", { class: "muted" }, "Nothing exported yet.")); return; }
    const line = (e) => {
      const f = e.part === "out" ? "docbook" : e.part;
      const what = e.action === "download_override" ? h("b", { class: "fail-text" }, `downloaded anyway (${e.missing} missing, ${e.extra} extra words)`) : "downloaded";
      return h("li", { class: "small" }, `${when(e.at)} · ${e.who} ${""}`, what, ` ${FORMAT_NAMES[f] || f}`);
    };
    history.append(h("table", {}, h("thead", {}, h("tr", {}, ["Export", "When", "By", "Result", "Files", "Downloads"].map((t) => h("th", {}, t)))),
      h("tbody", {}, [...rows].reverse().map((r) => {
        const mine = (events || []).filter((e) => e.export === r.n && e.action !== "export");
        return h("tr", {}, h("td", {}, `#${r.n}`), h("td", { class: "small" }, when(r.at)), h("td", {}, r.who || "—"),
          h("td", {}, Object.entries(r.verdicts || { docbook: r.verdict }).map(([f, v]) => [(FORMAT_SHORT[f] || f) + " ", badge(v, v.toUpperCase()), " "]), r.override_alt_text ? h("div", { class: "small muted" }, "picture-description override") : null),
          h("td", {}, r.zip ? [h("a", { href: `/api/jobs/${id}/exports/${r.n}/delivery.zip` }, "DocBook ZIP"), " (", h("a", { href: `/api/jobs/${id}/exports/${r.n}/qc_report.html`, target: "_blank" }, "QC"), ")"] : null,
            r.epub ? [r.zip ? " · " : "", h("a", { href: `/api/jobs/${id}/exports/${r.n}/book.epub` }, "ePub"), " (", h("a", { href: `/api/jobs/${id}/exports/${r.n}/epub_qc_report.html`, target: "_blank" }, "QC"), ")"] : null,
            Object.entries(r.others || {}).map(([f, o], i) => [(r.zip || r.epub || i) ? " · " : "", h("a", { href: `/api/jobs/${id}/exports/${r.n}/formats/${f}/delivery.zip` }, `${o.label} ZIP`), " (", h("a", { href: `/api/jobs/${id}/exports/${r.n}/formats/${f}/qc_report.html`, target: "_blank" }, "QC"), ")"])),
          h("td", {}, mine.length ? h("ul", { style: "margin:0;padding-left:16px" }, mine.map(line)) : h("span", { class: "muted small" }, "none yet")));
      }))));
  }
  try { const hist = await get(`/api/jobs/${id}/export-history`); await paintSummary(hist.exports); list(hist.exports, hist.events); } catch { list(exports, []); }

  app.append(summary, box, progress, out, history);
}

async function resultPanel(r, id) {
  const out = [];
  if (r.qc?.verdict && r.zip) {
    const q = r.qc;
    out.push(h("h2", {}, "DocBook"), verdictBanner({ verdict: q.verdict, reasons: q.reasons }), losslessBlock(q, me().role === "manager"), await problemList(q, id, r.n, `/api/jobs/${id}/exports/${r.n}/report`),
      h("div", { class: "panel" }, h("div", { class: "row" },
        h("a", { class: "btn primary", href: `/api/jobs/${id}/exports/${r.n}/delivery.zip`, dataset: { testid: "download-zip" } }, `Download the delivery ZIP (${r.zip})`),
        h("a", { class: "btn", href: `/api/jobs/${id}/exports/${r.n}/qc_report.html?download=true`, dataset: { testid: "download-qc" } }, "Download the QC report (HTML)"),
        h("a", { class: "btn", href: `/api/jobs/${id}/exports/${r.n}/qc_report.html`, target: "_blank" }, "Open the QC report"),
        h("a", { class: "btn", href: `/api/jobs/${id}/exports/${r.n}/report/review_list.html`, target: "_blank" }, "Open the review list"))),
      h("div", { class: "panel", dataset: { testid: "qc" } }, qcSections(q)));
  }
  if (r.epub_qc && r.epub) {
    const q = r.epub_qc;
    out.push(h("h2", {}, "ePub 3"), verdictBanner({ verdict: q.verdict, reasons: q.reasons }), losslessBlock(q, me().role === "manager"), await problemList(q, id, r.n, `/api/jobs/${id}/exports/${r.n}/epub_report`),
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
    out.push(h("h2", {}, o.label), verdictBanner({ verdict: q.verdict, reasons: q.reasons }), losslessBlock(q, me().role === "manager"), await problemList(q, id, r.n, `${base}/report`),
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
