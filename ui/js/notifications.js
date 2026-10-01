// Approvals and notifications.
// Approvers (managers, Finance) get "Waiting for you": GET /get_pending_approvals lists exactly the claims
// where it is their turn, so anything listed can be sent to /approve or /reject and nothing else can.
// Everyone gets their notifications below, as a read-only list.

let me = null;

// What the API asks this person to do, and how the button says it (api_docs.md, get_pending_approvals).
const ACTIONS = {
  approve: { label: "Approve", busy: "Approving…", done: "Approved." },
  release_advance: { label: "Release advance", busy: "Releasing…", done: "Advance released." },
  verify: { label: "Verify settlement", busy: "Verifying…", done: "Settlement verified." },
  release_payment: { label: "Release payout", busy: "Releasing…", done: "Payout released." },
};

(async function () {
  me = await startPage("inbox");
  if (isApprover(me.role)) {
    document.getElementById("title").textContent = "Approvals";
    document.getElementById("intro").textContent = "Claims waiting for your decision, oldest first. Your notifications are below.";
    document.getElementById("queue-panel").hidden = false;
    document.getElementById("list-head").hidden = false;
  }
  document.getElementById("refresh").addEventListener("click", load);
  load();
})();

function load() {
  if (isApprover(me.role)) loadQueue();
  loadNotes();
}

// ---- Waiting for you ----------------------------------------------------------------------
async function loadQueue() {
  const box = document.getElementById("queue");
  let queue;
  try {
    queue = await api("/get_pending_approvals");
  } catch (error) {
    box.innerHTML = `<div class="panel-pad"><div class="alert">${escapeHtml(error.message)}</div></div>`;
    return;
  }
  document.getElementById("queue-count").textContent = queue.length ? `${queue.length} waiting` : "";
  box.innerHTML = queue.length
    ? `<div class="notes">${queue.map(queueRowHtml).join("")}</div>`
    : `<div class="empty"><i class="ph ph-check-circle" aria-hidden="true"></i><strong>Nothing is waiting for you</strong>
        <span>When it is your turn on a claim, it appears here.</span></div>`;
}

function queueRowHtml(item) {
  const action = ACTIONS[item.action] || ACTIONS.approve;
  const advance = Number(item.advance_requested) > 0 ? `, advance ${formatMoney(item.advance_requested)}` : "";
  // The docs offer Reject on a manager's approval; Finance steps have the single action.
  const canReject = item.action === "approve";
  return `
    <article class="note-row" data-claim="${escapeHtml(item.claim_no)}" data-action="${escapeHtml(item.action)}">
      <span class="avatar" aria-hidden="true">${escapeHtml(initials(item.claimant_name))}</span>
      <div class="note-body">
        <p><strong>${escapeHtml(item.claimant_name)}</strong> · ${escapeHtml(item.template_name)}, <span class="mono">${formatMoney(item.estimated_amount)}</span>${advance}</p>
        <div class="note-meta">
          <span class="mono">${escapeHtml(item.claim_no)}</span>
          <span>Level L${escapeHtml(item.level)}</span>
          <span>${statusBadge(item.status)}</span>
          <span>Raised ${formatDateTime(item.created_at)}</span>
        </div>
        <div class="alert" data-row-error role="alert" hidden></div>
        <div class="note-actions">
          <button type="button" class="btn btn-primary btn-sm" data-act>${action.label}${item.action === "release_advance" ? " " + formatMoney(item.advance_requested) : ""}</button>
          ${canReject ? '<button type="button" class="btn btn-danger btn-sm" data-reject>Reject</button>' : ""}
        </div>
        ${canReject ? `<form class="reject-box" data-reject-form novalidate hidden>
          <div class="field">
            <label for="why-${escapeHtml(item.claim_no)}">Reason for rejecting</label>
            <textarea class="textarea" id="why-${escapeHtml(item.claim_no)}" required></textarea>
            <span class="help">The employee sees this in their notifications.</span>
          </div>
          <div style="display:flex;gap:8px">
            <button type="submit" class="btn btn-danger btn-sm">Reject claim</button>
            <button type="button" class="btn btn-ghost btn-sm" data-cancel>Cancel</button>
          </div>
        </form>` : ""}
      </div>
    </article>`;
}

// One listener for every row's buttons.
document.getElementById("queue").addEventListener("click", async (event) => {
  const row = event.target.closest(".note-row");
  if (!row) return;

  if (event.target.closest("[data-reject]")) {
    row.querySelector("[data-reject-form]").hidden = false;
    row.querySelector("textarea").focus();
  }
  if (event.target.closest("[data-cancel]")) {
    row.querySelector("[data-reject-form]").hidden = true;
  }
  const button = event.target.closest("[data-act]");
  if (button) {
    const action = ACTIONS[row.dataset.action] || ACTIONS.approve;
    const label = button.textContent;
    button.disabled = true;
    button.textContent = action.busy;
    try {
      const result = await api("/approve", { method: "POST", body: { claim_no: row.dataset.claim } });
      const next = result.next_approver ? ` Now with ${result.next_approver.name}.` : "";
      finish(row, action.done + next);
    } catch (error) {
      showRowError(row, error);
      button.disabled = false;
      button.textContent = label;
    }
  }
});

document.getElementById("queue").addEventListener("submit", async (event) => {
  event.preventDefault();
  const row = event.target.closest(".note-row");
  const remarks = row.querySelector("textarea").value.trim();
  if (!remarks) {
    showRowError(row, { message: "Please give a reason. The employee will see it." });
    return;
  }
  const button = event.target.querySelector("[type=submit]");
  button.disabled = true;
  try {
    await api("/reject", { method: "POST", body: { claim_no: row.dataset.claim, remarks } });
    finish(row, "Rejected. The employee has been told why.");
  } catch (error) {
    showRowError(row, error);
    button.disabled = false;
  }
});

// Confirm in place. Nothing is remembered: on the next load the API no longer lists the claim.
function finish(row, text) {
  row.querySelector(".note-actions")?.remove();
  row.querySelector("[data-reject-form]")?.remove();
  row.querySelector("[data-row-error]").hidden = true;
  row.querySelector(".note-body").insertAdjacentHTML("beforeend", `<p class="alert alert-success decision">${escapeHtml(text)}</p>`);
  const left = document.querySelectorAll("#queue [data-act]").length;
  document.getElementById("queue-count").textContent = left ? `${left} waiting` : "";
}

function showRowError(row, error) {
  renderError(row.querySelector("[data-row-error]"), error);
}

// ---- Notifications (read-only) ------------------------------------------------------------
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
            <span class="mono">${escapeHtml(n.claim_no)}</span>
            <span>${formatDateTime(n.created_at)}</span>
          </div>
        </div>
      </article>`).join("")}</div>`
    : `<div class="empty"><i class="ph ph-bell-simple" aria-hidden="true"></i><strong>No notifications yet</strong>
        <span>Approvals, advances and payouts will appear here.</span></div>`;
}
