import { clear, get, h, spinner } from "./util.js";
import { booksView } from "./view_books.js";
import { newView, profileView, convertView } from "./view_flow.js";
import { detailsView } from "./view_details.js";
import { reviewView } from "./view_review.js";
import { exportView } from "./view_export.js";
import { checkView } from "./view_check.js";
import { loginView, queueView } from "./view_queue.js";
import { me } from "./util.js";
import { attachHelp, maybeTour, startNotices } from "./help.js";

const app = document.getElementById("app");
let cleanup = null;

async function route() {
  cleanup?.(); cleanup = null;
  const hash = location.hash.replace(/^#/, "") || "/";
  const [path, query] = hash.split("?");
  const params = new URLSearchParams(query || "");
  const parts = path.split("/").filter(Boolean);
  // Each route draws into its own container, so a slow earlier route cannot add to this one.
  const root = h("div");
  // "Loading…" until the screen draws its first element, so a slow server never shows a blank page.
  const loading = h("div", { class: "panel", dataset: { testid: "loading" } }, spinner("Loading…"));
  clear(app).append(root, loading);
  const seen = new MutationObserver(() => { if (root.firstChild) { loading.remove(); seen.disconnect(); } });
  seen.observe(root, { childList: true });
  const ctx = { app: root, params, onLeave: (fn) => { cleanup = fn; } };
  const who = me();
  document.getElementById("me").textContent = who.name ? `${who.name} (${who.role})` : "Sign in";
  if (parts[0] === "job" && parts[1] && ["review", "details", "export", "edit"].includes(parts[2])) {
    try { localStorage.setItem(`lastBook:${who.name.toLowerCase()}`, location.hash); } catch { /* private window */ }
  }
  try {
    if (!who.name && parts[0] !== "login") { location.replace(`#/login`); return; }
    if (parts[0] === "login") await loginView(ctx);
    else if (parts[0] === "queue") await queueView(ctx);
    else if (parts.length === 0) await booksView(ctx);
    else if (parts[0] === "new") await newView(ctx);
    else if (parts[0] === "check") await checkView(ctx);
    else if (parts[0] === "job" && !/^[0-9a-f]{8,}$/i.test(parts[1] || "")) location.replace("#/new");
    else if (parts[0] === "job" && parts[1]) {
      const step = parts[2] || "auto";
      ctx.id = parts[1];
      if (step === "profile") await profileView(ctx);
      else if (step === "convert") await convertView(ctx);
      else if (step === "details") await detailsView(ctx);
      else if (step === "review") await reviewView(ctx);
      else if (step === "export") await exportView(ctx);
      else {
        const job = await get(`/api/jobs/${ctx.id}`);
        const next = !job.profile ? "profile" : job.state === "converted" ? "details" : "convert";
        location.replace(`#/job/${ctx.id}/${next}`);
      }
    } else root.append(h("p", {}, "That page does not exist."));
  } catch (e) {
    root.append(h("div", { class: "banner error", role: "alert", dataset: { testid: "error" } }, e.message));
  }
  loading.remove(); seen.disconnect();
  attachHelp(root, parts); maybeTour();
  app.focus();
}

async function health() {
  try {
    const d = await get("/api/health");
    const el = document.getElementById("health");
    el.textContent = `Free disk: ${(d.free_bytes / 1e9).toFixed(0)} GB` + (d.models_ready ? "" : " · layout models missing");
    el.title = d.lan ? "The office network is allowed" : "This computer only";
  } catch { /* shown by the screens */ }
}
window.addEventListener("hashchange", route);
startNotices();
health(); setInterval(health, 60000);
route();
