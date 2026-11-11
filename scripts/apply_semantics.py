"""Create the Unity Catalog metric views in semantics/*.sql.

Runs as the apply_semantics task of dbt_job (resources/dbt.job.yml), after
dbt, because the metric views read dbt's silver and bronze tables and live in
dbt's gold schema. Each file is one CREATE OR REPLACE VIEW ... WITH METRICS
statement, so every run can re-apply all of them. See docs/semantics.md.

Placeholders replaced in each file: {catalog}, {bronze_schema},
{silver_schema}, {gold_schema}.

Usage:
  apply_semantics.py --catalog C --bronze-schema B --silver-schema S
                     --gold-schema G --semantics-dir semantics
"""

import argparse
from pathlib import Path

from pyspark.sql import SparkSession


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--bronze-schema", required=True)
    parser.add_argument("--silver-schema", required=True)
    parser.add_argument("--gold-schema", required=True)
    parser.add_argument("--semantics-dir", required=True)
    args = parser.parse_args()

    placeholders = {
        "{catalog}": args.catalog,
        "{bronze_schema}": args.bronze_schema,
        "{silver_schema}": args.silver_schema,
        "{gold_schema}": args.gold_schema,
    }
    spark = SparkSession.builder.getOrCreate()
    files = sorted(Path(args.semantics_dir).glob("*.sql"))
    if not files:
        raise RuntimeError(f"no .sql files in {args.semantics_dir}")

    created, failed = [], []
    for sql_file in files:
        sql = sql_file.read_text()
        for placeholder, value in placeholders.items():
            sql = sql.replace(placeholder, value)
        try:
            spark.sql(sql.strip().rstrip(";"))
            created.append(sql_file.name)
        except Exception as e:  # noqa: BLE001 - keep going, report and fail at the end
            failed.append(f"{sql_file.name}: {str(e).splitlines()[0]}")

    target = f"{args.catalog}.{args.gold_schema}"
    print(f"\nCREATED in {target} ({len(created)})")
    for item in created:
        print(f"  {item}")
    print(f"\nFAILED ({len(failed)})")
    for item in failed:
        print(f"  {item}")
    if failed:
        # Raise instead of sys.exit: serverless runs this in IPython, where any
        # SystemExit (even 0) fails the task.
        raise RuntimeError(f"{len(failed)} metric view(s) failed, see FAILED above")


if __name__ == "__main__":
    main()
