"""Apply PII tags and column masks from config/ingestion.yml.

Runs as the apply_governance task of dbt_job (resources/dbt.job.yml), after
dbt. Idempotent: every statement can be re-run safely.

1. CREATE SCHEMA IF NOT EXISTS <catalog>.governance, then the mask functions
   in governance/ (with {catalog} replaced).
2. For each source with pii_columns, tag those columns
   ('pii' = 'true', 'pii_source' = <source_system>) in
   <landing>.<target_table>, <bronze>.bronze_<target_table> and
   <silver>.silver_<target_table>, where the table and column exist.
3. Attach the column masks in MASKS.

Usage:
  apply_governance.py --catalog C --landing-schema L --bronze-schema B
                      --silver-schema S --config config/ingestion.yml
                      --governance-dir governance
"""

import argparse
from pathlib import Path

import yaml
from pyspark.sql import SparkSession

# (layer, table, column, function in <catalog>.governance)
MASKS = [
    ("bronze", "bronze_users", "email", "mask_email"),
]


def quote(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--landing-schema", required=True)
    parser.add_argument("--bronze-schema", required=True)
    parser.add_argument("--silver-schema", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--governance-dir", required=True)
    args = parser.parse_args()

    spark = SparkSession.builder.getOrCreate()
    catalog = args.catalog
    schemas = {"landing": args.landing_schema, "bronze": args.bronze_schema, "silver": args.silver_schema}
    summary = {"tagged": [], "masked": [], "skipped": [], "failed": []}

    def run(sql: str, label: str, bucket: str) -> None:
        try:
            spark.sql(sql)
            summary[bucket].append(label)
        except Exception as e:  # noqa: BLE001 - keep going, report and fail at the end
            summary["failed"].append(f"{label}: {str(e).splitlines()[0]}")

    # 1. Governance schema and mask functions
    statements = [(f"CREATE SCHEMA IF NOT EXISTS {quote(catalog)}.governance", f"schema {catalog}.governance")]
    for sql_file in sorted(Path(args.governance_dir).glob("*.sql")):
        sql = sql_file.read_text().replace("{catalog}", catalog).strip().rstrip(";")
        statements.append((sql, f"function from {sql_file.name}"))
    for sql, label in statements:
        try:
            spark.sql(sql)
            print(f"{label}: ok")
        except Exception as e:  # noqa: BLE001 - report and fail at the end
            summary["failed"].append(f"{label}: {str(e).splitlines()[0]}")

    # Which tables and columns exist, and of which type, in the three schemas
    rows = spark.sql(
        f"""
        SELECT c.table_schema, c.table_name, c.column_name, t.table_type
        FROM {quote(catalog)}.information_schema.columns c
        JOIN {quote(catalog)}.information_schema.tables t
          ON t.table_schema = c.table_schema AND t.table_name = c.table_name
        WHERE c.table_schema IN ({", ".join(repr(s) for s in schemas.values())})
        """
    ).collect()
    columns = {(r.table_schema, r.table_name, r.column_name.lower()) for r in rows}
    table_types = {(r.table_schema, r.table_name): r.table_type for r in rows}

    def alter(schema: str, table: str) -> str:
        kind = "STREAMING TABLE" if table_types.get((schema, table)) == "STREAMING_TABLE" else "TABLE"
        return f"ALTER {kind} {quote(catalog)}.{quote(schema)}.{quote(table)}"

    # 2. PII tags
    with open(args.config) as f:
        sources = yaml.safe_load(f)["sources"]
    for src in sources:
        target = src["target_table"]
        for layer, table in (("landing", target), ("bronze", f"bronze_{target}"), ("silver", f"silver_{target}")):
            schema = schemas[layer]
            fqn = f"{catalog}.{schema}.{table}"
            if (schema, table) not in table_types:
                if src["pii_columns"]:
                    summary["skipped"].append(f"{fqn}: table does not exist")
                continue
            for column in src["pii_columns"]:
                if (schema, table, column.lower()) not in columns:
                    summary["skipped"].append(f"{fqn}.{column}: column does not exist")
                    continue
                run(
                    f"{alter(schema, table)} ALTER COLUMN {quote(column)} "
                    f"SET TAGS ('pii' = 'true', 'pii_source' = '{src['source_system']}')",
                    f"{fqn}.{column}",
                    "tagged",
                )

    # 3. Column masks
    for layer, table, column, function in MASKS:
        schema = schemas[layer]
        fqn = f"{catalog}.{schema}.{table}"
        if (schema, table, column) not in columns:
            summary["skipped"].append(f"mask {fqn}.{column}: column does not exist")
            continue
        run(
            f"{alter(schema, table)} ALTER COLUMN {quote(column)} "
            f"SET MASK {quote(catalog)}.governance.{quote(function)}",
            f"{fqn}.{column} -> {catalog}.governance.{function}",
            "masked",
        )

    for bucket in ("tagged", "masked", "skipped", "failed"):
        print(f"\n{bucket.upper()} ({len(summary[bucket])})")
        for item in summary[bucket]:
            print(f"  {item}")
    if summary["failed"]:
        # Don't sys.exit(0) on success: serverless runs this in IPython, where any
        # SystemExit (even 0) fails the task.
        raise RuntimeError(f"{len(summary['failed'])} governance statement(s) failed, see FAILED above")


if __name__ == "__main__":
    main()
