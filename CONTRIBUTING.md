# Contributing to HUNTX

HUNTX is a polyglot repository: a Python ingestion pipeline, a set of Go
command-line tools and agents, and a static dashboard built with Tailwind and
vanilla JavaScript. Each language has its own gate, and a change is only
mergeable when every gate that covers it passes.

## Repository layout

| Path | What lives there |
| --- | --- |
| `src/huntx/` | The Python ingestion, transform, and publish pipeline. |
| `cmd/` | Go binaries: `huntx-engine`, `huntx-daemon`, `huntx-probe`, `huntx-tools`, `huntx-wasm`. |
| `internal/` | Shared Go packages: output verification, release manifests, site generation. |
| `docs/` | The published dashboard. `docs/assets/js/` holds the front-end modules. |
| `scripts/` | Python entry points invoked by the workflows. |
| `tests/` | Pytest suites plus the Node and Playwright front-end tests. |
| `configs/` | Maintainer-curated source lists. |
| `deploy/` | Dockerfiles and the `huntx-fleet` Helm chart. |

`docs/assets/js/data.js` and everything under `docs/artifacts/` are generated
by the pipeline. Do not hand-edit them; change the generator instead.

## Getting set up

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-ci.txt
pip install -e .

npm ci --ignore-scripts
```

Go uses the toolchain declared in `go.mod`; `actions/setup-go` resolves it from
that file and local development should do the same rather than pinning a
different version.

## Running the gates locally

Run the gate for whichever language you touched. Running all of them is never
wrong.

```bash
# Python
python -m black --check src tests scripts
python -m flake8 src/huntx tests scripts
python -m mypy src/huntx
python -m pytest -q -m "not perf"

# Go
gofmt -l .
go vet ./...
go test -race ./...
(cd src/huntx/connectors/v2ray_collector && go vet ./... && go test -race ./...)

# Front-end
npm run build:css
npm run lint
node --experimental-default-type=module --test tests/frontend_runtime.test.mjs
npx playwright test
python scripts/update_frontend.py --check
```

The performance suite is excluded by default. Run it deliberately with
`python -m pytest -m perf` when you change anything on a hot path.

## Coding standards

The authoritative style guides are `conductor/code_styleguides/python.md` and
`conductor/code_styleguides/go.md`. In short:

- **Python** is formatted with Black at a 120-character line length, annotated
  on every public signature, and catches explicit exception types rather than
  bare `except:`. Persistent files are written through
  `src/huntx/utils/atomic.py`.
- **Go** is formatted with `gofmt`, inspects every returned error, and takes
  `context.Context` as the first argument on anything that performs I/O.
- **JavaScript** is linted with ESLint. Every value that originates from an
  ingested configuration must pass through `escapeHTML()` before it reaches
  `innerHTML`. This is the single most important rule in the front-end; a
  proxy name is attacker-controlled text.

## Commits and pull requests

Use Conventional Commit subjects (`fix:`, `feat:`, `docs:`, `build:`,
`refactor:`, `test:`, `chore:`), optionally scoped — `fix(frontend): …`.

A pull request should do one thing. When a change requires a wide mechanical
edit — a reformat, a rename — put that in its own commit so the substantive
change stays reviewable, and add the reformat commit to
`.git-blame-ignore-revs`.

Describe what breaks if the change is wrong. For a pipeline change, say what
happens to a run that is mid-flight when it deploys; HUNTX publishes on a
schedule and a bad run reaches the live site.

## Adding a source

Sources are curated, not crowdsourced. A new source belongs in `configs/` with
a note on why it is trustworthy. Ingestion is deny-by-default: anything that is
not a recognised proxy configuration is discarded at the stream boundary, and
new formats need a decoder, a normalizer, and tests covering malformed input
before they are accepted.

## Security

Do not open a public issue for a vulnerability. Follow `SECURITY.md`.
