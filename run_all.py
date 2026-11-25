"""End-to-end pipeline runner: download/verify data, run Part A SQL, run Part B stats."""

from __future__ import annotations

import json
from pathlib import Path

from src.build_outputs import build_static_html_report, run_part_a_sql
from src.ingest import (
    create_sample_fixture,
    download_criteo,
    download_rees46,
    profile_rees46,
)
from src.stats import analyze_criteo


def main() -> None:
    raw_dir = Path("data/raw")
    out_dir = Path("outputs")

    print("[1/4] Checking/downloading raw datasets...")
    criteo_path = download_criteo(raw_dir)
    rees_paths = download_rees46(raw_dir)

    print("[2/4] Profiling REES46 data quality and building sample fixture...")
    dq = profile_rees46(rees_paths, out_dir)
    create_sample_fixture(rees_paths)
    print(f"      REES46 total rows: {dq['total_rows']:,}")

    print("[3/4] Running Part A SQL (funnel + cohorts + retention)...")
    part_a = run_part_a_sql(rees_paths, out_dir=out_dir)
    print(f"      Sessions viewed: {part_a['sessions_viewed']:,}")

    print("[4/4] Running Part B statistical analysis (Criteo Uplift)...")
    part_b = analyze_criteo(criteo_path, out_dir=out_dir)
    print(f"      Criteo rows: {part_b['total_rows']:,}")

    build_static_html_report(out_dir=out_dir, html_path=Path("docs/index.html"))
    combined = {"data_quality": dq, "part_a": part_a, "part_b": part_b}
    with open(out_dir / "headline_results.json", "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2)
    print("Done. All outputs written to outputs/.")


if __name__ == "__main__":
    main()
