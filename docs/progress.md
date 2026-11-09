# Progress

Status of the `databricks_poc` project: a Declarative Automation Bundle (DAB)
that deploys a dbt Core project to Databricks.

Last updated: 2026-11-05 (old prod catalog dropped). Workspace facts (jobs, runs, warehouses, catalog
bindings and grants) were checked on 2026-11-04; the service principal, its
access and the prod schemas on 2026-11-05.

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
| `dbt_job` | `resources/dbt.job.yml` | Task `ingest_landing` (`pipeline_task` on `ingestion_pipeline`), then task `dbt` (depends on it; skipped if ingestion fails): `dbt_task` on serverless compute (environment version 5, `dbt-databricks==1.12.8`) running `dbt deps`, `dbt seed` (only `product_categories`), `dbt build` with `--target=${bundle.target}`. The warehouse comes from `profiles.yml`; the job has no `warehouse_id`. |

| `ingestion_pipeline` (`ingestion_landing`) | `resources/ingestion.pipeline.yml` | Serverless Lakeflow Declarative Pipeline. Reads `config/ingestion.yml` and loads each source with Auto Loader from `${var.landing_root}` into a streaming table in `${var.landing_schema}`. See `docs/ingestion-framework.md`. |

Bundle variables for ingestion: `landing_root` (dev:
`/Volumes/dbw_dbxpoc_sbx_weu/raw/landing/`, prod:
`/Volumes/dbw_dbxpoc_prd_sbx_weu/raw/landing/`) and `landing_schema` (dev:
`${workspace.current_user.short_name}_landing`, prod: `landing`).

There are no dashboards or apps. `src/notebook.ipynb` is the template's "Hello
world" notebook and is not part of any job.

The job has no schedule or trigger. In prod it runs as the service principal
`sp-dbxpoc-cicd` (`run_as` in `databricks.yml`).

Deployed jobs (as of 2026-11-04):

| Target | Workspace | Job name | Job ID |
|---|---|---|---|
| dev | dev | `[dev nilabja_saha] dbt_job` | 466035394578471 |
| prod | prod | not deployed | — |

The first prod run in the prod workspace (run 754759551858732) succeeded on
2026-11-04. That manual prod deployment was then destroyed so CI can own prod:
`databricks bundle summary -t prod` shows `dbt_job` as not deployed, the prod
workspace has no jobs, and its `.bundle/databricks_poc/prod` folder is gone.
Since PR #3, prod uses the prod workspace's default catalog
`dbw_dbxpoc_prd_sbx_weu`. CD run `#42041046902` (2026-11-05) succeeded and
created `landing`, `bronze`, `silver` and `gold` there, owned by
`sp-dbxpoc-cicd`.

### CI/CD (GitHub Actions, `.github/workflows/`)

| Workflow | Job | Trigger | What it does |
|---|---|---|---|
| `ci.yml` | `ci` | pull request to `main`, manual | Installs dbt and sqlfmt from `requirements-dbt.txt`; `sqlfmt --check src/`; `dbt deps`; `dbt parse` for `dev` and `prod`, offline with dummy values. No secrets, `contents: read`. |
| `cd.yml` | `deploy-prod` | push to `main`, manual | Waits for approval on the GitHub environment `prod`; Databricks CLI 1.22.1; writes the `dbxpoc-prd` profile for `sp-dbxpoc-cicd` (OAuth M2M) from `vars.DATABRICKS_HOST` and `secrets.DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET`; `bundle validate --strict`, `bundle deploy`, `bundle run dbt_job` for `prod`; step summary. Concurrency group `prod-deploy`, never cancelled. |

Prod is deployed only by CD: merge to `main` → approval on the `prod`
environment → deploy and run as `sp-dbxpoc-cicd`. **Prod must not be deployed
from laptops any more.**

The prod `root_path` is `/Workspace/Users/${workspace.current_user.userName}/.bundle/...`,
which for CD is the service principal's own folder. A fixed path in a user's
folder would fail: the service principal is not a workspace admin and has no
access to user folders.

