## What this changes

<!-- One paragraph. What behaviour is different after this merges? -->

## Why

<!-- The problem being solved. Link the issue if there is one. -->

## Blast radius

<!-- HUNTX publishes to a live site on a schedule. What happens to a run that is
     mid-flight when this deploys? What does a bad version of this change break? -->

## Gates

<!-- Tick the gates you ran locally. CI runs all of them regardless. -->

- [ ] `python -m black --check src tests scripts`
- [ ] `python -m flake8 src/huntx tests scripts`
- [ ] `python -m mypy src/huntx`
- [ ] `python -m pytest -q -m "not perf"`
- [ ] `gofmt -l .` / `go vet ./...` / `go test -race ./...`
- [ ] `npm run lint` and the front-end tests
- [ ] Not applicable — this change touches none of the above

## Notes for the reviewer

<!-- Anything that is deliberate and would otherwise look wrong. -->
