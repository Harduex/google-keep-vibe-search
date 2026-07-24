#!/usr/bin/env python3
"""Validate a wave/lane plan's two structural invariants before agents execute it.

1. OVERLAP  -- no two lanes in the same wave own the same path. An overlap means two
               concurrent agents can write the same file, which lane ownership exists
               to prevent. This is a plan bug, not something agents should negotiate.
2. COVERAGE -- every requirement id is referenced by the plan. An unreferenced id is
               work nobody owns; it will be silently dropped.

Both assume the table conventions this skill prescribes:
  - an ownership matrix whose rows start `| <wave-number> | <lane> | <paths> |`, with
    every owned path wrapped in backticks
  - requirement ids matching --id-pattern, found in the requirement source files

Usage:
    check-lane-plan.py PLAN.md [--requirements GLOB ...] [--id-pattern REGEX]
                               [--plan-files GLOB ...]

PLAN.md is the master index -- the ownership matrix is parsed from it. Coverage, though,
is satisfied by the plan as a WHOLE: a requirement is commonly referenced only in the
per-wave spec that implements it. Pass --plan-files for the full set, or the check will
report ids as unowned when they are merely documented elsewhere.

Exit 0 = both invariants hold. Exit 1 = a violation. Exit 2 = nothing parsed (wrong
file, or the tables do not match the expected shape -- do not read that as a pass).
"""

from __future__ import annotations

import argparse
import collections
import glob as globmod
import re
import sys


def parse_ownership(plan_text: str) -> tuple[dict[str, dict[str, set[str]]], list[str]]:
    """({wave: {lane: {paths}}}, unenforceable) from the ownership matrix rows.

    A row whose Owns cell has prose but no backticked path is reported, never skipped
    silently -- prose like "everything (formatting only)" is not an enforceable write set,
    and quietly ignoring it makes the overlap count look better than it is.
    """
    waves: dict[str, dict[str, set[str]]] = collections.defaultdict(dict)
    unenforceable: list[str] = []
    in_matrix = False
    for line in plan_text.splitlines():
        # Anchor to the table whose header declares an Owns column. Other tables in a plan
        # (a status table, a task index) share the "| <number> | ..." shape, and matching
        # those produced confident nonsense.
        if line.lstrip().startswith("|") and re.search(r"\|\s*owns\s*\|", line, re.I):
            in_matrix = True
            continue
        if in_matrix and not line.lstrip().startswith("|"):
            in_matrix = False
        if not in_matrix or not re.match(r"^\|\s*\d+\s*\|", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        wave, lane = cells[0], re.sub(r"\*+", "", cells[1]).strip()
        paths = set(re.findall(r"`([^`]+)`", cells[2]))
        if not paths:
            if cells[2]:
                unenforceable.append(f"wave {wave} lane {lane or '—'}: {cells[2][:60]!r}")
            continue
        waves[wave].setdefault(lane or "—", set()).update(paths)
    return waves, unenforceable


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("plan")
    p.add_argument("--requirements", nargs="*", default=[], help="globs of requirement files")
    p.add_argument("--id-pattern", default=r"[A-Z]{1,2}\d{1,3}", help="requirement id regex")
    p.add_argument(
        "--plan-files",
        nargs="*",
        default=[],
        help="globs for the whole plan (master index + wave specs) searched for coverage",
    )
    args = p.parse_args()

    matrix_text = open(args.plan, encoding="utf-8").read()
    waves, unenforceable = parse_ownership(matrix_text)

    plan_files = sorted({f for g in args.plan_files for f in globmod.glob(g)} | {args.plan})
    plan_text = "".join(open(f, encoding="utf-8").read() for f in plan_files)

    failures = 0
    print(f"plan: {args.plan}")

    if not waves:
        print("!! no ownership rows parsed -- check the table shape before trusting this")
        return 2
    print(f"waves parsed: {len(waves)}  lanes: {sum(len(v) for v in waves.values())}")

    for row in unenforceable:
        print(f"  x write set is prose, not a path list -- not enforceable: {row}")
    failures += len(unenforceable)

    for wave in sorted(waves, key=lambda w: int(w)):
        owner_of: dict[str, str] = {}
        for lane, paths in waves[wave].items():
            for path in paths:
                if path in owner_of and owner_of[path] != lane:
                    print(f"  x wave {wave}: {path} owned by both {owner_of[path]} and {lane}")
                    failures += 1
                owner_of[path] = lane
    print(f"overlaps: {failures}")

    if args.requirements:
        files = [f for g in args.requirements for f in globmod.glob(g)]
        if not files:
            print("!! --requirements matched no files")
            return 2
        text = "".join(open(f, encoding="utf-8").read() for f in files)
        ids = set(re.findall(rf"^\|\s*({args.id_pattern})\s*\|", text, re.M))
        if not ids:
            print(f"!! no ids matching /{args.id_pattern}/ in {len(files)} requirement file(s)")
            return 2
        unowned = sorted(i for i in ids if not re.search(rf"\b{re.escape(i)}\b", plan_text))
        print(
            f"requirements: {len(ids)} in {len(files)} file(s) | "
            f"searched {len(plan_files)} plan file(s) | unowned: {unowned or 'none'}"
        )
        failures += len(unowned)

    print("\nOK -- invariants hold." if not failures else f"\nFAIL -- {failures} violation(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
