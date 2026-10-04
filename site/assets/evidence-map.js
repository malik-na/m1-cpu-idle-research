/* Read-only navigation and decoding of the build's pinned evidence data. */
(() => {
  "use strict";
  const root = document.querySelector("#EvidenceMap");
  const dataElement = document.querySelector("script[type='application/json']#evidence-map-data");
  if (!root || !dataElement) return;

  let data;
  try {
    data = JSON.parse(dataElement.textContent);
    const claimFields = ["title", "status", "description", "support", "next", "source"];
    const claimNames = ["native", "command", "software", "physical", "energy"];
    const validClaims = claimNames.every(name => claimFields.every(field => typeof data.claims?.[name]?.[field] === "string"));
    const validWord = /^0x[0-9a-f]{8}$/i.test(data.pcpm?.word);
    const validReads = Number.isInteger(data.pcpm?.reads) && data.pcpm.reads > 0 && data.pcpm.reads <= 10000;
    const validReleased = Number.isInteger(data.pcpm?.guardedReleased) && data.pcpm.guardedReleased >= 0 && data.pcpm.guardedReleased <= data.pcpm.reads;
    const validImage = typeof data.ps3?.deployed === "boolean" && typeof data.ps3?.booted === "boolean";
    const validCap = Number.isInteger(data.ps3?.cap) && data.ps3.cap > 0 && Number.isInteger(data.ps3?.attempts) && data.ps3.attempts > 0;
    if (!validClaims || !validWord || !validReads || !validReleased || !validImage || !validCap) return;
  } catch (_) {
    return;
  }

  const select = selector => root.querySelector(selector);
  const buttons = selector => [...root.querySelectorAll(selector)];
  const write = (selector, value) => {
    const element = select(selector);
    if (element) element.textContent = value;
  };
  const word = Number.parseInt(data.pcpm.word.slice(2), 16);
  const actual = (word >>> 4) & 0xf;
  const desired = word & 0xf;
  const fields = {
    actual: `ACTUAL is bits 7:4. Here ${actual.toString(2).padStart(4, "0")}₂ = ${actual}. This is the decoded numeric field; CPU-slot physical meaning is not calibrated.`,
    desired: `DESIRED is bits 3:0. Here ${desired.toString(2).padStart(4, "0")}₂ = ${desired}. A requested code is not proof of a completed CPU transition.`,
    remaining: "Bits 31:8 are retained in the raw word. Their latch and clear behavior is uncalibrated here; this view assigns no physical meaning to them."
  };
  let selectedNode = "physical";
  let selectedField = "actual";
  let selectedMode = "recorded";

  const bits = select("#map-bits");
  if (bits) {
    const fragment = document.createDocumentFragment();
    for (let bit = 31; bit >= 0; bit--) {
      const cell = document.createElement("span");
      const label = document.createElement("small");
      cell.className = "map-bit";
      cell.dataset.field = bit >= 8 ? "remaining" : bit >= 4 ? "actual" : "desired";
      label.textContent = bit;
      cell.append(String((word >>> bit) & 1), label);
      fragment.append(cell);
    }
    bits.replaceChildren(fragment);
    bits.setAttribute("role", "img");
    bits.setAttribute("aria-label", `32 bits of register word ${data.pcpm.word}`);
  }

  const dots = select("#map-dot-grid");
  if (dots) {
    const fragment = document.createDocumentFragment();
    for (let index = 0; index < data.pcpm.reads; index++) {
      const dot = document.createElement("i");
      dot.title = `Read ${index + 1}: ${data.pcpm.word}`;
      dot.setAttribute("aria-hidden", "true");
      fragment.append(dot);
    }
    dots.replaceChildren(fragment);
    dots.setAttribute("role", "img");
    dots.setAttribute("aria-label", `${data.pcpm.reads} recorded reads, each register word ${data.pcpm.word}`);
  }

  write(".map-word-summary strong", data.pcpm.word);
  write(".map-word-summary > span", `${data.pcpm.reads} successful 32-bit reads · one constant word`);
  write("[data-map-field='actual']", `ACTUAL = ${actual}`);
  write("[data-map-field='desired']", `DESIRED = ${desired}`);
  write(".map-plan-warning .map-result-tag", data.ps3.booted ? "Image booted · consult capture record" : data.ps3.deployed ? "Installed image · unbooted" : "Image not deployed");
  root.dataset.image = data.ps3.booted ? "booted" : data.ps3.deployed ? "installed-unbooted" : "not-deployed";
  root.dataset.sourceCap = String(data.ps3.cap);
  root.dataset.attemptCap = String(data.ps3.attempts);

  const render = () => {
    const claim = data.claims[selectedNode];
    buttons("[data-map-node]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.mapNode === selectedNode)));
    write("#map-node-status", claim.status);
    write("#map-node-title", claim.title);
    write("#map-node-description", claim.description);
    write("#map-node-support", claim.support);
    write("#map-node-next", claim.next);
    const source = select("#map-node-source");
    if (source) source.setAttribute("href", claim.source);
    buttons("[data-map-mode]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.mapMode === selectedMode)));
    const recorded = select(".map-recorded");
    const planned = select(".map-planned");
    if (recorded) recorded.hidden = selectedMode !== "recorded";
    if (planned) planned.hidden = selectedMode !== "planned";
    buttons("[data-map-field]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.mapField === selectedField)));
    buttons(".map-bit").forEach(cell => cell.classList.toggle("is-selected", cell.dataset.field === selectedField));
    write("#map-field-explanation", fields[selectedField]);
    root.dataset.selectedNode = selectedNode;
    root.dataset.selectedField = selectedField;
    root.dataset.mode = selectedMode;
  };

  buttons("[data-map-node]").forEach(button => button.addEventListener("click", () => {
    if (!Object.hasOwn(data.claims, button.dataset.mapNode)) return;
    selectedNode = button.dataset.mapNode;
    render();
  }));
  buttons("[data-map-field]").forEach(button => button.addEventListener("click", () => {
    if (!Object.hasOwn(fields, button.dataset.mapField)) return;
    selectedField = button.dataset.mapField;
    render();
  }));
  buttons("[data-map-mode]").forEach(button => button.addEventListener("click", () => {
    if (!["recorded", "planned"].includes(button.dataset.mapMode)) return;
    selectedMode = button.dataset.mapMode;
    render();
  }));
  render();
})();
