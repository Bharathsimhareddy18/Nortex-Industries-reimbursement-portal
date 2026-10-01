// Claims: the list of my claims (GET /get_my_claims) and one claim's page (GET /get_claim):
// tracker, approvals, settlement, updates. Everything comes from the API; the page fetches the
// claim again after each upload or submit instead of remembering anything.

const content = document.getElementById("content");
const claimNo = new URLSearchParams(location.search).get("claim");
let me = null;
let claim = null;      // the last GET /get_claim answer
let claimNotes = [];   // this claim's notifications, fetched once

(async function () {
  me = await startPage("claims");
  if (!claimNo) {
    showList();
    return;
  }
  const [detail, notes] = await Promise.allSettled([loadClaim(), api("/get_all_notifications")]);
  if (detail.status === "rejected") {
    showNotAllowed(detail.reason); // 403 not involved, 404 no such claim
    return;
  }
  claimNotes = notes.status === "fulfilled" ? notes.value.filter((n) => n.claim_no === claimNo) : null;
  drawClaim();
})();

async function loadClaim() {
  claim = await api("/get_claim?claim_no=" + encodeURIComponent(claimNo));
}

// After an upload or a submit: read the claim again, then redraw.
async function reloadAndDraw() {
  try {
    await loadClaim();
  } catch {
    // Keep the last copy; the next page load will show the change.
  }
  drawClaim();
}

// ---- The list ---------------------------------------------------------------------------
async function showList() {
  let claims;
  try {
    claims = await api("/get_my_claims");
  } catch (error) {
    content.innerHTML = `<div class="alert">${escapeHtml(error.message)}</div>`;
    return;
  }
  const rows = claims.map((c) => `
    <tr>
      <td><a class="row-link mono" href="claims.html?claim=${encodeURIComponent(c.claim_no)}">${escapeHtml(c.claim_no)}</a></td>
      <td>${escapeHtml(c.template_name || "-")}</td>
      <td class="mono">${formatMoney(c.estimated_amount)}</td>
      <td>${c.created_at ? formatDateTime(c.created_at) : "-"}</td>
      <td>${statusBadge(c.status)}</td>
      <td><div class="actions"><a class="btn btn-ghost btn-sm" href="claims.html?claim=${encodeURIComponent(c.claim_no)}">Open</a></div></td>
    </tr>`).join("");

  content.innerHTML = `
    <header class="page-head">
      <div><h1>Claims</h1><p>All your claims, newest first. Open one to track it or file its settlement.</p></div>
      <form id="lookup" style="display:flex;gap:8px" novalidate>
        <input class="input mono" id="lookup-no" placeholder="TRQ-2026-0001" style="width:190px;height:40px" aria-label="Claim number">
        <button class="btn btn-ghost" type="submit">Open</button>
      </form>
    </header>
    <section class="panel">
      ${claims.length ? `<div class="table-wrap"><table class="table">
        <thead><tr><th>Claim no</th><th>Type</th><th>Estimate</th><th>Raised</th><th>Status</th><th></th></tr></thead>
        <tbody>${rows}</tbody></table></div>`
      : `<div class="empty"><i class="ph ph-files" aria-hidden="true"></i><strong>No claims yet</strong>
          <span>Raise a request, or type a claim number above to open it.</span>
          <a href="new-request.html" class="btn btn-primary btn-sm">New request</a></div>`}
    </section>`;

  document.getElementById("lookup").addEventListener("submit", (event) => {
    event.preventDefault();
    const value = document.getElementById("lookup-no").value.trim();
    if (value) location.href = "claims.html?claim=" + encodeURIComponent(value);
  });
}

