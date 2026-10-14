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

function setRecoveryStep(step) {
  document.querySelectorAll(".doctor-steps [data-step]").forEach((item) => {
    if (Number(item.dataset.step) === step) item.setAttribute("aria-current", "step");
    else item.removeAttribute("aria-current");
  });
}

function choices() {
  return {
    platform: byId("doctor-platform").value,
    network: byId("doctor-network").value,
    symptom: byId("doctor-symptom").value
  };
}

function invalidateCatalogCheck() {
  catalogRequestVersion += 1;
  catalogButton.disabled = false;
  catalogButton.removeAttribute("aria-busy");
  catalogStatus.dataset.freshness = "unknown";
  catalogStatus.textContent =
    "Not checked. This verifies published metadata only, not proxy connectivity.";
}

function clearReportedOutcome() {
  byId("doctor-original").value = "unknown";
  byId("doctor-alternative").value = "unknown";
  byId("doctor-tls-disabled").checked = false;
  resultPanel.classList.add("hidden");
  byId("doctor-copy").textContent = "Copy summary";
}

form.addEventListener("change", () => {
  // A changed setup invalidates the old plan and any claimed result.
  if (planPanel.classList.contains("hidden")) return;
  planPanel.classList.add("hidden");
  outcomePanel.classList.add("hidden");
  clearReportedOutcome();
  invalidateCatalogCheck();
  setRecoveryStep(1);
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
  clearReportedOutcome();
  invalidateCatalogCheck();
  planPanel.classList.remove("hidden");
  outcomePanel.classList.remove("hidden");
  setRecoveryStep(2);
  planPanel.scrollIntoView({ behavior: "instant", block: "start" });
  byId("plan-heading")?.focus({ preventScroll: true });
});

catalogButton.addEventListener("click", async () => {
  const requestVersion = ++catalogRequestVersion;
  catalogButton.disabled = true;
  catalogButton.setAttribute("aria-busy", "true");
  catalogStatus.dataset.freshness = "unknown";
  catalogStatus.textContent = "Checking catalog snapshot metadata…";
  try {
    const result = await checkPublishedCatalog();
    if (requestVersion !== catalogRequestVersion) return;
    catalogStatus.dataset.freshness = result.freshness || "unknown";
    catalogStatus.textContent = result.message +
      (result.generatedAt ? " Snapshot: " + result.generatedAt : "");
  } catch {
    if (requestVersion === catalogRequestVersion) {
      catalogStatus.textContent = "Catalog check failed. Proxy connectivity is unknown.";
    }
  } finally {
    if (requestVersion === catalogRequestVersion) {
      catalogButton.disabled = false;
      catalogButton.removeAttribute("aria-busy");
    }
  }
});

outcomePanel.addEventListener("change", () => {
  // Never leave a visible result after its underlying self-report changed.
  resultPanel.classList.add("hidden");
  byId("doctor-copy").textContent = "Copy summary";
  setRecoveryStep(2);
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
  byId("doctor-copy").textContent = "Copy summary";
  resultPanel.classList.remove("hidden");
  setRecoveryStep(3);
  byId("doctor-result-title")?.focus({ preventScroll: true });
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
  clearReportedOutcome();
  invalidateCatalogCheck();
  planPanel.classList.add("hidden");
  outcomePanel.classList.add("hidden");
  setRecoveryStep(1);
  form.scrollIntoView({ behavior: "instant", block: "start" });
  byId("doctor-platform")?.focus({ preventScroll: true });
});
