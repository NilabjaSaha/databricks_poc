# Progress

Status of the `databricks_poc` project: a Declarative Automation Bundle (DAB)
that deploys a dbt Core project to Databricks.

Last updated: 2026-11-04. Workspace facts (jobs, runs, warehouses, catalog
bindings and grants) were checked on 2026-11-04.

## What's built

### Workspaces

| Target | Workspace | CLI profile | SQL warehouse |
|---|---|---|---|
| dev | `https://adb-7405619838309890.10.azuredatabricks.net` | `adb-7405619838309890` | `wh-dbxpoc-sbx-2xs` (`6f0a5b155517b87b`) |
| prod | `https://adb-7405615711496172.12.azuredatabricks.net` | `dbxpoc-prd` | `wh-dbxpoc-prd-2xs` (`7e4c13089dc9ec4a`) |

Both workspaces share one Unity Catalog metastore (`c8366777-…`). Each target
pins its profile in `databricks.yml`. Both warehouses are serverless Pro,
2X-Small. `wh-dbxpoc-prd-2xs` was created on 2026-11-04 with auto stop 10
minutes, 1–1 clusters and tags `project=dbxpoc`, `env=prod`.

### Bundle (`databricks.yml`, `resources/`)

| Resource | File | What it does |
|---|---|---|
| `dbt_job` | `resources/dbt.job.yml` | One `dbt_task` on serverless compute (environment version 5, `dbt-databricks==1.12.8`). Runs `dbt deps`, `dbt seed`, `dbt build` with `--target=${bundle.target}`. The warehouse comes from `profiles.yml`; the job has no `warehouse_id`. |

There are no pipelines, dashboards or apps. `src/notebook.ipynb` is the
template's "Hello world" notebook and is not part of any job.

The job has no schedule or trigger.

Deployed jobs (as of 2026-11-04):

| Target | Workspace | Job name | Job ID |
|---|---|---|---|
| dev | dev | `[dev nilabja_saha] dbt_job` | 466035394578471 |
| prod | prod | not deployed | — |

The first prod run in the prod workspace (run 754759551858732) succeeded on
2026-11-04. That manual prod deployment was then destroyed so CI can own prod:
`databricks bundle summary -t prod` shows `dbt_job` as not deployed, the prod
workspace has no jobs, and its `.bundle/databricks_poc/prod` folder is gone.
The data written by that run stays in `dbw_dbxpoc_prod_weu`.

### dbt project (`dbt_project.yml`, `src/`)

