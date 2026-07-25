"""Promote the current run to the committed baseline — a deliberate act, never a side effect.

`make bench` and `make bench-compare` never call this. Re-baselining goes in its own commit
with the reason in the message, so a regression can never be absorbed silently by a run.
"""

import shutil
import sys
from pathlib import Path

BENCH_DIR = Path(__file__).parent
BASELINES_DIR = BENCH_DIR / "baselines"
RUN_DIR = BENCH_DIR / ".run"


def main() -> int:
    BASELINES_DIR.mkdir(exist_ok=True)
    accepted = []
    for task in ("scifact", "newsgroups20"):
        current = RUN_DIR / f"{task}_current.json"
        if not current.exists():
            print(f"{task}: no current run to accept (run `make bench` first).")
            continue
        shutil.copyfile(current, BASELINES_DIR / f"{task}.json")
        accepted.append(task)

    if not accepted:
        print("Nothing accepted.", file=sys.stderr)
        return 1

    print(f"Accepted as baseline: {', '.join(accepted)}")
    print("Commit the baseline files on their own, with the reason in the message.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
