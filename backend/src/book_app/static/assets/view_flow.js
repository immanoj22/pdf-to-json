import { steps } from "./steps.js";
import { STATE, badge, bytes, elapsed, errBox, get, h, post, put, spinner, toast, upload, api, when, clear } from "./util.js";

export async function newView({ app }) {
  const health = await get("/api/health");
  const msg = h("div");
  const prog = h("div", { class: "bar", hidden: true }, h("div", { style: "width:0" }));
  const input = h("input", { type: "file", accept: "application/pdf,.pdf", hidden: true, dataset: { testid: "file-input" } });
  const drop = h("div", { class: "drop", dataset: { testid: "dropzone" }, tabindex: "0" },
    h("p", { style: "font-size:18px;margin:0 0 8px" }, "Drop the book's PDF here"),
    h("p", { class: "muted" }, `or `, h("button", { onclick: () => input.click() }, "choose a file"), ` · PDF only, up to ${bytes(health.max_upload_bytes)}`));
  async function send(file) {
    clear(msg);
    if (!file) return;
    prog.hidden = false;
    const bar = prog.firstChild;
    drop.querySelectorAll("button").forEach((b) => (b.disabled = true));
    try {
      const job = await upload(`/api/jobs?filename=${encodeURIComponent(file.name)}`, file, (a, b) => (bar.style.width = `${(100 * a) / b}%`));
      location.hash = `#/job/${job.id}/profile`;
    } catch (e) {
      msg.append(errBox(e)); prog.hidden = true; drop.querySelectorAll("button").forEach((b) => (b.disabled = false));
    }
  }
  input.onchange = () => send(input.files[0]);
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); send(e.dataTransfer.files[0]); });
  app.append(h("h1", {}, "New book"), steps({ id: "", state: "" }, "upload"), drop, input, prog, msg,
    h("p", { class: "muted small" }, "The PDF stays on this computer. Nothing is sent anywhere."));
}

async function loadJob(id) { return get(`/api/jobs/${id}`); }

export async function profileView({ app, id }) {
  const job = await loadJob(id);
  let chosen = job.profile;
  app.append(h("h1", {}, job.name), steps(job, "profile"), h("h2", {}, "Choose the profile"),
    h("p", { class: "muted" }, "The profile holds the client's rules (for example Jaypee's). Pick one, or upload a new one."));
  const list = h("div", { class: "panel", dataset: { testid: "profile-list" } });
  const cont = h("button", { class: "primary", dataset: { testid: "profile-continue" }, disabled: !chosen }, "Continue");
  async function refresh(select) {
    const { profiles } = await get("/api/profiles");
    if (select) chosen = select;
    clear(list);
    const body = h("tbody");
    for (const p of profiles) {
      const radio = h("input", { type: "radio", name: "profile", value: p.ref, checked: chosen === p.ref || (chosen && p.origin === "builtin" && chosen === `${p.name}@${p.version}`), onchange: () => { chosen = p.ref; cont.disabled = false; } });
      body.append(h("tr", { dataset: { profile: p.ref } },
        h("td", {}, radio), h("td", {}, h("b", {}, p.name), p.description && h("div", { class: "muted small" }, p.description)),
        h("td", {}, p.version + (p.origin === "uploaded" ? ` (upload ${p.revision})` : "")),
        h("td", {}, badge(p.status)), h("td", { class: "small" }, p.added || p.date || "")));
    }
    list.append(h("table", {}, h("thead", {}, h("tr", {}, ["", "Profile", "Version", "Status", "Date"].map((t) => h("th", {}, t)))), body));
  }
  await refresh();
  app.append(list, uploadPanel(refresh), makerPanel());
  const err = h("div");
  cont.onclick = async () => {
    clear(err);
    try {
      await put(`/api/jobs/${id}/profile`, { ref: chosen });
      location.hash = job.state === "converted" ? `#/job/${id}/details` : `#/job/${id}/convert`;
    } catch (e) { err.append(errBox(e)); }
  };
  app.append(err, h("div", { class: "row" }, cont));
}

function uploadPanel(refresh) {
  const out = h("div", { dataset: { testid: "profile-upload-result" } });
  const file = h("input", { type: "file", accept: ".yaml,.yml,text/yaml", dataset: { testid: "profile-file" } });
  async function go(e) {
    clear(out);
    const f = file.files[0];
    if (!f) return;
    const text = await f.arrayBuffer();
    const url = `/api/profiles?filename=${encodeURIComponent(f.name)}`;
    try {
      const r = await api("POST", url, text, { raw: true, type: "text/yaml" });
      out.append(h("div", { class: "banner pass", dataset: { testid: "profile-saved" } },
        r.profile.new ? `Saved as a new version: ${r.profile.ref}. It is marked “untested”.` : `This exact file was already stored as ${r.profile.ref}.`));
      await refresh(r.profile.ref);
      document.querySelector("[data-testid=profile-continue]").disabled = false;
    } catch (err) {
      if (err.status === 422 && err.body.errors) {
        out.append(h("div", { class: "banner error", role: "alert", dataset: { testid: "profile-errors" } },
          h("b", {}, `The profile has ${err.body.errors.length} problem(s). Nothing was stored.`),
          h("table", {}, h("thead", {}, h("tr", {}, ["Line", "Field", "Problem", "Did you mean"].map((t) => h("th", {}, t)))),
            h("tbody", {}, err.body.errors.map((x) => h("tr", {}, h("td", {}, x.line ?? ""), h("td", {}, x.field), h("td", {}, x.message), h("td", {}, x.suggestion || "")))))));
      } else out.append(errBox(err));
    }
  }
  file.onchange = go;
  return h("div", { class: "panel" }, h("h3", {}, "Upload a profile file (YAML)"),
    h("p", { class: "muted small" }, "It is checked at once. A good file is stored as a new version and marked “untested”; older versions are never overwritten."),
    file, out);
}

