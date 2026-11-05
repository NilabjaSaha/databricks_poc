# Declarative Automation Bundles Project

This project uses Declarative Automation Bundles (DABs) for deployment. Add project-specific instructions below.

## For AI Agents: Use Databricks AI Tools

**BEFORE any other action, read the `databricks-core` skill.**

It sets you up to work with this project reliably: CLI authentication, profile
selection, data discovery, and the bundle deployment workflow. Without it,
results are often slower and less accurate.

If this skill is not available (Databricks AI Tools are not installed), you can install them for your coding agent in seconds:

```bash
databricks aitools install
```

If the CLI is not installed, see: https://docs.databricks.com/dev-tools/cli/install

---

## Project Instructions

<!-- Add your project-specific instructions, coding conventions, or notes here -->

Project status, open issues and next steps: [docs/progress.md](docs/progress.md).

## Conventions

### Databricks CLI profiles

| Target | Profile | Workspace |
|---|---|---|
| dev | `adb-7405619838309890` | `https://adb-7405619838309890.10.azuredatabricks.net` |
| prod | `dbxpoc-prd` | `https://adb-7405615711496172.12.azuredatabricks.net` |

- `databricks.yml` pins the profile per target, so `bundle` commands only need
  `-t <target>`. For other CLI commands, pass `-p <profile>` explicitly.

### Catalog, schema and warehouse per target

| Target | Catalog | Schemas | SQL warehouse |
|---|---|---|---|
| dev | `dbw_dbxpoc_sbx_weu` | `<user>_landing`, `<user>_bronze`, `<user>_silver`, `<user>_gold` (e.g. `nilabja_saha_bronze`) | `wh-dbxpoc-sbx-2xs` |
| prod | `dbw_dbxpoc_prd_sbx_weu` | `landing`, `bronze`, `silver`, `gold` | `wh-dbxpoc-prd-2xs` |

- Prod catalog grants: `sp-dbxpoc-cicd` has `USE CATALOG`, `USE SCHEMA`,
  `CREATE SCHEMA`; nilabja.saha@knowit.se has `ALL PRIVILEGES` + `MANAGE`;
  saquib.herman@knowit.se is read-only.
- dbt reads catalogs from `profiles.yml`; `src/macros/generate_schema_name.sql`
  builds the schema names. Change both together.
- Don't hardcode catalog or schema names in models; use `ref()`, `source()` and
  `target`.

### Naming

- Bundle resource files: `resources/<name>.<resource_type>.yml` (e.g.
  `dbt.job.yml`).
- dbt models: `<layer>_<entity>.sql` in `src/models/<layer>/`, layers
  `bronze`, `silver`, `gold`. Gold aggregates add a grain suffix with a double
  underscore: `gold_sales__daily`.
- dbt property files start with an underscore: `_silver.yml`, `_gold.yml`.
- Seeds that stand in for source data go in `src/seeds/landing/`.
- Names of catalogs, schemas, tables and columns: lowercase `snake_case`.

### Deployment

- **Deploy and run to `dev` only.** Prod is deployed only by CD
  (`.github/workflows/cd.yml`, as `sp-dbxpoc-cicd`), never from a laptop.
- Run `databricks bundle validate --strict -t <target>` before every deploy.
- Don't create, change or delete workspace resources (catalogs, schemas,
  grants, warehouses, jobs) outside the bundle without asking first.

### Secrets

- **Never commit secrets**: tokens, passwords, `.env`, `~/.databrickscfg`, or
  the contents of `~/.databricks/`.
- Credentials come from the environment only. `profiles.yml` reads
  `DBT_ACCESS_TOKEN` / `DATABRICKS_TOKEN`; locally `scripts/dbt_env.sh` sets
  them.
- Check `git diff --cached` for secrets before every commit. This repo is
  public.
