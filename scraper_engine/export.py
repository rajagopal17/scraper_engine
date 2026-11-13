from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path


def export_run(records: list[dict], output_dir: Path, run_label: str | None = None) -> tuple[Path, Path]:
    """Write the same validated records that were merged into Postgres to JSON + CSV.

    This is the first sink of a pluggable-sink design: callers wanting a different
    downstream (an API, another DB, object storage) add an adapter with the same
    records list, without touching the scraping/validation pipeline.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    label = run_label or datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    json_path = output_dir / f"run_{label}.json"
    json_path.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")

    csv_path = output_dir / f"run_{label}.csv"
    fieldnames: list[str] = []
    for r in records:
        for k in r.keys():
            if k not in fieldnames:
                fieldnames.append(k)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow(r)

    return json_path, csv_path
