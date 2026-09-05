import test from "node:test";
import assert from "node:assert/strict";
import { isShazamSongUrl, makeRequest, youtubeSearchUrl, youtubeVideoUrl } from "../common.js";

test("normalizes watch, short and share URLs to one video without playlist data", () => {
  assert.equal(youtubeVideoUrl("https://www.youtube.com/watch?v=abcdefghijk&list=PL123"), "https://www.youtube.com/watch?v=abcdefghijk");
  assert.equal(youtubeVideoUrl("https://youtube.com/shorts/abcdefghijk?feature=share"), "https://www.youtube.com/watch?v=abcdefghijk");
  assert.equal(youtubeVideoUrl("https://youtu.be/abcdefghijk?t=30"), "https://www.youtube.com/watch?v=abcdefghijk");
  for (const path of ["watch?list=PL123&index=2&v=abcdefghijk", "watch/?v=abcdefghijk&list=PL123", "live/abcdefghijk", "embed/abcdefghijk"]) {
    assert.equal(youtubeVideoUrl(`https://m.youtube.com/${path}`), "https://www.youtube.com/watch?v=abcdefghijk");
  }
});
test("rejects searches, channels, impostor domains and bad IDs", () => {
  for (const value of ["https://youtube.com/results?search_query=x", "https://youtube.com/@x", "https://youtube.example/watch?v=abcdefghijk", "https://youtube.com/watch?v=bad!"]) assert.equal(youtubeVideoUrl(value), null);
});
test("recognizes standard and locale Shazam song pages", () => {
  assert.equal(isShazamSongUrl("https://www.shazam.com/song/6769044593/name"), true);
  assert.equal(isShazamSongUrl("https://www.shazam.com/en-gb/song/6769044593/name"), true);
  assert.equal(isShazamSongUrl("https://www.shazam.com/artist/1/name"), false);
});
test("creates encoded searches only with usable song data", () => {
  assert.equal(youtubeSearchUrl("Song & Dance", "A/B"), "https://www.youtube.com/results?search_query=Song%20%26%20Dance%20A%2FB");
  assert.equal(youtubeSearchUrl("", ""), null);
});
test("request IDs and wire fields are stable", () => {
  assert.deepEqual(makeRequest("download", {url:"u"}, () => "id-1"), {id:"id-1",type:"download",url:"u"});
});
