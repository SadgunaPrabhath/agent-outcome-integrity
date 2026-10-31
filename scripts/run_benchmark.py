"""Run the AOIE benchmark and write reports.

Usage:
    python -m scripts.run_benchmark [--out benchmark/reports]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running as a plain script from the repo root.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark.metrics import compute_metrics
from benchmark.reports import write_reports
from benchmark.runners import BenchmarkRunner, browser_factory, scripted_factory
from benchmark.tasks import browser_drivable_catalog, default_catalog

# adapter -> (task catalog, adapter factory, report basename, latest filename)
_ADAPTERS = {
    "scripted": (default_catalog, scripted_factory, "benchmark", "latest"),
    "browser": (browser_drivable_catalog, browser_factory, "browser", "browser_latest"),
}


async def _main(out_dir: str, adapter: str) -> int:
    catalog_fn, factory, basename, latest_name = _ADAPTERS[adapter]
    runner = BenchmarkRunner(tasks=catalog_fn(), adapter_factory=factory)
    records = await runner.run()
    metrics = compute_metrics(records)
    json_path, md_path = write_reports(
        records, metrics, out_dir, basename=basename, latest_name=latest_name
    )

    print(f"Adapter: {adapter}")
    print(f"Ran {metrics.total_tasks} task×scenario combinations.")
    print(f"  Apparent success (agent):   {metrics.apparent_success_rate}")
    print(f"  Verified success (AOIE):    {metrics.verified_success_rate}")
    print(f"  False completion rate:      {metrics.false_completion_rate}")
    print(f"  Detection rate:             {metrics.detection_rate}")
    print(f"  Recovery success rate:      {metrics.recovery_success_rate}")
    print(f"  AOIE accuracy vs truth:     {metrics.aoie_accuracy}")
    print(f"\nReports written:\n  {json_path}\n  {md_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the AOIE benchmark.")
    parser.add_argument("--out", default="benchmark/reports", help="output directory")
    parser.add_argument(
        "--adapter",
        default="scripted",
        choices=sorted(_ADAPTERS),
        help="which agent to benchmark (default: scripted)",
    )
    args = parser.parse_args()
    return asyncio.run(_main(args.out, args.adapter))


if __name__ == "__main__":
    raise SystemExit(main())
