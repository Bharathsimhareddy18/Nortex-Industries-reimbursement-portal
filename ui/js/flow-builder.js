// Flow builder (admin): build a template as an ordered list of blocks, then save it as JSON with POST / PUT /admin/templates.
// The page keeps the flow in one object (`flow`) and redraws the middle and right panels from it after every change.

const BLOCKS = [
  { type: "form", icon: "ph-file-text", label: "Ask for fields", help: "Questions the employee answers" },
  { type: "approval", icon: "ph-user-check", label: "Approval", help: "Someone approves or rejects" },
  { type: "advance", icon: "ph-hand-coins", label: "Advance", help: "Finance releases an advance" },
  { type: "upload_bills", icon: "ph-receipt", label: "Ask for bills", help: "Employee uploads bills, AI checks them" },
  { type: "finance_review", icon: "ph-magnifying-glass", label: "Finance review", help: "Finance verifies the bills" },
  { type: "payout", icon: "ph-paper-plane-tilt", label: "Payout", help: "Release the money (last step)" },
];
const BLOCK = Object.fromEntries(BLOCKS.map((b) => [b.type, b]));
const FIELD_TYPES = [
  ["text", "Short text"], ["longtext", "Paragraph"], ["integer", "Whole number"], ["money", "Amount (₹)"],
  ["datetime", "Date and time"], ["boolean", "Yes / no"], ["choice", "Choice from a list"],
];
const ALL_HEADS = ["Travelling", "Lodging", "Meals", "Business Entertainment", "Local conveyance", "Other"];

let flow = { name: "", steps: [] };
let selected = null;   // index of the step being edited
let users = [];        // people who can be picked as approvers
let templateId = null; // set when editing an existing flow
let counter = 0;

// ---- Small helpers -------------------------------------------------------------------------
const $ = (id) => document.getElementById(id);
const allFields = () => flow.steps.filter((s) => s.type === "form").flatMap((s) => s.fields);
const moneyFields = () => allFields().filter((f) => f.type === "money" && f.name);

function newId() {
  counter += 1;
  return "s" + counter + Math.random().toString(36).slice(2, 5);
}

// "Client name" -> "client_name"; a number is added when another field already has it.
function slug(label, except) {
  const base = label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").replace(/^[^a-z]+/, "").slice(0, 34) || "field";
  const taken = new Set(allFields().filter((f) => f !== except).map((f) => f.name));
  let name = base, n = 2;
  while (taken.has(name)) name = base + "_" + n++;
  return name;
}

function newField(label = "") {
  return { name: "", label, type: "text", required: true, choices: "", min: "" };
}

function newStep(type) {
  const id = newId();
  switch (type) {
    case "form": return { id, type, title: "", fields: [newField()] };
    case "approval": return { id, type, approver: { mode: "reporting_manager", emp_code: "" } };
    case "advance": return { id, type, approver: { mode: "user", emp_code: "" }, amount_field: "" };
    case "upload_bills": return { id, type, heads: [...ALL_HEADS] };
    default: return { id, type, approver: { mode: "user", emp_code: "" } }; // finance_review, payout
  }
}

const personName = (code) => (users.find((u) => u.emp_code === code) || {}).name;

function summary(step) {
  switch (step.type) {
    case "form": return step.fields.map((f) => f.label || "(no label)").join(", ") || "No fields yet";
    case "upload_bills": return step.heads.join(", ") || "No bill types chosen";
    case "approval":
      return step.approver.mode === "reporting_manager" ? "The claimant's Reporting Manager" : personName(step.approver.emp_code) || "Choose a person";
    default: return personName(step.approver.emp_code) || "Choose a person";
  }
}

const stepTitle = (step) => (step.type === "form" ? step.title || "Form" : BLOCK[step.type].label);

// ---- The blocks on the left ----------------------------------------------------------------
function drawPalette() {
  $("palette").innerHTML = BLOCKS.map((b) => `
    <button type="button" class="block" draggable="true" data-type="${b.type}">
      <i class="ph ${b.icon}" aria-hidden="true"></i><span>${b.label}<small>${b.help}</small></span>
    </button>`).join("");
}

