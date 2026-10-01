// The settlement part of a claim's page: upload receipts one at a time (upload_receipt),
// show each verdict, then submit_settlement. The receipts and totals come from GET /get_claim;
// after each upload or submit the page fetches the claim again, so nothing is stored here.

const MAX_BYTES = 5 * 1024 * 1024; // same limit as the API, checked here to fail fast
// What a bill can be for, by claim type. A trip can include any of them; a food claim only needs the food ones.
const HEADS_BY_TEMPLATE = {
  Travelling: ["Travelling", "Local conveyance", "Lodging", "Meals", "Business Entertainment", "Other"],
  Food: ["Meals", "Business Entertainment", "Other"],
  "Hotel stay": ["Lodging", "Meals", "Other"],
};
const headsFor = (templateName) => HEADS_BY_TEMPLATE[templateName] || HEADS_BY_TEMPLATE.Travelling;
const RESULT_LOOK = {
  ok: { label: "Counted", tone: "success" },
  excluded: { label: "Flagged", tone: "danger" },
  duplicate: { label: "Duplicate", tone: "warn" },
};
// Bill photos by line id, as object URLs. Memory only: they are fetched from GET /get_receipt_image
// (the owner, the approvers and Finance may all open them) and kept for this visit.
const thumbnails = {};

function thumbHtml(lineId) {
  return thumbnails[lineId]
    ? `<a href="${thumbnails[lineId]}" target="_blank" rel="noopener" title="Open the bill" style="display:block"><img src="${thumbnails[lineId]}" alt="Photo of the bill"></a>`
    : `<div class="thumb"><i class="ph ph-receipt" aria-hidden="true"></i></div>`;
}

// Loads each bill's photo from the API and swaps it in for the placeholder icon.
async function hydrateThumbnails(receipts) {
  for (const r of receipts || []) {
    if (!thumbnails[r.line_id]) {
      try {
        thumbnails[r.line_id] = await apiImage(`/get_receipt_image?line_id=${encodeURIComponent(r.line_id)}`);
      } catch {
        continue; // keep the icon: the file may be gone after a server restart
      }
    }
    const slot = document.querySelector(`.receipt[data-line="${CSS.escape(String(r.line_id))}"] .thumb-slot`);
    if (slot) slot.innerHTML = thumbHtml(r.line_id);
  }
}

function settlementHtml(claim) {
  const receipts = claim.receipts || [];
  if (claim.totals) return submittedHtml(claim.totals, receipts, nextFinanceStep(claim));


  return `
    <div class="settle-title"><h2>File the settlement</h2><span>Upload one bill at a time. Each is read and checked against what you say it is for.</span></div>
    <form id="upload-form" novalidate>
      <div class="settle-form">
        <div class="field">
          <label for="head">What is this bill for?<span class="req">*</span></label>
          <select class="select" id="head" required>
            <option value="">Select…</option>${headsFor(claim.template_name).map((h) => `<option>${h}</option>`).join("")}
          </select>
          <span class="help">The amount is read from the bill. You never type it.</span>
        </div>
        <div class="field">
          <span class="label">Bill photo<span class="req">*</span></span>
          <label class="dropzone" id="dropzone" for="file">
            <i class="ph ph-file-arrow-up" aria-hidden="true"></i>
            <span><strong id="file-name">Drop the bill here, or click to browse</strong><br><span style="font-size:12.5px">PNG or JPEG, up to 5 MB</span></span>
          </label>
          <input type="file" id="file" accept="image/png,image/jpeg" hidden>
        </div>
      </div>
      <div class="alert" id="upload-error" role="alert" hidden style="margin-top:16px"></div>
      <div class="settle-foot">
        <div class="preview-row"><img class="preview" id="preview" alt="Selected bill" hidden></div>
        <button type="submit" class="btn btn-primary" id="upload-button"><i class="ph ph-scan" aria-hidden="true"></i>Upload and check</button>
      </div>
    </form>
    ${receiptsHtml(receipts)}
    ${receipts.length ? `
      <div class="alert" id="submit-error" role="alert" hidden style="margin-top:16px"></div>
      <div class="settle-foot">
        <span class="muted" style="font-size:13px">Only counted bills go to Finance. You cannot add bills after submitting.</span>
        <button type="button" class="btn btn-primary" id="submit-button"><i class="ph ph-paper-plane-tilt" aria-hidden="true"></i>Submit settlement</button>
      </div>` : ""}`;
}

function receiptsHtml(receipts) {
  if (!receipts.length) return "";
  const counted = receipts.filter((r) => r.status === "ok");
  const total = counted.reduce((sum, r) => sum + Number(r.amount || 0), 0);
  return `<div class="receipts">
      ${receipts.map(receiptHtml).join("")}
      <div class="totals">
        <div><span class="muted">Bills counted</span><span>${counted.length} of ${receipts.length}</span></div>
        <div class="grand"><span>Counted so far</span><span class="mono">${formatMoney(total)}</span></div>
      </div>
    </div>`;
}

