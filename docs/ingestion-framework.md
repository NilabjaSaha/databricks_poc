# Ingestion framework

`config/ingestion.yml` describes every source the ingestion framework loads
into the landing schema. It holds one entry per source under `sources:`, and
contains nothing environment-specific: the landing root (a volume today, ADLS
later) comes from a bundle variable in `databricks.yml`.

CI validates the file with `scripts/validate_ingestion_config.py`.

## How the pipeline works

```
config/ingestion.yml ──▶ pipelines/ingestion/ingest_landing.py ──▶ <catalog>.<landing schema>.<target_table>
                          (one Auto Loader streaming table per source)            ▲
<landing_root>/<path> ───────────────────────────────────────────────────────────┘
```

1. The Lakeflow Declarative Pipeline `ingestion_landing`
   (`resources/ingestion.pipeline.yml`, serverless) gets two settings from the
   bundle: `landing_root` (bundle variable) and `ingestion_config_path` (the
   deployed copy of `config/ingestion.yml`).
2. `ingest_landing.py` reads the config and, for each source, defines a
   streaming table named `target_table`. Auto Loader (`cloudFiles`) reads new
   files under `<landing_root>/<path>` incrementally, with `format`, `options`
   and `schema_hints` from the config. New columns are added to the table
   (`schemaEvolutionMode: addNewColumns`).
3. The `warn`, `drop` and `fail` rules become pipeline expectations
   (`expect_all`, `expect_all_or_drop`, `expect_all_or_fail`).
4. `source_system`, `pii_columns` and `tags` are stored as table properties
   (`dbxpoc.source_system`, `dbxpoc.pii_columns`, `dbxpoc.tag.<key>`).
5. The pipeline publishes to the bundle variable `landing_schema`, the same
   schema dbt reads its `landing` source from: `<user>_landing` in dev,
   `landing` in prod.

Each update only processes files it has not seen before.

## Metadata columns

Every landing table has the source columns plus:

| Column | Set by | Meaning |
|---|---|---|
| `_ingested_at` | pipeline (`current_timestamp()`) | When the row was ingested. |
| `_source_file` | pipeline (`_metadata.file_path`) | Full path of the file the row came from. |
| `_rescued_data` | Auto Loader | Values that didn't fit the schema (wrong type, unexpected column), as JSON. `NULL` when the row parsed cleanly. |

**Decision:** the bronze models keep these columns. `bronze_orders`,
`bronze_reviews` and `bronze_users` stay `select *`, so each bronze row shows
when and from which file it was ingested, and any rescued data. Silver and gold
select their columns explicitly and don't carry them.

## Data quality results

- **Pipeline UI:** open the pipeline, select a table, and see the **Data
  quality** tab: passed and failed records per expectation, and dropped
  records.
- **SQL:** query the event log of a table (shown for dev; use `landing` in
  prod):

```sql
SELECT
  timestamp,
  e.dataset,
  e.name AS expectation,
  e.passed_records,
  e.failed_records
FROM (
  SELECT
    timestamp,
    explode(from_json(
      details:flow_progress:data_quality:expectations,
      'array<struct<name string, dataset string, passed_records bigint, failed_records bigint>>'
    )) AS e
  FROM event_log(TABLE(dbw_dbxpoc_sbx_weu.nilabja_saha_landing.orders))
  WHERE event_type = 'flow_progress'
    AND details:flow_progress:data_quality:expectations IS NOT NULL
)
ORDER BY timestamp DESC;
```

`drop` rules count their removed rows in `failed_records`; the rows are not in
the table.

## Switching to ADLS

The source location is only the bundle variable `landing_root`, set per target
in `databricks.yml`. Moving a target from the volume to ADLS is a one-line
change, for example:

```yaml
      landing_root: abfss://landing@stdbxpocsbxweu01.dfs.core.windows.net/
```

Neither the pipeline code nor `config/ingestion.yml` changes, because every
`path` is relative to `landing_root`. Before switching, Unity Catalog needs an
external location covering that URL, with `READ FILES` for the identity that
runs the pipeline.

## Why the dbt landing seeds were removed

