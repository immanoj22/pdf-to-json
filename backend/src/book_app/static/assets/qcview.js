import { badge, h } from "./util.js";

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
export { badge };
