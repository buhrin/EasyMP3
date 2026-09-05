import test from "node:test";
import assert from "node:assert/strict";

class Event {
  listeners = [];
  addListener(listener) { this.listeners.push(listener); }
  emit(value) { for (const listener of this.listeners) listener(value); }
}

const runtimeMessages = new Event();
let stored = [];
let lastPort;
let protocolVersion = 1;
let downloadMode = "failure";

function makePort() {
  lastPort = {
    onMessage: new Event(),
    onDisconnect: new Event(),
    sent: [],
    disconnected: false,
    postMessage(message) {
      this.sent.push(message);
      queueMicrotask(() => {
        if (message.type === "hello") {
          this.onMessage.emit({ id: message.id, ok: true, protocolVersion, outputFolder: "C:\\Music" });
        } else if (message.type === "download" && downloadMode === "failure") {
          this.onMessage.emit({ id: message.id, ok: false, error: "failed" });
        } else if (message.type === "download") {
          const jobId = downloadMode === "fast" ? "job-fast" : "job-active";
          if (downloadMode === "fast") {
            this.onMessage.emit({ type: "job", job: { id: jobId, url: message.url, status: "Completed" } });
          }
          this.onMessage.emit({ id: message.id, ok: true, jobId });
        }
      });
    },
    disconnect() {
      this.disconnected = true;
      this.onDisconnect.emit();
    },
  };
  return lastPort;
}

globalThis.chrome = {
  runtime: {
    onMessage: runtimeMessages,
    connectNative: makePort,
    sendMessage: () => Promise.resolve(),
    getURL: path => `chrome-extension://test/${path}`,
    get lastError() { return null; },
  },
  tabs: { query: (_query, callback) => callback([]), sendMessage: () => Promise.resolve() },
  storage: {
    session: {
      get: async () => ({ jobs: stored }),
      set: async value => { stored = value.jobs; },
    },
  },
};

const background = await import("../background.js");
const send = message => new Promise(resolve => runtimeMessages.listeners[0](
  message,
  { url: "chrome-extension://test/popup.html" },
  resolve,
));

test("a rejected download closes an idle helper connection", async () => {
  const response = await send({ type: "download", url: "https://youtube.com/watch?v=abcdefghijk" });
  assert.equal(response.ok, false, response.error);
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(lastPort.disconnected, true);
});

test("disconnect turns active records into terminal errors", async () => {
  const job = { id: "job-1", url: "https://www.youtube.com/watch?v=abcdefghijk", status: "Queued" };
  background.__test.jobs.set(job.id, job);
  background.__test.failActiveJobs("helper disconnected");
  await new Promise(resolve => setTimeout(resolve, 0));
  const state = await send({ type: "get-state" });
  assert.equal(state.jobs.find(value => value.id === job.id).status, "Error");
});

test("a fast terminal event is not overwritten by a queued placeholder", async () => {
  downloadMode = "fast";
  const response = await send({ type: "download", url: "https://youtube.com/watch?v=bcdefghijkl" });
  assert.equal(response.ok, true);
  assert.equal(background.__test.jobs.get("job-fast").status, "Completed");
});

test("an active job keeps its port until the host reports idle", async () => {
  downloadMode = "success";
  const response = await send({ type: "download", url: "https://youtube.com/watch?v=cdefghijklm" });
  assert.equal(response.ok, true);
  assert.equal(lastPort.disconnected, false);
  lastPort.onMessage.emit({ type: "job", job: { id: "job-active", url: "https://www.youtube.com/watch?v=cdefghijklm", status: "Completed" } });
  assert.equal(lastPort.disconnected, false);
  lastPort.onMessage.emit({ type: "idle" });
  assert.equal(lastPort.disconnected, true);
});

test("a protocol mismatch rejects the operation", async () => {
  protocolVersion = 99;
  downloadMode = "failure";
  const response = await send({ type: "download", url: "https://youtube.com/watch?v=defghijklmn" });
  assert.match(response.error, /Incompatible/);
  protocolVersion = 1;
});
