document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("contact-form");
  const status = document.getElementById("contact-status");
  const button = form.querySelector('[type="submit"]');
  // One message per send: while one is on its way (SMTP can take seconds) further submits are
  // ignored. The button is marked, not disabled, so keyboard focus stays on it.
  let sending = false;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (sending) return;
    sending = true;
    if (button) button.setAttribute("aria-disabled", "true");
    status.textContent = "Sending...";
    status.style.color = "white";

    const formData = new FormData(form);
    const data = Object.fromEntries(formData.entries());

    try {
      const response = await fetch("/api/contact", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
      });

      if (response.ok) {
        status.textContent = "Message sent successfully!";
        status.style.color = "lightgreen";
        form.reset();
      } else {
        status.textContent = "Failed to send message. Please try again.";
        status.style.color = "orange";
      }
    } catch (error) {
      console.error("Error:", error);
      status.textContent = "Network error — please check your connection.";
      status.style.color = "red";
    } finally {
      sending = false;
      if (button) button.removeAttribute("aria-disabled");
    }
  });
});
