module.exports = {
  darkMode: "class",
  content: [
    "./docs/index.html",
    // Scan authored UI modules only. Generated data.js and vendored wasm_exec.js
    // can contain arbitrary data tokens (for example "static") that Tailwind
    // mistakes for utility classes, making the checked-in CSS change whenever
    // telemetry changes.
    "./docs/assets/js/app.js",
    "./docs/assets/js/decoder.js",
    "./docs/assets/js/globe.js",
    "./docs/assets/js/i18n.js",
    "./docs/assets/js/qrcode.js",
    "./docs/assets/js/rule-studio.js",
    "./docs/assets/js/telemetry-stream.js",
    "./docs/assets/js/wasm-worker.js",
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
