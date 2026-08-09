# Go Code Style Guide

## Formatting
- **Standard Tooling**: Code must be formatted with `gofmt` or `goimports`.

## Conventions
- **Error Handling**: Explicitly inspect returned errors (`if err != nil`). Never ignore errors quietly.
- **Context Usage**: Pass `context.Context` as first argument for any I/O bound or network function.
- **Concurrency**: Use `sync.WaitGroup` or channels for worker lifecycle management. Avoid unbuffered channels without explicit ownership semantics.
