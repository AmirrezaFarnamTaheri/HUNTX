from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one occurrence, found {count}")
    return text.replace(old, new, 1)


def run(*args: str, cwd: str | None = None) -> None:
    subprocess.run(args, cwd=ROOT / cwd if cwd else ROOT, check=True)


def patch_app() -> None:
    path = "docs/assets/js/app.js"
    app = read(path)

    app = replace_once(
        app,
        'btn.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });',
        'const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;\n            btn.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "nearest", inline: "center" });',
        "reduced motion tab scrolling",
    )

    start = app.index("  renderHeader() {")
    end = app.index("\n  renderHero() {", start)
    header = app[start:end]
    header = replace_once(
        header,
        'class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4"',
        'class="max-w-7xl mx-auto px-2 sm:px-4 lg:px-8 h-16 flex items-center justify-between gap-2 sm:gap-4"',
        "compact header shell",
    )
    header = replace_once(
        header,
        'class="flex items-center gap-3 group focus-ring rounded-xl p-1"',
        'class="flex shrink-0 items-center gap-2 group focus-ring rounded-xl p-1"',
        "compact brand",
    )
    header = replace_once(
        header,
        'class="px-1.5 py-0.5 text-[9px] font-mono font-bold bg-cyan-950/80',
        'class="hidden sm:inline px-1.5 py-0.5 text-[9px] font-mono font-bold bg-cyan-950/80',
        "hide version on narrow phones",
    )
    header = replace_once(
        header,
        'class="flex items-center gap-1.5 sm:gap-2.5"',
        'class="relative shrink-0 flex items-center gap-1 sm:gap-2.5"',
        "header controls container",
    )
    header = header.replace('class="hidden lg:flex items-center gap-2 px-3 py-1.5', 'class="hidden xl:flex items-center gap-2 px-3 py-1.5')
    header = header.replace('class="hidden sm:flex', 'class="hidden 2xl:flex')
    header = replace_once(
        header,
        'class="min-h-[44px] w-[72px] sm:w-[92px]',
        'class="min-h-[44px] w-[64px] sm:w-[92px]',
        "compact locale control",
    )

    menu_markup = '''

          <button
            id="btn-header-tools"
            class="2xl:hidden p-2 min-h-[44px] min-w-[44px] flex items-center justify-center bg-gray-900 hover:bg-gray-800 border border-gray-800 hover:border-cyan-500/40 text-gray-300 hover:text-cyan-300 rounded-xl transition-all focus-ring cursor-pointer"
            title="${i18n.translate("Tools")}"
            aria-label="${i18n.translate("Tools")}"
            aria-haspopup="menu"
            aria-expanded="false"
            aria-controls="header-tools-menu"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"></path></svg>
          </button>

          <div
            id="header-tools-menu"
            class="hidden absolute top-[52px] right-0 z-[70] w-56 p-2 bg-gray-950/98 backdrop-blur-xl border border-gray-700 rounded-2xl shadow-2xl shadow-black/40"
            role="menu"
            aria-label="${i18n.translate("Tools")}"
          >
            <button id="menu-open-scanner" role="menuitem" class="w-full min-h-[44px] px-3 py-2 text-left text-xs font-mono text-emerald-300 hover:bg-gray-900 rounded-xl focus-ring">${i18n.translate("IP Scanner")}</button>
            <button id="menu-open-builder" role="menuitem" class="w-full min-h-[44px] px-3 py-2 text-left text-xs font-mono text-cyan-300 hover:bg-gray-900 rounded-xl focus-ring">${i18n.translate("Sub Builder")}</button>
            <button id="menu-open-decoder" role="menuitem" class="w-full min-h-[44px] px-3 py-2 text-left text-xs font-mono text-gray-200 hover:bg-gray-900 rounded-xl focus-ring">${i18n.translate("Decoder")}</button>
            <a href="architecture.html" target="_blank" role="menuitem" class="flex items-center min-h-[44px] px-3 py-2 text-xs font-mono text-indigo-300 hover:bg-gray-900 rounded-xl focus-ring">${i18n.translate("Architecture")}</a>
            <a href="https://github.com/AmirrezaFarnamTaheri/HUNTX" target="_blank" rel="noopener noreferrer" role="menuitem" class="flex items-center min-h-[44px] px-3 py-2 text-xs font-mono text-gray-300 hover:bg-gray-900 rounded-xl focus-ring">GitHub</a>
          </div>'''
    closing = "        </div>\n      </div>\n    `;"
    header = replace_once(header, closing, menu_markup + "\n" + closing, "mobile tools menu")

    locale_handler = '''    document.getElementById("language-selector")?.addEventListener("change", (event) => {
      i18n.setLocale(event.target.value);
    });'''
    enhanced_handlers = '''    const toolsButton = document.getElementById("btn-header-tools");
    const toolsMenu = document.getElementById("header-tools-menu");
    const setToolsOpen = (open) => {
      if (!toolsButton || !toolsMenu) return;
      const expanded = Boolean(open);
      toolsButton.setAttribute("aria-expanded", expanded ? "true" : "false");
      toolsMenu.classList.toggle("hidden", !expanded);
      if (expanded) toolsMenu.querySelector('[role="menuitem"]')?.focus();
    };
    toolsButton?.addEventListener("click", () => setToolsOpen(toolsButton.getAttribute("aria-expanded") !== "true"));
    header.onkeydown = (event) => {
      if (event.key === "Escape" && toolsButton?.getAttribute("aria-expanded") === "true") {
        setToolsOpen(false);
        toolsButton.focus();
      }
    };
    document.getElementById("menu-open-scanner")?.addEventListener("click", () => {
      this.lastFocusedElement = toolsButton;
      setToolsOpen(false);
      this.openCleanIPScannerModal();
    });
    document.getElementById("menu-open-builder")?.addEventListener("click", () => {
      this.lastFocusedElement = toolsButton;
      setToolsOpen(false);
      this.openSubscriptionBuilderModal();
    });
    document.getElementById("menu-open-decoder")?.addEventListener("click", () => {
      this.lastFocusedElement = toolsButton;
      setToolsOpen(false);
      this.openDecoderModal();
    });
    toolsMenu?.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => setToolsOpen(false)));

    document.getElementById("language-selector")?.addEventListener("change", (event) => {
      i18n.setLocale(event.target.value);
      const selector = document.getElementById("language-selector");
      const localizedLabel = i18n.translate("Language");
      selector?.setAttribute("aria-label", localizedLabel);
      selector?.setAttribute("title", localizedLabel);
      toolsButton?.setAttribute("aria-label", i18n.translate("Tools"));
      toolsButton?.setAttribute("title", i18n.translate("Tools"));
      toolsMenu?.setAttribute("aria-label", i18n.translate("Tools"));
    });'''
    header = replace_once(header, locale_handler, enhanced_handlers, "header menu and locale handlers")
    app = app[:start] + header + app[end:]

    app = app.replace(
        'class="text-gray-400 font-mono truncate max-w-[220px]">${escapeHTML(file.hash.slice(0, 16))}',
        'class="technical-ltr text-gray-400 font-mono truncate max-w-[220px]">${escapeHTML(file.hash.slice(0, 16))}',
    )
    app = app.replace(
        'class="p-4 bg-gray-950 border border-gray-800 rounded-2xl max-h-[300px] overflow-y-auto font-mono text-xs"',
        'class="technical-ltr p-4 bg-gray-950 border border-gray-800 rounded-2xl max-h-[300px] overflow-y-auto font-mono text-xs"',
    )
    write(path, app)


