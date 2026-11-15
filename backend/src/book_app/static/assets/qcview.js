import { FORMAT_SHORT, badge, get, h } from "./util.js";

const table = (head, rows, nums = []) => h("div", { style: "overflow-x:auto" }, h("table", {}, h("thead", {}, h("tr", {}, head.map((t, i) => h("th", { class: nums.includes(i) ? "n" : "" }, t)))),
  h("tbody", {}, rows.map((r) => h("tr", {}, r.map((c, i) => h("td", { class: nums.includes(i) ? "n" : "" }, c)))))));

export function verdictBanner(r) {
  const v = r.verdict;
  return h("div", { class: `banner ${v}`, dataset: { testid: "verdict" } }, h("b", {}, v === "pass" ? "PASS" : v === "warn" ? "WARN" : "FAIL"),
    v === "pass" ? " — nothing to report." : v === "warn" ? " — usable, but look at these:" : " — do not deliver:",
    h("ul", { style: "margin:6px 0 0" }, (r.reasons || []).map((x) => h("li", {}, x))));
}

export function qcSections(q) {
  const out = [];
  if (q.dtd) {
    out.push(h("h3", {}, "DTD (DocBook 4.2)"), h("p", { dataset: { testid: "dtd" } }, `${q.dtd.errors} error(s) in ${q.dtd.files} file(s).`));
    const by = Object.entries(q.dtd.by_file || {});
    if (by.length) out.push(table(["File", "Errors", "First problem"], by.map(([f, v]) => [f, v.errors, (v.first || [])[0] || ""]), [1]));
  }
  if (q.house_rules?.by_rule) {
    const rules = Object.entries(q.house_rules.by_rule);
    out.push(h("h3", {}, `Jaypee house rules (${q.house_rules.violations ?? 0} finding(s))`),
      table(["Rule", "Guideline item", "Checked", "Findings", "Examples"], rules.map(([k, v]) => [k, v.item, v.checked, v.violations ? h("b", {}, v.violations) : 0, (v.examples || []).slice(0, 3).join("; ")]), [2, 3]));
  } else if (q.house_rules?.error) out.push(h("p", { class: "muted" }, q.house_rules.error));
  if (q.lossless) {
    const l = q.lossless;
    out.push(h("h3", {}, "Lossless check"), h("p", { dataset: { testid: "lossless" } }, `${l.missing} word(s) missing, ${l.extra} extra, out of ${l.tokens} in the book. XML matches the ledger: ${l.xml_matches_ledger ? "yes" : "NO"}. Unexplained character changes: ${l.character_changes?.unexplained ?? 0}.`));
  }
  if (q.text?.compared_with) {
    out.push(h("h3", {}, "Text compared with the converter's"), h("p", {}, `${q.text.removed} word(s) removed, ${q.text.added} added.`),
      q.text.removed_examples?.length ? h("p", { class: "small" }, "Removed: ", q.text.removed_examples.join(", ")) : null,
      q.text.added_examples?.length ? h("p", { class: "small" }, "Added: ", q.text.added_examples.join(", ")) : null);
  }
  if (q.overrides && (q.overrides.alt_text_placeholders || q.overrides.profile_upload)) {
    out.push(h("h3", {}, "Overrides recorded"), h("ul", {}, q.overrides.alt_text_placeholders ? h("li", { dataset: { testid: "override" } }, `Exported with ${q.overrides.alt_text_placeholders} missing picture description(s).`) : null,
      q.overrides.profile_upload ? h("li", {}, "The profile is an upload (untested).") : null));
  }
  if (q.warnings?.length) out.push(h("h3", {}, "Warnings"), h("ul", {}, q.warnings.map((w) => h("li", {}, w))));
  if (q.element_counts && Object.keys(q.element_counts).length) {
    out.push(h("details", {}, h("summary", {}, "Element counts"), table(["Element", "Count"], Object.entries(q.element_counts), [1])));
  }
  return out;
}
export function epubQcSections(q) {
  const out = [];
  const ec = q.epubcheck || {};
  out.push(h("h3", {}, "EPUBCheck"), h("p", { dataset: { testid: "epubcheck" } },
    ec.status === "run" ? `EPUBCheck ${ec.version}: ${ec.errors} error(s), ${ec.warnings} warning(s).` : `Not run: ${ec.reason || "no result"}.`));
  if (ec.messages?.length) out.push(table(["Severity", "Message", "Where"], ec.messages.slice(0, 20).map((m) => [m.severity, m.message, (m.locations || [])[0] || ""])));
  const own = Object.entries(q.own_checks || {});
  const total = own.reduce((s, [, v]) => s + v.violations, 0);
  out.push(h("h3", {}, `Our ePub checks (${total} finding(s))`),
    table(["Check", "Rule", "Checked", "Findings", "Examples"], own.map(([k, v]) => [k, v.item, v.checked, v.violations ? h("b", {}, v.violations) : 0, (v.examples || []).slice(0, 3).join("; ")]), [2, 3]));
  if (q.lossless) {
    const l = q.lossless;
    out.push(h("h3", {}, "Lossless check"), h("p", { dataset: { testid: "epub-lossless" } }, `${l.missing} word(s) missing, ${l.extra} extra, out of ${l.tokens} in the book. Pages match the ledger: ${l.xml_matches_ledger ? "yes" : "NO"}. Unexplained character changes: ${l.character_changes?.unexplained ?? 0}.`));
  }
  if (q.counts) out.push(h("details", {}, h("summary", {}, "Counts"), table(["Count", "Value"], Object.entries(q.counts).filter(([, v]) => typeof v !== "object"), [1])));
  if (q.warnings?.length) out.push(h("h3", {}, "Warnings"), h("ul", {}, q.warnings.map((w) => h("li", {}, w))));
  return out;
}

