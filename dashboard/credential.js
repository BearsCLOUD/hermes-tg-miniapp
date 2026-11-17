/* Credential discovery for the Mini App page.
 *
 * Telegram's signed initData is the bearer credential. It reaches the page
 * in the URL fragment (#tgWebAppData=...), but in two different shapes, and
 * the difference decides whether the app works at all:
 *
 *   - percent-encoded: the whole query string is encoded, so the "&"
 *     separators arrive as "%26" and the credential must be decoded as one
 *     unit;
 *   - raw: the separators are literal, so the credential is the whole
 *     remainder of the fragment.
 *
 * Telegram's own SDK only handles the first shape correctly: its
 * urlParseHashParams() runs the fragment through urlParseQueryString(),
 * which splits on "&" and keeps the FIRST pair. On a raw fragment the SDK
 * therefore publishes a truncated credential (for example "query_id=..." with
 * no hash), and a page that trusts tg.initData first sends a bearer token
 * that no verifier can accept.
 *
 * So every source is collected, and the credential is chosen by
 * completeness rather than by arrival order: a candidate must carry the
 * signature field and more than one pair to be usable.
 */
(function () {
  var MARKER = "tgWebAppData=";

  function fromFragment(text) {
    if (!text) return "";
    var at = text.indexOf(MARKER);
    if (at < 0) return "";
    var rest = text.slice(at + MARKER.length);
    var encoded = rest.indexOf("%3D") >= 0 || rest.indexOf("%26") >= 0;
    if (!encoded) return rest;
    var amp = rest.indexOf("&");
    var value = amp >= 0 ? rest.slice(0, amp) : rest;
    try {
      return decodeURIComponent(value);
    } catch (e) {
      return value;
    }
  }

  function fromSessionStorage() {
    try {
      var raw = window.sessionStorage.getItem("__telegram__initParams");
      if (!raw) return "";
      var params = JSON.parse(raw);
      if (params && typeof params.tgWebAppData === "string") {
        return params.tgWebAppData;
      }
    } catch (e) { /* storage may be blocked */ }
    return "";
  }

  function fromSdk() {
    try {
      var app = window.Telegram && window.Telegram.WebApp;
      if (app && typeof app.initData === "string") return app.initData;
    } catch (e) { /* SDK may be half-initialised */ }
    return "";
  }

  function pairs(value) {
    if (!value) return [];
    return value.split("&").filter(function (part) {
      return part.indexOf("=") > 0;
    });
  }

  /* A usable credential carries the signature and at least a couple of
   * fields; the user object alone is not enough. */
  function isComplete(value) {
    if (!value) return false;
    var parts = pairs(value);
    if (parts.length < 3) return false;
    for (var i = 0; i < parts.length; i++) {
      if (parts[i].indexOf("hash=") === 0) return true;
    }
    return false;
  }

  function read() {
    var candidates = [
      { source: "fragment", value: fromFragment(window.location.hash) },
      { source: "query", value: fromFragment(window.location.search) },
      { source: "sessionStorage", value: fromSessionStorage() },
      { source: "sdk", value: fromSdk() },
    ];
    var best = { source: "", value: "" };
    for (var i = 0; i < candidates.length; i++) {
      if (isComplete(candidates[i].value)) {
        return {
          value: candidates[i].value,
          source: candidates[i].source,
          complete: true,
        };
      }
      if (candidates[i].value && candidates[i].value.length > best.value.length) {
        best = {
          source: candidates[i].source,
          value: candidates[i].value,
          complete: false,
        };
      }
    }
    return { value: best.value, source: best.source, complete: false };
  }

  function describe(credential) {
    var value = (credential && credential.value) || "";
    return {
      source: (credential && credential.source) || "",
      complete: !!(credential && credential.complete),
      length: value.length,
      pairs: pairs(value).length,
      has_hash: /(^|&)hash=/.test(value),
      has_signature: /(^|&)signature=/.test(value),
      fragment_length: (window.location.hash || "").length,
      query_length: (window.location.search || "").length,
      sdk_present: !!(window.Telegram && window.Telegram.WebApp),
      sdk_length: fromSdk().length,
      storage_length: fromSessionStorage().length,
    };
  }

  window.miniappCredential = { read: read, describe: describe };
})();
