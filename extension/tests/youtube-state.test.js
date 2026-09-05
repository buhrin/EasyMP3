import test from "node:test";
import assert from "node:assert/strict";
await import("../youtube-state.js");
const state = globalThis.EasyMP3YouTubeState;
test("normalizes supported YouTube video page forms", () => {
  const expected = "https://www.youtube.com/watch?v=abcdefghijk";
  assert.equal(state.videoUrl("https://www.youtube.com/watch?list=PL123&v=abcdefghijk&index=2"), expected);
  assert.equal(state.videoUrl("https://m.youtube.com/watch?feature=share&v=abcdefghijk"), expected);
  assert.equal(state.videoUrl("https://www.youtube.com/shorts/abcdefghijk?list=PL123"), expected);
  assert.equal(state.videoUrl("https://www.youtube.com/live/abcdefghijk?si=x"), expected);
  assert.equal(state.videoUrl("https://www.youtube.com/embed/abcdefghijk"), expected);
});

test("rejects pages without a valid current video", () => {
  assert.equal(state.videoUrl("https://www.youtube.com/playlist?list=PL123"), null);
  assert.equal(state.videoUrl("https://www.youtube.com/watch?list=PL123"), null);
  assert.equal(state.videoUrl("https://youtube.example/watch?v=abcdefghijk"), null);
});
test("navigation renders only the job for the new video", () => {
  const jobs = new Map();
  state.saveJob(jobs, { id: "old", url: "old-url", status: "Downloading..." });
  state.saveJob(jobs, { id: "new", url: "new-url", status: "Processing..." });
  assert.equal(state.buttonState(jobs, "new-url").status, "Processing...");
});
test("a terminal event wins over a later click response", () => {
  const jobs = new Map();
  state.saveJob(jobs, { id: "job", url: "video-url", status: "Completed" });
  assert.equal(state.queueIfCurrent(jobs, "video-url", "video-url", "job").status, "Completed");
});
test("a response for the old page does not update the new page", () => {
  const jobs = new Map();
  assert.equal(state.queueIfCurrent(jobs, "old-url", "new-url"), null);
  assert.equal(jobs.has("old-url"), false);
});

test("an old completed job cannot change a new video's button", () => {
  const jobs = new Map();
  state.saveJob(jobs, { id: "old", url: "old-url", status: "Completed" });
  assert.equal(state.queueIfCurrent(jobs, "old-url", "new-url", "old"), null);
});

test("a repeat download starts a new job after a prior completion", () => {
  const jobs = new Map();
  state.saveJob(jobs, { id: "old", url: "video-url", status: "Completed" });
  assert.equal(state.queueIfCurrent(jobs, "video-url", "video-url", "new").status, "Queued");
  assert.equal(jobs.get("video-url").id, "new");
});
