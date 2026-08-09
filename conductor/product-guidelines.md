# Product Guidelines: HuntX

## Tone & Voice
- **Technical & Concise**: Direct, informative CLI output and log messaging without unnecessary fluff.
- **Security-Conscious & Trustworthy**: Clear explanations of security boundaries, APK rejection policies, and secret redaction.
- **Helpful & Responsive**: User-facing GatherX bot messages are clear, friendly, and actionable with explicit command hints.

## UX & Interaction Principles
- **Command-Driven Simplicity**: Telegram bot interactions rely on intuitive slash commands (`/start`, `/get`, `/status`, `/help`).
- **Resilient Feedback**: Long-running operations provide immediate progress feedback and clear error recovery paths.
- **Clean Documentation**: Code comments, CLI help screens, and README documentation follow concise Markdown standards with clear usage examples.

## Quality Standards
- **Strict Linting & Formatting**: Adherence to PEP 8, Black (120 line length limit), and Flake8 standards.
- **Type Safety**: Mypy static type checking enforced across all core modules.
- **Test Coverage**: Pytest suite for every format parser, pipeline stage, state mutation, and bot handler.
