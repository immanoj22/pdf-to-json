// Sign in (a name and a role, no password: the app is for the office network) and the queue.
import { STATE, append, badge, clear, errBox, get, h, me, post, signIn, toast } from "./util.js";

export async function loginView({ app }) {
  const who = me();
  const name = h("input", { type: "text", value: who.name, placeholder: "Your name", "aria-label": "Your name", dataset: { testid: "login-name" } });
  const role = (v, label, help) => h("label", { style: "display:block;margin:6px 0" },
    h("input", { type: "radio", name: "role", value: v, checked: (who.role || "reviewer") === v, dataset: { testid: `login-${v}` } }), ` ${label} `, h("span", { class: "muted small" }, help));
  const err = h("div");
  const go = h("button", { class: "primary", dataset: { testid: "login-go" }, onclick: () => {
    clear(err);
    const n = name.value.trim();
    if (!n) { err.append(errBox({ message: "Enter your name." })); return; }
    signIn(n, app.querySelector("input[name=role]:checked").value);
    location.hash = "#/";
  } }, "Continue");
  app.append(h("h1", {}, "Who is using the app?"), h("div", { class: "panel" },
    h("label", { class: "field" }, h("span", {}, "Name"), name),
    role("manager", "Manager", "— uploads books, runs the queue, assigns reviewers, exports."),
    role("reviewer", "Reviewer", "— reviews and edits the books given to them."),
    h("p", { class: "muted small" }, "No password: the app is used on the office network. Your name goes into the audit log of everything you do."),
    go, err));
  name.focus();
}

const fmt = (s) => (s == null ? "" : s >= 3600 ? `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min` : `${Math.max(1, Math.round(s / 60))} min`);

export async function queueView({ app, onLeave }) {
  const manager = me().role === "manager";
  app.append(h("h1", {}, "Queue"), h("p", { class: "muted" }, "Books are converted in this order. A failed book leaves the queue and never holds up the others."));
  const box = h("div", { class: "panel", dataset: { testid: "queue-panel" } });
  const err = h("div");
  app.append(err, box);
  async function act(id, path, body) {
    clear(err);
    try { await post(`/api/queue/${id}/${path}`, body); await paint(); } catch (e) { err.append(errBox(e)); }
  }
  async function cancel(id) {
    clear(err);
    try { await post(`/api/jobs/${id}/cancel`); await paint(); } catch (e) { err.append(errBox(e)); }
  }
  async function retry(id) {
    clear(err);
    try { await post(`/api/jobs/${id}/convert`); toast("Back in the queue."); await paint(); } catch (e) { err.append(errBox(e)); }
  }
  async function paint() {
    let d;
    try { d = await get("/api/queue"); } catch (e) { clear(box).append(errBox(e)); return; }
    const rows = d.queue.filter((r) => r.position != null || ["converting", "failed"].includes(r.state));
    const status = (r) => {
      if (r.state === "converting") return `converting · step ${r.progress?.index ?? 0} of ${r.progress?.total ?? 18}`;
      if (r.state === "queued") return r.paused ? "paused" : "queued";
      return STATE[r.state] || r.state;
    };
    append(clear(box), h("table", { dataset: { testid: "queue-table" } },
      h("thead", {}, h("tr", {}, ["#", "Book", "Profile", "Uploaded by", "Status", "Time left", ""].map((t) => h("th", {}, t)))),
      h("tbody", {}, rows.map((r) => h("tr", { dataset: { testid: "queue-row", job: r.id, state: r.state } },
        h("td", {}, r.position ?? ""),
        h("td", {}, h("a", { href: `#/job/${r.id}` }, r.name), h("div", { class: "muted small" }, `${r.pages} pages`)),
        h("td", { class: "small" }, r.profile || ""),
        h("td", { class: "small" }, r.uploaded_by || ""),
        h("td", { dataset: { testid: "queue-status" } }, badge(r.paused ? "warn" : r.state, status(r)),
          r.state === "failed" && h("div", { class: "small", dataset: { testid: "queue-error" } }, r.failure?.message || "")),
        h("td", { class: "small" }, r.eta ? (r.state === "queued" ? `starts in ${fmt(r.eta.starts_in)}, done in ${fmt(r.eta.finishes_in)}` : `done in ${fmt(r.eta.finishes_in)}`) : ""),
        h("td", { class: "row" }, manager && r.state === "failed" && h("button", { class: "small primary", dataset: { testid: "queue-retry" }, onclick: () => retry(r.id) }, "Retry"), manager && r.state === "queued" && [
          h("button", { class: "small", dataset: { testid: "queue-up" }, onclick: () => act(r.id, "move", { direction: "up" }) }, "↑"),
          h("button", { class: "small", dataset: { testid: "queue-down" }, onclick: () => act(r.id, "move", { direction: "down" }) }, "↓"),
          h("button", { class: "small", dataset: { testid: "queue-pause" }, onclick: () => act(r.id, "pause", { paused: !r.paused }) }, r.paused ? "Resume" : "Pause"),
        ], manager && ["queued", "converting"].includes(r.state) && h("button", { class: "small danger", dataset: { testid: "queue-cancel" }, onclick: () => cancel(r.id) }, "Cancel")))))),
      !rows.length && h("p", { class: "muted", dataset: { testid: "queue-empty" } }, "Nothing is waiting. Upload books on the New book page."),
      h("p", { class: "muted small" }, `Up to ${d.max_parallel_jobs} book${d.max_parallel_jobs === 1 ? "" : "s"} at a time. Estimates use this computer's measured speed.`));
  }
  await paint();
  const timer = setInterval(paint, 2000);
  onLeave(() => clearInterval(timer));
}

