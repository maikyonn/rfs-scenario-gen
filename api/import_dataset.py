"""CLI to import a CrashEvent CSV into the evaluation database.

Usage:
    python -m api.import_dataset <csv_path> --name "CrashEvent WA 2022"
"""

import argparse
import sys

from api.db import create_dataset, init_db, insert_records, update_dataset_record_count
from api.importers.crashevent import parse_crashevent_csv


def main():
    parser = argparse.ArgumentParser(description="Import a CrashEvent CSV into the evaluation DB")
    parser.add_argument("csv_path", help="Path to the CrashEvent CSV file")
    parser.add_argument("--name", required=True, help="Dataset display name")
    parser.add_argument("--source", default=None, help="Optional source description")
    args = parser.parse_args()

    init_db()

    print(f"Parsing {args.csv_path}...")
    records = parse_crashevent_csv(args.csv_path)
    print(f"  Found {len(records)} generatable records")

    if not records:
        print("No records to import. Exiting.")
        sys.exit(1)

    # Show breakdown
    from collections import Counter
    by_type = Counter(r["crash_type"] for r in records)
    by_pattern = Counter(r["pattern"] for r in records)

    print("\nBy crash type:")
    for ct, count in by_type.most_common():
        print(f"  {ct}: {count}")

    print("\nBy pattern:")
    for pat, count in by_pattern.most_common():
        print(f"  {pat}: {count}")

    dataset_id = create_dataset(args.name, source=args.source or args.csv_path)
    insert_records(dataset_id, records)
    update_dataset_record_count(dataset_id, len(records))

    print(f"\nImported {len(records)} records into dataset #{dataset_id} '{args.name}'")


if __name__ == "__main__":
    main()
