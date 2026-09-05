import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import { parseHTML } from "linkedom";

const stateSource = await readFile(new URL("../youtube-state.js", import.meta.url), "utf8");
const contentSource = await readFile(new URL("../youtube.js", import.meta.url), "utf8");

function actionMarkup(id, hidden = false) {
  return `
    <ytd-watch-metadata id="${id}"${hidden ? " style=\"display:none\"" : ""}>
      <div id="actions"><div id="actions-inner"><div id="menu">
        <ytd-menu-renderer>
          <div id="top-level-buttons-computed"><button aria-label="Like">Like</button></div>
          <div id="flexible-item-buttons">
            <yt-button-view-model><button aria-label="Save to playlist">Save</button></yt-button-view-model>
          </div>
          <div id="button-shape"><button aria-label="More actions">More</button></div>
        </ytd-menu-renderer>
      </div></div></div>
    </ytd-watch-metadata>`;
}

async function harness() {
  const { window, document } = parseHTML(`<html><body>${actionMarkup("old", true)}${actionMarkup("live")}</body></html>`);
  const frames = [];
  let resolveDownload;
  const downloadResult = new Promise(resolve => { resolveDownload = resolve; });
  const messages = [];
  const listeners = [];
  const chrome = {
    runtime: {
      getURL: path => `chrome-extension://test/${path}`,
      onMessage: { addListener: listener => listeners.push(listener) },
      sendMessage: message => {
        messages.push(message);
        return message.type === "download" ? downloadResult : Promise.resolve({ jobs: [] });
      },
    },
  };
  window.HTMLElement.prototype.getClientRects = function () {
    return this.closest("[style*='display:none']") ? [] : [{}];
  };
  const context = vm.createContext({
    window,
    document,
    chrome,
    MutationObserver: window.MutationObserver,
    URL,
    Map,
    Set,
    console,
    location: { href: "https://www.youtube.com/watch?list=PL123&index=4&v=abcdefghijk" },
    getComputedStyle: element => ({
      display: element.style?.display || "block",
      visibility: element.style?.visibility || "visible",
      backgroundColor: element.style?.backgroundColor || "",
      color: element.style?.color || "",
      columnGap: "normal",
      gap: "normal",
    }),
    requestAnimationFrame: callback => { frames.push(callback); return frames.length; },
    addEventListener: () => {},
  });
  vm.runInContext(stateSource, context);
  vm.runInContext(contentSource, context);

  async function drain(limit = 10) {
    let count = 0;
    while (count < limit) {
      await Promise.resolve();
      if (!frames.length) {
        await Promise.resolve();
        if (!frames.length) return count;
      }
      frames.shift()(performance.now());
      count += 1;
    }
    return count;
  }
  return { chrome, context, document, drain, frames, listeners, messages, resolveDownload };
}

test("places one button after Save on a playlist watch URL and ignores hidden actions", async () => {
  const page = await harness();
  assert.ok(await page.drain() < 10, "DOM should settle without a perpetual RAF loop");

  const button = page.document.getElementById("easy-mp3-download");
  const liveMenu = page.document.querySelector("#live ytd-menu-renderer");
  const saveSlot = liveMenu.querySelector("#flexible-item-buttons");
  assert.equal(button.parentElement, liveMenu);
  assert.equal(saveSlot.nextElementSibling, button);
  assert.equal(button.nextElementSibling.id, "button-shape");
  assert.equal(page.document.querySelector("#old #easy-mp3-download"), null);
  assert.equal(button.querySelector("img").src, "chrome-extension://test/icons/icon-32.png");
});

test("re-adds the button when YouTube replaces its action DOM", async () => {
  const page = await harness();
  await page.drain();
  const oldButton = page.document.getElementById("easy-mp3-download");
  page.document.getElementById("live").outerHTML = actionMarkup("replacement");

  assert.ok(await page.drain() < 10, "replacement DOM should settle");
  const newButton = page.document.getElementById("easy-mp3-download");
  assert.notEqual(newButton, oldButton);
  assert.equal(newButton.previousElementSibling.id, "flexible-item-buttons");
});

test("keeps Sending state through mutation rescans until the host responds", async () => {
  const page = await harness();
  await page.drain();
  const button = page.document.getElementById("easy-mp3-download");
  button.click();
  await Promise.resolve();
  assert.equal(button.querySelector(".easy-mp3-label").textContent, "Sending…");
  assert.equal(button.disabled, true);

  page.document.querySelector("#live").append(page.document.createElement("div"));
  assert.ok(await page.drain() < 10, "unrelated mutations should settle");
  assert.equal(button.querySelector(".easy-mp3-label").textContent, "Sending…");
  assert.equal(button.disabled, true);

  page.resolveDownload({ ok: true, jobId: "job-1" });
  await new Promise(resolve => setImmediate(resolve));
  await page.drain();
  assert.equal(button.querySelector(".easy-mp3-label").textContent, "Queued");
  assert.equal(page.messages.some(message => message.type === "download" && message.url === "https://www.youtube.com/watch?v=abcdefghijk"), true);
});

test("copies Save colours and updates them without an observer loop", async () => {
  const page = await harness();
  const save = page.document.querySelector('#live button[aria-label="Save to playlist"]');
  save.style.backgroundColor = 'rgb(48, 48, 48)';
  save.style.color = 'rgb(241, 241, 241)';
  assert.ok(await page.drain() < 10);
  const button = page.document.getElementById('easy-mp3-download');
  assert.equal(button.style.getPropertyValue('--easy-mp3-native-background'), save.style.backgroundColor);
  assert.equal(button.style.getPropertyValue('--easy-mp3-native-text'), save.style.color);
  save.setAttribute('style', 'background-color:rgb(240, 240, 240);color:rgb(15, 15, 15)');
  page.document.documentElement.setAttribute('dark', '');
  assert.ok(await page.drain() < 10);
  assert.equal(button.style.getPropertyValue('--easy-mp3-native-background'), save.style.backgroundColor);
  assert.equal(button.style.getPropertyValue('--easy-mp3-native-text'), save.style.color);
});
