# Governance: PII tags and column masks

`scripts/apply_governance.py` tags personal data and masks email addresses,
driven by `pii_columns` in `config/ingestion.yml`. It runs as the last task of
`dbt_job`:

```
ingest_landing  ──▶  dbt  ──▶  apply_governance
```

Every run applies everything again; all statements are idempotent. The task
prints a summary (`TAGGED`, `MASKED`, `SKIPPED`, `FAILED`) and fails if any
statement failed.

## What is tagged

For every source with `pii_columns`, those columns get two column tags:

| Tag | Value |
|---|---|
| `pii` | `true` |
| `pii_source` | the source's `source_system`, e.g. `shop` |

They are applied in three tables per source, where the table and the column
exist (anything else is listed under `SKIPPED`):

| Layer | Table | Today |
|---|---|---|
| landing | `<landing_schema>.<target_table>` | `users`: `name`, `email`, `zip`, `birth_date`; `reviews`: `reviewer` |
| bronze | `<bronze_schema>.bronze_<target_table>` | same columns in `bronze_users`, `bronze_reviews` |
| silver | `<silver_schema>.silver_<target_table>` | nothing: `silver_users` has none of the PII columns, there is no `silver_reviews` |

Landing tables are pipeline-owned streaming tables, so the script uses
`ALTER STREAMING TABLE` for them and `ALTER TABLE` for dbt's tables.

`pii` and `pii_source` are ordinary tags, not governed tags, so setting them
only needs `APPLY TAG` on the table, which the table owner has.

Find tagged columns:

```sql
SELECT schema_name, table_name, column_name, tag_name, tag_value
FROM <catalog>.information_schema.column_tags
WHERE tag_name IN ('pii', 'pii_source')
ORDER BY schema_name, table_name, column_name;
```

## How the email mask works

`governance/mask_email.sql` defines `<catalog>.governance.mask_email`. The
script creates `<catalog>.governance` if needed, runs the file with `{catalog}`
replaced (`CREATE OR REPLACE FUNCTION`), and attaches the function:

```sql
ALTER TABLE <catalog>.<bronze_schema>.bronze_users
  ALTER COLUMN email SET MASK <catalog>.governance.mask_email;
```

From then on every query of `bronze_users.email` goes through the function:

| Caller | Sees |
|---|---|
| Member of the workspace group `admins` | the real address, e.g. `user1@example.com` |
| Anyone else, including `sp-dbxpoc-cicd` | first letter and domain, e.g. `u***@example.com` |

Check that the mask is attached:

```sql
DESCRIBE TABLE EXTENDED <catalog>.<bronze_schema>.bronze_users;
-- "# Column Masks" section: email | `<catalog>`.`governance`.`mask_email`
```

The masks to attach are listed in `MASKS` in the script.

**`is_member('admins')` checks the `admins` group of the workspace that runs
the query.** Dev and prod share one metastore, and dev can read prod catalogs
(read-only binding), so dev workspace admins see real emails in prod data when
they query it from dev. An account group with `is_account_group_member()`
would avoid that; it was kept as `is_member('admins')` on purpose for now.

## Why on bronze, and why after dbt

**Bronze, not silver.** Silver is PII-free by design: `silver_users` keeps
`city`, `state`, `birth_year` and `sales_channel` and drops `name`, `email`,
`zip` and `birth_date`. `bronze_users` is the first dbt table that still has
`email`. The landing streaming table is only tagged, not masked: a mask on a
pipeline-owned table belongs in the pipeline definition.

**After dbt.** dbt rebuilds its tables on every run (`CREATE OR REPLACE TABLE
AS SELECT`), and new tables or columns only exist after `dbt build`. Running
governance as the task after `dbt` tags and masks whatever dbt produced, and
the job only finishes successfully once tags and masks are in place.

Tested in dev on 2026-11-09: rebuilding `bronze_users` with
`dbt run -s bronze_users` kept both the column mask and the column tags.
`CREATE OR REPLACE` doesn't remove them, so there is no unmasked window
between the `dbt` and `apply_governance` tasks, and no dbt `post_hook` is
needed.

**Consequences:**

- dbt runs as a non-admin in prod (`sp-dbxpoc-cicd`), so a dbt model that reads
  `bronze_users.email` would get masked values. No model does today.
- The landing streaming table `users` (and `reviews.reviewer`) is tagged but
  not masked: anyone who can read the landing schema sees real emails there.

## Permissions

| Target | Identity | Needs | Status |
|---|---|---|---|
| dev | the developer | `CREATE SCHEMA` on `dbw_dbxpoc_sbx_weu` (or an existing `governance` schema it can create functions in); owner of its own tables | in place |
| prod | `sp-dbxpoc-cicd` | `USE CATALOG`, `CREATE SCHEMA` on `dbw_dbxpoc_prd_sbx_weu`; it then owns `governance` and `mask_email`; owner of the landing, bronze and silver tables it creates | in place (granted 2026-11-05) |

The service principal needs no extra grant: it creates and owns the
`governance` schema and the function, and it owns the tables it tags and
masks, which covers `APPLY TAG`, `SET MASK` and `EXECUTE`.

In dev, all developers share the `governance` schema of
`dbw_dbxpoc_sbx_weu`. Whoever runs the task first owns `mask_email`; another
developer's `CREATE OR REPLACE FUNCTION` then fails unless they get `MANAGE` on
the function (or the schema has a group owner).
