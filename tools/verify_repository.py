#!/usr/bin/env python3
"""Check published research links, file hashes, and trace aggregation."""

import hashlib
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify_links():
    broken = []
    for page in ROOT.rglob("*.md"):
        if ".git" in page.parts:
            continue
        for target in re.findall(r"\]\(([^)]+)\)", page.read_text()):
            if target.startswith(("http:", "https:", "mailto:", "#")):
                continue
            target = target.split("#", 1)[0]
            if target and not (page.parent / target).exists():
                broken.append(f"{page.relative_to(ROOT)} -> {target}")
    if broken:
        raise AssertionError("broken local Markdown links:\n" + "\n".join(broken))


def verify_manifest():
    manifest = ROOT / "MANIFEST.sha256"
    listed = set()
    for line in manifest.read_text().splitlines():
        digest, relative = line.split("  ", 1)
        path = ROOT / relative
        if not path.is_file():
            raise AssertionError(f"manifest file missing: {relative}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            raise AssertionError(f"manifest hash mismatch: {relative}")
        listed.add(relative)
    actual_files = {
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*")
        if path.is_file() and ".git" not in path.parts and path != manifest
        and "__pycache__" not in path.parts and not path.name.endswith(".pyc")
    }
    if listed != actual_files:
        raise AssertionError(f"manifest set mismatch: missing={sorted(actual_files-listed)}, extra={sorted(listed-actual_files)}")


def verify_trace():
    script = ROOT / "notes/tools/analyze-ktrace.py"
    spec = importlib.util.spec_from_file_location("analyze_ktrace", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    actual = module.analyze(ROOT / "notes/raw/ktrace/idle-5s-events.jsonl.gz")
    saved = json.loads((ROOT / "notes/raw/ktrace/idle-5s-summary.json").read_text())
    keys = (
        "event_counts", "matched_idle_callback_pairs", "anomalies",
        "entry_callback_timing_by_cluster_and_peer_state",
        "entry_callback_timing_by_cpu_and_peer_state", "span_ns",
    )
    for key in keys:
        if actual[key] != saved[key]:
            raise AssertionError(f"public trace does not reproduce {key}")


def main():
    verify_links()
    verify_manifest()
    verify_trace()
    print("links, manifest, and public trace summary: OK")


if __name__ == "__main__":
    main()