// Reviewers of a converted book: one or more names, each with a page range or the whole book.
export function assignPanel(job, onSaved) {
  const rows = (job.assigned_to?.length ? job.assigned_to : [{ name: "", first: null, last: null }]).map((r) => ({ ...r }));
  const box = h("div", { class: "panel", dataset: { testid: "assign-panel" } });
  const err = h("div");
  function paint() {
    clear(box).append(h("b", {}, `Reviewers of ${job.name}`),
      ...rows.map((r, i) => h("div", { class: "row", dataset: { testid: "assign-row" } },
        h("input", { type: "text", value: r.name, placeholder: "Reviewer's name", "aria-label": "Reviewer's name", dataset: { testid: "assign-name" }, oninput: (e) => { r.name = e.target.value; } }),
        h("input", { type: "number", min: 1, max: job.pages, value: r.first ?? "", placeholder: "from page", style: "width:120px", "aria-label": "First page", dataset: { testid: "assign-first" }, oninput: (e) => { r.first = e.target.value; } }),
        h("input", { type: "number", min: 1, max: job.pages, value: r.last ?? "", placeholder: "to page", style: "width:120px", "aria-label": "Last page", dataset: { testid: "assign-last" }, oninput: (e) => { r.last = e.target.value; } }),
        h("span", { class: "muted small" }, "Leave the pages empty for the whole book."),
        h("button", { class: "small", onclick: () => { rows.splice(i, 1); paint(); } }, "Remove"))),
      h("div", { class: "row", style: "margin-top:6px" },
        h("button", { class: "small", dataset: { testid: "assign-add" }, onclick: () => { rows.push({ name: "", first: null, last: null }); paint(); } }, "Add a reviewer"),
        h("button", { class: "primary small", dataset: { testid: "assign-save" }, onclick: async () => {
          clear(err);
          try { const d = await (await import("./util.js")).put(`/api/jobs/${job.id}/assignments`, { reviewers: rows }); toast("Reviewers saved."); onSaved(d); }
          catch (e) { err.append(errBox(e)); }
        } }, "Save reviewers")), err);
  }
  paint();
  return box;
}
