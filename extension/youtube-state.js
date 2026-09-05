(function (root) {
  const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/;

  function videoUrl(value) {
    try {
      const url = new URL(value);
      if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.port) return null;
      if (!["youtube.com", "www.youtube.com", "m.youtube.com"].includes(url.hostname)) return null;
      let id = null;
      if (/^\/watch\/?$/.test(url.pathname)) id = url.searchParams.get("v");
      else {
        const match = url.pathname.match(/^\/(?:shorts|live|embed)\/([^/?#]+)/);
        id = match?.[1] || null;
      }
      return id && VIDEO_ID.test(id) ? `https://www.youtube.com/watch?v=${id}` : null;
    } catch {
      return null;
    }
  }

  function saveJob(cache, job) { cache.set(job.url, job); return job; }
  function queueIfCurrent(cache, submittedUrl, currentUrl, jobId) {
    if (submittedUrl !== currentUrl) return null;
    const existing = cache.get(submittedUrl);
    if (existing && (!jobId || existing.id === jobId)) return existing;
    const queued = { id: jobId, url: submittedUrl, status: "Queued" };
    cache.set(submittedUrl, queued);
    return queued;
  }
  function buttonState(cache, url) { return cache.get(url) || null; }
  root.EasyMP3YouTubeState = { buttonState, queueIfCurrent, saveJob, videoUrl };
})(globalThis);
