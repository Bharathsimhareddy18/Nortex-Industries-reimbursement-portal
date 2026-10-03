// The three single-purpose claim pages, each reached from a button on the claim page (claims.html):
//   claim-form.html      fill in the next form of an admin-built flow      (data-page="form")
//   claim-bills.html     upload bills, then send them to be settled        (data-page="bills")
//   claim-decision.html  read the claim and bills, then approve or reject  (data-page="decide")
// They reuse the claim loading and HTML helpers of claims.js (loaded first), which does nothing on these pages by itself.

// What the API asks this person to do, and how the button reads (the same actions as the Approvals page).
const DECISION = {
  approve: { label: "Approve", busy: "Approving…", done: "Approved." },
  release_advance: { label: "Release advance", busy: "Releasing…", done: "Advance released." },
  verify: { label: "Verify settlement", busy: "Verifying…", done: "Settlement verified." },
  release_payment: { label: "Release payout", busy: "Releasing…", done: "Payout released." },
};

const overviewUrl = () => "claims.html?claim=" + encodeURIComponent(claimNo);

(async function () {
  me = await startPage("claims");
  if (!claimNo) {
    location.replace("claims.html");
    return;
  }
  try {
    await Promise.all([loadClaim(), loadMyStep()]);
  } catch (error) {
    showNotAllowed(error); // 403 not involved, 404 no such claim
    return;
  }
  ({ form: showForm, bills: showBills, decide: showDecision })[document.body.dataset.page]();
})();

function pageHead(title, subtitle) {
  return `<header class="claim-head">
      <div>
        <div class="claim-title"><h1>${escapeHtml(title)}</h1></div>
        <p class="claim-sub"><span class="mono">${escapeHtml(claim.claim_no)}</span>, ${escapeHtml(subtitle)}</p>
      </div>
      <a href="${overviewUrl()}" class="btn btn-ghost"><i class="ph ph-arrow-left" aria-hidden="true"></i>Back to the claim</a>
    </header>`;
}

// For someone who opened a page that has nothing for them (a stale link, a step already done).
function nothingToDo(title, text) {
  content.innerHTML = pageHead(title, claim.template_name) + `<div class="alert alert-info">${escapeHtml(text)} <a href="${overviewUrl()}">Open the claim</a>.</div>`;
}

// ---- Fill in the next form -----------------------------------------------------------------
function showForm() {
  if (!needsMyForm()) return nothingToDo("Fill in the form", "There is no form waiting for you on this claim.");
  content.innerHTML = pageHead(claim.flow.form_title, claim.template_name) + `
    <article class="panel panel-pad">
      <form id="step-form" novalidate style="display:grid;gap:24px">
        <div class="alert" id="form-error" role="alert" hidden></div>
        <div class="form-grid" id="fields">${claim.flow.form_fields.map(fieldHtml).join("")}</div>
        <div class="form-foot"><button type="submit" class="btn btn-primary" id="step-button"><i class="ph ph-paper-plane-tilt" aria-hidden="true"></i>Submit</button></div>
      </form>
    </article>`;

  document.getElementById("step-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const { values, problems } = readForm(claim.flow.form_fields);
    if (problems.length) return showProblems("Please fill in the highlighted fields.", problems);
    const button = document.getElementById("step-button");
    button.disabled = true;
    button.textContent = "Sending…";
    try {
      await api("/submit_step", { method: "POST", body: { claim_no: claimNo, fields: values } });
      location.href = overviewUrl();
    } catch (error) {
      showProblems(error.message, error.problems);
      button.disabled = false;
      button.innerHTML = '<i class="ph ph-paper-plane-tilt" aria-hidden="true"></i>Submit';
    }
  });
}

// ---- Upload bills --------------------------------------------------------------------------
function showBills() {
  if (!(isMine() && claim.status === "awaiting_settlement" && !claim.totals)) {
    return nothingToDo("Upload bills", "This claim is not waiting for bills from you.");
  }
  content.innerHTML = pageHead("Upload bills", claim.template_name) + `<article class="panel panel-pad"><section id="settlement">${settlementHtml(claim)}</section></article>`;
  wireSettlement(claimNo, async () => {
    await loadClaim().catch(() => {});
    if (claim.totals || claim.status !== "awaiting_settlement") location.href = overviewUrl(); // submitted: the claim page takes over
    else showBills(); // another bill was added: redraw this page
  });
  hydrateThumbnails(claim.receipts);
}

// ---- Approve or reject ---------------------------------------------------------------------
function showDecision() {
  if (!myStep) return nothingToDo("Review", "Nothing is waiting on you for this claim.");
  const action = DECISION[myStep.action] || DECISION.approve;
  const canReject = myStep.action === "approve"; // the Finance steps only have the one action
  content.innerHTML = pageHead("Review claim", `${claim.template_name}, raised by ${claim.claimant_name}`) + `
    ${reasonHtml()}
    <section class="panel"><div class="panel-head"><h2>Details</h2></div><div class="panel-pad">${factsHtml()}</div></section>
    ${claim.totals ? `<section class="panel panel-pad">${settlementHtml(claim)}</section>` : billsHtml()}
    <section class="panel panel-pad" id="decision" style="display:grid;gap:12px">
      <strong>Your decision</strong>
      <div class="alert" id="decision-error" role="alert" hidden></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button type="button" class="btn btn-primary" id="decision-act">${action.label}</button>
        ${canReject ? '<button type="button" class="btn btn-danger" id="decision-reject">Reject</button>' : ""}
      </div>
      <form id="decision-reject-form" novalidate hidden style="display:grid;gap:8px">
        <label for="decision-why">Reason for rejecting</label>
        <textarea class="textarea" id="decision-why" required></textarea>
        <span class="help muted">The employee sees this in their notifications.</span>
        <div style="display:flex;gap:8px">
          <button type="submit" class="btn btn-danger btn-sm">Reject claim</button>
          <button type="button" class="btn btn-ghost btn-sm" id="decision-cancel">Cancel</button>
        </div>
      </form>
    </section>`;
  hydrateThumbnails(claim.receipts);

  const errorBox = document.getElementById("decision-error");
  const act = document.getElementById("decision-act");
  const form = document.getElementById("decision-reject-form");
  const done = () => { location.href = "approvals.html"; }; // back to the queue, for the next one

  act.addEventListener("click", async () => {
    errorBox.hidden = true;
    act.disabled = true;
    act.textContent = action.busy;
    try {
      await api("/approve", { method: "POST", body: { claim_no: claimNo } });
      done();
    } catch (error) {
      renderError(errorBox, error);
      act.disabled = false;
      act.textContent = action.label;
    }
  });
  document.getElementById("decision-reject")?.addEventListener("click", () => { form.hidden = false; document.getElementById("decision-why").focus(); });
  document.getElementById("decision-cancel").addEventListener("click", () => { form.hidden = true; });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const remarks = document.getElementById("decision-why").value.trim();
    if (!remarks) return renderError(errorBox, { message: "Please give a reason. The employee will see it." });
    try {
      await api("/reject", { method: "POST", body: { claim_no: claimNo, remarks } });
      done();
    } catch (error) {
      renderError(errorBox, error);
    }
  });
}
