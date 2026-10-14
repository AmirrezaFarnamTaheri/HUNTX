/**
 * HUNTX Control Room: a small progressive enhancement over the existing
 * tabbed application. No client data, subscriptions or secrets are persisted.
 *
 * Keep workspace semantics separate from the telemetry renderer so navigation
 * can evolve without changing proxy parsing, validation or publishing.
 */
const entries = {
  radar: {
    title: "Network overview",
    description: "Understand what was published, what was actually measured, and where evidence is still missing.",
    action: { label: "Browse proxies", type: "tab", target: "proxies" }
  },
  proxies: {
    title: "Explore published proxies",
    description: "Compare published proxy candidates by protocol, region and recorded evidence. Verify connectivity through your client on this network.",
    action: { label: "View published feeds", type: "tab", target: "artifacts" }
  },
  studio: {
    title: "Build a subscription",
    description: "Configure and export client-ready routing profiles without changing the source endpoints.",
    action: { label: "Inspect a configuration", type: "tab", target: "decoder" }
  },
  decoder: {
    title: "Inspect a configuration",
    description: "Decode and review connection parameters locally before importing them into your client.",
    action: { label: "View published feeds", type: "tab", target: "artifacts" }
  },
  artifacts: {
    title: "Published feeds",
    description: "Find generated subscriptions and inspect their publication metadata. Artifact integrity is not proof of live connectivity.",
    action: { label: "Browse proxies", type: "tab", target: "proxies" }
  }
};

export const WORKSPACES = Object.freeze(Object.fromEntries(
  Object.entries(entries).map(([key, value]) => [key, Object.freeze({
    ...value, action: Object.freeze(value.action)
  })])
));

export function resolveWorkspace(value) {
  return Object.hasOwn(WORKSPACES, value) ? WORKSPACES[value] : WORKSPACES.radar;
}

// Keep navigation text genuinely localizable instead of changing only <html dir>.
const translations = {
  fa: {
    radar: ["نمای کلی شبکه", "ببینید چه چیزهایی منتشر شده، چه مواردی واقعاً اندازه‌گیری شده و کجا هنوز شواهد کافی نداریم.", "مرور پروکسی‌ها"],
    proxies: ["مرور پروکسی‌های منتشرشده", "پروکسی‌های منتشرشده را بر اساس پروتکل، منطقه و شواهد ثبت‌شده بررسی کنید. اتصال در شبکه شما فقط با آزمایش در کلاینت مشخص می‌شود.", "مشاهده اشتراک‌ها"],
    studio: ["ساخت اشتراک", "پروفایل‌های مسیریابی قابل استفاده در کلاینت را بدون تغییر سرورهای اصلی بسازید و خروجی بگیرید.", "بررسی پیکربندی"],
    decoder: ["بررسی پیکربندی", "پیش از وارد کردن به کلاینت، پارامترهای اتصال را به‌صورت محلی بازبینی کنید.", "مشاهده اشتراک‌ها"],
    artifacts: ["فیدهای منتشرشده", "اشتراک‌های تولیدشده و اطلاعات انتشار را ببینید. سلامت فایل به معنی اتصال زنده نیست.", "مرور پروکسی‌ها"],
    shell: ["HUNTX / فضای کار", "ابزار بازیابی شبکه", "فضای کار", "داده‌ها و ابزارهای اتصال، در یک نمای متمرکز"]
  },
  "zh-CN": {
    radar: ["网络概览", "查看已发布的数据、实际测量的结果，以及尚缺少证据的部分。", "浏览代理"],
    proxies: ["浏览已发布代理", "按协议、地区和已记录的检测结果比较已发布的代理节点。是否能在当前网络使用，仍需在客户端测试。", "查看订阅源"],
    studio: ["创建订阅", "在不修改原始节点的前提下配置并导出客户端路由配置。", "检查配置"],
    decoder: ["检查配置", "导入客户端之前，在本地解码并检查连接参数。", "查看订阅源"],
    artifacts: ["已发布订阅源", "查找生成的订阅和发布元数据。文件完整性不能证明实时连接可用。", "浏览代理"],
    shell: ["HUNTX / 工作区", "网络修复工具", "工作区", "集中查看连接数据与工具"]
  },
  ru: {
    radar: ["Обзор сети", "Узнайте, что опубликовано, что действительно измерено и где пока нет подтверждений.", "Смотреть прокси"],
    proxies: ["Обзор опубликованных прокси", "Сравнивайте опубликованные узлы по протоколу, региону и зафиксированным проверкам. Доступность в вашей сети нужно проверить в клиенте.", "Смотреть подписки"],
    studio: ["Создать подписку", "Настраивайте и экспортируйте профили маршрутизации без изменения исходных узлов.", "Проверить конфигурацию"],
    decoder: ["Проверить конфигурацию", "Локально проверьте параметры подключения перед импортом в клиент.", "Смотреть подписки"],
    artifacts: ["Опубликованные подписки", "Изучайте созданные подписки и метаданные публикации. Целостность файла не гарантирует подключение.", "Смотреть прокси"],
    shell: ["HUNTX / рабочая область", "Диагностика сети", "Рабочая область", "Данные и инструменты подключения в одном месте"]
  }
};

