// Approvals: the claims waiting for THIS person right now, from GET /get_pending_approvals.
// The API lists a claim only when it is this person's turn, so anything shown here can be approved or rejected,
// and a claim leaves the list as soon as it is decided. Nothing is remembered in the browser.

let me = null;

// What the API asks this person to do, and how the button reads (api_docs.md, get_pending_approvals).
const ACTIONS = {
  approve: { label: "Approve", busy: "Approving…", done: "Approved." },
  release_advance: { label: "Release advance", busy: "Releasing…", done: "Advance released." },
  verify: { label: "Verify settlement", busy: "Verifying…", done: "Settlement verified." },
  release_payment: { label: "Release payout", busy: "Releasing…", done: "Payout released." },
};

(async function () {
  me = await startPage("approvals");
  // Every signed-in person can have a queue: an admin-built flow may ask anyone to approve.
  document.getElementById("refresh").addEventListener("click", loadQueue);
  loadQueue();
})();

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
    ? `<div class="notes">${queue.map(rowHtml).join("")}</div>`
    : `<div class="empty"><i class="ph ph-check-circle" aria-hidden="true"></i><strong>Nothing is waiting for you</strong>
        <span>When it is your turn on a claim, it appears here.</span></div>`;
}

function rowHtml(item) {
  const action = ACTIONS[item.action] || ACTIONS.approve;
  const advance = Number(item.advance_requested) > 0 ? `, advance ${formatMoney(item.advance_requested)}` : "";
  // Only a manager's approval can be rejected here; the Finance steps have the single action.
  const canReject = item.action === "approve";
  const claimLink = `claim-decision.html?claim=${encodeURIComponent(item.claim_no)}`;
  return `
    <article class="note-row" data-claim="${escapeHtml(item.claim_no)}" data-action="${escapeHtml(item.action)}">
      <span class="avatar" aria-hidden="true">${escapeHtml(initials(item.claimant_name))}</span>
      <div class="note-body">
        <p><strong>${escapeHtml(item.claimant_name)}</strong> · ${escapeHtml(item.template_name)}, ${Number(item.estimated_amount) > 0 ? `<span class="mono">${formatMoney(item.estimated_amount)}</span>` : ""}${advance}</p>
        <div class="note-meta">
          <span class="mono">${escapeHtml(item.claim_no)}</span>
          ${item.level ? `<span>Level L${escapeHtml(item.level)}</span>` : ""}
          <span>${statusBadge(item.status)}</span>
          <span>Raised ${formatDateTime(item.created_at)}</span>
        </div>
        ${item.reason ? `<p style="white-space:pre-wrap;margin:10px 0 0"><span class="muted">Why: </span>${escapeHtml(item.reason)}</p>` : ""}
        <div class="alert" data-row-error role="alert" hidden></div>
        <div class="note-actions">
          <button type="button" class="btn btn-primary btn-sm" data-act>${action.label}${item.action === "release_advance" ? " " + formatMoney(item.advance_requested) : ""}</button>
          ${canReject ? '<button type="button" class="btn btn-danger btn-sm" data-reject>Reject</button>' : ""}
          <a class="btn btn-ghost btn-sm" href="${claimLink}"><i class="ph ph-receipt" aria-hidden="true"></i>Review claim and bills</a>
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
      await api("/approve", { method: "POST", body: { claim_no: row.dataset.claim } });
      finish(row, action.done);
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

// Confirm in place. On the next load the API no longer lists the claim.
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
