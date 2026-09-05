import { HOST_NAME, TERMINAL_STATES, makeRequest, youtubeVideoUrl } from "./common.js";

const PROTOCOL_VERSION = 1;
const HISTORY_LIMIT = 50;
let port = null;
let handshake = null;
let operations = 0;
let hostIdle = true;
let persistChain = Promise.resolve();
const pending = new Map();
const jobs = new Map();
const intentionalDisconnects = new WeakSet();

function broadcast(message) {
  chrome.runtime.sendMessage(message).catch(() => {});
  chrome.tabs.query({ url: ["https://www.youtube.com/*", "https://youtube.com/*", "https://m.youtube.com/*"] }, tabs => {
    for (const tab of tabs) {
      if (tab.id) chrome.tabs.sendMessage(tab.id, message).catch(() => {});
    }
  });
}

function activeJobs() {
  return [...jobs.values()].some(job => !TERMINAL_STATES.has(job.status));
}

function trimHistory() {
  const terminalIds = [...jobs].filter(([, job]) => TERMINAL_STATES.has(job.status)).map(([id]) => id);
  for (const id of terminalIds.slice(0, Math.max(0, terminalIds.length - HISTORY_LIMIT))) jobs.delete(id);
}

function persistJobs() {
  trimHistory();
  const snapshot = [...jobs.values()];
  persistChain = persistChain.then(() => chrome.storage.session.set({ jobs: snapshot }));
  return persistChain;
}

async function restoreJobs() {
  const stored = (await chrome.storage.session.get({ jobs: [] })).jobs;
  for (const old of stored) {
    const job = TERMINAL_STATES.has(old.status)
      ? old
      : { ...old, status: "Error", error: "EasyMP3 helper connection was lost." };
    jobs.set(job.id, job);
  }
  await persistJobs();
}
const restored = restoreJobs();

function maybeDisconnect() {
  if (!port || !hostIdle || operations || pending.size || activeJobs()) return;
  const old = port;
  port = null;
  handshake = null;
  intentionalDisconnects.add(old);
  old.disconnect();
}

function failActiveJobs(error) {
  for (const [id, job] of jobs) {
    if (TERMINAL_STATES.has(job.status)) continue;
    const failed = { ...job, status: "Error", error };
    jobs.set(id, failed);
    broadcast({ type: "job", job: failed });
  }
  persistJobs();
}

function connect() {
  if (port) return port;
  hostIdle = true;
  port = chrome.runtime.connectNative(HOST_NAME);
  const connected = port;
  connected.onMessage.addListener(message => {
    if (message.type === "job" && message.job) {
      jobs.set(message.job.id, message.job);
      hostIdle = TERMINAL_STATES.has(message.job.status) && !activeJobs();
      persistJobs();
      broadcast({ type: "job", job: message.job });
      return;
    }
    if (message.type === "idle") {
      hostIdle = true;
      broadcast({ type: "idle" });
      maybeDisconnect();
      return;
    }
    if (!message.id || !pending.has(message.id)) return;
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    message.ok ? resolve(message) : reject(new Error(message.error || "EasyMP3 helper error"));
  });
  connected.onDisconnect.addListener(() => {
    if (port === connected) {
      port = null;
      handshake = null;
    }
    if (intentionalDisconnects.has(connected)) return;
    const error = chrome.runtime.lastError?.message || "EasyMP3 helper disconnected";
    for (const { reject } of pending.values()) reject(new Error(error));
    pending.clear();
    failActiveJobs(error);
    broadcast({ type: "host-disconnected", error });
  });
  return connected;
}

function rawRequest(type, fields = {}) {
  const message = makeRequest(type, fields);
  return new Promise((resolve, reject) => {
    pending.set(message.id, { resolve, reject });
    try { connect().postMessage(message); }
    catch (error) { pending.delete(message.id); reject(error); }
  });
}

function compatibleHost() {
  if (!handshake) {
    handshake = rawRequest("hello").then(result => {
      if (result.protocolVersion !== PROTOCOL_VERSION) {
        throw new Error(`Incompatible EasyMP3 helper protocol (expected ${PROTOCOL_VERSION}, got ${result.protocolVersion ?? "none"}).`);
      }
      return result;
    }).catch(error => { handshake = null; throw error; });
  }
  return handshake;
}

async function request(type, fields = {}) {
  operations += 1;
  if (type === "download") hostIdle = false;
  try {
    const hello = await compatibleHost();
    if (type === "hello") return hello;
    const result = await rawRequest(type, fields);
    if (type === "choose_folder") {
      handshake = Promise.resolve({ ...hello, outputFolder: result.outputFolder });
    }
    if (type === "download" && result.jobId && !jobs.has(result.jobId)) {
      const job = { id: result.jobId, url: fields.url, status: "Queued" };
      jobs.set(job.id, job);
      await persistJobs();
      broadcast({ type: "job", job });
    }
    return result;
  } finally {
    operations -= 1;
    if (type === "download" && !activeJobs()) hostIdle = true;
    maybeDisconnect();
  }
}

function isExtensionSender(sender) {
  return sender.url?.startsWith(chrome.runtime.getURL(""));
}

function trustedDownload(message, sender) {
  const requested = youtubeVideoUrl(message.url);
  if (!requested) return null;
  if (isExtensionSender(sender)) return requested;
  const page = youtubeVideoUrl(sender.tab?.url);
  return page === requested ? requested : null;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "get-state") {
    restored.then(() => sendResponse({ ok: true, jobs: [...jobs.values()] }));
    return true;
  }
  if (!["hello", "choose_folder", "download"].includes(message.type)) return;
  if (message.type !== "download" && !isExtensionSender(sender)) {
    sendResponse({ ok: false, error: "This action is only available in the EasyMP3 popup." });
    return;
  }
  const fields = {};
  if (message.type === "download") {
    fields.url = trustedDownload(message, sender);
    if (!fields.url) {
      sendResponse({ ok: false, error: "Open a single YouTube video first." });
      return;
    }
    if ([...jobs.values()].some(job => job.url === fields.url && !TERMINAL_STATES.has(job.status))) {
      sendResponse({ ok: false, error: "This video is already queued." });
      return;
    }
  }
  restored.then(() => request(message.type, fields))
    .then(sendResponse, error => sendResponse({ ok: false, error: error.message }));
  return true;
});

export const __test = { activeJobs, failActiveJobs, jobs, request, trimHistory };
