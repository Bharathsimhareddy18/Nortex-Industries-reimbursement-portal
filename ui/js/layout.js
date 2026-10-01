// Draws the sidebar and the top bar shared by every signed-in page, so the menu is defined once.
// Usage on a page:  const me = await startPage("dashboard");

async function startPage(activeKey) {
  requireLogin();
  // /auth/me has the name; /dashboard/me does not. One call gives the shell everything.
  const me = await api("/auth/me");
  // The admin has one page (admin.html); the employee pages have nothing to show for them.
  if (me.role === "Admin" && activeKey !== "admin") {
    location.replace("admin.html");
    return new Promise(() => {});
  }
  drawSidebar(me, activeKey);
  drawAppbar(me);
  return me;
}

function initials(name) {
  return name.split(" ").map((part) => part[0]).slice(0, 2).join("");
}

function drawSidebar(me, activeKey) {
  const links = me.role === "Admin" ? [{ key: "admin", href: "admin.html", icon: "ph-shield-check", label: "Admin" }] : [
    { key: "dashboard", href: "dashboard.html", icon: "ph-squares-four", label: "Dashboard" },
    { key: "claims", href: "claims.html", icon: "ph-files", label: "Claims" },
    { key: "new", href: "new-request.html", icon: "ph-plus-circle", label: "New request" },
    // No approval-queue endpoint exists, so approvers act from the notifications list.
    isApprover(me.role)
      ? { key: "inbox", href: "notifications.html", icon: "ph-check-square-offset", label: "Approvals" }
      : { key: "inbox", href: "notifications.html", icon: "ph-bell", label: "Notifications" },
  ];

  const nav = links
    .map((l) => `<a href="${l.href}" class="nav-link${l.key === activeKey ? " is-active" : ""}"${l.key === activeKey ? ' aria-current="page"' : ""}>
        <i class="ph ${l.icon}" aria-hidden="true"></i><span>${l.label}</span></a>`)
    .join("");

  document.getElementById("sidebar").innerHTML = `
    <a href="dashboard.html" class="brand"><img class="brand-mark" src="assets/logo.svg" width="30" height="30" alt=""><span>Nortex</span></a>
    <div>
      <div class="nav-label">Work</div>
      <nav class="nav" aria-label="Main">${nav}</nav>
    </div>`;
}

function drawAppbar(me) {
  const isAdmin = me.role === "Admin";
  const scope = isAdmin ? "Signed in as Admin (read-only view of everyone)" : isApprover(me.role) ? `Signed in as ${me.role}` : "You're viewing your own claims";
  document.getElementById("appbar").innerHTML = `
    <span class="scope-pill"><i class="ph-fill ph-circle" aria-hidden="true" style="font-size:8px"></i><span>${escapeHtml(scope)}</span></span>
    <div class="appbar-right">
      ${isAdmin ? "" : '<a href="notifications.html" class="bell" aria-label="Notifications"><i class="ph ph-bell" aria-hidden="true"></i><span class="bell-count" id="bell-count" hidden></span></a>'}
      <span class="me"><span class="avatar" aria-hidden="true">${escapeHtml(initials(me.name))}</span><span>${escapeHtml(me.name)}</span></span>
      <button type="button" class="btn btn-ghost btn-sm" id="sign-out" aria-label="Sign out"><i class="ph ph-sign-out" aria-hidden="true"></i></button>
    </div>`;

  document.getElementById("sign-out").addEventListener("click", () => {
    clearSession();
    location.href = "login.html";
  });

  // The count is a total, not "unread": the API cannot mark notifications as read yet.
  if (isAdmin) return;
  api("/get_all_notifications").then((notes) => {
    if (!notes.length) return;
    const badge = document.getElementById("bell-count");
    badge.textContent = notes.length > 9 ? "9+" : notes.length;
    badge.hidden = false;
  }).catch(() => {});
}
