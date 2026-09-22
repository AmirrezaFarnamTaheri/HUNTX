// HUNTX boot guard.
//
// A classic script, loaded before the app module. It exists for exactly one
// failure: a returning visitor whose browser still holds the PREVIOUS
// deployment's modules while the page and entry script are the NEW ones.
// That mismatch surfaces as
//
//   SyntaxError: The requested module './decoder.js' does not provide an
//   export named 'x'
//
// and the app never boots. The service worker now serves all first-party code
// network-first, which prevents this going forward, but a visitor whose
// browser is still running the *old* service worker for the transitional visit
// runs the old caching logic, and only this guard can rescue that one load.
//
// Recovery is deliberately blunt and bounded: drop HUNTX's caches, unregister
// the worker, and reload once. A sessionStorage flag guarantees at most one
// attempt per session, so a genuinely broken deploy fails visibly instead of
// reloading in a loop.

(function () {
  "use strict";

  var FLAG = "huntx_skew_recovered";
  var CACHE_PREFIX = "huntx-cache-";

  // Messages that confirm incompatible module versions (e.g., browser cached
  // an old module tree while the page loaded the new one). Generic "Failed to
  // fetch" can match transient or offline errors; only recover for these
  // version-skew-specific patterns.
  var SKEW_PATTERN = /does not provide an export named|Unable to resolve module specifier/i;

  function isSkew(message) {
    return SKEW_PATTERN.test(String(message || ""));
  }

  function alreadyTried() {
    try {
      return sessionStorage.getItem(FLAG) === "1";
    } catch (_e) {
      // Without storage we cannot bound the retries, so do not risk a loop.
      return true;
    }
  }

  function markTried() {
    try {
      sessionStorage.setItem(FLAG, "1");
    } catch (_e) {
      // Handled by alreadyTried(): with no storage we never get this far.
    }
  }

  function recover() {
    if (alreadyTried()) return;
    markTried();

    var work = [];
    if ("caches" in window) {
      work.push(
        caches.keys().then(function (keys) {
          return Promise.all(
            keys
              .filter(function (key) {
                return key.indexOf(CACHE_PREFIX) === 0;
              })
              .map(function (key) {
                return caches.delete(key);
              })
          );
        })
      );
    }
    if ("serviceWorker" in navigator) {
      work.push(
        navigator.serviceWorker.getRegistrations().then(function (registrations) {
          var huntxScope = new URL("./", document.baseURI).href;
          return Promise.all(
            registrations
              .filter(function (registration) {
                return registration.scope === huntxScope;
              })
              .map(function (registration) {
                return registration.unregister();
              })
          );
        })
      );
    }

    // Reload whether or not cleanup succeeded: the reload is the recovery.
    var reload = function () {
      window.location.reload();
    };
    Promise.all(work).then(reload, reload);
  }

  window.addEventListener("error", function (event) {
    if (isSkew(event && event.message)) recover();
  });

  window.addEventListener("unhandledrejection", function (event) {
    var reason = event && event.reason;
    if (isSkew(reason && reason.message)) recover();
  });

  // A page that loaded cleanly has no use for the flag; clearing it lets a
  // later deploy in the same tab recover again.
  window.addEventListener("load", function () {
    setTimeout(function () {
      try {
        sessionStorage.removeItem(FLAG);
      } catch (_e) {
        // Nothing to clear.
      }
    }, 5000);
  });
})();