function currentLocale(root) {
  const selected = root.getElementById("language-selector")?.value;
  const htmlLang = root.documentElement?.lang;
  const value = selected || htmlLang || "en";
  return Object.hasOwn(translations, value) ? value : "en";
}

function activeWorkspace(root) {
  const selected = root.querySelector('.nav-tab-btn[aria-selected="true"]');
  if (selected?.dataset?.tabTarget) return selected.dataset.tabTarget;
  const hash = root.defaultView?.location?.hash?.slice(1) || "radar";
  return Object.hasOwn(WORKSPACES, hash) ? hash : "radar";
}

export function syncWorkspace(root = document) {
  const key = activeWorkspace(root);
  const workspace = resolveWorkspace(key);
  const locale = currentLocale(root);
  const localized = translations[locale]?.[key];
  const shell = translations[locale]?.shell;
  const title = root.getElementById("workspace-title");
  const description = root.getElementById("workspace-description");
  const path = root.getElementById("workspace-path");
  const action = root.getElementById("workspace-action");
  const intro = root.querySelector(".rail-intro");
  const doctor = root.querySelector('#page-tabs-nav a[href="network-doctor.html"]');
  if (title) title.textContent = localized?.[0] || workspace.title;
  if (description) description.textContent = localized?.[1] || workspace.description;
  if (path) path.textContent = shell?.[0] || "HUNTX / Workspace";
  if (action) {
    action.textContent = localized?.[2] || workspace.action.label;
    action.dataset.workspaceTarget = workspace.action.target;
  }
  if (doctor) doctor.textContent = shell?.[1] || "Fix connection";
  if (intro) {
    const heading = intro.querySelector("strong");
    const caption = intro.querySelector("p");
    if (heading) heading.textContent = shell?.[2] || "Workspaces";
    if (caption) caption.textContent = shell?.[3] || "Connection data and tools, together.";
  }
  return key;
}

export function mountControlRoom(root = document) {
  const nav = root.getElementById("page-tabs-nav");
  if (!nav || !root.getElementById("workspace-masthead")) return () => {};
  const view = root.defaultView;
  let queued = false;
  const scheduleSync = () => {
    if (queued) return;
    queued = true;
    queueMicrotask(() => {
      queued = false;
      syncWorkspace(root);
    });
  };
  const onClick = (event) => {
    const action = event.target.closest?.("[data-workspace-target]");
    if (!action) return;
    const target = action.dataset.workspaceTarget;
    if (!Object.hasOwn(WORKSPACES, target)) return;
    const button = nav.querySelector(`.nav-tab-btn[data-tab-target="${target}"]`);
    if (button) {
      button.click();
      button.focus({ preventScroll: true });
    }
  };
  const onChange = (event) => {
    if (event.target?.id === "language-selector") scheduleSync();
  };
  const observer = new MutationObserver(scheduleSync);
  observer.observe(nav, { subtree: true, attributes: true, attributeFilter: ["aria-selected"] });
  root.addEventListener("click", onClick);
  root.addEventListener("change", onChange);
  view?.addEventListener("hashchange", scheduleSync);
  scheduleSync();
  return () => {
    observer.disconnect();
    root.removeEventListener("click", onClick);
    root.removeEventListener("change", onChange);
    view?.removeEventListener("hashchange", scheduleSync);
  };
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => mountControlRoom(), { once: true });
  } else {
    mountControlRoom();
  }
}
