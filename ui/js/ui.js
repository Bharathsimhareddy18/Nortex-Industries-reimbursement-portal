// Small helpers shared by every page: formatting, safe HTML, status labels,
// and the six claim steps. Everything about claims comes from the API; nothing is stored here.

// Anything that came from the API or the user is escaped before it goes into innerHTML,
// so a merchant name like "<b>" is shown as text, not run as markup.
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// The API sends money as strings ("48000.00"); Indian grouping reads naturally to Nortex staff.
function formatMoney(value) {
  const number = Number(value);
  if (value === null || value === undefined || Number.isNaN(number)) return "-";
  return "₹" + number.toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

// API times are UTC without a "Z"; adding it makes the browser show local time.
function toDate(isoString) {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(isoString) ? isoString : isoString + "Z");
}

function formatDateTime(isoString) {
  return toDate(isoString).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

// One label and one colour per claim status, used by every badge on every page.
const STATUS = {
  pending_approval: { label: "Awaiting approval", tone: "info" },
  awaiting_advance: { label: "Awaiting advance", tone: "warn" },
  awaiting_settlement: { label: "Upload receipts", tone: "accent" },
  settlement_review: { label: "With Finance", tone: "neutral" },
  paid: { label: "Paid", tone: "success" },
  rejected: { label: "Rejected", tone: "danger" },
  returned: { label: "Returned", tone: "warn" },
};

function statusBadge(status) {
  const s = STATUS[status] || { label: status, tone: "neutral" };
  return `<span class="badge badge-${s.tone}">${escapeHtml(s.label)}</span>`;
}

// Managers and Finance can approve; plain employees only raise claims.
const APPROVER_ROLES = ["Reporting Manager", "Head of Department", "Head of Division", "MD", "Finance"];

function isApprover(role) {
  return APPROVER_ROLES.includes(role);
}

// Shows the API's detail and, when present, each problem as a bullet.
function renderError(element, error) {
  const problems = (error.problems || []).map((p) => `<li>${escapeHtml(p)}</li>`).join("");
  element.innerHTML = `<p>${escapeHtml(error.message)}</p>${problems ? `<ul>${problems}</ul>` : ""}`;
  element.hidden = false;
}

// ---- The six steps of a claim, shared by the new-request page and the claim page -----
const CLAIM_STEPS = [
  { title: "Travel request", icon: "ph-file-text", later: "You fill the form" },
  { title: "Trip approval", icon: "ph-user-check", later: "Goes for a decision" },
  { title: "Advance", icon: "ph-hand-coins", later: "Reaches you before the trip" },
  { title: "Trip settlement", icon: "ph-receipt", later: "You upload the bills" },
  { title: "Finance review", icon: "ph-magnifying-glass", later: "Verified, then released" },
  { title: "Payout", icon: "ph-paper-plane-tilt", later: "Paid and closed" },
];

// Every template has the same life in the API (request, managers approve, bills, Finance, payout);
// only Travelling can add an advance. So the steps are shared and only the names follow the template.
function claimSteps(templateName) {
  if (!templateName || templateName === "Travelling") return CLAIM_STEPS;
  return CLAIM_STEPS.map((step, i) =>
    i === 0 ? { ...step, title: templateName + " request" } :
    i === 1 ? { ...step, title: "Approval" } :
    i === 3 ? { ...step, title: "Settlement" } : step);
}

// Position of the advance step in CLAIM_STEPS; pages drop it when no advance was requested.
const ADVANCE_STEP = 2;

// Which step is in progress for each status. "paid" is past the last step, so all are done.
const STEP_FOR_STATUS = { pending_approval: 1, awaiting_advance: 2, awaiting_settlement: 3, settlement_review: 4, paid: 6 };

// steps: [{ title, icon, note, state }] where state is "", "is-done" or "is-current".
function trackerHtml(steps) {
  return `<ol class="tracker" style="--steps:${steps.length}" aria-label="Claim progress">${steps.map((s) => `
    <li class="track-step ${s.state}">
      <span class="track-dot"><i class="ph ${s.state === "is-done" ? "ph-check" : s.icon}" aria-hidden="true"></i></span>
      <span class="track-text"><strong>${s.title}</strong><small>${s.note || ""}</small></span>
    </li>`).join("")}</ol>`;
}
