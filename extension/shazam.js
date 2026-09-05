(function (root) {
  const SONG_ROUTE = /\/(?:[a-z]{2}(?:-[a-z]{2})?\/)?song\/\d+(?:\/|$)/i;
  const POLL_MS = 100;
  const MAX_WAIT_MS = 10000;

  function startRedirect(options = {}) {
    if (options.enabled === false) return { check() {}, stop() {} };
    const doc = options.document || document;
    const page = options.location || location;
    const logic = options.logic || root.EasyMP3Shazam;
    const Observer = options.MutationObserver || MutationObserver;
    const now = options.now || Date.now;
    const schedule = options.setTimeout || setTimeout;
    const cancel = options.clearTimeout || clearTimeout;
    let route = page.pathname;
    let started = now();
    let fallbackAt = null;
    let menuAttempted = false;
    let staleDirect = null;
    let staleMetadata = null;
    let metadataCleared = false;
    let timer = null;
    let stopped = false;

    const stop = () => {
      stopped = true;
      if (timer !== null) cancel(timer);
      observer.disconnect();
    };

    function resetForRoute(nextRoute) {
      staleDirect = logic.directLink(doc);
      const oldData = logic.songData(doc, route);
      staleMetadata = oldData.title && oldData.artist ? `${oldData.title}\n${oldData.artist}` : null;
      metadataCleared = false;
      route = nextRoute;
      started = now();
      fallbackAt = null;
      menuAttempted = false;
    }

    function check() {
      if (stopped) return;
      if (page.pathname !== route) {
        resetForRoute(page.pathname);
        return;
      }
      if (!SONG_ROUTE.test(route)) return;

      const direct = logic.directLink(doc);
      if (!direct) staleDirect = null;
      if (direct && direct !== staleDirect) {
        stop();
        page.replace(direct);
        return;
      }

      const data = logic.songData(doc, route);
      const fingerprint = data.title && data.artist ? `${data.title}\n${data.artist}` : null;
      if (!fingerprint) metadataCleared = true;
      const metadataIsCurrent = !staleMetadata || metadataCleared || fingerprint !== staleMetadata;
      const fallback = metadataIsCurrent ? logic.searchUrl(data) : null;
      const menu = logic.menuButton(doc);
      if (menu && !menuAttempted) {
        menuAttempted = true;
        menu.click();
        fallbackAt = now() + POLL_MS;
      } else if (fallback && fallbackAt === null) {
        fallbackAt = now() + POLL_MS;
      }

      if (fallback && fallbackAt !== null && now() >= fallbackAt) {
        stop();
        page.replace(fallback);
      }
    }

    function poll() {
      check();
      if (stopped) return;
      if (now() - started >= MAX_WAIT_MS) {
        stop();
        return;
      }
      timer = schedule(poll, POLL_MS);
    }

    const observer = new Observer(check);
    observer.observe(doc.documentElement, { childList: true, subtree: true, attributes: true });
    check();
    if (!stopped) timer = schedule(poll, POLL_MS);
    return { check, stop };
  }

  root.EasyMP3ShazamRedirect = { startRedirect };
  if (typeof chrome !== "undefined" && SONG_ROUTE.test(location.pathname)) {
    chrome.storage.sync.get({ shazamRedirect: true }, ({ shazamRedirect }) => {
      if (shazamRedirect) startRedirect();
    });
  }
})(globalThis);