def patch_i18n() -> None:
    path = "docs/assets/js/i18n.js"
    text = read(path)
    additions = {
        "fa": {
            "Tools": "ابزارها",
            "Production feed URL copied to clipboard": "نشانی اشتراک تولیدی در کلیپ‌بورد کپی شد",
            "Portable artifact path copied — deploy or serve over HTTPS before importing": "مسیر بسته کپی شد — پیش از وارد کردن، آن را روی HTTPS منتشر کنید",
            "Failed to copy": "کپی ناموفق بود",
            "No active nodes to copy": "گره فعالی برای کپی وجود ندارد",
            "Please enter proxy URIs to convert": "نشانی‌های پروکسی را برای تبدیل وارد کنید",
            "Batch conversion complete": "تبدیل گروهی کامل شد",
            "Cannot copy invalid JSON": "JSON نامعتبر قابل کپی نیست",
            "Clean IPs exported as CSV": "IPهای پاک به CSV صادر شدند",
            "Clean IPs exported as JSON": "IPهای پاک به JSON صادر شدند",
            "All filters reset": "همه فیلترها بازنشانی شدند",
        },
        "zh-CN": {
            "Tools": "工具",
            "Production feed URL copied to clipboard": "生产订阅地址已复制到剪贴板",
            "Portable artifact path copied — deploy or serve over HTTPS before importing": "已复制便携文件路径——导入前请通过 HTTPS 部署或提供服务",
            "Failed to copy": "复制失败",
            "No active nodes to copy": "没有可复制的活动节点",
            "Please enter proxy URIs to convert": "请输入要转换的代理 URI",
            "Batch conversion complete": "批量转换完成",
            "Cannot copy invalid JSON": "无法复制无效 JSON",
            "Clean IPs exported as CSV": "Clean IP 已导出为 CSV",
            "Clean IPs exported as JSON": "Clean IP 已导出为 JSON",
            "All filters reset": "所有筛选条件已重置",
        },
        "ru": {
            "Tools": "Инструменты",
            "Production feed URL copied to clipboard": "Адрес рабочей подписки скопирован",
            "Portable artifact path copied — deploy or serve over HTTPS before importing": "Путь к артефакту скопирован — перед импортом опубликуйте его по HTTPS",
            "Failed to copy": "Не удалось скопировать",
            "No active nodes to copy": "Нет активных узлов для копирования",
            "Please enter proxy URIs to convert": "Введите URI прокси для преобразования",
            "Batch conversion complete": "Пакетное преобразование завершено",
            "Cannot copy invalid JSON": "Нельзя скопировать некорректный JSON",
            "Clean IPs exported as CSV": "Clean IP экспортированы в CSV",
            "Clean IPs exported as JSON": "Clean IP экспортированы в JSON",
            "All filters reset": "Все фильтры сброшены",
        },
    }
    for locale, mapping in additions.items():
        marker = f'  "{locale}": {{\n' if "-" in locale else f"  {locale}: {{\n"
        payload = "".join(
            f"    {json.dumps(key, ensure_ascii=False)}: {json.dumps(value, ensure_ascii=False)},\n"
            for key, value in mapping.items()
        )
        text = replace_once(text, marker, marker + payload, f"{locale} finish translations")

    dynamic = r'''
    const filteredHubMatch = source.match(/^Filtered by (.+) \(([A-Z]{2})\)$/i);
    if (filteredHubMatch) {
      if (locale === "fa") return `فیلتر بر اساس ${filteredHubMatch[1]} (${filteredHubMatch[2]})`;
      if (locale === "zh-CN") return `已按 ${filteredHubMatch[1]} (${filteredHubMatch[2]}) 筛选`;
      if (locale === "ru") return `Фильтр: ${filteredHubMatch[1]} (${filteredHubMatch[2]})`;
    }
    const filteredOperatorMatch = source.match(/^Filtered proxies for operator:\s*(.+)$/i);
    if (filteredOperatorMatch) {
      if (locale === "fa") return `فیلتر پروکسی‌ها بر اساس اپراتور: ${filteredOperatorMatch[1]}`;
      if (locale === "zh-CN") return `已按运营商筛选代理：${filteredOperatorMatch[1]}`;
      if (locale === "ru") return `Прокси отфильтрованы по оператору: ${filteredOperatorMatch[1]}`;
    }
    const filteredCountryMatch = source.match(/^Filtered proxies for country:\s*(.+)$/i);
    if (filteredCountryMatch) {
      if (locale === "fa") return `فیلتر پروکسی‌ها بر اساس کشور: ${filteredCountryMatch[1]}`;
      if (locale === "zh-CN") return `已按国家筛选代理：${filteredCountryMatch[1]}`;
      if (locale === "ru") return `Прокси отфильтрованы по стране: ${filteredCountryMatch[1]}`;
    }
    const loadedConverterMatch = source.match(/^Loaded\s+(\d+)\s+active nodes into converter$/i);
    if (loadedConverterMatch) {
      if (locale === "fa") return `${loadedConverterMatch[1]} گره در مبدل بارگذاری شد`;
      if (locale === "zh-CN") return `已将 ${loadedConverterMatch[1]} 个节点载入转换器`;
      if (locale === "ru") return `В конвертер загружено узлов: ${loadedConverterMatch[1]}`;
    }
    const dedupMatch = source.match(/^Deduplication complete:\s*(\d+)\s+unique nodes\.$/i);
    if (dedupMatch) {
      if (locale === "fa") return `حذف تکراری‌ها کامل شد: ${dedupMatch[1]} گره یکتا.`;
      if (locale === "zh-CN") return `去重完成：${dedupMatch[1]} 个唯一节点。`;
      if (locale === "ru") return `Дедупликация завершена: ${dedupMatch[1]} уникальных узлов.`;
    }
    const switchedTabMatch = source.match(/^Switched to tab:\s*(.+)$/i);
    if (switchedTabMatch) {
      if (locale === "fa") return `زبانه فعال: ${switchedTabMatch[1]}`;
      if (locale === "zh-CN") return `已切换到标签：${switchedTabMatch[1]}`;
      if (locale === "ru") return `Открыта вкладка: ${switchedTabMatch[1]}`;
    }
    const viewModeMatch = source.match(/^View mode:\s*(.+)$/i);
    if (viewModeMatch) {
      if (locale === "fa") return `حالت نمایش: ${viewModeMatch[1]}`;
      if (locale === "zh-CN") return `视图模式：${viewModeMatch[1]}`;
      if (locale === "ru") return `Режим отображения: ${viewModeMatch[1]}`;
    }
    const failedMatch = source.match(/^(Export|Conversion) failed:\s*(.+)$/i);
    if (failedMatch) {
      if (locale === "fa") return `${failedMatch[1].toLowerCase() === "export" ? "صدور" : "تبدیل"} ناموفق بود: ${failedMatch[2]}`;
      if (locale === "zh-CN") return `${failedMatch[1].toLowerCase() === "export" ? "导出" : "转换"}失败：${failedMatch[2]}`;
      if (locale === "ru") return `${failedMatch[1].toLowerCase() === "export" ? "Экспорт" : "Преобразование"} не выполнено: ${failedMatch[2]}`;
    }
'''
    text = replace_once(text, "    return source;\n  }", dynamic + "    return source;\n  }", "runtime i18n patterns")
    write(path, text)