function receiptHtml(r) {
  const look = RESULT_LOOK[r.status] || { label: r.status, tone: "neutral" };
  const facts = [r.head, r.bill_no && "Bill " + r.bill_no, r.bill_date, r.paid_by && "Paid by " + r.paid_by]
    .filter(Boolean).map((f) => `<span>${escapeHtml(f)}</span>`).join("");
  return `<div class="receipt${r.status === "ok" ? "" : " is-out"}" data-line="${escapeHtml(r.line_id)}">
      <span class="thumb-slot" style="display:contents">${thumbHtml(r.line_id)}</span>
      <div class="receipt-body">
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><strong>${escapeHtml(r.merchant || "Unknown merchant")}</strong>
          <span class="badge badge-${look.tone}">${look.label}</span></div>
        <div class="facts">${facts}</div>
        <p style="color:var(--${r.status === "ok" ? "muted" : look.tone})">${escapeHtml(r.message)}</p>
      </div>
      <span class="amount mono">${formatMoney(r.amount)}</span>
    </div>`;
}

// The settlement step waiting on someone (Ravi to verify, then Kavitha to pay), if any.
function nextFinanceStep(claim) {
  return (claim.approvals || []).find((a) => a.phase === "settlement" && a.decision === "pending") || null;
}

function submittedHtml(s, receipts, next) {
  // At most one of payable / recoverable is above zero.
  const outcome = Number(s.payable) > 0
    ? `<div class="grand"><span>Nortex pays you</span><span class="mono">${formatMoney(s.payable)}</span></div>`
    : Number(s.recoverable) > 0
      ? `<div class="grand"><span>Deducted from payroll</span><span class="mono">${formatMoney(s.recoverable)}</span></div>`
      : `<div class="grand"><span>Nothing to pay either way</span><span class="mono">${formatMoney(0)}</span></div>`;
  return `
    <div class="settle-title"><h2>Settlement submitted</h2><span>${next ? `Now with ${escapeHtml(next.name)} in Finance.` : "Finance has finished with it."}</span></div>
    <div class="receipts" style="margin-top:0">
      ${receipts.map(receiptHtml).join("")}
      <div class="totals">
        <div><span class="muted">Bills you paid</span><span class="mono">${formatMoney(s.paid_by_employee)}</span></div>
        <div><span class="muted">Advance received</span><span class="mono">${formatMoney(s.advance)}</span></div>
        ${outcome}
      </div>
    </div>`;
}

// Hooks up the form drawn by settlementHtml. `redraw` repaints the claim page after a change.
function wireSettlement(claimNo, redraw) {
  const form = document.getElementById("upload-form");
  if (!form) return; // already submitted: nothing to wire

  const fileInput = document.getElementById("file");
  const dropzone = document.getElementById("dropzone");
  const preview = document.getElementById("preview");

  function pickFile(file) {
    if (!file) return;
    document.getElementById("file-name").textContent = file.name;
    preview.src = URL.createObjectURL(file);
    preview.hidden = false;
  }
  fileInput.addEventListener("change", () => pickFile(fileInput.files[0]));
  dropzone.addEventListener("dragover", (event) => { event.preventDefault(); dropzone.classList.add("is-over"); });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("is-over"));
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("is-over");
    const file = event.dataTransfer.files[0];
    if (!file) return;
    // Put the dropped file into the input so the form reads it the same way as a click.
    const transfer = new DataTransfer();
    transfer.items.add(file);
    fileInput.files = transfer.files;
    pickFile(file);
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorBox = document.getElementById("upload-error");
    errorBox.hidden = true;
    const head = document.getElementById("head").value;
    const file = fileInput.files[0];
    const problem =
      !head ? "Choose what the bill is for." :
      !file ? "Choose a photo of the bill." :
      !["image/png", "image/jpeg"].includes(file.type) ? "The bill must be a PNG or JPEG photo." :
      file.size > MAX_BYTES ? "The photo is larger than 5 MB." : "";
    if (problem) {
      renderError(errorBox, { message: problem });
      return;
    }

    const data = new FormData();
    data.append("claim_no", claimNo);
    data.append("head", head);
    data.append("file", file);

    const button = document.getElementById("upload-button");
    button.disabled = true;
    button.textContent = "Reading the bill…";
    try {
      const result = await api("/upload_receipt", { method: "POST", form: data });
      thumbnails[result.line_id] = preview.src;
      redraw(); // the receipt (and its verdict) now comes back in get_claim
    } catch (error) {
      renderError(errorBox, error);
      button.disabled = false;
      button.innerHTML = '<i class="ph ph-scan" aria-hidden="true"></i>Upload and check';
    }
  });

  const submit = document.getElementById("submit-button");
  if (!submit) return;
  submit.addEventListener("click", async () => {
    const errorBox = document.getElementById("submit-error");
    errorBox.hidden = true;
    submit.disabled = true;
    submit.textContent = "Submitting…";
    try {
      await api("/submit_settlement", { method: "POST", body: { claim_no: claimNo } });
      redraw(); // status and totals now come back in get_claim
    } catch (error) {
      renderError(errorBox, error);
      submit.disabled = false;
      submit.innerHTML = '<i class="ph ph-paper-plane-tilt" aria-hidden="true"></i>Submit settlement';
    }
  });
}
