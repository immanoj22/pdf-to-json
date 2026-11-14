import { steps } from "./steps.js";
import { PART_LABELS } from "./view_details.js";
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
      h("a", { class: "btn", href: "/api/profile-maker/base", download: "docbook_base.yaml" }, "Download the base profile")),
    h("div", { class: "row small muted", style: "margin-bottom:8px" }, "Base profiles of the other formats: ",
      ["html_base", "dtbook_nimas_base", "daisy3_base", "jats_base", "bits_base"].map((n) => h("a", { href: `/api/profile-maker/base?name=${n}`, download: `${n}.yaml`, dataset: { testid: `maker-${n}` } }, n))), pre);
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
      box.append(planPanel(id));
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

// Book parts before the conversion (optional): the conversion follows them, so confirming the
// same ranges later converts nothing again. They are still confirmed before any export.
function planPanel(id) {
  const box = h("details", { class: "panel", dataset: { testid: "plan-panel" } }, h("summary", {}, "Book parts (optional): give them now if you know them"));
  const out = h("div");
  (async () => {
    const d = await get(`/api/jobs/${id}/parts/plan`);
    const v = structuredClone(d.parts);
    const body = h("tbody");
    for (const part of d.keys) {
      const first = h("input", { type: "number", min: 1, max: d.pages, value: v[part]?.first ?? "", style: "width:90px", "aria-label": `${PART_LABELS[part][0]} first page`, dataset: { testid: `plan-${part}-first` } });
      const last = h("input", { type: "number", min: 1, max: d.pages, value: v[part]?.last ?? "", style: "width:90px", "aria-label": `${PART_LABELS[part][0]} last page`, dataset: { testid: `plan-${part}-last` } });
      const read = () => { v[part] = first.value === "" && last.value === "" ? null : { first: +first.value, last: +last.value }; };
      first.oninput = last.oninput = read;
      body.append(h("tr", {}, h("td", {}, h("b", {}, PART_LABELS[part][0])), h("td", {}, first), h("td", {}, last)));
    }
    const who = h("input", { type: "text", value: localStorage.getItem("reviewer") || "", placeholder: "Your name", "aria-label": "Your name", dataset: { testid: "plan-who" } });
    const save = h("button", { dataset: { testid: "plan-save" }, onclick: async () => {
      clear(out);
      try {
        await put(`/api/jobs/${id}/parts/plan`, { parts: v, who: who.value.trim() });
        localStorage.setItem("reviewer", who.value.trim());
        out.append(h("div", { class: "banner pass", dataset: { testid: "plan-saved" } }, "Saved. The conversion follows these parts; you confirm them after it, before exporting."));
      } catch (e) { out.append(errBox(e)); for (const p of e.body?.problems || []) out.append(h("div", { class: "err" }, `${PART_LABELS[p.part]?.[0] || ""} ${p.message}`)); }
    } }, "Save the parts for the conversion");
    const remove = d.planned && h("button", { class: "small", dataset: { testid: "plan-clear" }, onclick: async () => { await put(`/api/jobs/${id}/parts/plan`, { parts: null }); clear(out).append(h("div", { class: "banner info" }, "Removed: the converter finds the parts itself.")); } }, "Remove");
    box.open = d.planned;
    box.append(h("p", { class: "muted small" }, `Leave a part empty when the book has none. The book has ${d.pages} pages. Empty: the converter finds the parts itself.`),
      d.planned && h("div", { class: "banner info" }, `Parts given by ${d.planned_by}.`),
      h("table", {}, h("thead", {}, h("tr", {}, ["Part", "First page", "Last page"].map((t) => h("th", {}, t)))), body),
      h("div", { class: "row", style: "margin-top:8px" }, who, save, remove), out);
  })().catch((e) => box.append(errBox(e)));
  return box;
}