def patch_delivery() -> None:
    updater_path = "scripts/update_frontend.py"
    updater = read(updater_path)
    updater = updater.replace('  <link rel="preconnect" href="https://fonts.googleapis.com">\n', '')
    updater = updater.replace('  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous">\n', '')
    updater = re.sub(r'  <link href="https://fonts\.googleapis\.com/css2\?[^\n]+\n', '', updater)
    updater = updater.replace("@media (max-width: 639px) {\n      #page-tabs-nav .no-scrollbar", "@media (max-width: 1023px) {\n      #page-tabs-nav .no-scrollbar")
    updater = updater.replace(
        '''    .technical-ltr,
    code,
    pre {''',
        '''    .technical-ltr,
    code,
    pre,
    textarea.font-mono {''',
    )
    write(updater_path, updater)

    config = '''module.exports = {
  darkMode: "class",
  content: [
    "./docs/index.html",
    "./docs/assets/js/**/*.js",
    "./scripts/update_frontend.py"
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "Consolas", "Liberation Mono", "monospace"]
      }
    }
  },
  plugins: []
};
'''
    write("tailwind.config.cjs", config)

    gitignore = read(".gitignore")
    additions = []
    for entry in ("playwright-report/", "test-results/"):
        if entry not in gitignore:
            additions.append(entry)
    if additions:
        gitignore = gitignore.rstrip() + "\n" + "\n".join(additions) + "\n"
        write(".gitignore", gitignore)