// New blocks go in before the Payout step (if there is one), because the payout must stay last.
function addBlock(type, at) {
  const step = newStep(type);
  const payout = flow.steps.findIndex((s) => s.type === "payout");
  const index = at ?? (payout >= 0 ? payout : flow.steps.length);
  flow.steps.splice(index, 0, step);
  selected = index;
  draw();
}

// ---- The flow in the middle ----------------------------------------------------------------
function drawCanvas() {
  const box = $("canvas");
  if (!flow.steps.length) {
    box.innerHTML = `<div class="canvas-empty"><div><i class="ph ph-flow-arrow" style="font-size:32px" aria-hidden="true"></i>
      <p><strong>Start here</strong><br>Drag a block in, or click one on the left.<br>Most flows begin with “Ask for fields”.</p></div></div>`;
    return;
  }
  box.innerHTML = flow.steps.map((step, i) => `
    ${i ? '<div class="connector"></div>' : ""}
    <div class="step-card${i === selected ? " is-selected" : ""}" draggable="true" data-index="${i}">
      <span class="step-num">${i + 1}</span>
      <i class="ph ${BLOCK[step.type].icon}" aria-hidden="true"></i>
      <div><strong>${escapeHtml(stepTitle(step))}</strong><small>${escapeHtml(summary(step))}</small></div>
      <div class="step-tools">
        <button type="button" class="icon-btn" data-up="${i}" aria-label="Move up" ${i === 0 ? "disabled" : ""}><i class="ph ph-arrow-up"></i></button>
        <button type="button" class="icon-btn" data-down="${i}" aria-label="Move down" ${i === flow.steps.length - 1 ? "disabled" : ""}><i class="ph ph-arrow-down"></i></button>
        <button type="button" class="icon-btn" data-remove="${i}" aria-label="Remove step"><i class="ph ph-trash"></i></button>
      </div>
    </div>`).join("");
}

function move(from, to) {
  if (to < 0 || to >= flow.steps.length) return;
  const [step] = flow.steps.splice(from, 1);
  flow.steps.splice(to, 0, step);
  selected = to;
  draw();
}

// Where would a drop at this height land? Before the first card whose middle is below the pointer.
function dropIndex(y) {
  const cards = [...document.querySelectorAll(".step-card")];
  const next = cards.find((c) => { const r = c.getBoundingClientRect(); return y < r.top + r.height / 2; });
  return next ? Number(next.dataset.index) : flow.steps.length;
}

function wireCanvas() {
  const canvas = $("canvas");
  let dragging = null; // "new:<type>" or "move:<index>"

  document.addEventListener("dragstart", (event) => {
    const block = event.target.closest(".block");
    const card = event.target.closest(".step-card");
    dragging = block ? "new:" + block.dataset.type : card ? "move:" + card.dataset.index : null;
    if (dragging) {
      event.dataTransfer.setData("text/plain", dragging);
      event.dataTransfer.effectAllowed = "copyMove";
      if (card) card.classList.add("is-dragging");
    }
  });
  document.addEventListener("dragend", () => { dragging = null; clearMarks(); document.querySelectorAll(".is-dragging").forEach((c) => c.classList.remove("is-dragging")); });

  function clearMarks() {
    canvas.classList.remove("is-over", "drop-end");
    canvas.querySelectorAll(".drop-before").forEach((c) => c.classList.remove("drop-before"));
  }

  canvas.addEventListener("dragover", (event) => {
    if (!dragging) return;
    event.preventDefault();
    clearMarks();
    canvas.classList.add("is-over");
    const index = dropIndex(event.clientY);
    const card = canvas.querySelector(`.step-card[data-index="${index}"]`);
    if (card) card.classList.add("drop-before"); else canvas.classList.add("drop-end");
  });
  canvas.addEventListener("dragleave", (event) => { if (!canvas.contains(event.relatedTarget)) clearMarks(); });
  canvas.addEventListener("drop", (event) => {
    if (!dragging) return;
    event.preventDefault();
    const index = dropIndex(event.clientY);
    const [kind, value] = dragging.split(":");
    clearMarks();
    dragging = null;
    if (kind === "new") addBlock(value, index);
    else {
      const from = Number(value);
      move(from, index > from ? index - 1 : index);
    }
  });

  canvas.addEventListener("click", (event) => {
    const up = event.target.closest("[data-up]"), down = event.target.closest("[data-down]"), remove = event.target.closest("[data-remove]");
    if (up) return move(Number(up.dataset.up), Number(up.dataset.up) - 1);
    if (down) return move(Number(down.dataset.down), Number(down.dataset.down) + 1);
    if (remove) {
      flow.steps.splice(Number(remove.dataset.remove), 1);
      selected = null;
      return draw();
    }
    const card = event.target.closest(".step-card");
    if (card) { selected = Number(card.dataset.index); draw(); }
  });
}

