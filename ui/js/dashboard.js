// Dashboard: who I am, my claims (GET /get_my_claims), and my latest notifications.

(async function () {
  const me = await startPage("dashboard");

  const hour = new Date().getHours();
  const part = hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening";
  document.getElementById("greeting").textContent = `Good ${part}, ${me.name.split(" ")[0]}`;
  document.getElementById("subtitle").textContent = `${me.designation}, ${me.department}`;

  document.getElementById("details").innerHTML = [
    ["Employee code", me.emp_code],
    ["Role", me.role],
    ["Department", me.department],
    ["Cost centre", me.cost_centre],
    ["City", me.city],
    ["Reports to", me.reporting_manager_code || "Nobody"],
  ].map(([label, value]) => `<div><dt>${label}</dt><dd>${escapeHtml(value)}</dd></div>`).join("");

  let claims = [];
  try {
    claims = await api("/get_my_claims");
    drawClaims(claims);
  } catch (error) {
    document.getElementById("claims").innerHTML = `<div class="panel-pad"><div class="alert">${escapeHtml(error.message)}</div></div>`;
  }

  let notes = [];
  try {
    notes = await api("/get_all_notifications");
    drawLatestNotes(notes);
  } catch (error) {
    document.getElementById("latest-notes").innerHTML = `<div class="panel-pad"><div class="alert">${escapeHtml(error.message)}</div></div>`;
  }

  // Approvers see their queue count (GET /get_pending_approvals); employees, the claims waiting for bills.
  const queue = isApprover(me.role) ? await api("/get_pending_approvals").catch(() => []) : null;
  const needReceipts = claims.filter((c) => c.status === "awaiting_settlement").length;
  document.getElementById("stats").innerHTML = `
    <div class="panel stat tone-sky">
      <span class="label"><i class="ph ph-bell" aria-hidden="true"></i>Notifications</span>
      <span class="value">${notes.length}</span>
      <span class="note">${notes.length ? "Latest " + formatDateTime(notes[0].created_at) : "Nothing yet"}</span>
    </div>
    <div class="panel stat">
      <span class="label"><i class="ph ph-files" aria-hidden="true"></i>Claims raised</span>
      <span class="value">${claims.length}</span>
      <span class="note">${claims.length ? "Latest " + formatDateTime(claims[0].created_at) : "None yet"}</span>
    </div>
    ${queue === null
      ? `<div class="panel stat tone-blue">
      <span class="label"><i class="ph ph-receipt" aria-hidden="true"></i>Waiting for your bills</span>
      <span class="value">${needReceipts}</span>
      <span class="note">File them from the claim page</span>
    </div>`
      : `<a class="panel stat tone-blue" href="notifications.html" style="text-decoration:none">
      <span class="label"><i class="ph ph-check-square-offset" aria-hidden="true"></i>Waiting for your decision</span>
      <span class="value">${queue.length}</span>
      <span class="note">${queue.length ? "Open Approvals" : "Nothing waiting"}</span>
    </a>`}`;
})();

function drawClaims(claims) {
  const box = document.getElementById("claims");
  if (!claims.length) {
    box.innerHTML = `<div class="empty"><i class="ph ph-airplane-tilt" aria-hidden="true"></i>
      <strong>No claims yet</strong>
      <span>Start with a travel, food or hotel request.</span>
      <a href="new-request.html" class="btn btn-primary btn-sm">New request</a></div>`;
    return;
  }
  const rows = claims.map((c) => `
    <tr>
      <td><a class="row-link mono" href="claims.html?claim=${encodeURIComponent(c.claim_no)}">${escapeHtml(c.claim_no)}</a></td>
      <td>${escapeHtml(c.template_name || "-")}</td>
      <td class="mono">${formatMoney(c.estimated_amount)}</td>
      <td>${c.level ? "L" + escapeHtml(c.level) : "-"}</td>
      <td>${c.created_at ? formatDateTime(c.created_at) : "-"}</td>
      <td>${statusBadge(c.status)}</td>
      <td><div class="actions">
        <a class="btn ${c.status === "awaiting_settlement" ? "btn-primary" : "btn-ghost"} btn-sm" href="${c.status === "awaiting_settlement" ? "claim-bills.html" : "claims.html"}?claim=${encodeURIComponent(c.claim_no)}">${c.status === "awaiting_settlement" ? "File settlement" : "Open"}</a>
      </div></td>
    </tr>`).join("");
  box.innerHTML = `<div class="table-wrap"><table class="table">
    <thead><tr><th>Claim no</th><th>Type</th><th>Estimate</th><th>Level</th><th>Raised</th><th>Status</th><th></th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

function drawLatestNotes(notes) {
  const box = document.getElementById("latest-notes");
  if (!notes.length) {
    box.innerHTML = `<div class="empty"><i class="ph ph-bell-simple" aria-hidden="true"></i><strong>You are all caught up</strong>
      <span>Approvals, advances and payouts will show up here.</span></div>`;
    return;
  }
  box.innerHTML = `<div class="notes">${notes.slice(0, 5).map((n) => `
    <div class="note-row" style="grid-template-columns:1fr">
      <div class="note-body">
        <p>${escapeHtml(n.message)}</p>
        <div class="note-meta"><span class="mono">${escapeHtml(n.claim_no)}</span><span>${formatDateTime(n.created_at)}</span></div>
      </div>
    </div>`).join("")}</div>`;
}
