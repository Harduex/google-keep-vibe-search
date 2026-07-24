#!/usr/bin/env python3
"""Prove a "formatting only" / "comments only" claim: executable code must be unchanged.

Compares every changed Python file against a git ref by parsing both sides to an AST and
comparing. Docstrings are blanked first, because docstrings ARE AST nodes -- a naive
ast.dump comparison fails on a legitimate docstring rewrite and tempts an agent to either
skip docstrings or loosen the check.

Usage:
    assert-code-unchanged.py [--base REF] [--head REF] [PATH ...]

    --base REF   git ref to compare against (default: HEAD)
    --head REF   compare that ref instead of the working tree -- use this to audit an
                 already-committed change, e.g. --base <sha>~1 --head <sha>
    PATH         limit to these paths (default: whole repo)

Exit 0 = executable code identical. Exit 1 = a real code change. Exit 2 = cannot verify.
Non-Python changes are listed as unchecked -- cover those with a typecheck/test run.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"git {' '.join(args)} failed: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return r.stdout


def show_or_none(ref: str, path: str) -> str | None:
    """File content at `ref`, or None if it did not exist there (added since)."""
    r = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def blank_docstrings(tree: ast.AST) -> ast.AST:
    """Set every docstring to '' so only executable structure remains."""
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        body = getattr(node, "body", None)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body[0].value.value = ""
    return tree


def normalized(source: str, allow_import_reorder: bool = False) -> str:
    tree = blank_docstrings(ast.parse(source))
    if not allow_import_reorder:
        return ast.dump(tree)
    # An import-sorter (isort et al.) reorders module-level imports, which IS a real AST
    # change. Sort those nodes so a formatter sweep passes -- but only when explicitly
    # asked, because a comments-only sweep must never move an import.
    imports, rest = [], []
    for node in tree.body:
        (imports if isinstance(node, (ast.Import, ast.ImportFrom)) else rest).append(node)
    return " ".join(sorted(ast.dump(n) for n in imports) + [ast.dump(n) for n in rest])


def main() -> int:
    p = argparse.ArgumentParser(add_help=True)
    p.add_argument("--base", default="HEAD", help="git ref to compare against")
    p.add_argument("--head", default=None, help="ref to compare instead of the working tree")
    p.add_argument(
        "--allow-import-reorder",
        action="store_true",
        help="tolerate module-level import reordering (use for a black+isort formatting "
        "sweep; NEVER for a comments-only sweep, which must not move imports)",
    )
    p.add_argument("paths", nargs="*", default=None)
    args = p.parse_args()
    paths = args.paths or []

    if args.head:
        changed = git("diff", "--name-only", args.base, args.head, "--", *paths).split()
        untracked: list[str] = []
    else:
        changed = git("diff", "--name-only", args.base, "--", *paths).split()
        untracked = git("ls-files", "--others", "--exclude-standard", "--", *paths).split()

    py_changed = sorted(f for f in changed if f.endswith(".py"))
    py_added = sorted(f for f in untracked if f.endswith(".py"))
    other = sorted(f for f in changed + untracked if not f.endswith(".py"))

    code_changed: list[str] = []
    unverifiable: list[str] = []

    for f in py_changed:
        old = show_or_none(args.base, f)
        if old is None:
            code_changed.append(f"{f} (added since {args.base})")
            continue
        if args.head:
            new = show_or_none(args.head, f)
            if new is None:
                code_changed.append(f"{f} (deleted at {args.head})")
                continue
        else:
            try:
                new = open(f, encoding="utf-8").read()
            except FileNotFoundError:
                code_changed.append(f"{f} (deleted)")
                continue
        try:
            if normalized(old, args.allow_import_reorder) != normalized(
                new, args.allow_import_reorder
            ):
                code_changed.append(f)
        except SyntaxError as e:
            unverifiable.append(f"{f} (SyntaxError: {type(e).__name__})")

    for f in py_added:
        code_changed.append(f"{f} (added -- a comment/format-only change adds no files)")

    print(f"base: {args.base}")
    print(f"python files compared: {len(py_changed)}")
    if other:
        print(f"unchecked non-python changes ({len(other)}) -- verify with typecheck/tests:")
        for f in other:
            print(f"  ? {f}")
    if unverifiable:
        print("COULD NOT VERIFY:")
        for f in unverifiable:
            print(f"  ! {f}")
    if code_changed:
        print("EXECUTABLE CODE CHANGED:")
        for f in code_changed:
            print(f"  x {f}")
        print("\nFAIL -- this is not a comment/formatting-only change.")
        return 1
    if unverifiable:
        print("\nINCONCLUSIVE -- a file could not be parsed.")
        return 2
    print("\nOK -- executable code is identical; only comments/formatting/docstrings differ.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
