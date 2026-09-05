(function (root) {
  function youtubeTarget(value) {
    try {
      const url = new URL(value);
      const hosts = ["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"];
      if (!hosts.includes(url.hostname)) return null;
      if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.port) return null;
      if (url.hostname === "youtu.be" || url.pathname === "/watch" || url.pathname === "/results") return url.href;
    } catch {}
    return null;
  }

  function songId(pathname) {
    return pathname.match(/\/song\/(\d+)(?:\/|$)/i)?.[1] || null;
  }

  function directLink(doc) {
    const exact = doc.querySelector("a[data-test-id='track_userevent_open_in_youtube'][role='menuitem']");
    if (exact) {
      const menu = exact.closest?.("[role='menu']");
      if (!menu || menu.getAttribute?.("aria-hidden") !== "true") return youtubeTarget(exact.href);
    }
    for (const menu of doc.querySelectorAll("[role='menu'][aria-hidden='false'], [data-testid*='menu'], [data-test-id*='menu']")) {
      for (const link of menu.querySelectorAll("a[href]")) {
        const target = youtubeTarget(link.href);
        if (target) return target;
      }
    }
    return null;
  }

  function menuButton(doc) {
    const exact = doc.querySelector("button[data-test-id='track_userevent_more_options'], [data-test-id='track_userevent_more_options'] button");
    if (exact) return exact;

    const title = doc.querySelector("[class*='trackTitle'], [data-testid='track-title']");
    const track = title?.closest?.("[class*='NewTrackPageHeader_trackContent'], section, article, header, [data-testid*='track'], [data-test-id*='track']");
    return track?.querySelector?.("button[aria-label*='more options' i], button[aria-label='more' i]") || null;
  }

  function songData(doc, pathname) {
    let title = doc.querySelector("[class*='trackTitle'], [data-testid='track-title']")?.textContent?.trim();
    let artist = doc.querySelector("[data-test-id='track_userevent_artist_link'], [data-testid='track-subtitle']")?.textContent?.trim();
    const wantedId = songId(pathname);
    const candidates = [];
    for (const node of doc.querySelectorAll("script[type='application/ld+json']")) {
      try {
        const raw = JSON.parse(node.textContent);
        const queue = Array.isArray(raw) ? [...raw] : [raw];
        while (queue.length) {
          const item = queue.shift();
          if (!item || typeof item !== "object") continue;
          if (item["@graph"]) queue.push(...item["@graph"]);
          if (item["@type"] === "MusicRecording") candidates.push(item);
        }
      } catch {}
    }
    const idOf = item => String(item.url || item["@id"] || "").match(/\/song\/(\d+)\//)?.[1];
    const song = candidates.find(item => wantedId && idOf(item) === wantedId)
      || candidates.find(item => !idOf(item));
    if (song) {
      title ||= song.name;
      const by = song.byArtist;
      artist ||= typeof by === "string"
        ? by
        : Array.isArray(by)
          ? by.map(value => typeof value === "string" ? value : value?.name).filter(Boolean).join(", ")
          : by?.name;
    }
    return { title, artist };
  }

  function searchUrl(data) {
    if (!data.title || !data.artist) return null;
    return `https://www.youtube.com/results?search_query=${encodeURIComponent(`${data.title} ${data.artist}`)}`;
  }

  root.EasyMP3Shazam = { directLink, menuButton, searchUrl, songData, youtubeTarget };
})(globalThis);