// ---- The settings on the right -------------------------------------------------------------
const personOptions = (chosen) => `<option value="">Choose a person…</option>` + users.map((u) =>
  `<option value="${escapeHtml(u.emp_code)}" ${u.emp_code === chosen ? "selected" : ""}>${escapeHtml(u.name)} · ${escapeHtml(u.role)}</option>`).join("");

function drawInspector() {
  const box = $("inspector");
  const step = flow.steps[selected];
  if (!step) {
    box.innerHTML = `<h2>Settings</h2><p class="muted">Click a step to change it.</p>`;
    return;
  }
  const head = `<h2><i class="ph ${BLOCK[step.type].icon}" aria-hidden="true"></i> ${BLOCK[step.type].label}</h2>`;

  if (step.type === "form") {
    box.innerHTML = head + `
      <div class="field"><label for="step-title">Title of this form</label><input class="input" id="step-title" value="${escapeHtml(step.title)}" placeholder="e.g. Client details" maxlength="100"></div>
      ${step.fields.map((f, i) => fieldRowHtml(f, i)).join("")}
      <button type="button" class="btn btn-ghost btn-sm" id="add-field"><i class="ph ph-plus"></i>Add a field</button>`;
    return;
  }
  if (step.type === "upload_bills") {
    box.innerHTML = head + `<p class="muted">What the employee may upload a bill for.</p>
      <div class="heads">${ALL_HEADS.map((h) => `<label class="check"><input type="checkbox" data-head="${h}" ${step.heads.includes(h) ? "checked" : ""}>${h}</label>`).join("")}</div>
      <p class="muted">Each bill is read by AI and checked against what it was claimed for.</p>`;
    return;
  }
  const canBeManager = step.type === "approval";
  const mode = step.approver.mode;
  box.innerHTML = head + `
    ${canBeManager ? `<label class="radio"><input type="radio" name="mode" value="reporting_manager" ${mode === "reporting_manager" ? "checked" : ""}>
        <span>The claimant's Reporting Manager<br><small class="muted">Different for each employee</small></span></label>
      <label class="radio"><input type="radio" name="mode" value="user" ${mode === "user" ? "checked" : ""}><span>A specific person</span></label>` : ""}
    ${mode === "user" ? `<div class="field"><label for="person">${step.type === "approval" ? "Approver" : "Who does this"}</label>
        <select class="select" id="person">${personOptions(step.approver.emp_code)}</select></div>` : ""}
    ${step.type === "advance" ? `<div class="field"><label for="amount-field">The advance amount is the answer to</label>
        <select class="select" id="amount-field"><option value="">Choose a money field…</option>${moneyFields().map((f) =>
          `<option value="${f.name}" ${f.name === step.amount_field ? "selected" : ""}>${escapeHtml(f.label)}</option>`).join("")}</select>
        <span class="help">Add an “Amount” field to a form first.</span></div>` : ""}
    ${step.type === "approval" ? "" : `<p class="muted">${step.type === "advance" ? "Finance releases the advance before the trip." : step.type === "payout" ? "This must be the last step." : "Verifies the bills before the payout."}</p>`}`;
}