Merged on 2026-10-29 from
[saquibherman/dbt_core_databricks_demo](https://github.com/saquibherman/dbt_core_databricks_demo),
with its git history (commits `fa96b2c` to `993b70b`). Sources sit under `src/`
as in the Databricks `dbt-sql` bundle template.

| Layer | Models | Materialization | Notes |
|---|---|---|---|
| landing (source) | `orders`, `products`, `reviews`, `users` | seeds | Sample data in `src/seeds/landing/`, generated for this POC. Defined as source `landing` in `src/models/sources/landing_sources.yml`. |
| bronze | `bronze_orders`, `bronze_reviews`, `bronze_users`, `products_snapshot`, `product_categories` | table / snapshot / seed | `bronze_users` is tagged `contains_pii`. `products_snapshot` is a timestamp snapshot of `landing.products` on `created_at`. |
| silver | `silver_orders`, `silver_products`, `silver_users` | table | `silver_orders.order_amount` uses the `multiply_columns` macro. `silver_products` reads current rows of `products_snapshot`. |
| gold | `gold_sales__daily`, `gold_avg_rating__daily` | view | Daily revenue by product, category, vendor, city and channel; daily average rating per product. |

Tests: `unique` and `not_null` on source IDs (severity `warn`), a custom generic
test `assert_non_negative` (`src/tests/generic/`), and two unit tests
(`test_order_amount_calc`, `test_gold_avg_rating`).

Macros (`src/macros/`): `generate_schema_name` (see below),
`multiply_columns`, `current_timestamp`, `databricks__snapshot_get_time`.
Package: `dbt-labs/dbt_utils` 1.4.1.

A full `dbt build` runs 27 nodes; all passed locally and in the job runs on
2026-10-29 (dev) and 2026-11-04 (prod workspace).

## Catalogs and schemas per target

`profiles.yml` is the source of truth for dbt. `macros/generate_schema_name.sql`
builds the schema names.

| Target | Catalog | Schemas | Example |
|---|---|---|---|
| dev (local and deployed) | `dbw_dbxpoc_sbx_weu` | `<user>_landing`, `<user>_bronze`, `<user>_silver`, `<user>_gold` | `nilabja_saha_bronze` |
| prod | `dbw_dbxpoc_prod_weu` | `landing`, `bronze`, `silver`, `gold` | `dbw_dbxpoc_prod_weu.gold.gold_sales__daily` |

`<user>` is the part of the user name before `@`, with non-word characters
replaced by `_`. Locally `scripts/dbt_env.sh` sets it as `DBT_DEV_SCHEMA`; the
job passes `${workspace.current_user.short_name}` as the `dev_schema` var.

Catalogs on the metastore that matter here:

| Catalog | Created | Owner | Isolation and bindings |
|---|---|---|---|
| `dbw_dbxpoc_sbx_weu` | with the dev workspace | dev workspace admins | `ISOLATED`; dev (`7405619838309890`) read-write, prod (`7405615711496172`) read-only. `USE CATALOG`, `USE SCHEMA` and `SELECT` granted directly to nilabja.saha@knowit.se and saquib.herman@knowit.se |
| `dbw_dbxpoc_prod_weu` | 2026-10-29, SQL `CREATE CATALOG` from dev (the REST API refuses catalogs on Default Storage) | nilabja.saha@knowit.se | `ISOLATED`; prod (`7405615711496172`) read-write, dev (`7405619838309890`) read-only |
| `dbw_dbxpoc_prd_sbx_weu` | with the prod workspace (its default catalog) | prod workspace admins | `ISOLATED`; prod read-write, dev read-only. `USE CATALOG`, `USE SCHEMA` and `SELECT` granted directly to nilabja.saha@knowit.se and saquib.herman@knowit.se |

### Cross-workspace access

The bindings and grants below were set up on purpose, to compare dev and prod
data side by side. Each workspace can read the other's catalogs but write only
its own.

| From workspace | Catalog | Access | Through |
|---|---|---|---|
| dev → prod | `dbw_dbxpoc_prod_weu` | read-only | read-only binding |
| dev → prod | `dbw_dbxpoc_prd_sbx_weu` | read-only | read-only binding; `USE CATALOG`, `USE SCHEMA`, `SELECT` granted to nilabja.saha@knowit.se and saquib.herman@knowit.se |
| prod → dev | `dbw_dbxpoc_sbx_weu` | read-only | read-only binding; `USE CATALOG`, `USE SCHEMA`, `SELECT` granted to nilabja.saha@knowit.se and saquib.herman@knowit.se |

A read-only binding blocks writes from that workspace whatever the grants say.

**Risk:** code running in the prod workspace (jobs, notebooks, dbt) can read dev
data in `dbw_dbxpoc_sbx_weu` for these users. A prod model that refers to a dev
table by mistake would still run and silently publish dev data. Prod models must
only use `ref()`/`source()` resolved through the prod target. Remove the prod
binding on `dbw_dbxpoc_sbx_weu` once the comparison is no longer needed.

## How auth works

- **Databricks CLI profiles:** `adb-7405619838309890` (dev) and `dbxpoc-prd`
  (prod), both auth type `databricks-cli` (OAuth user-to-machine). Each target
  in `databricks.yml` pins its profile, so `bundle` commands pick the right one
  from `-t`.
- **Local dbt:** `profiles.yml` reads the token from `DBT_ACCESS_TOKEN` or,
  failing that, `DATABRICKS_TOKEN`. `source scripts/dbt_env.sh [profile]`
  exports a short-lived OAuth token from the CLI profile (default: dev) and
  `DBT_DEV_SCHEMA`.
- **`.env`:** `dbt_env.sh` also writes both values to `.env` (mode 600,
  git-ignored) for VS Code. dbt Power User reads `.env` through the Python
  extension's `python.envFile` setting.
- **Token lifetime:** about one hour. When dbt fails with HTTP 403 on
  `OpenSession`, run `source scripts/dbt_env.sh` again.
- **Deployed job:** Databricks injects `DBT_HOST` and `DBT_ACCESS_TOKEN`. No
  secrets are stored in the bundle.
- **Databricks Connect:** uses the same CLI profile
  (`DATABRICKS_CONFIG_PROFILE=adb-7405619838309890`). Tested against serverless
  on 2026-11-04 with databricks-connect 18.0.9.

## Deploy and run in WSL

One-time setup, from the project root:

```bash
uv sync --dev
source .venv/bin/activate
uv tool install --python 3.12 dbt-core --with dbt-databricks==1.12.8
uv tool install --python 3.12 "shandy-sqlfmt[jinjafmt]==0.32.0"
databricks auth login --host https://adb-7405619838309890.10.azuredatabricks.net
```

`.venv` holds databricks-connect 18.0.x pinned to serverless environment v5
(constraints written by `databricks environments setup-local`). dbt lives in
its own uv tool environment because dbt-databricks 1.12.8 needs protobuf 6.x
and the v5 constraints pin protobuf 5.x.

Local dbt, in each new terminal:

```bash
source scripts/dbt_env.sh
dbt debug
dbt build
```

Bundle, dev target (the profile comes from `databricks.yml`):

```bash
databricks bundle validate --strict -t dev
databricks bundle deploy -t dev
databricks bundle run dbt_job -t dev
```

Prod uses the same commands with `-t prod`. Deploy to prod only when that has
been explicitly agreed (see the conventions in `AGENTS.md`).

VS Code (local `.vscode/settings.json`, not committed):
`dbt.dbtPythonPathOverride` points at
`~/.local/share/uv/tools/dbt-core/bin/python` and `python.envFile` at `.env`.
The `claude` CLI is not on the WSL PATH; it ships with the VS Code extension
under `~/.vscode-server/extensions/anthropic.claude-code-*/resources/native-binary/`.

## Done

- 2026-10-29: Bundle generated from the `default-python` template and pushed to
  the public repo https://github.com/NilabjaSaha/databricks_poc.
- 2026-10-29: Databricks AI Dev Kit installed for Claude Code (databricks
  plugin v0.2.32, `mlflow-onboarding` skill); `.claude/`, `.github/`,
  `.vscode/` and `.ai-dev-kit/` are git-ignored.
- 2026-10-29: dbt demo merged in with history; dbt sources moved under `src/`;
  the `models:`/`seeds:` config key fixed (it named a different project, so
  layer schemas and materializations were ignored); per-user dev schemas; sample
  landing seeds; `scripts/dbt_env.sh`; `requirements.txt` folded into
  `pyproject.toml`.
- 2026-10-29: dbt Power User working in VS Code; Databricks Connect tested on
  serverless.
- 2026-10-29: Prod catalog `dbw_dbxpoc_prod_weu` created; prod root path moved
  from `/Workspace/Shared` (writable by all users) to the user's folder; dev and
  prod jobs deployed and run successfully (both in the dev workspace).
- 2026-11-04: Prod target moved to the dedicated prod workspace; CLI profiles
  pinned per target; `wh-dbxpoc-prd-2xs` created and used by the dbt prod
  output; `dbw_dbxpoc_prd_sbx_weu` bound read-only to dev.
- 2026-11-04: `dbw_dbxpoc_prod_weu` isolated (prod read-write, dev read-only);
  the old prod job (939346687312514) and its bundle folder deleted from the dev
  workspace.
- 2026-11-04: First prod run in the prod workspace succeeded; the manual prod
  deployment was then destroyed so CI can own prod.
- 2026-11-04: Dependency lock conflict fixed: serverless environment v5
  constraints kept for `.venv`, dbt and sqlfmt moved to uv tools.

## Open issues

1. **Unpushed commits.** `main` is several commits ahead of GitHub.
2. **No CI deploys prod yet.** The manual prod deployment was destroyed, so
   nothing runs prod until CI is in place.
3. **Sample data in prod.** The job runs `dbt seed` in every target, so prod's
   `landing` schema holds generated sample data, not real data.
4. **Two sources of truth for catalog and schema.** The bundle variables
   `catalog` and `schema` in `databricks.yml` are not used by any resource;
   dbt reads `profiles.yml`. They can drift.
5. **Token expires hourly** for local dbt and dbt Power User.
6. **No schedule** on `dbt_job`, and no failure notifications.
7. **No license** on the upstream dbt repo, whose code is now in this public
   repo. Not yet confirmed with its author.
8. **Python scaffolding leftovers:** `[project.scripts] main =
   "databricks_poc.main:main"` points at a module that does not exist, and
   `tests/` has only `conftest.py`.
9. **Unused prod warehouse:** `dbx_poc` (`7aba3a527638a7ac`) in the prod
   workspace is stopped and not referenced.

## Next steps

1. Push the local commits.
2. Set up CI to validate and deploy the bundle, with prod deployed only from
   CI (see also step 8).
3. Replace prod's seeded landing data with a real ingestion path, and remove
   `dbt seed` (or limit it to `product_categories`) in the prod job.
4. Make `profiles.yml` the only place catalog and schema are set: remove the
   unused bundle variables, or pass them to dbt with `--vars`.
5. Switch local dbt to `auth_type: oauth` so tokens refresh without
   `dbt_env.sh`.
6. Add a schedule (paused automatically in dev) and failure email notifications
   to `dbt_job`.
7. Run prod as a service principal instead of a user, and grant it access to
   the prod catalog.
8. Add CI checks: `databricks bundle validate --strict`, `dbt parse`,
   `sqlfmt --check`.
9. Remove the unused Python scaffolding, or add real Python code and tests.