export { badge };


// ---- plain-words summary: what is wrong, and where to fix it -------------------------------
const KIND_WORDS = { alt_text: "picture or equation description", figure: "picture", heading: "heading", table: "table", list: "list", join: "paragraph split across pages", character: "odd character", structure: "chapter or part structure", caption: "caption", language: "language", page_label: "page number", settings: "book setting" };
const kindWord = (k) => KIND_WORDS[String(k).replace(/^.*?: /, "")] || String(k).replace(/^.*?: /, "").replace(/_/g, " ");

async function reviewItems(base) {
  try { const r = await fetch(`${base}/review_list.json`); return r.ok ? await r.json() : []; } catch { return []; }
}

// One list of problems for one format: each line says what it is in plain words and links to
// the review item / Browse page, the book details, or the full QC report.
export async function problemList(q, id, n, reportBase) {
  const lines = [];
  const items = (await reviewItems(reportBase)).filter((i) => i.severity === "must_check");
  const byKind = new Map();
  for (const i of items) { const k = i.kind; if (!byKind.has(k)) byKind.set(k, []); byKind.get(k).push(i); }
  const browse = (i) => `#/job/${id}/review?mode=browse&page=${i.page || 1}`;
  for (const [k, rows] of [...byKind].sort((a, b) => b[1].length - a[1].length)) {
    const first = rows[0];
    lines.push(h("li", { dataset: { testid: "problem" } }, h("b", {}, `${rows.length} ${kindWord(k)} item(s) a person must check`), ` — e.g. page ${first.page_label || first.page}: ${first.reason}. `,
      h("a", { href: browse(first) }, "Open the first on its page"), " · ", h("a", { href: `#/job/${id}/review` }, "Go to the review list")));
  }
  for (const w of q.settings_to_supply || []) lines.push(h("li", { dataset: { testid: "problem" } }, `Book setting missing: ${typeof w === "string" ? w : JSON.stringify(w)}. `, h("a", { href: `#/job/${id}/details` }, "Fill it in the book details")));
  const ec = q.epubcheck;
  if (ec?.errors) for (const m of (ec.messages || []).filter((x) => x.severity !== "WARNING").slice(0, 5)) lines.push(h("li", { dataset: { testid: "problem" } }, h("b", {}, "ePub checker error: "), `${m.message} (${(m.locations || [])[0] || "no location"})`));
  for (const [k, v] of Object.entries(q.house_rules?.by_rule || q.own_checks || {})) if (v.violations) lines.push(h("li", { dataset: { testid: "problem" } }, h("b", {}, `${v.violations} finding(s): ${v.item}. `), (v.examples || []).slice(0, 2).join("; ")));
  if (q.dtd?.errors) lines.push(h("li", { dataset: { testid: "problem" } }, h("b", {}, `${q.dtd.errors} XML structure error(s).`), " See the QC report for the files."));
  if (!lines.length) return h("p", { class: "muted small", dataset: { testid: "no-problems" } }, "No problems to follow up.");
  return h("div", { class: "panel", dataset: { testid: "problems" } }, h("h3", {}, "What to look at"), h("ul", {}, lines));
}

// Lossless is the release rule: any missing or extra word blocks the download. Say so plainly.
export function losslessBlock(q, isManager) {
  const l = q.lossless || {};
  if (!l.missing && !l.extra) return h("p", { class: "small", dataset: { testid: "lossless-ok" } }, badge("pass", "PASS"), " Lossless check: every word of the book is in the file (0 missing, 0 extra).");
  return h("div", { class: "banner fail", dataset: { testid: "lossless-block" } }, h("b", {}, "BLOCKED — this file is not released."),
    ` It is missing ${l.missing || 0} word(s) and has ${l.extra || 0} extra, out of ${l.tokens} in the book. `,
    isManager ? "As a manager you can download it anyway: you are asked to confirm, and your name is written to the audit log." : "Only a manager can download it anyway. Ask your manager, or fix the edits and export again.");
}

// The one-glance answer at the top of the screen, for the newest export.
export async function summaryBanner(r, id) {
  const rank = { pass: 0, warn: 1, fail: 2 };
  const parts = [["docbook", r.qc], ["epub", r.epub && r.epub_qc], ...Object.keys(r.others || {}).map((f) => [f, r.other_qc?.[f]])].filter(([, q]) => q?.verdict);
  const worst = parts.reduce((m, [, q]) => (rank[q.verdict] > rank[m] ? q.verdict : m), "pass");
  const lossy = parts.filter(([, q]) => q.lossless?.missing || q.lossless?.extra);
  const word = { pass: "PASS", warn: "WARN", fail: "FAIL" }[worst];
  const lead = { pass: "Nothing to report. Safe to deliver.", warn: "Usable, but someone must look at the points below first.", fail: "Do not deliver this export." }[worst];
  return h("div", { class: `banner ${worst}`, dataset: { testid: "summary" } }, h("div", { style: "font-size:1.3em" }, h("b", {}, word), ` — export #${r.n}. ${lead}`),
    h("ul", { style: "margin:6px 0 0" }, parts.map(([f, q]) => h("li", {}, h("b", {}, `${FORMAT_SHORT[f] || f} ${q.verdict.toUpperCase()}`), q.reasons?.length ? `: ${q.reasons.join("; ")}` : ": nothing to report")),
      lossy.map(([f]) => h("li", {}, h("b", {}, `${FORMAT_SHORT[f] || f} is blocked`), ": the text check found missing or extra words."))),
    h("div", { class: "small" }, h("a", { href: `#/job/${id}/review` }, "Review list"), " · ", h("a", { href: `#/job/${id}/review?mode=browse` }, "Browse pages")));
}
