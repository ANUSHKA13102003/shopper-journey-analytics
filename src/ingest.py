"""Dataset download, verification, and data quality profiling."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import duckdb

CRITEO_URL = (
    "https://huggingface.co/datasets/criteo/criteo-uplift/resolve/main/"
    "criteo-research-uplift-v2.1.csv.gz"
)
REES46_DATASET = "mkechinov/ecommerce-behavior-data-from-multi-category-store"


def has_kaggle_auth() -> bool:
    """Return True if Kaggle credentials exist in env or ~/.kaggle."""
    if os.environ.get("KAGGLE_API_TOKEN"):
        return True
    kaggle_dir = Path.home() / ".kaggle"
    return (kaggle_dir / "access_token").exists() or (kaggle_dir / "kaggle.json").exists()


def download_criteo(raw_dir: Path) -> Path:
    """Download Criteo Uplift v2.1 from Hugging Face if missing or incomplete."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / "criteo-research-uplift-v2.1.csv.gz"
    if dest.exists() and dest.stat().st_size > 100_000_000:
        return dest

    cmd = ["curl", "-L", "--fail", "--retry", "3", "-o", str(dest), CRITEO_URL]
    subprocess.run(cmd, check=True)
    if not dest.exists() or dest.stat().st_size <= 100_000_000:
        raise RuntimeError(f"Criteo download incomplete: {dest}")
    return dest


def download_rees46(raw_dir: Path) -> list[Path]:
    """Download and unzip REES46 Oct+Nov 2019 CSVs via Kaggle CLI."""
    rees_dir = raw_dir / "rees46"
    rees_dir.mkdir(parents=True, exist_ok=True)
    oct_csv = rees_dir / "2019-Oct.csv"
    nov_csv = rees_dir / "2019-Nov.csv"
    if (
        oct_csv.exists()
        and nov_csv.exists()
        and oct_csv.stat().st_size > 1_000_000_000
        and nov_csv.stat().st_size > 1_000_000_000
    ):
        return [oct_csv, nov_csv]

    if not has_kaggle_auth():
        raise RuntimeError(
            "Kaggle credentials missing. Set KAGGLE_API_TOKEN or place "
            "access_token / kaggle.json in ~/.kaggle/."
        )

    kaggle_exe = Path(sys.executable).parent / (
        "kaggle.exe" if os.name == "nt" else "kaggle"
    )
    cmd = [
        str(kaggle_exe),
        "datasets",
        "download",
        "-d",
        REES46_DATASET,
        "-p",
        str(rees_dir),
        "--unzip",
    ]
    subprocess.run(cmd, check=True)
    for f in (oct_csv, nov_csv):
        if not f.exists() or f.stat().st_size < 1_000_000_000:
            raise RuntimeError(f"Missing or incomplete REES46 file: {f}")
    return [oct_csv, nov_csv]


