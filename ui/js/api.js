// Every call to the API goes through api() below, so the session headers
// and the "401 means back to login" rule live in exactly one place.

const SESSION_KEY = "nortex.session";

// localStorage (not sessionStorage) so the login survives reloads and new tabs.
// The API expires sessions after 12 hours anyway, and we find out through a 401.
function getSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY));
  } catch {
    return null;
  }
}

// Older versions of this UI also saved claims and decisions in the browser. The API now returns all of
// that, so remove any leftovers: the session below is the only thing this app keeps.
try {
  Object.keys(localStorage)
    .filter((key) => key.startsWith("nortex.") && key !== SESSION_KEY)
    .forEach((key) => localStorage.removeItem(key));
} catch {}

function saveSession(session) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

// There is no logout endpoint yet, so signing out just means forgetting the token.
function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

// Pages behind the login call this first, so nobody sees a half-drawn screen before the 401 arrives.
function requireLogin() {
  if (!getSession()) location.replace("login.html");
}

// Carries the API's { detail, problems } so a screen can show both.
class ApiError extends Error {
  constructor(status, detail, problems) {
    super(detail);
    this.status = status;
    this.problems = problems || [];
  }
}

// options: { method, body (sent as JSON), form (a FormData, sent as multipart) }
async function api(path, options = {}) {
  const headers = {};
  const session = getSession();
  if (session) {
    headers["emp-code"] = session.emp_code;
    headers["session-token"] = session.session_token;
  }

  let payload;
  if (options.form) {
    // No Content-Type here: the browser must add the multipart boundary itself.
    payload = options.form;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(options.body);
  }

  let response;
  try {
    // Every call waits for the address read from .env.local (js/config.js); after the first, it is instant.
    const base = await API_BASE_READY;
    response = await fetch(base + path, { method: options.method || "GET", headers, body: payload });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check your connection and try again.");
  }

  const data = await response.json().catch(() => null);

  // A 401 from login itself means "wrong email or password", which the login page shows.
  // Anywhere else it means the session is missing or expired.
  if (response.status === 401 && path !== "/auth/login") {
    clearSession();
    location.replace("login.html");
    // Never settle: the page is leaving, so no screen should try to show an error meanwhile.
    return new Promise(() => {});
  }

  if (!response.ok) {
    const detail = (data && data.detail) || `Something went wrong (${response.status}).`;
    throw new ApiError(response.status, detail, data && data.problems);
  }
  return data;
}


// An <img> tag cannot send the session headers, so a protected image (a bill) is fetched here
// and handed to the page as an object URL.
async function apiImage(path) {
  const session = getSession();
  const base = await API_BASE_READY;
  const response = await fetch(base + path, {
    headers: { "emp-code": session ? session.emp_code : "", "session-token": session ? session.session_token : "" },
  });
  if (response.status === 401) {
    clearSession();
    location.replace("login.html");
    return new Promise(() => {});
  }
  if (!response.ok) throw new ApiError(response.status, "The image could not be loaded.");
  return URL.createObjectURL(await response.blob());
}
