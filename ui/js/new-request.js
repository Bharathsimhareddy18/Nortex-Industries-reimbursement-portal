// New request: list templates, draw the chosen template's form from get_template_required_fields,
// then create_claim. The form is built from data, so a new field in the API needs no UI change.

// Only presentation lives here; the list of templates itself comes from the API.
const TEMPLATE_LOOK = {
  Travelling: { icon: "ph-airplane-tilt", tone: "tone-sky", text: "Trips, with an optional advance before you go." },
  Food: { icon: "ph-fork-knife", tone: "tone-blue", text: "Meals while working away from base." },
  "Hotel stay": { icon: "ph-bed", tone: "tone-navy", text: "Nights stayed, limited by the city tier." },
};

// Extra help for fields whose rule is not obvious from the label.
const FIELD_HELP = {
  advance_requested: "Up to 60% of the estimated trip cost.",
};

let currentTemplate = null;
let currentFields = [];

(async function () {
  await startPage("new");
  try {
    const templates = await api("/get_templates");
    drawTemplates(templates);
  } catch (error) {
    document.getElementById("templates").hidden = true;
    renderError(document.getElementById("page-error"), error);
  }
})();

function drawTemplates(templates) {
  const box = document.getElementById("templates");
  box.innerHTML = templates.map((t) => {
    const look = TEMPLATE_LOOK[t.template_name] || { icon: "ph-file-text", tone: "tone-sky", text: "" };
    return `<button type="button" class="template" data-id="${t.template_id}" data-name="${escapeHtml(t.template_name)}">
        <span class="template-icon ${look.tone}"><i class="ph ${look.icon}" aria-hidden="true"></i></span>
        <span><strong>${escapeHtml(t.template_name)}</strong><span>${look.text}</span></span>
      </button>`;
  }).join("");

  box.addEventListener("click", (event) => {
    const tile = event.target.closest(".template");
    if (!tile) return;
    box.querySelectorAll(".template").forEach((t) => t.classList.toggle("is-selected", t === tile));
    openTemplate(Number(tile.dataset.id), tile.dataset.name);
  });
}

async function openTemplate(id, name) {
  const form = document.getElementById("claim-form");
  document.getElementById("result").hidden = true;
  document.getElementById("form-error").hidden = true;
  try {
    // The API wants both id and name, and 404s if they do not match.
    const data = await api(`/get_template_required_fields?template_id=${id}&template_name=${encodeURIComponent(name)}`);
    currentTemplate = data;
    currentFields = data.fields;
    document.getElementById("form-title").textContent = data.template_name + " details";
    document.getElementById("fields").innerHTML = data.fields.map(fieldHtml).join("");
    updateRequesting();
    form.hidden = false;
    form.querySelector("input, select")?.focus();
  } catch (error) {
    renderError(document.getElementById("page-error"), error);
  }
}

// One input per field type, as the API docs describe.
function fieldHtml(field) {
  const id = "f-" + field.name;
  const required = field.required ? "required" : "";
  const min = field.min !== null ? `min="${field.min}"` : "";
  const value = field.default !== null && field.default !== false ? `value="${escapeHtml(field.default)}"` : "";
  const help = FIELD_HELP[field.name] ? `<span class="help">${FIELD_HELP[field.name]}</span>` : "";
  const label = `<label for="${id}">${escapeHtml(field.label)}${field.required ? '<span class="req" aria-hidden="true">*</span>' : ""}</label>`;
  let input;

  if (field.type === "boolean") {
    const checked = field.default ? "checked" : "";
    return `<div class="field span-2" data-field="${field.name}">
        <label class="check"><input type="checkbox" id="${id}" ${checked}>${escapeHtml(field.label)}</label>
        ${help}<span class="error" hidden></span></div>`;
  }
  if (field.type === "choice") {
    // Option values are indexes, so a numeric choice (city_tier 1, 2, 3) is sent back as a number, not "1".
    const options = field.choices.map((c, i) => `<option value="${i}">${escapeHtml(c)}</option>`).join("");
    input = `<select class="select" id="${id}" ${required}><option value="">Choose…</option>${options}</select>`;
  } else if (field.type === "integer") {
    input = `<input class="input" id="${id}" type="number" step="1" inputmode="numeric" ${min} ${value} ${required}>`;
  } else if (field.type === "money") {
    input = `<input class="input mono" id="${id}" type="number" step="0.01" inputmode="decimal" ${min} ${value} ${required}>`;
  } else if (field.type === "datetime") {
    input = `<input class="input" id="${id}" type="datetime-local" ${required}>`;
  } else {
    input = `<input class="input" id="${id}" type="text" ${required}>`;
  }
  return `<div class="field" data-field="${field.name}">${label}${input}${help}<span class="error" hidden></span></div>`;
}