def write_browser_tests() -> None:
    write(
        "playwright.config.mjs",
        '''import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: "frontend_browser.spec.mjs",
  timeout: 30_000,
  fullyParallel: false,
  use: {
    baseURL: "http://127.0.0.1:4173",
    headless: true,
    trace: "retain-on-failure"
  },
  webServer: {
    command: "python -m http.server 4173 --directory docs --bind 127.0.0.1",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
    timeout: 15_000
  }
});
''',
    )
    write(
        "tests/frontend_browser.spec.mjs",
        r'''import { test, expect } from "@playwright/test";

async function isolateLocalPage(page) {
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname === "127.0.0.1" || url.hostname === "localhost") {
      await route.continue();
    } else {
      await route.abort();
    }
  });
}

for (const width of [320, 375, 640, 768, 1024, 1280]) {
  test(`header is usable without clipping at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await isolateLocalPage(page);
    await page.goto("/");
    await expect(page.locator("#main-header")).toBeVisible();
    const metrics = await page.locator("#main-header").evaluate((header) => {
      const visible = [...header.querySelectorAll("button, select, a")]
        .filter((el) => {
          const style = getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
        })
        .map((el) => {
          const rect = el.getBoundingClientRect();
          return { left: rect.left, right: rect.right };
        });
      return {
        scrollWidth: header.scrollWidth,
        clientWidth: header.clientWidth,
        minLeft: Math.min(...visible.map((item) => item.left)),
        maxRight: Math.max(...visible.map((item) => item.right))
      };
    });
    expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth + 1);
    expect(metrics.minLeft).toBeGreaterThanOrEqual(-1);
    expect(metrics.maxRight).toBeLessThanOrEqual(width + 1);

    const tools = page.locator("#btn-header-tools");
    await expect(tools).toBeVisible();
    await expect(tools).toHaveAttribute("aria-expanded", "false");
    await tools.click();
    await expect(page.locator("#header-tools-menu")).toBeVisible();
    await expect(tools).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("Escape");
    await expect(page.locator("#header-tools-menu")).toBeHidden();
    await expect(tools).toHaveAttribute("aria-expanded", "false");
  });
}

test("coarse-pointer tablet gets an explicit, stateful globe gate", async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 1024, height: 900 },
    hasTouch: true,
    isMobile: true,
    deviceScaleFactor: 1
  });
  const page = await context.newPage();
  await isolateLocalPage(page);
  await page.goto("/");
  expect(await page.evaluate(() => matchMedia("(any-pointer: coarse)").matches)).toBe(true);
  const gate = page.locator("#globe-touch-gate");
  const button = page.locator("#btn-globe-touch-toggle");
  await expect(gate).toBeVisible();
  await expect(button).toHaveAttribute("aria-pressed", "false");
  await button.click();
  await expect(button).toHaveAttribute("aria-pressed", "true");
  await context.close();
});

test("Persian locale updates semantics while technical data remains LTR", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await isolateLocalPage(page);
  await page.goto("/");
  const selector = page.locator("#language-selector");
  await selector.selectOption("fa");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(selector).toHaveAttribute("aria-label", "زبان");
  await expect(selector).toHaveAttribute("title", "زبان");
  const direction = await page.evaluate(() => {
    const probe = document.createElement("div");
    probe.className = "technical-ltr";
    probe.textContent = "1.2.3.4:443 / abc-def";
    document.body.appendChild(probe);
    return getComputedStyle(probe).direction;
  });
  expect(direction).toBe("ltr");
});

test("mobile tabs expose horizontal scrolling rather than hiding overflow affordance", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await isolateLocalPage(page);
  await page.goto("/");
  const scroller = page.locator("#page-tabs-nav > div");
  const metrics = await scroller.evaluate((el) => ({
    scrollWidth: el.scrollWidth,
    clientWidth: el.clientWidth,
    scrollbarWidth: getComputedStyle(el).scrollbarWidth
  }));
  expect(metrics.scrollWidth).toBeGreaterThan(metrics.clientWidth);
  expect(metrics.scrollbarWidth).not.toBe("none");
  const moved = await scroller.evaluate((el) => {
    el.scrollLeft = el.scrollWidth;
    return el.scrollLeft;
  });
  expect(Math.abs(moved)).toBeGreaterThan(0);
});
''',
    )


