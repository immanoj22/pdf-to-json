// Small helpers shared by all screens. No libraries: the app loads nothing from outside.

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (k === "checked" || k === "disabled" || k === "selected" || k === "hidden") el[k] = !!v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  add(el, children);
  return el;
}
function add(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}
export const clear = (el) => { el.replaceChildren(); return el; };

export class ApiError extends Error {
  constructor(status, body) {
    super(body?.detail || `The request failed (${status}).`);
    this.status = status; this.body = body || {}; this.code = body?.code;
  }
}
export async function api(method, url, body, opts = {}) {
  const init = { method, headers: {} };
  if (body !== undefined && !opts.raw) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body); }
  if (opts.raw) { init.body = body; if (opts.type) init.headers["Content-Type"] = opts.type; }
  let res;
  try { res = await fetch(url, init); }
  catch { throw new ApiError(0, { detail: "The app is not answering. Is it still running?" }); }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text.slice(0, 200) }; }
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}
export const get = (u) => api("GET", u);
export const post = (u, b = {}) => api("POST", u, b);
export const put = (u, b = {}) => api("PUT", u, b);
export const del = (u) => api("DELETE", u);

export function upload(url, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded, e.total);
    xhr.onload = () => {
      let data = null;
      try { data = JSON.parse(xhr.responseText); } catch { /* not JSON */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data); else reject(new ApiError(xhr.status, data));
    };
    xhr.onerror = () => reject(new ApiError(0, { detail: "The upload was interrupted. Is the app still running?" }));
    xhr.send(file);
  });
}

export function toast(text, ms = 3500) {
  const box = document.getElementById("toast");
  const t = h("div", { role: "status" }, text);
  box.append(t);
  setTimeout(() => t.remove(), ms);
}
export const bytes = (n) => n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : n >= 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`;
export function elapsed(fromIso, toIso) {
  if (!fromIso) return "";
  const s = Math.max(0, Math.round(((toIso ? new Date(toIso) : new Date()) - new Date(fromIso)) / 1000));
  const m = Math.floor(s / 60);
  return m ? `${m} min ${String(s % 60).padStart(2, "0")} s` : `${s} s`;
}
export const when = (iso) => iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";
export const STATE = {
  uploaded: "Uploaded", queued: "Waiting to start", converting: "Converting", converted: "Converted",
  failed: "Stopped with an error", cancelled: "Cancelled",
};
export const badge = (cls, text) => h("span", { class: `badge ${cls}` }, text ?? cls);
export function errBox(e) { return h("div", { class: "banner error", role: "alert", dataset: { testid: "error" } }, e.message || String(e)); }
export function spinner(text) { return h("span", {}, h("span", { class: "spinner" }), text); }
export function confirmDialog(text) { return window.confirm(text); }
