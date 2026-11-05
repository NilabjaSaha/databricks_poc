# Ingestion framework: config

`config/ingestion.yml` describes every source the ingestion framework loads
into the landing schema. It holds one entry per source under `sources:`, and
contains nothing environment-specific: the landing root (a volume today, ADLS
later) comes from a bundle variable in `databricks.yml`.

CI validates the file with `scripts/validate_ingestion_config.py`.

## Fields

| Field | Type | Required | Meaning |
|---|---|---|---|
| `name` | string, `snake_case` | yes | Unique source name. |
| `source_system` | string, `snake_case` | yes | System the data comes from, e.g. `shop`. |
| `path` | string | yes | Folder relative to the landing root, e.g. `shop/orders/`. No leading `/`, no `abfss://` or other URL. |
| `format` | `csv`, `json`, `parquet`, `avro`, `orc`, `text`, `binaryFile` | yes | File format for Auto Loader (`cloudFiles.format`). |
| `options` | map of string → string | yes (may be `{}`) | Reader options, e.g. `header: "true"`. Quote values: all options are strings. |
| `schema_hints` | string | yes | Column names and Spark SQL types, e.g. `"id BIGINT, price DECIMAL(10,2)"`. Must match what downstream dbt models expect. |
| `target_table` | string, `snake_case` | yes | Table name in the landing schema of the target (`<user>_landing` in dev, `landing` in prod). Unique across sources. |
| `expectations` | map with keys `warn`, `drop`, `fail` | yes | Each level is a map of `rule_name: SQL condition` (rows must satisfy the condition). `warn`: keep the row, count the violation. `drop`: remove the row. `fail`: stop the pipeline. A rule name may appear in only one level. |
| `pii_columns` | list of strings | yes (may be `[]`) | Columns holding personal data. Each must be a column in `schema_hints`. |
| `tags` | map of string → string | yes (may be `{}`) | Free-form labels, e.g. `domain: sales`. |

The top-level `version` must be `1`.

## Add a new source

1. Add an entry under `sources:` in `config/ingestion.yml`. Copy an existing
   one and change every field. Use a new `name` and `target_table`.
2. Put the files under `<landing root>/<path>`.
3. Set `schema_hints` to the column names and types the dbt models will read.
   If a dbt model uses the table, add it to the `landing` source in
   `src/models/sources/landing_sources.yml`.
4. Start with a `drop` rule for the primary key being not null, and `warn`
   rules for simple sanity checks. Use `fail` only for data that must never
   reach the landing schema.
5. List personal data in `pii_columns`.
6. Run `uv run scripts/validate_ingestion_config.py` and open a pull request.