// ---- One claim --------------------------------------------------------------------------
function drawClaim() {
  const summary = [claim.template_name, formatMoney(claim.estimated_amount), "Level L" + claim.level, "Raised " + formatDateTime(claim.created_at)]
    .map(escapeHtml).join(", ");
  const by = isMine() ? "" : `<p class="claim-sub">Raised by ${escapeHtml(claim.claimant_name)}</p>`;

  content.innerHTML = `
    <header class="claim-head">
      <div>
        <div class="claim-title"><h1 class="mono">${escapeHtml(claim.claim_no)}</h1>${statusBadge(claim.status)}</div>
        <p class="claim-sub">${summary}</p>
        ${by}
      </div>
      <a href="claims.html" class="btn btn-ghost"><i class="ph ph-arrow-left" aria-hidden="true"></i>All claims</a>
    </header>

    ${reasonHtml()}

    <article class="panel claim-card">
      ${progressSection()}
      ${canSettle() ? `<section id="settlement">${settlementHtml(claim)}</section>` : waitingHtml()}
    </article>

    ${canSettle() ? "" : billsHtml()}

    <div class="claim-grid">
      <section class="panel">
        <div class="panel-head"><h2>Updates</h2><span class="muted" style="font-size:12.5px">From your notifications</span></div>
        <div class="panel-pad">${updatesHtml()}</div>
      </section>
      <section class="panel">
        <div class="panel-head"><h2>Details</h2></div>
        <div class="panel-pad">${factsHtml()}</div>
      </section>
    </div>`;

  if (canSettle()) wireSettlement(claimNo, reloadAndDraw);
  hydrateThumbnails(claim.receipts); // the photos of the bills, for the owner, the approvers and Finance alike
}

// Why the money is needed, in the claimant's own words. Approvers and Finance read this first.
function reasonHtml() {
  const reason = claim.fields && claim.fields.reason;
  if (!reason) return "";
  return `<section class="panel">
      <div class="panel-head"><h2>Why this money is needed</h2></div>
      <div class="panel-pad"><p style="white-space:pre-wrap;margin:0">${escapeHtml(reason)}</p></div>
    </section>`;
}

// The uploaded bills, for people who are not filing the settlement (an approver or Finance checking the invoices).
function billsHtml() {
  const receipts = claim.receipts || [];
  if (!receipts.length) return "";
  return `<section class="panel">
      <div class="panel-head"><h2>Bills</h2><span class="muted" style="font-size:12.5px">Click a photo to open it</span></div>
      <div class="panel-pad">${receiptsHtml(receipts)}</div>
    </section>`;
}

function isMine() {
  return claim.claimant_code === me.emp_code;
}

function hasAdvance() {
  return Number(claim.advance_requested) > 0;
}

// Bills can be filed by the owner once the claim is fully approved (and any advance released).
// Once submitted, the section stays to show the totals.
function canSettle() {
  return isMine() && (claim.status === "awaiting_settlement" || Boolean(claim.totals));
}

// The first step still waiting, in a phase ("request" or "settlement").
function pendingStep(phase) {
  return claim.approvals.find((a) => a.phase === phase && a.decision === "pending") || null;
}

// Before approval: say who the claim is waiting for instead of showing an upload that would be refused.
function waitingHtml() {
  const next = pendingStep("request");
  const text = {
    pending_approval: next ? `Waiting for ${next.name} (${next.role}). You can upload bills once every approver has said yes.` : "Waiting for approval.",
    awaiting_advance: `Approved. Waiting for ${next ? next.name : "Finance"} to release your advance; bill upload opens after that.`,
    settlement_review: "The bills are with Finance.",
    paid: "Paid and closed.",
  }[claim.status];
  return text ? `<section><p class="muted">${escapeHtml(text)}</p></section>` : "";
}

// 403 (not involved) or 404 (no such claim): nothing else on the page applies.
function showNotAllowed(error) {
  content.innerHTML = `
    <header class="claim-head">
      <div class="claim-title"><h1 class="mono">${escapeHtml(claimNo)}</h1></div>
      <a href="claims.html" class="btn btn-ghost"><i class="ph ph-arrow-left" aria-hidden="true"></i>All claims</a>
    </header>
    <div class="alert">${escapeHtml(error.message)}</div>`;
}

// What each approval step asks for, in words.
const STEP_ACTION = { approve: "Approve", release_advance: "Release advance", verify: "Verify bills", release_payment: "Release payout" };

