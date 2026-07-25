import json
import subprocess
import sys
from pathlib import Path


def main():
    print(
        "WARNING: Domain shift: Medical abstracts/newsgroup posts are not personal notes. Deltas transfer, absolute numbers do not."
    )

    bench_dir = Path(__file__).parent

    # Run the benchmarks
    subprocess.run([sys.executable, "-m", "bench.run_retrieval"], check=True)
    subprocess.run([sys.executable, "-m", "bench.run_tagging"], check=True)

    baselines_dir = bench_dir / "baselines"
    run_dir = bench_dir / ".run"

    regression = False
    threshold = 0.05  # 5% relative regression threshold

    for task in ["scifact", "newsgroups20"]:
        base_path = baselines_dir / f"{task}.json"
        curr_path = run_dir / f"{task}_current.json"

        if not base_path.exists():
            print(f"No baseline for {task}, skipping comparison.")
            continue

        with open(base_path) as f:
            base_data = json.load(f)
        with open(curr_path) as f:
            curr_data = json.load(f)

        print(f"\nComparing {task}...")

        if task == "scifact":
            for signal, metrics in base_data["metrics"].items():
                for metric_name, base_val in metrics.items():
                    curr_val = curr_data["metrics"][signal][metric_name]
                    # We expect curr_val >= base_val - threshold
                    if curr_val < base_val - (base_val * threshold):
                        print(
                            f"REGRESSION in {task} {signal} {metric_name}: base={base_val}, curr={curr_val}"
                        )
                        regression = True
        elif task == "newsgroups20":
            for metric_name, base_val in base_data["metrics"].items():
                curr_val = curr_data["metrics"][metric_name]
                if metric_name in ["untagged_percent", "llm_call_count"]:
                    # Lower is better
                    if curr_val > base_val + (base_val * threshold):
                        print(
                            f"REGRESSION in {task} {metric_name}: base={base_val}, curr={curr_val}"
                        )
                        regression = True
                else:
                    # Higher is better
                    if curr_val < base_val - (base_val * threshold):
                        print(
                            f"REGRESSION in {task} {metric_name}: base={base_val}, curr={curr_val}"
                        )
                        regression = True

    if regression:
        print("\nFailed: Regressions detected!")
        sys.exit(1)
    else:
        print("\nSuccess: No regressions detected.")
        sys.exit(0)


if __name__ == "__main__":
    main()
