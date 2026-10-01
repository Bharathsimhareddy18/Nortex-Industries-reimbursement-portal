// This UI is served by the same FastAPI server as the API, so by default every call goes to the same address
// (an empty base means "this site"). To point the UI at a different server, add a .env.local file at the site
// root with one line:  server = https://example.com   (the file is not shipped, so the default below applies).
// Note: the API gives no cross-origin permission (no CORS), so that only works for a server that allows this site itself.
const DEFAULT_API_BASE = "";

const API_BASE_READY = fetch(".env.local", { cache: "no-store" })
  .then((response) => (response.ok ? response.text() : ""))
  .then((text) => {
    const line = text.split("\n").map((l) => l.trim()).find((l) => /^server\s*=/.test(l));
    if (!line) return DEFAULT_API_BASE;
    // "server = https://x/" -> "https://x" (quotes and a trailing slash are tolerated)
    return line.slice(line.indexOf("=") + 1).trim().replace(/^["']|["']$/g, "").replace(/\/+$/, "");
  })
  .catch(() => DEFAULT_API_BASE);
