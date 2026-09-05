export const HOST_NAME = "com.easymp3.host";
export const TERMINAL_STATES = new Set(["Completed", "Error"]);

export function youtubeVideoUrl(value) {
  try {
    const url = new URL(value);
    if (!["https:", "http:"].includes(url.protocol) || url.username || url.password || url.port) return null;
    if (!["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"].includes(url.hostname)) return null;
    let id = null;
    if (url.hostname === "youtu.be") id = url.pathname.split("/").filter(Boolean)[0];
    else if (url.pathname.replace(/\/$/, "") === "/watch") id = url.searchParams.get("v");
    else if (/^\/(shorts|live|embed)\//.test(url.pathname)) id = url.pathname.split("/")[2];
    if (!id || !/^[A-Za-z0-9_-]{11}$/.test(id)) return null;
    return `https://www.youtube.com/watch?v=${id}`;
  } catch { return null; }
}

export function youtubeSearchUrl(title, artist) {
  const terms = [title, artist].map(x => (x || "").trim()).filter(Boolean);
  return terms.length ? `https://www.youtube.com/results?search_query=${encodeURIComponent(terms.join(" "))}` : null;
}

export function isShazamSongUrl(value) {
  try {
    const url = new URL(value);
    return url.hostname === "www.shazam.com" && /\/(?:[a-z]{2}(?:-[a-z]{2})?\/)?song\/\d+(?:\/|$)/i.test(url.pathname);
  } catch { return false; }
}

export function makeRequest(type, fields = {}, random = () => crypto.randomUUID()) {
  return { id: random(), type, ...fields };
}