Service principal `sp-dbxpoc-cicd` (application ID
`e33d9717-3d53-4d8d-a39c-f1b2ff4512dc`), as of 2026-11-05: active, no groups,
entitlements `workspace-access`, `databricks-sql-access`, `workspace-consume`;
`CAN_USE` on `wh-dbxpoc-prd-2xs`; `USE CATALOG`, `USE SCHEMA`, `CREATE SCHEMA`
on the prod catalog `dbw_dbxpoc_prd_sbx_weu`.

### dbt project (`dbt_project.yml`, `src/`)

Merged on 2026-10-29 from
[saquibherman/dbt_core_databricks_demo](https://github.com/saquibherman/dbt_core_databricks_demo),
with its git history (commits `fa96b2c` to `993b70b`). Sources sit under `src/`
as in the Databricks `dbt-sql` bundle template.

| Layer | Models | Materialization | Notes |
|---|---|---|---|
| landing (source) | `orders`, `products`, `reviews`, `users` | streaming tables (ingestion pipeline) | Loaded from files under `landing_root` by `ingestion_landing`; see `docs/ingestion-framework.md`. The files are generated sample data for this POC. Defined as source `landing` in `src/models/sources/landing_sources.yml`. |
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
| prod | `dbw_dbxpoc_prd_sbx_weu` | `landing`, `bronze`, `silver`, `gold` | `dbw_dbxpoc_prd_sbx_weu.gold.gold_sales__daily` |

`<user>` is the part of the user name before `@`, with non-word characters
replaced by `_`. Locally `scripts/dbt_env.sh` sets it as `DBT_DEV_SCHEMA`; the
job passes `${workspace.current_user.short_name}` as the `dev_schema` var.

Catalogs on the metastore that matter here:

| Catalog | Created | Owner | Isolation and bindings |
|---|---|---|---|
| `dbw_dbxpoc_sbx_weu` | with the dev workspace | dev workspace admins | `ISOLATED`; dev (`7405619838309890`) read-write, prod (`7405615711496172`) read-only. `USE CATALOG`, `USE SCHEMA` and `SELECT` granted directly to nilabja.saha@knowit.se and saquib.herman@knowit.se |
| `dbw_dbxpoc_prd_sbx_weu` (**prod**) | with the prod workspace (its default catalog) | prod workspace admins | `ISOLATED`; prod (`7405615711496172`) read-write, dev (`7405619838309890`) read-only. Grants: `sp-dbxpoc-cicd`: `USE CATALOG`, `USE SCHEMA`, `CREATE SCHEMA`; nilabja.saha@knowit.se: `ALL PRIVILEGES` + `MANAGE`; saquib.herman@knowit.se: read-only (`USE CATALOG`, `USE SCHEMA`, `SELECT`); prod workspace users: `USE CATALOG` |

### Cross-workspace access

The bindings and grants below were set up on purpose, to compare dev and prod
data side by side. Each workspace can read the other's catalogs but write only
its own.

| From workspace | Catalog | Access | Through |
|---|---|---|---|
| dev → prod | `dbw_dbxpoc_prd_sbx_weu` | read-only | read-only binding; grants to nilabja.saha@knowit.se and saquib.herman@knowit.se (see above) |
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
uv tool install --python 3.12 dbt-core --with-requirements requirements-dbt.txt --with-executables-from shandy-sqlfmt
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

Prod is deployed only by CD (see "CI/CD" above), never from a laptop. Locally,
`databricks bundle validate --strict -t prod` is still fine.

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
- 2026-11-05: Prod `run_as` set to `sp-dbxpoc-cicd`; prod `root_path` follows
  the deploying identity; GitHub Actions CI (`ci`) and prod CD (`deploy-prod`)
  added (PR #1), with the service principal in the prod bundle permissions
  (PR #2). First successful CD run: `#42034493138`, into `dbw_dbxpoc_prod_weu`.
- 2026-11-05: Prod catalog switched to `dbw_dbxpoc_prd_sbx_weu`, the prod
  workspace's default catalog (PR #3); first successful CD run on it:
  `#42041046902`. `dbw_dbxpoc_prod_weu` was then dropped.
- 2026-11-05: Ingestion config `config/ingestion.yml` with a validator in CI.
- 2026-11-06: Metadata-driven ingestion pipeline (`ingestion_landing`) added.
  In dev the dbt-seeded landing tables were dropped by hand, and the pipeline
  created them as streaming tables: orders 300, products 20, reviews 120,
  users 50 rows (matching the CSVs), no `NULL` `created_at`, no rescued data.
- 2026-11-07: Step F4. Landing seeds removed (`src/seeds/landing/`); `dbt seed`
  only loads `product_categories`. `dbt_job` now runs `ingest_landing` (the
  pipeline) before `dbt`. Full dev job run succeeded.
- 2026-11-07: Incremental test in dev: one new file
  `shop/orders/orders_2026_11_07.csv` (orders `90001`, `90002`). The update
  ingested 2 orders and 0 rows for the other tables; `landing.orders` went from
  300 to 302 with `_source_file` pointing at the new file, and both orders
  reached `silver_orders`.
- 2026-11-08: Prod ingestion live: `feat/metadata-ingestion` merged (PR #5);
  CD run `#42531947606` succeeded. Prod has the volume `raw.landing`, and
  `landing.orders` is a streaming table owned by `sp-dbxpoc-cicd`.
- 2026-11-09: G1 governance: `apply_governance` task after `dbt` tags every
  `pii_columns` column (`pii`, `pii_source`) in landing and bronze and masks
  `bronze_users.email` with `<catalog>.governance.mask_email`. Two dev job runs
  succeeded (10 tagged, 1 masked, 5 skipped, 0 failed). A rebuild of
  `bronze_users` keeps the mask and the tags. See `docs/governance.md`.

## Open issues

1. **`ci` is not a required check.** The `protect-main` ruleset requires pull
   requests and blocks deletion and force pushes, but does not require the `ci`
   status check. (The `prod` environment, its required reviewers, the variable
   `DATABRICKS_HOST` and the two secrets are set up.)
2. **Sample data only.** The landing files are generated sample data; there
   is no real source system feeding `landing_root` yet.
3. **Two sources of truth for catalog and schema.** The bundle variables
   `catalog` and `schema` in `databricks.yml` are not used by any resource;
   dbt reads `profiles.yml`. They can drift.
4. **Token expires hourly** for local dbt and dbt Power User.
5. **No schedule** on `dbt_job`, and no failure notifications.
6. **No license** on the upstream dbt repo, whose code is now in this public
   repo. Not yet confirmed with its author.
7. **Python scaffolding leftovers:** `[project.scripts] main =
   "databricks_poc.main:main"` points at a module that does not exist, and
   `tests/` has only `conftest.py`.
8. **Unused prod warehouse:** `dbx_poc` (`7aba3a527638a7ac`) in the prod
   workspace is stopped and not referenced.
9. **CI does not validate the bundle.** `databricks bundle validate` needs
   workspace auth, and CI uses no secrets; CD validates before deploying.
10. **Dev admins see real prod emails.** `mask_email` uses
    `is_member('admins')`, which checks the admins group of the workspace that
    runs the query. Dev can read prod catalogs (read-only binding), so dev
    workspace admins querying prod `bronze_users` from dev get real emails. An
    account group with `is_account_group_member()` would avoid it.
11. **The service principal sees masked emails.** `sp-dbxpoc-cicd` is not an
    admin, so a future dbt model reading `bronze_users.email` in prod would get
    masked values (no model does today).
12. **Shared dev governance schema.** All developers share
    `dbw_dbxpoc_sbx_weu.governance`. The first to run `apply_governance` owns
    `mask_email`; another developer's `CREATE OR REPLACE FUNCTION` fails until
    they get `MANAGE` on it (or the schema gets a group owner).
13. **`landing.users` is readable unmasked.** The landing streaming tables are
    tagged but not masked, so anyone who can read the landing schema sees real
    names, emails, zips and birth dates (and `reviews.reviewer`).

## Next steps

1. Add `ci` as a required check in `protect-main`.
2. Decide the mask identity check (open issue 10) and how to protect
   `landing.users` (open issue 13), then merge `feat/governance-semantics`.
3. Make `profiles.yml` the only place catalog and schema are set: remove the
   unused bundle variables, or pass them to dbt with `--vars`.
4. Switch local dbt to `auth_type: oauth` so tokens refresh without
   `dbt_env.sh`.
5. Add a schedule (paused automatically in dev) and failure email notifications
   to `dbt_job`.
6. Remove the unused Python scaffolding, or add real Python code and tests.
