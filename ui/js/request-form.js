// Request form: one page per template. It draws the template's form from get_template_required_fields, then create_claim.
// The form is built from data, so a new field in the API needs no UI change.

let currentTemplate = null;
let currentFields = [];

(async function () {
  await startPage("new");
  const params = new URLSearchParams(location.search);
  const id = Number(params.get("template")), name = params.get("name") || "";
  if (!id) {
    location.replace("new-request.html");
    return;
  }
  try {
    // The API wants both id and name, and 404s if they do not match.
    const data = await api(`/get_template_required_fields?template_id=${id}&template_name=${encodeURIComponent(name)}`);
    currentTemplate = data;
    currentFields = data.fields;
    document.getElementById("page-title").textContent = data.template_name;
    document.title = data.template_name + " · Nortex Travel Claims";
    document.getElementById("form-title").textContent = "Details";
    document.getElementById("fields").innerHTML = data.fields.map(fieldHtml).join("");
    updateRequesting();
    document.getElementById("claim-form").hidden = false;
    document.querySelector("#claim-form input, #claim-form select, #claim-form textarea")?.focus();
  } catch (error) {
    renderError(document.getElementById("page-error"), error);
  }
})();

// The field that decides the approval level, per the API docs. Hotel stay is worked out
// by the API from nights and the city's lodging limit, so we do not guess it here.
const AMOUNT_FIELD = { Travelling: "estimated_trip_cost", Food: "amount" };

// Redrawn on every keystroke: the "Requesting ₹X" line, and the steps that follow submit,
// which include the advance only while an advance amount above zero is filled in.
function updateRequesting() {
  if (currentTemplate.steps) { // an admin-built flow: show its own steps
    document.getElementById("requesting").textContent = "";
    document.getElementById("after-submit").innerHTML = flowTrackerHtml(currentTemplate.steps
      .map((s, i) => ({ ...s, state: i === 0 ? "current" : "pending", note: i === 0 ? "You are here" : "" })));
    return;
  }
  const input = document.getElementById("f-" + AMOUNT_FIELD[currentTemplate.template_name]);
  const value = input ? Number(input.value) : 0;
  document.getElementById("requesting").textContent = value > 0 ? "Requesting " + formatMoney(value) : "";

  const advanceInput = document.getElementById("f-advance_requested");
  const wantsAdvance = advanceInput ? Number(advanceInput.value) > 0 : false;
  document.getElementById("after-submit").innerHTML = trackerHtml(claimSteps(currentTemplate.template_name)
    .map((step, i) => ({ ...step, state: i === 0 ? "is-current" : "", note: i === 0 ? "You are here" : step.later }))
    .filter((step, i) => wantsAdvance || i !== ADVANCE_STEP));
}
document.getElementById("fields").addEventListener("input", updateRequesting);

document.getElementById("claim-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const { values, problems } = readForm(currentFields);
  if (problems.length) {
    showProblems("Please fill in the highlighted fields.", problems);
    return;
  }

  const button = document.getElementById("submit-button");
  button.disabled = true;
  button.textContent = "Sending…";
  try {
    const claim = await api("/create_claim", { method: "POST", body: { template_id: currentTemplate.template_id, fields: values } });
    showResult(claim);
  } catch (error) {
    showProblems(error.message, error.problems);
  } finally {
    button.disabled = false;
    button.innerHTML = '<i class="ph ph-paper-plane-tilt" aria-hidden="true"></i>Submit request';
  }
});

function showResult(claim) {
  document.getElementById("claim-form").hidden = true;
  document.querySelector(".page-head").hidden = true;

  const chain = claim.approvers.length
    ? claim.approvers.map((p) => `<div class="chain-person"><span class="avatar" aria-hidden="true">${escapeHtml(p.name.split(" ").map((w) => w[0]).join(""))}</span>
        <span>${escapeHtml(p.name)}<small>${escapeHtml(p.role)}</small></span></div>`).join('<i class="ph ph-caret-right" aria-hidden="true"></i>')
    : `<p class="muted">${claim.level ? "No approval needed. You can upload receipts after the trip." : "Nobody else needs to act on it."}</p>`;

  const box = document.getElementById("result");
  box.innerHTML = `
    <div style="display:grid;gap:24px">
      <div style="display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:flex-start">
        <div style="display:grid;gap:8px">
          <span class="muted">Request raised</span>
          <h2 class="mono" style="font-size:24px">${escapeHtml(claim.claim_no)}</h2>
        </div>
        ${statusBadge(claim.status)}
      </div>
      <dl class="facts-grid">
        ${Number(claim.estimated_amount) > 0 ? `<div><dt>Estimated amount</dt><dd class="mono">${formatMoney(claim.estimated_amount)}</dd></div>` : ""}
        ${claim.level ? `<div><dt>Approval level</dt><dd>L${escapeHtml(claim.level)}</dd></div>` : ""}
      </dl>
      <div style="display:grid;gap:8px">
        <span class="label">${claim.level ? "Approvers, in order" : "People who will act on it, in order"}</span>
        <div class="chain">${chain}</div>
      </div>
      <div style="display:flex;gap:12px;flex-wrap:wrap">
        <a class="btn btn-primary" href="claims.html?claim=${encodeURIComponent(claim.claim_no)}">Open this claim</a>
        <a class="btn btn-ghost" href="new-request.html">Raise another</a>
      </div>
    </div>`;
  box.hidden = false;
}
