#!/usr/bin/env python3
"""Assemble the generated-only branch payload from verified HUNTX artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    shutil.copytree(src, dst, dirs_exist_ok=True)


def first_dir(root: Path, name: str) -> Path | None:
    for path in [root / name, *root.rglob(name)]:
        if path.is_dir():
            return path
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint-root', type=Path, required=True)
    parser.add_argument('--dist-root', type=Path, required=True)
    parser.add_argument('--logs-root', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--run-attempt', required=True)
    parser.add_argument('--head-sha', required=True)
    parser.add_argument('--head-branch', required=True)
    parser.add_argument('--source-created-at', required=True)
    args = parser.parse_args()

    args.destination.mkdir(parents=True, exist_ok=True)
    dist = first_dir(args.dist_root, 'dist') or args.dist_root
    outputs = first_dir(args.checkpoint_root, 'outputs')
    outputs_dev = first_dir(args.checkpoint_root, 'outputs_dev')

    copy_tree(dist, args.destination / 'dist')
    if outputs:
        copy_tree(outputs, args.destination / 'outputs')
    if outputs_dev:
        copy_tree(outputs_dev, args.destination / 'outputs_dev')

    logs = first_dir(args.logs_root, 'logs') or args.logs_root
    summary = next(logs.rglob('run-summary.json'), None)
    if summary:
        (args.destination / 'run-summary').mkdir(exist_ok=True)
        shutil.copy2(summary, args.destination / 'run-summary' / 'run-summary.json')

    manifests = args.destination / 'manifests'
    manifests.mkdir(exist_ok=True)
    payload = {
        'schema_version': 1,
        'source_run_id': args.run_id,
        'source_run_attempt': int(args.run_attempt),
        'source_commit': args.head_sha,
        'source_branch': args.head_branch,
        'source_created_at': args.source_created_at,
    }
    (manifests / 'publication.json').write_text(json.dumps(payload, indent=2) + '\n')

    digest = hashlib.sha256()
    for path in sorted(args.destination.rglob('*')):
        if path.is_file():
            digest.update(str(path.relative_to(args.destination)).encode())
            digest.update(path.read_bytes())
    (manifests / 'SHA256SUMS').write_text(digest.hexdigest() + '\n')
    (args.destination / 'README.md').write_text(
        '# HUNTX generated outputs\n\nGenerated-only data plane snapshot. Do not edit manually.\n'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