// The field that decides the approval level, per the API docs. Hotel stay is worked out
// by the API from nights and the city's lodging limit, so we do not guess it here.
const AMOUNT_FIELD = { Travelling: "estimated_trip_cost", Food: "amount" };

// Redrawn on every keystroke: the "Requesting ₹X" line, and the steps that follow submit,
// which include the advance only while an advance amount above zero is filled in.
function updateRequesting() {
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

// Turns the inputs into the "fields" object create_claim expects. Returns problems found before sending.
function readForm() {
  const values = {};
  const problems = [];
  for (const field of currentFields) {
    const input = document.getElementById("f-" + field.name);
    if (field.type === "boolean") {
      values[field.name] = input.checked;
      continue;
    }
    const raw = input.value.trim();
    if (raw === "") {
      // Leave empty optional fields out, so the API applies its own default.
      if (field.required) problems.push(`${field.name}: This field is required`);
      continue;
    }
    if (field.type === "choice") values[field.name] = field.choices[Number(raw)];
    else if (field.type === "integer") values[field.name] = Number(raw);
    else if (field.type === "money") values[field.name] = raw; // strings keep paise exact
    else if (field.type === "datetime") values[field.name] = raw.length === 16 ? raw + ":00" : raw; // datetime-local omits seconds
    else values[field.name] = raw;
  }
  return { values, problems };
}

// Puts "field: message" problems under their input; anything else goes in the box at the top.
function showProblems(detail, problems) {
  document.querySelectorAll("#fields .field").forEach((f) => {
    f.classList.remove("has-error");
    f.querySelector(".error").hidden = true;
  });
  const leftover = [];
  for (const problem of problems) {
    const [name, ...rest] = problem.split(": ");
    const box = document.querySelector(`#fields [data-field="${CSS.escape(name)}"]`);
    if (box && rest.length) {
      box.classList.add("has-error");
      box.querySelector(".error").textContent = rest.join(": ");
      box.querySelector(".error").hidden = false;
    } else {
      leftover.push(problem);
    }
  }
  renderError(document.getElementById("form-error"), { message: detail, problems: leftover });
}

document.getElementById("claim-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const { values, problems } = readForm();
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
  document.querySelectorAll(".template").forEach((t) => t.classList.remove("is-selected"));

  const chain = claim.approvers.length
    ? claim.approvers.map((p) => `<div class="chain-person"><span class="avatar" aria-hidden="true">${escapeHtml(p.name.split(" ").map((w) => w[0]).join(""))}</span>
        <span>${escapeHtml(p.name)}<small>${escapeHtml(p.role)}</small></span></div>`).join('<i class="ph ph-caret-right" aria-hidden="true"></i>')
    : `<p class="muted">No approval needed. You can upload receipts after the trip.</p>`;

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
        <div><dt>Estimated amount</dt><dd class="mono">${formatMoney(claim.estimated_amount)}</dd></div>
        <div><dt>Approval level</dt><dd>L${escapeHtml(claim.level)}</dd></div>
      </dl>
      <div style="display:grid;gap:8px">
        <span class="label">Approvers, in order</span>
        <div class="chain">${chain}</div>
      </div>
      <div style="display:flex;gap:12px;flex-wrap:wrap">
        <a class="btn btn-primary" href="claims.html?claim=${encodeURIComponent(claim.claim_no)}">Open this claim</a>
        <a class="btn btn-ghost" href="new-request.html">Raise another</a>
      </div>
    </div>`;
  box.hidden = false;
}