function fieldRowHtml(f, i) {
  const needsMin = ["integer", "money"].includes(f.type);
  return `<div class="field-row" data-field="${i}">
      <div class="top">
        <input class="input" data-k="label" placeholder="Question, e.g. Client name" value="${escapeHtml(f.label)}" maxlength="100">
        <button type="button" class="icon-btn" data-del-field="${i}" aria-label="Remove field"><i class="ph ph-x"></i></button>
      </div>
      <select class="select" data-k="type">${FIELD_TYPES.map(([v, l]) => `<option value="${v}" ${v === f.type ? "selected" : ""}>${l}</option>`).join("")}</select>
      ${f.type === "choice" ? `<input class="input" data-k="choices" placeholder="Choices, separated by commas" value="${escapeHtml(f.choices)}">` : ""}
      <div class="opts">
        <label class="check"><input type="checkbox" data-k="required" ${f.required ? "checked" : ""}>Required</label>
        ${needsMin ? `<input class="input" data-k="min" type="number" step="any" placeholder="Minimum" value="${escapeHtml(f.min)}" style="width:110px">` : ""}
      </div>
    </div>`;
}

function wireInspector() {
  const box = $("inspector");
  const step = () => flow.steps[selected];

  // Text boxes: keep the data in step as they type, and redraw only the middle (the right panel would lose focus).
  box.addEventListener("input", (event) => {
    const target = event.target;
    if (target.id === "step-title") step().title = target.value;
    const row = target.closest("[data-field]");
    if (row && target.dataset.k && target.type !== "checkbox" && target.tagName !== "SELECT") {
      const f = step().fields[Number(row.dataset.field)];
      f[target.dataset.k] = target.value;
      if (target.dataset.k === "label") renameField(f);
    }
    drawCanvas();
  });

  box.addEventListener("change", (event) => {
    const target = event.target;
    const s = step();
    const row = target.closest("[data-field]");
    if (row && target.dataset.k) {
      const f = s.fields[Number(row.dataset.field)];
      f[target.dataset.k] = target.type === "checkbox" ? target.checked : target.value;
      if (target.dataset.k === "type") { if (f.type !== "money") dropReferences(f); draw(); return; }
    }
    if (target.dataset.head) s.heads = ALL_HEADS.filter((h) => (h === target.dataset.head ? target.checked : s.heads.includes(h)));
    if (target.name === "mode") { s.approver.mode = target.value; if (target.value !== "user") s.approver.emp_code = ""; draw(); return; }
    if (target.id === "person") s.approver.emp_code = target.value;
    if (target.id === "amount-field") s.amount_field = target.value;
    drawCanvas();
  });

  box.addEventListener("click", (event) => {
    if (event.target.closest("#add-field")) {
      step().fields.push(newField());
      draw();
      box.querySelector(".field-row:last-of-type input")?.focus();
    }
    const del = event.target.closest("[data-del-field]");
    if (del) {
      const [gone] = step().fields.splice(Number(del.dataset.delField), 1);
      dropReferences(gone);
      draw();
    }
  });
}

// A field gets its stored name from its label, unless it was already saved (its name must not change under claims in flight).
function renameField(f) {
  if (f.locked) return;
  const old = f.name;
  f.name = f.label.trim() ? slug(f.label, f) : "";
  repoint(old, f.name);
}

function repoint(old, name) {
  if (!old || old === name) return;
  flow.steps.forEach((s) => { if (s.type === "advance" && s.amount_field === old) s.amount_field = name; });
}

// A field that stopped being a money field (or was deleted) can no longer be the estimate or the advance amount.
function dropReferences(f) {
  flow.steps.forEach((s) => { if (s.type === "advance" && s.amount_field === f.name) s.amount_field = ""; });
}

// ---- Top section, drawing, saving ----------------------------------------------------------
function draw() {
  drawCanvas();
  drawInspector();
}

// Friendly checks before sending; the server checks again and has the last word.
function problems() {
  const found = [];
  if (flow.name.trim().length < 3) found.push("Give the flow a name (at least 3 letters).");
  if (flow.steps.length < 2) found.push("Add at least two steps.");
  flow.steps.forEach((s, i) => {
    const where = `Step ${i + 1} (${stepTitle(s)})`;
    if (s.type === "form") {
      if (!s.title.trim()) found.push(`${where}: give the form a title.`);
      if (!s.fields.length) found.push(`${where}: add at least one field.`);
      s.fields.forEach((f) => {
        if (!f.label.trim()) found.push(`${where}: every field needs a question.`);
        if (f.type === "choice" && f.choices.split(",").map((c) => c.trim()).filter(Boolean).length < 2) found.push(`${where}: “${f.label}” needs at least two choices.`);
      });
    }
    if (s.type === "upload_bills" && !s.heads.length) found.push(`${where}: choose what bills may be for.`);
    if (s.type === "advance" && !s.amount_field) found.push(`${where}: choose the amount field.`);
    if (s.approver && s.approver.mode === "user" && !s.approver.emp_code) found.push(`${where}: choose a person.`);
  });
  return found;
}

