// New request: the list of what can be claimed. Each tile opens that template's own page (request-form.html).

// Only presentation lives here; the list of templates itself comes from the API.
const TEMPLATE_LOOK = {
  Travelling: { icon: "ph-airplane-tilt", tone: "tone-sky", text: "Trips, with an optional advance before you go." },
  Food: { icon: "ph-fork-knife", tone: "tone-blue", text: "Meals while working away from base." },
  "Hotel stay": { icon: "ph-bed", tone: "tone-navy", text: "Nights stayed, limited by the city tier." },
};

(async function () {
  await startPage("new");
  try {
    drawTemplates(await api("/get_templates"));
  } catch (error) {
    document.getElementById("templates").hidden = true;
    renderError(document.getElementById("page-error"), error);
  }
})();

function drawTemplates(templates) {
  document.getElementById("templates").innerHTML = templates.map((t) => {
    const look = TEMPLATE_LOOK[t.template_name] || { icon: "ph-flow-arrow", tone: "tone-sky", text: "A custom flow set up by your admin." };
    return `<a class="template" href="request-form.html?template=${encodeURIComponent(t.template_id)}&name=${encodeURIComponent(t.template_name)}" style="text-decoration:none;color:inherit">
        <span class="template-icon ${look.tone}"><i class="ph ${look.icon}" aria-hidden="true"></i></span>
        <span><strong>${escapeHtml(t.template_name)}</strong><span>${look.text}</span></span>
      </a>`;
  }).join("");
}
