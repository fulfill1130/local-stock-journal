const navItems = Array.from(document.querySelectorAll("[data-section-target]"));
const sections = Array.from(document.querySelectorAll("[data-section]"));
const sectionTitle = document.querySelector("#section-title");

function showSection(sectionId) {
  for (const item of navItems) {
    const isActive = item.dataset.sectionTarget === sectionId;
    item.classList.toggle("active", isActive);
    item.setAttribute("aria-current", isActive ? "page" : "false");
  }

  for (const section of sections) {
    const isActive = section.dataset.section === sectionId;
    section.hidden = !isActive;
    section.classList.toggle("active", isActive);
  }

  const activeItem = navItems.find((item) => item.dataset.sectionTarget === sectionId);
  if (activeItem && sectionTitle) {
    sectionTitle.textContent = activeItem.textContent.trim();
  }
}

for (const item of navItems) {
  item.addEventListener("click", () => {
    showSection(item.dataset.sectionTarget);
  });
}

showSection("overview");
