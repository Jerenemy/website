// static/js/contact.js
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("contact-form");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    const res = await fetch("/api/contact", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        name: f.name.value,
        email: f.email.value,
        message: f.message.value,
      }),
    });

    const json = await res.json();
    document.getElementById("contact-status").textContent =
      json.ok ? "Sent!" : `Error: ${json.error || "unknown"}`;

    if (json.ok) f.reset();
  });
});
