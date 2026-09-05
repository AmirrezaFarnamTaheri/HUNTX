module.exports = {
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
