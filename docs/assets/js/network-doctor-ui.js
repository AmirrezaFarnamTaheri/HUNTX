import {
  createRecoveryPlan,
  classifyManualOutcome,
  formatSupportSummary,
  checkPublishedCatalog
} from "./network-doctor.js";

const byId = (id) => document.getElementById(id);
const form = byId("network-doctor-form");
const planPanel = byId("doctor-plan");
const outcomePanel = byId("doctor-outcome-form");
const resultPanel = byId("doctor-result");
const catalogButton = byId("doctor-catalog-check");
const catalogStatus = byId("doctor-catalog-status");
let catalogRequestVersion = 0;

function choices() {
  return {
    platform: byId("doctor-platform").value,
    network: byId("doctor-network").value,
    symptom: byId("doctor-symptom").value
  };
}

function invalidateCatalog() {
  catalogRequestVersion += 1;
  catalogButton.disabled = false;
  catalogButton.removeAttribute("aria-busy");
  catalogStatus.textContent =
    "Not checked. This verifies published metadata only, not proxy connectivity.";
}

function invalidateResult({ resetAnswers = false } = {}) {
  resultPanel.classList.add("hidden");
  byId("doctor-result-title").textContent = "";
  byId("doctor-result-detail").textContent = "";
  byId("doctor-report").value = "";
  byId("doctor-copy").textContent = "Copy summary";
  if (resetAnswers) {
    byId("doctor-original").value = "unknown";
    byId("doctor-alternative").value = "unknown";
    byId("doctor-tls-disabled").checked = false;
  }
}

form.addEventListener("change", () => {
  if (planPanel.classList.contains("hidden")) return;
  planPanel.classList.add("hidden");
  outcomePanel.classList.add("hidden");
  invalidateResult({ resetAnswers: true });
  invalidateCatalog();
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const plan = createRecoveryPlan(choices());
  byId("doctor-device-hint").textContent = plan.deviceHint;
  const list = byId("doctor-actions");
  list.replaceChildren();
  for (const step of plan.actions) {
    const li = document.createElement("li");
    const strong = document.createElement("strong");
    const description = document.createElement("p");
    strong.textContent = step.title;
    description.textContent = step.description;
    li.append(strong, description);
    list.append(li);
  }
  byId("doctor-safety").textContent = plan.safety;
  invalidateResult({ resetAnswers: true });
  invalidateCatalog();
  planPanel.classList.remove("hidden");
  outcomePanel.classList.remove("hidden");
  planPanel.scrollIntoView({ behavior: "instant", block: "start" });
});

catalogButton.addEventListener("click", async () => {
  const version = ++catalogRequestVersion;
  catalogButton.disabled = true;
  catalogButton.setAttribute("aria-busy", "true");
  catalogStatus.textContent = "Checking published catalog metadata…";
  try {
    const result = await checkPublishedCatalog();
    if (version !== catalogRequestVersion) return;
    catalogStatus.textContent = result.message +
      (result.generatedAt ? " Snapshot: " + result.generatedAt : "");
  } finally {
    if (version === catalogRequestVersion) {
      catalogButton.disabled = false;
      catalogButton.removeAttribute("aria-busy");
    }
  }
});

outcomePanel.addEventListener("change", () => {
  // A changed TLS setting or answer invalidates a previous success immediately.
  invalidateResult();
});

byId("doctor-summarize").addEventListener("click", () => {
  const selections = {
    ...choices(),
    originalWorks: byId("doctor-original").value,
    alternativeWorks: byId("doctor-alternative").value,
    tlsVerificationDisabled: byId("doctor-tls-disabled").checked
  };
  const result = classifyManualOutcome(selections);
  const titles = {
    unsafe: "Unsafe change — restore protection",
    "reported-original": "Original proxy appears restored",
    "reported-alternative": "A replacement appears to work",
    unresolved: "No recovery confirmed"
  };
  byId("doctor-result-title").textContent = titles[result.code];
  byId("doctor-result-detail").textContent =
    result.message + " No independent protocol-native test has been run by this page.";
  byId("doctor-report").value = formatSupportSummary(selections);
  resultPanel.classList.remove("hidden");
});

byId("doctor-copy").addEventListener("click", async () => {
  const report = byId("doctor-report");
  try {
    await navigator.clipboard.writeText(report.value);
    byId("doctor-copy").textContent = "Copied";
  } catch {
    report.focus();
    report.select();
    byId("doctor-copy").textContent = "Select and copy summary";
  }
});

byId("doctor-reset").addEventListener("click", () => {
  form.reset();
  invalidateResult({ resetAnswers: true });
  invalidateCatalog();
  planPanel.classList.add("hidden");
  outcomePanel.classList.add("hidden");
  form.scrollIntoView({ behavior: "instant", block: "start" });
});
