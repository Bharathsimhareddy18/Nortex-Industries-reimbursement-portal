// Admin: read-only tables of everything, plus the Templates tab, which lists the three built-in templates and the flows
// built in flow-builder.html (New flow / Edit).

const TABS = [
  { key: "users", label: "Users", icon: "ph-users", load: loadUsers },
  { key: "templates", label: "Templates", icon: "ph-stack", load: loadTemplates },
  { key: "claims", label: "Claims", icon: "ph-files", load: loadClaims },
  { key: "approvals", label: "Approvals", icon: "ph-check-square-offset", load: loadApprovals },
  { key: "notifications", label: "Notifications", icon: "ph-bell", load: loadNotifications },
];

const ACTION_LABEL = { approve: "Approve", release_advance: "Release advance", verify: "Verify", release_payment: "Release payout" };
const DECISION_BADGE = { pending: "badge-warn", approved: "badge-success", rejected: "badge-danger", returned: "badge-info" };

// Cells are HTML, so every value that came from the API is escaped before it gets here.
function table(headers, rows) {
  if (!rows.length) return `<div class="empty"><strong>Nothing here yet</strong></div>`;
  const head = headers.map((h) => `<th>${escapeHtml(h)}</th>`).join("");
  const body = rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("");
  return `<div class="table-wrap"><table class="table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

const mono = (value) => `<span class="mono">${escapeHtml(value)}</span>`;
const badge = (text, tone = "badge-neutral") => `<span class="badge ${tone}">${escapeHtml(text)}</span>`;

async function loadUsers() {
  const users = await api("/admin/users");
  return table(["Code", "Name", "Email", "Designation", "Department", "Reports to", "Role"], users.map((u) => [
    mono(u.emp_code), escapeHtml(u.name), escapeHtml(u.email), escapeHtml(u.designation || "-"), escapeHtml(u.department || "-"),
    u.reporting_manager_code ? mono(u.reporting_manager_code) : "-", badge(u.role),
  ]));
}

const STEP_NAME = { form: "Ask for fields", approval: "Approval", advance: "Advance", upload_bills: "Ask for bills", finance_review: "Finance review", payout: "Payout" };

// One line saying what a flow step is and who acts on it.
function describeStep(step, people) {
  const who = step.approver ? (step.approver.mode === "reporting_manager" ? "claimant's Reporting Manager" : people[step.approver.emp_code] || step.approver.emp_code) : "";
  const what = step.type === "form" ? step.fields.map((f) => f.label).join(", ") : step.type === "upload_bills" ? step.heads.join(", ") : who;
  return [escapeHtml(step.type === "form" ? step.title : STEP_NAME[step.type]), `<span class="muted">${escapeHtml(what)}</span>`];
}

async function loadTemplates() {
  const [templates, users] = await Promise.all([api("/admin/templates"), api("/admin/users")]);
  const people = Object.fromEntries(users.map((u) => [u.emp_code, u.name]));
  return templates.map((t) => t.kind === "fixed"
    ? `<div class="template-card">
      <h3>${escapeHtml(t.name)} <span class="muted">· built-in template ${escapeHtml(t.id)}</span></h3>
      ${table(["Field", "Key", "Type", "Required"], t.fields.map((f) => [
        escapeHtml(f.label), mono(f.name), escapeHtml(f.type), f.required ? badge("Required", "badge-accent") : badge("Optional")]))}
    </div>`
    : `<div class="template-card">
      <h3 style="display:flex;justify-content:space-between;align-items:center;gap:12px">
        <span>${escapeHtml(t.name)} <span class="muted">· custom flow ${escapeHtml(t.id)}</span></span>
        <a class="btn btn-ghost btn-sm" href="flow-builder.html?template=${encodeURIComponent(t.id)}"><i class="ph ph-pencil-simple" aria-hidden="true"></i>Edit</a>
      </h3>
      ${table(["Step", "Block", "Details"], t.flow.steps.map((s, i) => [String(i + 1), ...describeStep(s, people)]))}
    </div>`).join("");
}

async function loadClaims() {
  const claims = await api("/admin/claims");
  return table(["Claim", "Raised by", "Template", "Level", "Status", "Estimate", "Advance", "Raised"], claims.map((c) => [
    mono(c.claim_no), `${escapeHtml(c.claimant_name)} ${mono(c.claimant_code)}`, escapeHtml(c.template_name), "L" + escapeHtml(c.level),
    statusBadge(c.status), formatMoney(c.estimated_amount), formatMoney(c.advance_amount), formatDateTime(c.created_at),
  ]));
}

async function loadApprovals() {
  const rows = await api("/admin/approvals");
  return table(["Claim", "Stage", "Step", "Role", "Action", "Assigned to", "Decision", "Remarks", "Decided"], rows.map((a) => [
    mono(a.claim_no), escapeHtml(a.phase), escapeHtml(a.step), escapeHtml(a.role), escapeHtml(ACTION_LABEL[a.action] || a.action),
    `${escapeHtml(a.approver_name)} ${mono(a.approver_code)}`, badge(a.decision, DECISION_BADGE[a.decision]),
    escapeHtml(a.remarks || "-"), a.decided_at ? formatDateTime(a.decided_at) : "-",
  ]));
}

async function loadNotifications() {
  const notes = await api("/admin/notifications");
  return table(["When", "Sent to", "Claim", "Message"], notes.map((n) => [
    formatDateTime(n.created_at), `${escapeHtml(n.recipient_name)} ${mono(n.recipient_code)}`, n.claim_no ? mono(n.claim_no) : "-", escapeHtml(n.message),
  ]));
}

(async function () {
  const me = await startPage("admin");
  if (me.role !== "Admin") {
    location.replace("dashboard.html");
    return;
  }

  const tabsBox = document.getElementById("tabs");
  const content = document.getElementById("tab-content");
  const createButton = document.getElementById("create-template");

  tabsBox.innerHTML = TABS.map((t) =>
    `<button type="button" class="btn btn-sm btn-ghost" role="tab" data-tab="${t.key}"><i class="ph ${t.icon}" aria-hidden="true"></i>${t.label}</button>`).join("");

  async function show(key) {
    const tab = TABS.find((t) => t.key === key);
    tabsBox.querySelectorAll("button").forEach((b) => {
      const active = b.dataset.tab === key;
      b.classList.toggle("btn-primary", active);
      b.classList.toggle("btn-ghost", !active);
      b.setAttribute("aria-selected", active);
    });
    document.getElementById("tab-title").textContent = tab.label;
    createButton.hidden = key !== "templates";
    content.innerHTML = `<div class="panel-pad"><div class="skeleton"></div></div>`;
    try {
      content.innerHTML = await tab.load();
    } catch (error) {
      content.innerHTML = `<div class="panel-pad"><div class="alert">${escapeHtml(error.message)}</div></div>`;
    }
  }

  tabsBox.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-tab]");
    if (button) show(button.dataset.tab);
  });

  show(location.hash === "#templates" ? "templates" : "users");
})();
