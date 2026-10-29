# databricks_poc

A Declarative Automation Bundle (DAB) with a dbt Core project for Databricks.
Develop dbt models locally against a SQL warehouse, then deploy the same project
as a Databricks job with `databricks bundle deploy`.

The dbt models (bronze/silver/gold medallion layers, macros, seeds, snapshots)
were merged from [saquibherman/dbt_core_databricks_demo](https://github.com/saquibherman/dbt_core_databricks_demo).

* `databricks.yml`: bundle definition (workspace, dev/prod targets).
* `resources/`: bundle resources; `dbt.job.yml` runs dbt on serverless compute.
* `dbt_project.yml`, `profiles.yml`, `packages.yml`: dbt project and connection profile.
* `src/models`, `src/macros`, `src/seeds`, `src/snapshots`, `src/analyses`, `src/tests`: dbt sources.
* `src/seeds/landing/`: sample data for the `landing` source schema.
* `scripts/dbt_env.sh`: exports dbt credentials from your Databricks CLI login.
* `tests/`: Python unit tests (pytest). dbt tests live in `src/tests/`.

## Versions

| Component | Version | Notes |
|---|---|---|
| Databricks Runtime | 18 LTS (Spark 4.1.0) | Or serverless environment v5 |
| Python | 3.12 | Required by databricks-connect (`==3.12.*`) |
| dbt-databricks | 1.12.8 | Pulls in dbt-core 1.12.x; also pinned in `resources/dbt.job.yml` |
| databricks-connect | 18.3.x | Must not be newer than the compute's DBR version |
| Databricks CLI | v1.22.1 or later | Used for OAuth login and deployment |

## Setup

Prerequisites: [uv](https://docs.astral.sh/uv/) and the
[Databricks CLI](https://docs.databricks.com/dev-tools/cli/install).

```bash
uv sync --dev
source .venv/bin/activate
databricks auth login --host https://adb-7405619838309890.10.azuredatabricks.net
```

Do not install `pyspark` separately; it conflicts with `databricks-connect`.

## Local dbt development

`profiles.yml` sits in the project root, so dbt finds it without extra flags. It
reads a token from the environment. Export one from your CLI login (no personal
access token needed), together with your personal dev schema:

```bash
source scripts/dbt_env.sh            # or: source scripts/dbt_env.sh <cli-profile>
dbt deps
dbt debug                            # check the connection
dbt seed                             # load sample landing data
dbt build                            # run models, snapshots and tests
```

The OAuth token expires after about an hour; source the script again when dbt
reports an authentication error. You can also set `DATABRICKS_TOKEN` yourself,
for example in a git-ignored `.env` file.

In the `dev` target, objects are written to `<you>_landing`, `<you>_bronze`,
`<you>_silver` and `<you>_gold` (e.g. `nilabja_saha_bronze`) in the
`dbw_dbxpoc_sbx_weu` catalog, so developers don't overwrite each other. The
`prod` target writes to `landing`, `bronze`, `silver` and `gold`. See
`src/macros/generate_schema_name.sql`.

Format SQL with `sqlfmt src/`.

## Deploying with the bundle

```bash
databricks bundle validate
databricks bundle deploy --target dev
databricks bundle run dbt_job --target dev
```

The deployed dev job uses the same `profiles.yml` and your user name as the dev
schema, so it builds into the same schemas as your local runs. Databricks
injects `DBT_HOST` and `DBT_ACCESS_TOKEN` into the job.

For production:

```bash
databricks bundle deploy --target prod
databricks bundle run dbt_job --target prod
```

## Python tests

```bash
uv run pytest
```