A table belongs to the tool that created it. `dbt seed` created
`landing.orders`, `products`, `reviews` and `users` as plain Delta tables. A
Lakeflow Declarative Pipeline can only manage streaming tables it created
itself, so it cannot take over tables dbt made.

- The seeded tables were dropped by hand in dev on 2026-11-06, and the
  pipeline then created the streaming tables under the same names.
- Step F4 (2026-11-07) removed the landing seeds (`src/seeds/landing/` and
  their config), so `dbt seed` no longer produces these tables and can't try to
  replace the pipeline's.
- The names stay the same, so the dbt source `landing`
  (`src/models/sources/landing_sources.yml`) and every model on top of it don't
  change.

`product_categories` stays a dbt seed: it is reference data dbt owns, in the
bronze schema.

## Job orchestration

`dbt_job` (`resources/dbt.job.yml`) runs ingestion and dbt as one job:

| Task | Type | Depends on | Does |
|---|---|---|---|
| `ingest_landing` | `pipeline_task` on `ingestion_pipeline` (`full_refresh: false`) | — | Loads new files into the landing streaming tables. |
| `dbt` | `dbt_task` | `ingest_landing` | `dbt deps`, `dbt seed` (only `product_categories`), `dbt build`. |

The `dbt` task uses the default run condition (all dependencies succeeded): if
ingestion fails, `dbt` is skipped, so the models never build on a partial
load. CD runs the same job in prod.

`full_refresh: false` keeps the streaming state. A full refresh re-reads every
file and rebuilds the landing tables; start one only on purpose, from the
pipeline UI.

## Incremental loading

Auto Loader remembers which files it has processed. Each update reads only
files added since the last one; existing rows are not touched.

Worked example (dev, 2026-11-07): one new file with 2 orders.

| | Before | After |
|---|---|---|
| Rows ingested by the update | — | orders 2, products 0, reviews 0, users 0 |
| `landing.orders` | 300 | 302 |
| `_source_file` of the new rows | — | `…/shop/orders/orders_2026_11_07.csv` |
| Orders `90001`, `90002` in `silver_orders` | no | yes |

To repeat it:

1. Write a CSV with the same header as the source, for example
   `orders_2026_11_07.csv`:
   ```
   id,created_at,user_id,product_id,quantity,unit_price
   90001,2026-11-07 09:00:00,1,1,2,10.00
   90002,2026-11-07 09:05:00,2,3,1,25.50
   ```
2. Upload it to the dev volume. A new file name is what makes it new:
   ```bash
   databricks fs cp orders_2026_11_07.csv \
     dbfs:/Volumes/dbw_dbxpoc_sbx_weu/raw/landing/shop/orders/ -p adb-7405619838309890
   ```
3. Run the job: `databricks bundle run dbt_job -t dev`.
4. Check the result:
   ```sql
   SELECT _source_file, count(*)
   FROM dbw_dbxpoc_sbx_weu.nilabja_saha_landing.orders
   GROUP BY _source_file;

   SELECT * FROM dbw_dbxpoc_sbx_weu.nilabja_saha_silver.silver_orders
   WHERE id IN (90001, 90002);
   ```
   Rows written per table by each update (the event log covers the whole
   pipeline, so this lists every landing table; a table with no new files has
   no row in that update, i.e. 0):
   ```sql
   SELECT timestamp, origin.flow_name,
          details:flow_progress:metrics:num_output_rows::bigint AS rows
   FROM event_log(TABLE(dbw_dbxpoc_sbx_weu.nilabja_saha_landing.orders))
   WHERE event_type = 'flow_progress'
     AND details:flow_progress:metrics:num_output_rows IS NOT NULL
   ORDER BY timestamp DESC;
   ```

Re-uploading a file under a name Auto Loader has already seen is ignored.
Changing an existing file's content is not a supported way to correct data.

## Dependency pins in the pipeline

Pin pipeline dependencies with `~=` (for example `pyyaml~=6.0`), not
`>=6,<7`. The pipeline installs them with an unquoted `pip` command, so the
shell reads `<` and `>` as redirections and the install fails with "Failed to
install environment dependency". `~=6.0` means the same (`>=6.0, <7`). The
validator (`scripts/validate_ingestion_config.py`) uses the same pin.

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
