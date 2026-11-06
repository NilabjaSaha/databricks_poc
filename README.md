# databricks_poc

A Declarative Automation Bundle (DAB) with a dbt Core project for Databricks.
Develop dbt models locally against a SQL warehouse, then deploy the same project
as a Databricks job with `databricks bundle deploy`.

The dbt models (bronze/silver/gold medallion layers, macros, seeds, snapshots)
were merged from [saquibherman/dbt_core_databricks_demo](https://github.com/saquibherman/dbt_core_databricks_demo).

* `databricks.yml`: bundle definition (workspace, dev/prod targets).
* `resources/`: bundle resources; `ingestion.pipeline.yml` loads source files into the
  landing schema, `dbt.job.yml` runs that pipeline and then dbt on serverless compute.
* `config/ingestion.yml`, `pipelines/ingestion/`: metadata-driven ingestion (see
  `docs/ingestion-framework.md`).
* `dbt_project.yml`, `profiles.yml`, `packages.yml`: dbt project and connection profile.
* `src/models`, `src/macros`, `src/seeds`, `src/snapshots`, `src/analyses`, `src/tests`: dbt sources.
* `src/seeds/`: static lookup tables only (`product_categories`). Source data is
  not seeded: it arrives as files and is ingested by the pipeline.
* `scripts/dbt_env.sh`: exports dbt credentials from your Databricks CLI login.
* `tests/`: Python unit tests (pytest). dbt tests live in `src/tests/`.

## Versions

| Component | Version | Notes |
|---|---|---|
| Databricks Runtime | 18 LTS (Spark 4.1.0) | Or serverless environment v5 |
| Python | 3.12 | Required by databricks-connect (`==3.12.*`) |
| dbt-databricks | 1.12.8 | With dbt-core 1.12.x, installed as a uv tool (not in `.venv`); pinned in `requirements-dbt.txt` and `resources/dbt.job.yml` |
| databricks-connect | 18.0.x | In `.venv`; pinned with the serverless environment v5 constraints in `pyproject.toml` |
| Databricks CLI | v1.22.1 or later | Used for OAuth login and deployment |

## Setup

Prerequisites: [uv](https://docs.astral.sh/uv/) and the
[Databricks CLI](https://docs.databricks.com/dev-tools/cli/install).

```bash
uv sync --dev                        # .venv: databricks-connect, pytest, ruff
source .venv/bin/activate
uv tool install --python 3.12 dbt-core --with-requirements requirements-dbt.txt --with-executables-from shandy-sqlfmt
databricks auth login --host https://adb-7405619838309890.10.azuredatabricks.net
```

Their versions are pinned in `requirements-dbt.txt`. dbt and sqlfmt share one
uv tool environment (`~/.local/bin/dbt`, `~/.local/bin/sqlfmt`), separate from
`.venv`, because dbt-databricks 1.12.8 needs protobuf 6.x, while
the serverless environment v5 constraints in `pyproject.toml` (managed by
`databricks environments setup-local`) pin protobuf 5.x. For dbt Power User in
VS Code, set `dbt.dbtPythonPathOverride` to
`~/.local/share/uv/tools/dbt-core/bin/python`.

Do not install `pyspark` separately; it conflicts with `databricks-connect`.

## Local dbt development

`profiles.yml` sits in the project root, so dbt finds it without extra flags. It
reads a token from the environment. Export one from your CLI login (no personal
access token needed), together with your personal dev schema:

```bash
source scripts/dbt_env.sh            # or: source scripts/dbt_env.sh <cli-profile>
dbt deps
dbt debug                            # check the connection
dbt seed                             # load lookup tables (product_categories)
dbt build                            # run models, snapshots and tests
```

The OAuth token expires after about an hour; source the script again when dbt
reports an authentication error. You can also set `DATABRICKS_TOKEN` yourself,
for example in a git-ignored `.env` file.

In the `dev` target, objects are written to `<you>_landing`, `<you>_bronze`,
`<you>_silver` and `<you>_gold` (e.g. `nilabja_saha_bronze`) in the
`dbw_dbxpoc_sbx_weu` catalog, so developers don't overwrite each other. The
`prod` target runs in the prod workspace and writes to `landing`, `bronze`,
`silver` and `gold` in `dbw_dbxpoc_prd_sbx_weu`, the prod workspace's default
catalog. See `src/macros/generate_schema_name.sql`.

Grants on the prod catalog: the CD service principal `sp-dbxpoc-cicd` has
`USE CATALOG`, `USE SCHEMA` and `CREATE SCHEMA`; nilabja.saha@knowit.se has
`ALL PRIVILEGES` and `MANAGE`; saquib.herman@knowit.se is read-only.

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

Production is deployed only by CD (see below), never from a laptop.

## CI/CD

GitHub Actions workflows live in `.github/workflows/`.

**CI** (`ci.yml`, job `ci`) runs on every pull request to `main` and on manual
dispatch. It uses no secrets and only reads the repository:

1. Installs dbt and sqlfmt from `requirements-dbt.txt`, as in Setup.
2. `sqlfmt --check src/`.
3. `dbt deps`, then `dbt parse` for the `dev` and `prod` targets, offline with
   dummy values (`DBT_ACCESS_TOKEN=dummy`, `DBT_DEV_SCHEMA=ci`).

Require the `ci` check in branch protection for `main`.

**CD** (`cd.yml`, job `deploy-prod`) runs on every push to `main` and on manual
dispatch:

1. Waits for approval on the GitHub environment `prod`.
2. Installs Databricks CLI 1.22.1 and writes the `dbxpoc-prd` profile (the name
   `databricks.yml` pins) for the service principal `sp-dbxpoc-cicd`, using
   OAuth machine-to-machine.
3. `databricks bundle validate --strict -t prod`, `databricks bundle deploy -t prod`,
   `databricks bundle run dbt_job -t prod`.
4. Writes a summary of each step's result to the run page.

Only one prod deployment runs at a time (concurrency group `prod-deploy`, queued,
not cancelled). The prod job runs as `sp-dbxpoc-cicd` (`run_as` in
`databricks.yml`).

GitHub settings CD needs, in the `prod` environment:

| Kind | Name | Value |
|---|---|---|
| Variable | `DATABRICKS_HOST` | `https://adb-7405615711496172.12.azuredatabricks.net` |
| Secret | `DATABRICKS_CLIENT_ID` | application ID of `sp-dbxpoc-cicd` |
| Secret | `DATABRICKS_CLIENT_SECRET` | an OAuth secret of `sp-dbxpoc-cicd` |

## Python tests

```bash
uv run pytest
```
