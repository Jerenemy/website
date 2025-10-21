document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("contact-form");
  const status = document.getElementById("contact-status");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
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
    }
  });
});
