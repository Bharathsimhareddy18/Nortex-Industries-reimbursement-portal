// Form drawing and reading, shared by the request page (new-request.js) and the claim page (claims.js, for a later
// form step of an admin-built flow). Fields come from the API as data: {name, label, type, required, choices, min, default}.
// A form must contain  #fields  (the inputs) and  #form-error  (the message box).

// Extra help for fields whose rule is not obvious from the label.
const FIELD_HELP = {
  advance_requested: "Up to 60% of the estimated trip cost.",
  reason: "Your approvers and Finance will read this before they decide. Say what the money is for and why it is needed.",
};

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
  } else if (field.type === "longtext") {
    // A paragraph, so it gets a real text box and the full width of the form.
    return `<div class="field span-2" data-field="${field.name}">${label}
        <textarea class="textarea" id="${id}" rows="4" maxlength="1000" ${required}></textarea>
        ${help}<span class="error" hidden></span></div>`;
  } else {
    input = `<input class="input" id="${id}" type="text" ${required}>`;
  }
  return `<div class="field" data-field="${field.name}">${label}${input}${help}<span class="error" hidden></span></div>`;
}

// Turns the inputs into the "fields" object create_claim expects. Returns problems found before sending.
function readForm(currentFields) {
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
    if (field.type === "longtext" && field.min && raw.length < field.min) {
      problems.push(`${field.name}: Please write at least ${field.min} characters`);
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

