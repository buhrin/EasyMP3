(() => {
  const buttonId = "easy-mp3-download";
  const state = globalThis.EasyMP3YouTubeState;
  const jobs = new Map();
  const pendingUrls = new Set();
  let currentUrl = "";
  let scanScheduled = false;

  function videoUrl() { return state.videoUrl(location.href); }

  function visible(element) {
    if (!element?.isConnected) return false;
    for (let current = element; current && current !== document; current = current.parentElement) {
      const style = getComputedStyle(current);
      if (current.hidden || style.display === "none" || style.visibility === "hidden") return false;
    }
    if (typeof element.getClientRects === "function" && element.getClientRects().length === 0) return false;
    return true;
  }

  function actionGroups() {
    const watch = document.querySelector("ytd-watch-metadata, ytd-watch-flexy");
    const selectors = [
      "#actions-inner #menu > ytd-menu-renderer",
      "#actions #menu > ytd-menu-renderer",
      "#top-level-buttons-computed",
      "#actions-inner #top-level-buttons-computed",
      "#actions-inner",
      "#actions",
    ];
    const groups = [];
    for (const root of [watch, document]) {
      if (!root) continue;
      for (const selector of selectors) {
        for (const element of root.querySelectorAll(selector)) {
          if (visible(element) && !groups.includes(element)) groups.push(element);
        }
      }
      if (groups.length) break;
    }
    return groups;
  }

  function directChild(group, element) {
    let child = element;
    while (child?.parentElement && child.parentElement !== group) child = child.parentElement;
    return child?.parentElement === group ? child : null;
  }

  function saveControl(group) {
    const controls = group.querySelectorAll("button, a, yt-button-shape, ytd-button-renderer");
    for (const control of controls) {
      const name = [
        control.getAttribute?.("aria-label"),
        control.getAttribute?.("title"),
        control.textContent,
      ].filter(Boolean).join(" ").trim();
      if (/^(save|save to playlist)(\b|$)/i.test(name)) return directChild(group, control);
    }
    return null;
  }

  function overflowControl(group) {
    const control = group.querySelector(
      "button[aria-label*='More actions'], button[aria-label='More'], ytd-menu-renderer #button"
    );
    return directChild(group, control);
  }

  function makeButton() {
    const button = document.createElement("button");
    button.id = buttonId;
    button.type = "button";
    button.className = [
      "ytSpecButtonShapeNextHost", "ytSpecButtonShapeNextTonal",
      "ytSpecButtonShapeNextMono", "ytSpecButtonShapeNextSizeM",
      "ytSpecButtonShapeNextIconLeading",
    ].join(" ");

    const icon = document.createElement("img");
    icon.className = "easy-mp3-icon";
    icon.src = chrome.runtime.getURL("icons/icon-32.png");
    icon.alt = "";
    const label = document.createElement("span");
    label.className = "easy-mp3-label";
    button.append(icon, label);

    button.addEventListener("click", async () => {
      const submittedUrl = currentUrl;
      pendingUrls.add(submittedUrl);
      setButton(null);
      const result = await chrome.runtime.sendMessage({ type: "download", url: submittedUrl })
        .catch(error => ({ ok: false, error: error.message }));
      pendingUrls.delete(submittedUrl);
      if (!result.ok) {
        if (currentUrl === submittedUrl) setButton({ status: "Error", error: result.error });
        return;
      }
      const queued = state.queueIfCurrent(jobs, submittedUrl, currentUrl, result.jobId);
      if (queued) setButton(queued);
    });
    return button;
  }

  function setButton(job) {
    const button = document.getElementById(buttonId);
    if (!button) return;
    const label = button.querySelector(".easy-mp3-label");
    const pending = !job && pendingUrls.has(currentUrl);
    const text = pending ? "Sending…" : job?.status || "Download MP3";
    const terminal = !job || ["Completed", "Error"].includes(job.status);
    const dataState = job?.status === "Error" ? "error" : job && !terminal ? "queued" : "";
    if (label.textContent !== text) label.textContent = text;
    if (button.dataset.state !== dataState) button.dataset.state = dataState;
    const disabled = pending || !terminal;
    if (button.disabled !== disabled) button.disabled = disabled;
  }
  async function restore(url) {
    const result = await chrome.runtime.sendMessage({ type: "get-state" }).catch(() => null);
    for (const job of result?.jobs || []) state.saveJob(jobs, job);
    if (currentUrl === url) setButton(state.buttonState(jobs, url));
  }
  function addButton() {
    const url = videoUrl();
    if (!url) { document.getElementById(buttonId)?.remove(); currentUrl = ""; return; }
    if (currentUrl && currentUrl !== url) document.getElementById(buttonId)?.remove();
    currentUrl = url;
    const target = actionGroups()[0];
    if (!target) return;
    let button = document.getElementById(buttonId);
    if (!button) button = makeButton();

    const save = saveControl(target);
    // Read the native pill's actual colours; YouTube's theme variables differ
    // between page versions. Keep explicit light/dark CSS as a fallback.
    const nativeButton = save?.matches("button") ? save : save?.querySelector("button");
    if (nativeButton && visible(nativeButton)) {
      const nativeStyle = getComputedStyle(nativeButton);
      for (const [property, value] of [
        ["--easy-mp3-native-background", nativeStyle.backgroundColor],
        ["--easy-mp3-native-text", nativeStyle.color],
      ]) {
        if (value && value !== "transparent" && value !== "rgba(0, 0, 0, 0)" &&
            button.style.getPropertyValue(property) !== value) button.style.setProperty(property, value);
      }
    }
    const overflow = overflowControl(target);
    const desiredPrevious = save;
    const inRightPlace = button.parentElement === target &&
      (desiredPrevious ? button.previousElementSibling === desiredPrevious : !overflow || button.nextElementSibling === overflow);
    if (!inRightPlace) {
      if (save) save.after(button);
      else if (overflow) target.insertBefore(button, overflow);
      else target.append(button);
    }
    const parentStyle = getComputedStyle(target);
    const parentGap = Number.parseFloat(parentStyle.columnGap || parentStyle.gap);
    button.dataset.parentGap = parentGap > 0 ? "true" : "false";
    setButton(state.buttonState(jobs, url));
    if (!button.dataset.restoredUrl || button.dataset.restoredUrl !== url) {
      button.dataset.restoredUrl = url;
      restore(url);
    }
  }

  function scheduleScan() {
    if (scanScheduled) return;
    scanScheduled = true;
    requestAnimationFrame(() => {
      scanScheduled = false;
      addButton();
    });
  }
  chrome.runtime.onMessage.addListener(message => {
    if (message.type === "job") {
      state.saveJob(jobs, message.job);
      if (message.job.url === currentUrl) setButton(message.job);
    }
    if (message.type === "host-disconnected") {
      const failed = { url: currentUrl, status: "Error" };
      state.saveJob(jobs, failed); setButton(failed);
    }
  });
  new MutationObserver(scheduleScan).observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["hidden", "style", "class", "dark"],
  });
  addEventListener("yt-navigate-finish", () => {
    scheduleScan();
  });
  scheduleScan();
})();
