(() => {
  "use strict";
  const field = document.querySelector("#search");
  if (field) {
    const entries = [...document.querySelectorAll(".library-entry")];
    const counter = document.querySelector("#search-count");
    const empty = document.querySelector("#empty-results");
    const buttons = [...document.querySelectorAll(".filters button")];
    let category = "all";
    const refresh = () => {
      const terms = field.value.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
      let shown = 0;
      entries.forEach(entry => {
        const match = (category === "all" || entry.dataset.category === category) && terms.every(term => entry.dataset.search.includes(term));
        entry.hidden = !match;
        if (match) shown++;
      });
      counter.textContent = `${shown} of ${entries.length} documents`;
      empty.hidden = shown !== 0;
    };
    buttons.forEach(button => button.addEventListener("click", () => {
      category = button.dataset.filter;
      buttons.forEach(item => item.setAttribute("aria-pressed", String(item === button)));
      refresh();
    }));
    field.addEventListener("input", refresh);
    const params = new URLSearchParams(location.search);
    field.value = params.get("q") || "";
    const selected = buttons.find(button => button.dataset.filter === params.get("category"));
    if (selected) selected.click(); else refresh();
  }
  const copy = document.querySelector("#copy-handoff");
  if (copy) copy.addEventListener("click", async () => {
    const prompt = document.querySelector("#agent-prompt").textContent;
    const status = document.querySelector("#copy-status");
    try {
      await navigator.clipboard.writeText(prompt);
      status.textContent = "Handoff copied.";
    } catch (_) {
      status.textContent = "Select the handoff text above and copy it.";
    }
  });
})();
