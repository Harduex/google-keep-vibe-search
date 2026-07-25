"""Compare a fresh benchmark run against the committed baselines.

Exits non-zero on a regression beyond the per-metric threshold below, and also when there
is nothing to compare against — a run with no baseline is an unmeasured run, not a pass.

Thresholds come from observed run-to-run variance, not taste.

Measured on 2026-07-25 over three runs of identical code (same sample, same seed, one GPU):
the retrieval metrics move by up to ~1.8% relative — `plus_rerank recall@1` 0.583/0.593,
`plus_chunk recall@1` 0.542/0.552 — because float non-determinism flips documents that sit
on a rank boundary. 3% leaves headroom above that without hiding a real regression, which
would show up across every row rather than one metric of one combination. (An earlier 2%
threshold, plus a cache shared between runs, made the harness fail against its own baseline;
`run_retrieval.py` now uses a fresh cache per run so every run takes the same code path.)

UMAP/HDBSCAN are seeded but sensitive to library versions and thread counts, so the
clustering metrics get 5%. `untagged_percent` is an absolute percentage, so its threshold is
in points, not relative — a relative threshold on a near-zero baseline can never fire.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

BENCH_DIR = Path(__file__).parent
BASELINES_DIR = BENCH_DIR / "baselines"
RUN_DIR = BENCH_DIR / ".run"

RETRIEVAL_TOLERANCE = 0.03  # relative; observed run-to-run movement is ~1.8%
CLUSTERING_TOLERANCE = 0.05  # relative
UNTAGGED_TOLERANCE_POINTS = 5.0  # absolute percentage points

# Metrics where a *larger* number is worse.
LOWER_IS_BETTER = {"untagged_percent", "llm_calls", "latency_ms"}
# Recorded for context, never gated: they describe the machine, not the retrieval quality.
INFORMATIONAL = {"latency_ms"}


def _regressed(metric: str, base: float, current: float) -> bool:
    if metric in INFORMATIONAL:
        return False
    if metric == "untagged_percent":
        return current > base + UNTAGGED_TOLERANCE_POINTS
    tolerance = (
        CLUSTERING_TOLERANCE if metric in {"ari", "nmi", "v_measure"} else (RETRIEVAL_TOLERANCE)
    )
    if metric in LOWER_IS_BETTER:
        return current > base + abs(base) * tolerance
    return current < base - abs(base) * tolerance


def _compare_flat(
    task: str, scope: str, base: Dict[str, float], current: Dict[str, float]
) -> List[str]:
    failures = []
    for metric, base_value in base.items():
        if not isinstance(base_value, (int, float)) or isinstance(base_value, bool):
            continue
        if metric not in current:
            failures.append(f"{task} {scope}{metric}: missing from the current run")
            continue
        current_value = current[metric]
        if _regressed(metric, float(base_value), float(current_value)):
            failures.append(
                f"{task} {scope}{metric}: baseline {base_value} -> current {current_value}"
            )
    return failures


def compare_task(task: str) -> Tuple[List[str], bool]:
    """Return (failures, compared). `compared` is False when a baseline is missing."""
    base_path = BASELINES_DIR / f"{task}.json"
    current_path = RUN_DIR / f"{task}_current.json"

    if not base_path.exists():
        print(
            f"{task}: no committed baseline. Review this run's table, then accept it with "
            f"`make bench-accept`."
        )
        return [], False
    if not current_path.exists():
        return [f"{task}: the run produced no results file"], True

    with open(base_path, encoding="utf-8") as f:
        base_data = json.load(f)
    with open(current_path, encoding="utf-8") as f:
        current_data = json.load(f)

    base_sample = base_data.get("sample")
    current_sample = current_data.get("sample")
    if base_sample and current_sample and base_sample != current_sample:
        return (
            [
                f"{task}: sample changed ({base_sample} -> {current_sample}); metrics are not "
                f"comparable. Re-run with the baseline's sample or re-baseline deliberately."
            ],
            True,
        )

    print(f"\nComparing {task}...")
    base_metrics = base_data["metrics"]
    current_metrics = current_data["metrics"]
    failures: List[str] = []

    nested = all(isinstance(value, dict) for value in base_metrics.values())
    if nested:
        for signal, metrics in base_metrics.items():
            if signal not in current_metrics:
                failures.append(f"{task} {signal}: missing from the current run")
                continue
            failures.extend(_compare_flat(task, f"{signal} ", metrics, current_metrics[signal]))
    else:
        failures.extend(_compare_flat(task, "", base_metrics, current_metrics))

    return failures, True


def main() -> int:
    print("Running both suites, then comparing against the committed baselines.\n")
    for module in ("bench.run_retrieval", "bench.run_tagging"):
        result = subprocess.run([sys.executable, "-m", module])
        if result.returncode != 0:
            print(f"\n{module} failed — nothing to compare.", file=sys.stderr)
            return result.returncode

    all_failures: List[str] = []
    compared_any = False
    for task in ("scifact", "newsgroups20"):
        failures, compared = compare_task(task)
        all_failures.extend(failures)
        compared_any = compared_any or compared

    if all_failures:
        print("\nRegressions detected:")
        for failure in all_failures:
            print(f"  - {failure}")
        return 1

    if not compared_any:
        print("\nNo baselines to compare against — this run proves nothing yet.")
        return 1

    print("\nNo regressions beyond threshold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
