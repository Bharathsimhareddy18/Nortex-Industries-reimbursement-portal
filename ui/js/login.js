// Login: send email + password, keep the returned emp_code and session_token, go to the dashboard.

// Already signed in? Skip the form.
if (getSession()) location.replace("dashboard.html");

// The seeded demo users from the API docs, so a reviewer can try each role quickly.
const DEMO_USERS = [
  ["chaitanya.reddy", "Employee"],
  ["deepa.nair", "Employee"],
  ["suresh.iyer", "Reporting Manager"],
  ["meera.krishnan", "Head of Department"],
  ["arvind.rao", "Head of Division"],
  ["nandita.shah", "MD"],
  ["ravi.menon", "Finance"],
  ["kavitha.balan", "Finance Controller"],
  ["admin", "Admin"],
];

const form = document.getElementById("login-form");
const errorBox = document.getElementById("login-error");
const button = document.getElementById("login-button");

document.getElementById("demo-users").innerHTML = DEMO_USERS.map(
  ([user, role]) => `<li><button type="button" data-email="${user}@nortexindustries.com">${user.replace(".", " ")}<span>${role}</span></button></li>`
).join("");

document.getElementById("demo-users").addEventListener("click", (event) => {
  const pick = event.target.closest("button");
  if (!pick) return;
  form.email.value = pick.dataset.email;
  form.password.value = "nortex123";
  form.password.focus();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.hidden = true;

  if (!form.email.value.trim() || !form.password.value) {
    errorBox.textContent = "Enter your email and password.";
    errorBox.hidden = false;
    return;
  }

  button.disabled = true;
  button.textContent = "Signing in…";
  try {
    const session = await api("/auth/login", {
      method: "POST",
      body: { email: form.email.value.trim(), password: form.password.value },
    });
    saveSession(session);
    const me = await api("/auth/me");
    location.href = me.role === "Admin" ? "admin.html" : "dashboard.html";
  } catch (error) {
    // The API gives one message for a wrong email or a wrong password, on purpose.
    errorBox.textContent = error.message;
    errorBox.hidden = false;
    button.disabled = false;
    button.textContent = "Sign in";
  }
});
