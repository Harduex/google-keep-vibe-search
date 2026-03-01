---
name: debugger
description: Systematically diagnoses and resolves software defects using a structured, scientific approach. Applies isolation, binary chop, and root cause analysis techniques. Use when investigating bugs, diagnosing errors, tracing unexpected behavior, or resolving test failures.
---

# Scientific Debugging

## Protocol

Follow these 4 steps for every defect. Do not skip steps or take shortcuts.

### 1. Isolate: Write a failing test first

Before modifying any production code, write a failing test that reproduces the defect. This:
- Proves you understand the exact conditions that trigger the bug
- Creates a regression baseline
- Gives you a clear signal when the fix works

### 2. Diagnose: Understand before changing

- **Read the surrounding code** before touching anything. Resist the urge to tweak and see what happens.
- **Apply the scientific method**: Gather data, form a hypothesis, test it. Ensure your hypothesis explains all observed behaviors, not just a subset.
- **Binary chop**: For obscure bugs, use divide-and-conquer to narrow the search space. Bisect commit history, comment out code blocks, or reduce input data until you isolate the trigger.
- **Check the usual suspects**: Recently modified code, historically problematic modules, environment differences, race conditions.

### 3. Fix: Cure the root cause

- Fix the underlying cause, not the symptom. No band-aid patches, no exception masking, no workarounds.
- Make exactly one small, controlled, atomic change. If it doesn't work, revert immediately.
- Preserve existing code structure. Do not use the fix as an excuse to refactor.

### 4. Verify and learn

- Confirm the test from Step 1 now passes.
- Run the full relevant test suite to check for regressions.
- Provide a brief **5 Whys** analysis: Why did this bug exist? What allowed it to reach production? How can similar bugs be prevented?

## Diagnostic tools

- **Logs and traces**: For timing, concurrency, and distributed system issues.
- **git bisect**: To find the exact commit that introduced a regression.
- **Strategic debug output**: Add temporary logging at key decision points, remove it after diagnosis.

## Constraints

- Never refactor during debugging. The goal is a minimal, surgical fix.
- No change-marker comments. Leave no `// fix applied` breadcrumbs.
- If the root cause is architectural, report it and propose a fix separately. Do not combine debugging with redesign.
