import { youtubeVideoUrl } from "./common.js";

const element = id => document.getElementById(id);
let pageUrl = null;

function send(message) {
  return chrome.runtime.sendMessage(message).catch(error => ({ ok: false, error: error.message }));
}

function showError(result) {
  element("status").textContent = result.ok ? "" : result.error || "Unknown error";
}

function renderJob(job) {
  let item = document.querySelector(`[data-job-id="${CSS.escape(job.id)}"]`);
  if (!item) {
    item = document.createElement("li");
    item.dataset.jobId = job.id;
    element("jobs").prepend(item);
  }
  item.textContent = job.filename || job.url;
  const detail = document.createElement("small");
  detail.textContent = job.error ? `${job.status}: ${job.error}` : job.status;
  item.append(detail);
}

chrome.storage.sync.get({ shazamRedirect: true }, value => {
  element("redirect").checked = value.shazamRedirect;
});
element("redirect").addEventListener("change", () => {
  chrome.storage.sync.set({ shazamRedirect: element("redirect").checked });
});

chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
  pageUrl = youtubeVideoUrl(tabs[0]?.url);
  element("download").disabled = !pageUrl;
});
element("download").addEventListener("click", async () => {
  const result = await send({ type: "download", url: pageUrl });
  showError(result);
  if (result.ok) element("download").disabled = true;
});
element("choose").addEventListener("click", async () => {
  const result = await send({ type: "choose_folder" });
  showError(result);
  if (result.ok) element("folder").textContent = result.outputFolder || "No folder selected";
});

chrome.runtime.onMessage.addListener(message => {
  if (message.type === "job") {
    renderJob(message.job);
    if (message.job.url === pageUrl && ["Completed", "Error"].includes(message.job.status)) {
      element("download").disabled = false;
    }
  }
  if (message.type === "host-disconnected") {
    element("status").textContent = message.error || "EasyMP3 helper disconnected";
  }
});

send({ type: "hello" }).then(result => {
  showError(result);
  element("folder").textContent = result.ok
    ? result.outputFolder || "No folder selected"
    : "Helper unavailable";
});
send({ type: "get-state" }).then(result => {
  if (result.ok) result.jobs.forEach(renderJob);
});
