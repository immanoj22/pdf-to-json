"use strict";
// Focused, offline UI behavior checks. No browser, converter, book or file payload is used.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");
const tick = () => new Promise((resolve) => setImmediate(resolve));
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

class Element {
  constructor(tag = "div") {
    this.tag = tag; this.events = new Map(); this.children = []; this.dataset = {};
    this.hidden = false; this.disabled = false; this.files = []; this.clicks = 0;
    this.history = { text: [], value: [] }; this._text = ""; this._value = "";
    this.classes = new Set();
    this.classList = { toggle: (name, enabled) => enabled ? this.classes.add(name) : this.classes.delete(name) };
  }
  set textContent(value) { this._text = value; this.history.text.push(value); }
  get textContent() { return this._text; }
  set value(value) { this._value = value; this.history.value.push(value); }
  get value() { return this._value; }
  addEventListener(name, callback) {
    if (!this.events.has(name)) this.events.set(name, []);
    this.events.get(name).push(callback);
  }
  emit(name, event = {}) {
    event.preventDefault ||= () => { event.prevented = true; };
    return Promise.all((this.events.get(name) || []).map((callback) => callback(event)));
  }
  click() { this.clicks++; return this.emit("click"); }
  append(child) { this.children.push(child); }
  replaceChildren(...children) { this.children = children; }
}

const settings = { max_bytes: 2_000_000_000, reserve_bytes: 5_000_000_000, chunk_bytes: 4 * 1024 * 1024, token: "test-local-token" };
const reply = (body, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => structuredClone(body) });
const syntheticFile = (size, name = "synthetic.pdf") => ({
  name, size, slices: [],
  slice(start, end) {
    const part = { kind: "nonallocating-blob-slice", start, end: Math.min(end, size), size: Math.min(end, size) - start };
    this.slices.push(part); return part;
  },
  arrayBuffer() { throw new Error("The UI must not read a whole file into memory."); }
});

async function waitFor(condition, label) {
  for (let attempt = 0; attempt < 200; attempt++) {
    if (condition()) return;
    await tick();
  }
  throw new Error(`Timed out waiting for ${label}`);
}

async function harness(route, customSettings = {}) {
  const nodes = new Map(), window = new Element("window"), requests = [];
  const node = (id) => { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); };
  node("drop-zone").disabled = true;
  const config = { ...settings, ...customSettings };
  const context = vm.createContext({
    document: { getElementById: node, createElement: (tag) => new Element(tag) },
    window, AbortController, console,
    setTimeout: (callback) => setImmediate(callback),
    fetch: async (url, options = {}) => {
      const request = { url, ...options }; requests.push(request);
      if (url === "/api/config") return reply(config);
      if (options.method) assert.equal(options.headers["X-Upload-Token"], config.token);
      return route(request);
    }
  });
  vm.runInContext(source, context, { filename: "app.js" });
  await waitFor(() => !node("drop-zone").disabled, "configuration");
  return { node, window, requests, evaluate: (expression) => vm.runInContext(expression, context),
    idle: () => waitFor(() => !vm.runInContext("active", context), "UI idle") };
}

function happyRoute() {
  let size = 0, received = 0, polls = 0, inflight = 0, maxInflight = 0;
  const calls = [];
  const status = (state, extra = {}) => ({ id: "job1", state, size, received, message: state, ...extra });
  const route = async (request) => {
    calls.push(request);
    if (request.url === "/api/jobs") {
      size = JSON.parse(request.body).size; return reply(status("uploading"));
    }
    if (request.url.endsWith("/chunk")) {
      inflight++; maxInflight = Math.max(maxInflight, inflight);
      assert.equal(request.headers["X-Upload-Offset"], String(received));
      assert.equal(request.body.kind, "nonallocating-blob-slice");
      assert.equal(request.body.start, received);
      assert.ok(request.body.size <= settings.chunk_bytes);
      await tick(); received += request.body.size; inflight--;
      return reply(status("uploading"));
    }
    if (request.url.endsWith("/finish")) return reply(status("queued"));
    if (request.url === "/api/jobs/job1") {
      polls++;
      return reply(polls === 1 ? status("running") : status("done", { downloads: {
        "book.json": "/book", "review_list.json": "/review", "manifest.json": "/manifest"
      } }));
    }
    throw new Error(`Unexpected request ${request.url}`);
  };
  return { route, calls, maxInflight: () => maxInflight };
}