function progressSection() {
  const rejected = claim.approvals.find((a) => a.decision === "rejected");
  const current = STEP_FOR_STATUS[claim.status] ?? 1;
  const steps = claim.status === "rejected" ? "" : trackerHtml(claimSteps(claim.template_name).map((step, i) => {
    const state = i < current ? "is-done" : i === current ? "is-current" : "";
    let note = i < current ? "Done" : i === current ? currentNote(i) : step.later;
    if (i === 0) note = formatDateTime(claim.created_at);
    return { ...step, state, note };
  })
    // No advance asked for: the step does not exist for this claim, so it is not shown at all.
    .filter((step, i) => i !== ADVANCE_STEP || hasAdvance()));

  // Every step of both phases, in order, with who decided and when.
  const chain = claim.approvals.map((a) => {
    const icon = a.decision === "approved" ? '<i class="ph ph-check"></i>' : a.decision === "rejected" ? '<i class="ph ph-x"></i>' : escapeHtml(initials(a.name));
    const when = a.decided_at ? ` · ${formatDateTime(a.decided_at)}` : "";
    return `<span class="chain-person${a.decision === "approved" ? " is-done" : ""}${a.decision === "rejected" ? " is-rejected" : ""}">
      <span class="avatar" aria-hidden="true">${icon}</span>
      <span>${escapeHtml(a.name)} <small>${escapeHtml(STEP_ACTION[a.action] || a.role)}${when}</small></span>
    </span>`;
  }).join('<i class="ph ph-caret-right" aria-hidden="true"></i>');

  return `<section style="display:grid;gap:24px">
      <h2 style="font-size:17px">${escapeHtml(claim.template_name)}</h2>
      ${rejected ? `<div class="alert"><strong>Rejected by ${escapeHtml(rejected.name)}.</strong> ${escapeHtml(rejected.remarks || "")}</div>` : ""}
      ${steps}
      ${chain ? `<div class="subpanel">
        <div class="subpanel-head"><strong>Approvals</strong><span>one after another, in this order</span></div>
        <div class="chain">${chain}</div>
      </div>` : ""}
    </section>`;
}

function currentNote(step) {
  const next = pendingStep(step >= 4 ? "settlement" : "request");
  if (step === 1) return next ? `Waiting for ${next.name}` : "Waiting for a decision";
  if (step === 2) return next ? `Waiting for ${next.name}` : "Waiting for Finance";
  if (step === 3) return "Settlement to be filed";
  if (step === 4) return next ? `With ${next.name}` : "Verifying, then payout";
  return "";
}

function updatesHtml() {
  if (claimNotes === null) return `<div class="alert">Could not load the updates. Try refreshing.</div>`;
  if (!claimNotes.length) return `<p class="muted">No updates for this claim in your notifications yet.</p>`;
  // Notifications come newest first; the story reads better oldest first.
  return `<ol class="timeline">${[...claimNotes].reverse().map((n) =>
    `<li><div>${escapeHtml(n.message)}<small>${formatDateTime(n.created_at)}</small></div></li>`).join("")}</ol>`;
}

// The request form's answers, with readable labels ("number_of_days" -> "Number of days").
function fieldValue(value) {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  // A form answer is the local time the employee typed, not a UTC timestamp, so no UTC shift here.
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
    return new Date(value).toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
  }
  return String(value);
}

function factsHtml() {
  const rows = [
    ["Approval level", "L" + claim.level],
    ["Estimate", `<span class="mono">${formatMoney(claim.estimated_amount)}</span>`],
    // Only mention the advance when there is one.
    hasAdvance() ? ["Advance asked", `<span class="mono">${formatMoney(claim.advance_requested)}</span>`] : null,
    hasAdvance() ? ["Advance released", `<span class="mono">${formatMoney(claim.advance_amount)}</span>`] : null,
    ...Object.entries(claim.fields || {})
      .filter(([name]) => !["advance_requested", "estimated_trip_cost", "amount", "reason"].includes(name))
      .map(([name, value]) => [escapeHtml(name.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase())), escapeHtml(fieldValue(value))]),
  ].filter(Boolean);
  return `<dl class="facts-grid">${rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl>`;
}
