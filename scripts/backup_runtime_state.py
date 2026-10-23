"""Consistent SQLite backup with row counts and hashes, without resetting any ledger."""

import argparse
import hashlib
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path


def backup(source, destination):
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if source == destination or destination.exists():
        raise ValueError("Backup must have a new separate destination")
    destination.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 30

    def progress(*_):
        if time.monotonic() >= deadline:
            raise TimeoutError("Consistent SQLite backup exceeded thirty seconds")

    with (
        closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original,
        closing(sqlite3.connect(destination)) as copy,
    ):
        original.backup(copy, pages=128, sleep=0.05, progress=progress)
        if copy.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise ValueError("SQLite backup validation failed")
        tables = [r[0] for r in copy.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        counts = {
            table: copy.execute(
                'SELECT count(*) FROM "' + table.replace('"', '""') + '"'
            ).fetchone()[0]
            for table in tables
        }
    return dict(
        status="CONSISTENT_SQLITE_BACKUP",
        sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
        table_rows=counts,
        source_modified=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    report = backup(args.source, args.destination)
    args.destination.with_suffix(".receipt.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