def patch_runtime_tests() -> None:
    path = "tests/frontend_runtime.test.mjs"
    text = read(path)
    if "responsive shell is offline-safe" not in text:
        text += r'''

test("responsive shell is offline-safe and respects reduced motion", async () => {
  const fs = await import("node:fs/promises");
  const appSource = await fs.readFile(new URL("../docs/assets/js/app.js", import.meta.url), "utf8");
  const html = await fs.readFile(new URL("../docs/index.html", import.meta.url), "utf8");
  assert.match(appSource, /prefers-reduced-motion: reduce/);
  assert.match(appSource, /btn-header-tools/);
  assert.match(appSource, /aria-expanded/);
  assert.doesNotMatch(html, /fonts\.googleapis\.com|fonts\.gstatic\.com/);
});

test("runtime localization covers dynamic user feedback", async () => {
  const { i18n } = await import("../docs/assets/js/i18n.js");
  assert.notEqual(i18n.translate("Filtered proxies for operator: Example", "fa"), "Filtered proxies for operator: Example");
  assert.notEqual(i18n.translate("Loaded 42 active nodes into converter", "zh-CN"), "Loaded 42 active nodes into converter");
  assert.notEqual(i18n.translate("Deduplication complete: 9 unique nodes.", "ru"), "Deduplication complete: 9 unique nodes.");
});
'''
        write(path, text)