function makerPanel() {
  const pre = h("pre", { class: "prompt", dataset: { testid: "maker-prompt" } }, "Loading…");
  let text = "";
  get("/api/profile-maker/prompt").then((d) => { text = d.prompt; pre.textContent = text; }).catch((e) => (pre.textContent = e.message));
  const copy = h("button", { class: "primary", dataset: { testid: "maker-copy" }, onclick: async () => {
    try { await navigator.clipboard.writeText(text); } catch {
      const r = document.createRange(); r.selectNodeContents(pre); const s = getSelection(); s.removeAllRanges(); s.addRange(r); document.execCommand("copy");
    }
    toast("Prompt copied.");
  } }, "Copy the prompt");
  return h("details", { class: "panel", dataset: { testid: "maker-panel" } }, h("summary", {}, "Make a profile from a client spec"),
    h("ol", {}, h("li", {}, "Copy the prompt below."), h("li", {}, "Paste it into an AI chat, together with the client's guideline/spec and the schema file (download it below)."),
      h("li", {}, "Save the YAML the AI returns as a file ending in .yaml."), h("li", {}, "Upload that file above. If it has errors, paste them back into the chat and ask for a corrected file.")),
    h("div", { class: "banner warn", style: "margin:8px 0" }, h("b", {}, "Give the AI only the client's guideline/spec, never book content.")),
    h("div", { class: "row", style: "margin-bottom:8px" }, copy,
      h("a", { class: "btn", href: "/api/profile-maker/schema", download: "profile.schema.json", dataset: { testid: "maker-schema" } }, "Download the schema file"),
      h("a", { class: "btn", href: "/api/profile-maker/base", download: "docbook_base.yaml" }, "Download the base profile")), pre);
}

export async function convertView({ app, id, onLeave }) {
  let job = await loadJob(id);
  app.append(h("h1", {}, job.name), steps(job, "convert"));
  const box = h("div", { class: "panel", dataset: { testid: "convert-panel" } });
  app.append(box);
  let timer;
  onLeave(() => clearInterval(timer));
  const err = h("div");
  async function start() {
    clear(err);
    try { job = await post(`/api/jobs/${id}/convert`); paint(); poll(); } catch (e) { err.append(errBox(e)); }
  }
  async function cancel() {
    clear(err);
    try { job = await post(`/api/jobs/${id}/cancel`); paint(); } catch (e) { err.append(errBox(e)); }
  }
  let shown = "";
  function paint() {
    const p = job.progress;
    const sig = `${job.state}|${p?.index}|${job.failure?.message}`;
    if (sig === shown) {
      const t = box.querySelector("[data-testid=progress-text]");
      if (t) t.textContent = `${p ? `Stage ${p.index} of ${p.total} · ` : ""}Elapsed ${elapsed(job.started_at)}`;
      return;
    }
    shown = sig;
    clear(box);
    if (["queued", "converting"].includes(job.state)) {
      const pct = p ? Math.round((100 * p.index) / p.total) : 0;
      box.append(h("p", {}, spinner(job.state === "queued" ? "Waiting for a free slot…" : (p?.label || "Starting") + "…")),
        h("div", { class: "bar" }, h("div", { style: `width:${pct}%` })),
        h("p", { class: "muted", dataset: { testid: "progress-text" } }, p ? `Stage ${p.index} of ${p.total} · ` : "", `Elapsed ${elapsed(job.started_at)}`),
        h("p", { class: "muted small" }, "This can take several minutes for a long book. You can close this page; the work continues."),
        h("button", { class: "danger", dataset: { testid: "cancel" }, onclick: cancel }, "Cancel"));
    } else if (job.state === "converted") {
      box.append(h("div", { class: "banner pass", dataset: { testid: "converted" } }, `Done in ${elapsed(job.started_at, job.finished_at)}.`),
        h("a", { class: "btn primary", href: `#/job/${id}/details`, dataset: { testid: "to-details" } }, "Continue to book details"));
    } else if (job.state === "failed") {
      const f = job.failure || {};
      box.append(h("div", { class: "banner error", role: "alert", dataset: { testid: "failure" } },
        h("b", {}, "The conversion stopped."),
        h("p", {}, f.stage ? `Stage: ${f.stage}. ` : "", f.page ? `Page: ${f.page}. ` : "", f.message || ""),
        h("p", { class: "muted small" }, f.error_type || "")),
        h("button", { class: "primary", onclick: start }, "Convert again"));
    } else {
      box.append(h("p", {}, job.state === "cancelled" ? "The conversion was cancelled and its temporary files were removed." : `${job.pages} pages · profile ${job.profile || "not chosen yet"}.`),
        !job.profile ? h("a", { class: "btn", href: `#/job/${id}/profile` }, "Choose a profile first")
          : h("button", { class: "primary", dataset: { testid: "start-convert" }, onclick: start }, "Convert"));
    }
    box.append(err);
  }
  function poll() {
    clearInterval(timer);
    timer = setInterval(async () => {
      try { job = await loadJob(id); } catch { return; }
      paint();
      if (!["queued", "converting"].includes(job.state)) clearInterval(timer);
    }, 1000);
  }
  paint();
  if (["queued", "converting"].includes(job.state)) poll();
}
