import { h } from "./util.js";

export function steps(job, current) {
  const id = job.id || "";
  const converted = job.state === "converted";
  const items = [
    ["1 Upload", null, true],
    ["2 Profile", `#/job/${id}/profile`, !!id],
    ["3 Convert", `#/job/${id}/convert`, !!id],
    ["4 Book details", `#/job/${id}/details`, converted],
    ["5 Review", `#/job/${id}/review`, converted],
    ["6 Export", `#/job/${id}/export`, converted],
  ];
  return h("ol", { class: "stepper", dataset: { testid: "stepper" } }, items.map(([label, href, enabled], i) => {
    const key = ["upload", "profile", "convert", "details", "review", "export"][i];
    const cls = key === current ? "current" : (i < ["upload", "profile", "convert", "details", "review", "export"].indexOf(current) ? "done" : "");
    return h("li", { class: cls }, href && enabled ? h("a", { href }, label) : h("span", {}, label));
  }));
}
