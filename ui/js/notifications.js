// Notifications: the messages the system sent to this person, newest first. Read-only.
// (Things to DO, like approving a claim, are on the Approvals page.)

(async function () {
  await startPage("notifications");
  document.getElementById("refresh").addEventListener("click", loadNotes);
  loadNotes();
})();

async function loadNotes() {
  const list = document.getElementById("list");
  let notes;
  try {
    notes = await api("/get_all_notifications");
  } catch (error) {
    list.innerHTML = `<div class="panel-pad"><div class="alert">${escapeHtml(error.message)}</div></div>`;
    return;
  }
  list.innerHTML = notes.length
    ? `<div class="notes">${notes.map((n) => `
      <article class="note-row">
        <span class="note-icon" aria-hidden="true"><i class="ph ph-bell-simple"></i></span>
        <div class="note-body">
          <p>${escapeHtml(n.message)}</p>
          <div class="note-meta">
            ${n.claim_no ? `<a class="mono" href="claims.html?claim=${encodeURIComponent(n.claim_no)}">${escapeHtml(n.claim_no)}</a>` : ""}
            <span>${formatDateTime(n.created_at)}</span>
          </div>
        </div>
      </article>`).join("")}</div>`
    : `<div class="empty"><i class="ph ph-bell-simple" aria-hidden="true"></i><strong>No notifications yet</strong>
        <span>Approvals, advances and payouts will appear here.</span></div>`;
}