def patch_ci_and_dependabot() -> None:
    path = ".github/workflows/pr-validation.yml"
    workflow = read(path)
    needle = '''          node --experimental-default-type=module --test tests/frontend_runtime.test.mjs
          python scripts/update_frontend.py --check'''
    replacement = '''          node --experimental-default-type=module --test tests/frontend_runtime.test.mjs
          npx playwright install --with-deps chromium
          npx playwright test
          python scripts/update_frontend.py --check'''
    workflow = replace_once(workflow, needle, replacement, "browser CI gate")
    write(path, workflow)

    dep_path = ".github/dependabot.yml"
    dep = read(dep_path)
    if 'package-ecosystem: "npm"' not in dep and "package-ecosystem: npm" not in dep:
        dep = dep.rstrip() + '''

  - package-ecosystem: npm
    directory: "/"
    schedule:
      interval: weekly
      day: monday
      time: "06:30"
      timezone: Europe/Helsinki
    open-pull-requests-limit: 5
'''
        write(dep_path, dep + "\n")


def validate() -> None:
    run("python", "scripts/update_frontend.py")
    run("npm", "install", "--save-dev", "@playwright/test@1.63.0", "--package-lock-only", "--ignore-scripts")
    run("npm", "ci", "--ignore-scripts")
    run("npm", "run", "build:css")
    run("python", "scripts/update_frontend.py", "--check")
    run("node", "--experimental-default-type=module", "--test", "tests/frontend_runtime.test.mjs")
    run("npx", "playwright", "install", "--with-deps", "chromium")
    run("npx", "playwright", "test")
    run("python", "-m", "pytest", "-q", "tests/test_frontend_delivery.py")
    run("go", "test", "-race", "./...")
    run("go", "vet", "./...")
    run("go", "run", "golang.org/x/vuln/cmd/govulncheck@v1.7.0", "./...")
    run("go", "test", "-race", "./...", cwd="src/huntx/connectors/v2ray_collector")
    run("go", "vet", "./...", cwd="src/huntx/connectors/v2ray_collector")
    run("go", "run", "golang.org/x/vuln/cmd/govulncheck@v1.7.0", "./...", cwd="src/huntx/connectors/v2ray_collector")


if __name__ == "__main__":
    patch_app()
    patch_i18n()
    patch_delivery()
    write_browser_tests()
    patch_runtime_tests()
    patch_ci_and_dependabot()
    validate()