def profile_rees46(csv_paths: list[Path], out_dir: Path) -> dict:
    """Profile REES46 raw CSV files with DuckDB and write data_quality.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path("data/interim/duckdb_tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path("data/interim/duckdb_tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET memory_limit = '4GB'")
    con.execute(f"SET temp_directory = '{tmp_dir.as_posix()}'")
    con.execute("SET memory_limit = '4GB'")
    con.execute(f"SET temp_directory = '{tmp_dir.as_posix()}'")
    files_sql = ", ".join(f"'{p.as_posix()}'" for p in csv_paths)

    con.execute(
        f"""
        CREATE TEMP VIEW raw_events AS
        SELECT * FROM read_csv(
            [{files_sql}],
            header=true,
            delim=',',
            columns={{
                'event_time': 'TIMESTAMP',
                'event_type': 'VARCHAR',
                'product_id': 'BIGINT',
                'category_id': 'BIGINT',
                'category_code': 'VARCHAR',
                'brand': 'VARCHAR',
                'price': 'DOUBLE',
                'user_id': 'BIGINT',
                'user_session': 'VARCHAR'
            }}
        )
        """
    )

    summary_row = con.execute(
        """
        SELECT
            COUNT(*)::BIGINT AS total_rows,
            MIN(event_time)::VARCHAR AS min_event_time,
            MAX(event_time)::VARCHAR AS max_event_time,
            COUNT(DISTINCT user_id)::BIGINT AS distinct_users,
            COUNT(DISTINCT user_session)::BIGINT AS distinct_sessions,
            SUM(CASE WHEN category_code IS NULL THEN 1 ELSE 0 END)::BIGINT AS null_category_code,
            SUM(CASE WHEN brand IS NULL THEN 1 ELSE 0 END)::BIGINT AS null_brand,
            SUM(CASE WHEN user_session IS NULL THEN 1 ELSE 0 END)::BIGINT AS null_user_session,
            SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END)::BIGINT AS null_user_id,
            SUM(CASE WHEN price IS NULL OR price <= 0 THEN 1 ELSE 0 END)::BIGINT AS price_le_zero
        FROM raw_events
        """
    ).fetchdf().iloc[0]

    event_counts_df = con.execute(
        """
        SELECT event_type, COUNT(*)::BIGINT AS row_count
        FROM raw_events
        GROUP BY event_type
        ORDER BY row_count DESC
        """
    ).fetchdf()

    # Exact duplicate count via hash aggregation on key event columns
    print("  Checking exact duplicates...", flush=True)
    dup_row = con.execute(
        """
        SELECT
            COALESCE(SUM(cnt - 1), 0)::BIGINT AS duplicate_rows
        FROM (
            SELECT COUNT(*) AS cnt
            FROM raw_events
            GROUP BY event_time, event_type, product_id, user_id, user_session
            HAVING COUNT(*) > 1
        )
        """
    ).fetchdf().iloc[0]

    profile = {
        "total_rows": int(summary_row["total_rows"]),
        "min_event_time": str(summary_row["min_event_time"]),
        "max_event_time": str(summary_row["max_event_time"]),
        "distinct_users": int(summary_row["distinct_users"]),
        "distinct_sessions": int(summary_row["distinct_sessions"]),
        "null_category_code": int(summary_row["null_category_code"]),
        "null_brand": int(summary_row["null_brand"]),
        "null_user_session": int(summary_row["null_user_session"]),
        "null_user_id": int(summary_row["null_user_id"]),
        "price_le_zero": int(summary_row["price_le_zero"]),
        "duplicate_rows": int(dup_row["duplicate_rows"] or 0),
        "event_type_counts": {
            str(r["event_type"]): int(r["row_count"])
            for _, r in event_counts_df.iterrows()
        },
    }

    with open(out_dir / "data_quality.json", "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)

    return profile


def create_sample_fixture(
    csv_paths: list[Path],
    fixture_path: Path = Path("tests/fixtures/rees46_sample.parquet"),
    target_rows: int = 20000,
) -> Path:
    """Save ~20k real REES46 rows (sampled by user_id hash) for CI tests."""
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path("data/interim/duckdb_tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET memory_limit = '4GB'")
    con.execute(f"SET temp_directory = '{tmp_dir.as_posix()}'")
    files_sql = ", ".join(f"'{p.as_posix()}'" for p in csv_paths)
    con.execute(
        f"""
        COPY (
            SELECT *
            FROM read_csv(
                [{files_sql}],
                header=true,
                delim=',',
                columns={{
                    'event_time': 'TIMESTAMP',
                    'event_type': 'VARCHAR',
                    'product_id': 'BIGINT',
                    'category_id': 'BIGINT',
                    'category_code': 'VARCHAR',
                    'brand': 'VARCHAR',
                    'price': 'DOUBLE',
                    'user_id': 'BIGINT',
                    'user_session': 'VARCHAR'
                }}
            )
            WHERE user_id IS NOT NULL
              AND user_session IS NOT NULL
              AND ABS(HASH(user_id)) % 5000 = 0
            LIMIT {int(target_rows)}
        ) TO '{fixture_path.as_posix()}' (FORMAT PARQUET)
        """
    )
    return fixture_path


if __name__ == "__main__":
    raw = Path("data/raw")
    out = Path("outputs")
    download_criteo(raw)
    rees_files = download_rees46(raw)
    prof = profile_rees46(rees_files, out)
    create_sample_fixture(rees_files)
    print(json.dumps(prof, indent=2))
