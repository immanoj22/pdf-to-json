"use strict";
const $ = (id) => document.getElementById(id);
const picker = $("file"), drop = $("drop-zone"), cancel = $("cancel");
let config, job, active = false, cancelled = false, controller, cancellation;
const bytes = (n) => n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : `${(n / 1e6).toFixed(1)} MB`;
const pause = () => new Promise((resolve) => setTimeout(resolve, 1000));
async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.method) headers["X-Upload-Token"] = config.token;
  const response = await fetch(path, { ...options, headers, cache: "no-store" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}
function render(status) {
  $("state").textContent = status.state[0].toUpperCase() + status.state.slice(1);
  $("state").dataset.state = status.state;
  $("message").textContent = status.message || "";
  $("message").classList.toggle("error", status.state === "failed");
  if (status.size) {
    $("progress").value = Math.min(100, status.received / status.size * 100);
    $("amount").textContent = `${bytes(status.received)} / ${bytes(status.size)} uploaded`;
  }
  $("downloads").replaceChildren();
  $("downloads").hidden = status.state !== "done";
  for (const [name, url] of Object.entries(status.downloads || {})) {
    const link = document.createElement("a"), item = document.createElement("li");
    link.textContent = name; link.href = url; link.download = name;
    item.append(link); $("downloads").append(item);
  }
}
function cancelRemote() {
  cancellation ||= request(`/api/jobs/${job.id}/cancel`, { method: "POST" });
  return cancellation;
}
async function stopped() {
  if (!cancelled) return false;
  let status = await cancelRemote();
  while (!["done", "failed"].includes(status.state)) {
    render(status); await pause();
    status = await request(`/api/jobs/${job.id}`);
  }
  render(status);
  return true;
}
async function upload(file) {
  if (active || !config || !file) return;
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    render({ state: "failed", message: "Please choose a PDF file (.pdf)." }); return;
  }
  if (!file.size || file.size > config.max_bytes) {
    render({ state: "failed", message: `Choose a non-empty PDF no larger than ${bytes(config.max_bytes)}.` }); return;
  }
  active = true; cancelled = false; job = null; cancellation = null;
  drop.disabled = true; cancel.disabled = false;
  $("filename").textContent = file.name; $("filename").hidden = false;
  $("progress").value = 0;
  render({ state: "uploading", received: 0, size: file.size, message: "Checking available disk space…" });
  try {
    job = await request("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: file.name, size: file.size }) });
    if (await stopped()) return;
    render(job);
    for (let offset = job.received; offset < file.size;) {
      if (await stopped()) return;
      controller = new AbortController();
      const result = await request(`/api/jobs/${job.id}/chunk`, { method: "PUT", headers: { "X-Upload-Offset": String(offset) }, body: file.slice(offset, offset + config.chunk_bytes), signal: controller.signal });
      controller = null;
      if (await stopped()) return;
      if (result.received <= offset) throw new Error("The server did not accept the upload chunk.");
      offset = result.received; render(result);
    }
    if (await stopped()) return;
    let status = await request(`/api/jobs/${job.id}/finish`, { method: "POST" });
    while (true) {
      if (await stopped()) return;
      render(status);
      if (["done", "failed"].includes(status.state)) break;
      await pause();
      if (await stopped()) return;
      status = await request(`/api/jobs/${job.id}`);
    }
  } catch (error) {
    if (cancelled && job) {
      try { await stopped(); }
      catch (cancelError) { render({ state: "failed", message: `Could not confirm cancellation: ${cancelError.message}` }); }
    } else {
      render({ state: "failed", message: error.message });
      if (job) { try { await cancelRemote(); } catch (_) {} }
    }
  } finally {
    controller = null; active = false; drop.disabled = false; cancel.disabled = true; picker.value = "";
  }
}
cancel.addEventListener("click", () => {
  cancelled = true; cancel.disabled = true; controller?.abort();
  $("message").textContent = "Cancelling…";
  if (job) cancelRemote().catch(() => {});
});
drop.addEventListener("click", () => picker.click());
picker.addEventListener("change", () => upload(picker.files[0]));
for (const event of ["dragenter", "dragover", "dragleave", "drop"]) {
  window.addEventListener(event, (e) => e.preventDefault());
  drop.addEventListener(event, (e) => {
    drop.classList.toggle("dragging", ["dragenter", "dragover"].includes(event) && !active);
    if (event === "drop") upload(e.dataTransfer.files[0]);
  });
}
request("/api/config").then((value) => {
  config = value; drop.disabled = false;
  $("limits").textContent = `Maximum ${bytes(config.max_bytes)} per PDF · ${bytes(config.reserve_bytes)} disk reserve required in addition to the file.`;
}).catch((error) => render({ state: "failed", message: `Cannot connect to the local server: ${error.message}` }));
