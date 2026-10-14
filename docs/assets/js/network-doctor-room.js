/**
 * Network Doctor appearance. The only persisted value is the theme preference;
 * recovery selections and connection parameters are never stored or transmitted.
 */
const root = document.documentElement;
const toggle = document.getElementById("doctor-theme-toggle");
const STORAGE_KEY = "huntx_theme";

function getInitialTheme() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "dark" || stored === "light") return stored;
  } catch {
    // Storage is optional in private browsing and hardened browsers.
  }
  return "dark";
}

function applyTheme(theme) {
  const light = theme === "light";
  root.classList.toggle("light", light);
  root.classList.toggle("dark", !light);
  if (toggle) {
    toggle.setAttribute("aria-pressed", String(light));
    toggle.setAttribute("aria-label", light ? "Switch to dark theme" : "Switch to light theme");
    toggle.textContent = light ? "Dark appearance" : "Light appearance";
  }
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", light ? "#f1f6f8" : "#08121b");
}

applyTheme(getInitialTheme());
toggle?.addEventListener("click", () => {
  const next = root.classList.contains("light") ? "dark" : "light";
  applyTheme(next);
  try { localStorage.setItem(STORAGE_KEY, next); } catch { /* optional preference */ }
});

const principlesToggle = document.getElementById("doctor-principles-toggle");
const principles = document.querySelector(".doctor-principles");
principlesToggle?.addEventListener("click", () => {
  const expanded = principlesToggle.getAttribute("aria-expanded") !== "true";
  principlesToggle.setAttribute("aria-expanded", String(expanded));
  principlesToggle.textContent = expanded ? "Hide details" : "Show details";
  principles?.classList.toggle("is-expanded", expanded);
});