const checks = [];
async function check(name, action) {
  try { await action(); checks.push({ name, passed: true }); }
  catch (error) { checks.push({ name, passed: false, error: error.stack }); }
}

async function main() {
  await check("Configured decimal size limit and disk reserve are displayed", async () => {
    const h = await harness(() => { throw new Error("No mutation expected"); }, { max_bytes: 3_000_000_000 });
    assert.match(h.node("limits").textContent, /Maximum 3\.0 GB/);
    assert.match(h.node("limits").textContent, /5\.0 GB disk reserve/);
  });
  await check("Oversized synthetic PDF is refused before job creation or any slice", async () => {
    const h = await harness(() => { throw new Error("Oversize must not create a job"); });
    const file = syntheticFile(settings.max_bytes + 1);
    h.node("file").files = [file]; await h.node("file").emit("change");
    assert.equal(h.requests.filter((r) => r.method).length, 0);
    assert.equal(file.slices.length, 0);
    assert.equal(h.node("state").textContent, "Failed");
    assert.match(h.node("message").textContent, /no larger than 2\.0 GB/);
  });
  await check("Picker, sequential sliced upload, progress, status lifecycle and three downloads", async () => {
    const backend = happyRoute(), h = await harness(backend.route);
    await h.node("drop-zone").click(); assert.equal(h.node("file").clicks, 1);
    const file = syntheticFile(settings.chunk_bytes * 2 + 17, "<safe-name>.pdf");
    h.node("file").files = [file]; await h.node("file").emit("change");
    assert.equal(file.slices.length, 3); assert.equal(backend.maxInflight(), 1);
    assert.deepEqual(file.slices.map((part) => part.size), [settings.chunk_bytes, settings.chunk_bytes, 17]);
    const progress = h.node("progress").history.value;
    assert.ok(progress.some((p) => p > 0 && p < 50));
    assert.ok(progress.some((p) => p > 50 && p < 100));
    assert.equal(h.node("progress").value, 100);
    for (const state of ["Uploading", "Queued", "Running", "Done"]) assert.ok(h.node("state").history.text.includes(state));
    assert.equal(h.node("filename").textContent, "<safe-name>.pdf");
    assert.equal(h.node("downloads").hidden, false);
    assert.deepEqual(h.node("downloads").children.map((item) => item.children[0].textContent), ["book.json", "review_list.json", "manifest.json"]);
    for (const item of h.node("downloads").children) assert.equal(item.children[0].download, item.children[0].textContent);
    assert.equal(h.node("drop-zone").disabled, false); assert.equal(h.node("cancel").disabled, true);
  });
  await check("Drag and drop prevents navigation, highlights and starts upload", async () => {
    const backend = happyRoute(), h = await harness(backend.route);
    const drag = {}; await h.node("drop-zone").emit("dragover", drag); await h.window.emit("dragover", drag);
    assert.equal(drag.prevented, true); assert.ok(h.node("drop-zone").classes.has("dragging"));
    const outside = {}; await h.window.emit("drop", outside); assert.equal(outside.prevented, true);
    await h.node("drop-zone").emit("drop", { dataTransfer: { files: [syntheticFile(17)] } });
    await h.idle();
    assert.equal(h.node("state").textContent, "Done");
    assert.ok(!h.node("drop-zone").classes.has("dragging"));
  });
  await check("Cancellation aborts an in-flight chunk and prevents conversion", async () => {
    let chunkStarted = false, aborted = false, finishes = 0, cancels = 0;
    const h = await harness(async (r) => {
      if (r.url === "/api/jobs") return reply({ id: "job1", state: "uploading", received: 0, size: 100 });
      if (r.url.endsWith("/chunk")) {
        chunkStarted = true;
        return new Promise((resolve, reject) => r.signal.addEventListener("abort", () => {
          aborted = true; const error = new Error("Aborted"); error.name = "AbortError"; reject(error);
        }, { once: true }));
      }
      if (r.url.endsWith("/cancel")) { cancels++; return reply({ state: "failed", message: "Cancelled by user." }); }
      if (r.url.endsWith("/finish")) finishes++;
      throw new Error(`Unexpected request ${r.url}`);
    });
    h.node("file").files = [syntheticFile(100)]; const upload = h.node("file").emit("change");
    await waitFor(() => chunkStarted, "in-flight chunk");
    await h.node("cancel").click(); await upload;
    assert.equal(aborted, true); assert.equal(cancels, 1); assert.equal(finishes, 0);
    assert.equal(h.node("state").textContent, "Failed");
    assert.match(h.node("message").textContent, /Cancelled/);
    assert.equal(h.evaluate("active"), false);
  });
  await check("Running cancellation keeps upload disabled until terminal status is confirmed", async () => {
    const terminal = deferred(); let cancelling = false, terminalPoll = false, cancels = 0;
    const h = await harness(async (r) => {
      if (r.url === "/api/jobs") return reply({ id: "job1", state: "uploading", size: 1, received: 0 });
      if (r.url.endsWith("/chunk")) return reply({ state: "uploading", size: 1, received: 1 });
      if (r.url.endsWith("/finish")) return reply({ state: "queued" });
      if (r.url.endsWith("/cancel")) {
        cancels++; cancelling = true; return reply({ state: "running", message: "Cancelling converter" });
      }
      if (r.url === "/api/jobs/job1") {
        if (!cancelling) return reply({ state: "running", message: "Converting" });
        terminalPoll = true; return reply(await terminal.promise);
      }
      throw new Error(`Unexpected request ${r.url}`);
    });
    h.node("file").files = [syntheticFile(1)]; const upload = h.node("file").emit("change");
    await waitFor(() => h.node("state").textContent === "Running", "running conversion");
    await h.node("cancel").click();
    await waitFor(() => terminalPoll, "cancellation status polling");
    assert.equal(h.evaluate("active"), true); assert.equal(h.node("drop-zone").disabled, true);
    terminal.resolve({ state: "failed", message: "Cancelled; generated files retained." });
    await upload;
    assert.equal(cancels, 1); assert.equal(h.node("state").textContent, "Failed");
    assert.equal(h.evaluate("active"), false); assert.equal(h.node("drop-zone").disabled, false);
  });
  await check("Cancellation during job creation cancels the eventual job without an orphan", async () => {
    const created = deferred(); let creating = false, cancels = 0, chunks = 0;
    const h = await harness(async (r) => {
      if (r.url === "/api/jobs") { creating = true; return reply(await created.promise); }
      if (r.url.endsWith("/cancel")) { cancels++; return reply({ state: "failed", message: "Cancelled" }); }
      if (r.url.endsWith("/chunk")) chunks++;
      throw new Error(`Unexpected request ${r.url}`);
    });
    h.node("file").files = [syntheticFile(100)]; const upload = h.node("file").emit("change");
    await waitFor(() => creating, "pending job creation"); await h.node("cancel").click();
    assert.equal(h.evaluate("active"), true);
    created.resolve({ id: "job1", state: "uploading", size: 100, received: 0 }); await upload;
    assert.equal(cancels, 1); assert.equal(chunks, 0); assert.equal(h.node("state").textContent, "Failed");
  });
  await check("Server disk error is shown verbatim without starting a chunk", async () => {
    const message = "Not enough free disk: need 5,000,000,100 bytes including the 5 GB reserve.";
    const h = await harness((r) => {
      assert.equal(r.url, "/api/jobs"); return reply({ error: message }, 507);
    });
    h.node("file").files = [syntheticFile(100)]; await h.node("file").emit("change");
    assert.equal(h.node("message").textContent, message); assert.equal(h.node("state").textContent, "Failed");
    assert.equal(h.requests.filter((r) => r.url.endsWith("/chunk")).length, 0);
  });
  const result = { runner: "Node.js builtins (vm, assert); mocked DOM/fetch; no network", browser_visual_check: false,
    passed: checks.filter((item) => item.passed).length, failed: checks.filter((item) => !item.passed).length, checks };
  fs.writeFileSync(path.join(__dirname, "ui_check_results.json"), JSON.stringify(result, null, 2) + "\n");
  console.log(`${result.passed}/${checks.length} focused UI checks passed.`);
  for (const item of checks.filter((entry) => !entry.passed)) console.error(item.name + "\n" + item.error);
  process.exitCode = result.failed ? 1 : 0;
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