// The claim's total is the first amount field on the forms, other than the one used for the advance (the advance is capped
// at 60% of the total, so it cannot be its own total). The admin does not have to choose it.
function estimateField() {
  const advance = flow.steps.find((s) => s.type === "advance");
  const field = moneyFields().find((f) => !advance || f.name !== advance.amount_field);
  return field ? field.name : null;
}

function payload() {
  return {
    name: flow.name.trim(),
    estimate_field: estimateField(),
    steps: flow.steps.map((s) => {
      if (s.type === "form") {
        return { id: s.id, type: s.type, title: s.title.trim(), fields: s.fields.map((f) => {
          const field = { name: f.name, label: f.label.trim(), type: f.type, required: f.required };
          if (f.type === "choice") field.choices = f.choices.split(",").map((c) => c.trim()).filter(Boolean);
          if (["integer", "money"].includes(f.type) && f.min !== "" && f.min !== null) field.min = Number(f.min);
          return field;
        }) };
      }
      const out = { id: s.id, type: s.type };
      if (s.approver) out.approver = s.approver.mode === "user" ? { mode: "user", emp_code: s.approver.emp_code } : { mode: "reporting_manager" };
      if (s.type === "advance") out.amount_field = s.amount_field;
      if (s.type === "upload_bills") out.heads = s.heads;
      return out;
    }),
  };
}

async function save() {
  const errorBox = $("error");
  errorBox.hidden = true;
  const mine = problems();
  if (mine.length) {
    renderError(errorBox, { message: "Fix these before saving:", problems: mine });
    window.scrollTo({ top: 0, behavior: "smooth" });
    return;
  }
  const button = $("save");
  button.disabled = true;
  button.textContent = "Saving…";
  try {
    await api(templateId ? `/admin/templates/${templateId}` : "/admin/templates", { method: templateId ? "PUT" : "POST", body: payload() });
    location.href = "admin.html#templates";
  } catch (error) {
    renderError(errorBox, error);
    window.scrollTo({ top: 0, behavior: "smooth" });
    button.disabled = false;
    button.innerHTML = '<i class="ph ph-floppy-disk" aria-hidden="true"></i>Save flow';
  }
}

// Turn a saved flow back into the editable shape (names of saved fields are locked).
function load(template) {
  flow = {
    name: template.name,
    steps: template.flow.steps.map((s) => s.type === "form"
      ? { ...s, fields: s.fields.map((f) => ({ required: true, ...f, choices: (f.choices || []).join(", "), min: f.min ?? "", locked: true })) }
      : { ...s, approver: s.approver && { mode: s.approver.mode, emp_code: s.approver.emp_code || "" } }),
  };
  $("flow-name").value = flow.name;
  $("page-title").textContent = "Edit flow";
  selected = 0;
}

(async function () {
  const me = await startPage("admin");
  if (me.role !== "Admin") { location.replace("dashboard.html"); return; }

  try {
    users = (await api("/admin/users")).filter((u) => u.role !== "Admin");
    templateId = Number(new URLSearchParams(location.search).get("template")) || null;
    if (templateId) {
      const template = (await api("/admin/templates")).find((t) => t.id === templateId && t.kind === "flow");
      if (!template) { renderError($("error"), { message: "That flow was not found, or it is one of the built-in templates." }); templateId = null; }
      else load(template);
    }
  } catch (error) {
    renderError($("error"), error);
  }

  drawPalette();
  wireCanvas();
  wireInspector();
  $("palette").addEventListener("click", (event) => {
    const block = event.target.closest(".block");
    if (block) addBlock(block.dataset.type);
  });
  $("flow-name").addEventListener("input", (event) => { flow.name = event.target.value; });
  $("save").addEventListener("click", save);
  draw();
})();
