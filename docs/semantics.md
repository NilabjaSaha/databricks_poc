# Semantics: metric views

Two Unity Catalog metric views define the shop's business metrics once, so
SQL, AI/BI dashboards and Genie all compute revenue, orders and ratings the
same way.

| Metric view | Source | Joined to | Measures |
|---|---|---|---|
| `<gold_schema>.mv_sales` | `silver_orders` | `silver_products`, `silver_users` | `total_revenue`, `order_count`, `avg_order_value`, `units_sold` |
| `<gold_schema>.mv_reviews` | `bronze_reviews` | `silver_products` | `review_count`, `avg_rating` |

The definitions are in `semantics/*.sql`, one `CREATE OR REPLACE VIEW ... WITH
METRICS LANGUAGE YAML` statement per file. Every measure and dimension has a
`comment`, a `display_name` and, where useful, `synonyms`; Genie reads them to
match questions to columns, so keep them accurate when you change a definition.

## How they are deployed

`scripts/apply_semantics.py` runs as the `apply_semantics` task of `dbt_job`,
after `dbt` and next to `apply_governance`:

```
ingest_landing  ──▶  dbt  ──┬──▶  apply_governance
                            └──▶  apply_semantics
```

It replaces `{catalog}`, `{bronze_schema}`, `{silver_schema}` and
`{gold_schema}` in each file with the bundle variables of the target and runs
the statement. It prints `CREATED` and `FAILED` and fails the task if any view
failed.

| Target | Metric views in | Reads from |
|---|---|---|
| dev | `dbw_dbxpoc_sbx_weu.<user>_gold` | `<user>_silver`, `<user>_bronze` |
| prod | `dbw_dbxpoc_prd_sbx_weu.gold` | `silver`, `bronze` |

It runs after `dbt` because the views read dbt's tables and live in dbt's gold
schema, which dbt creates. It doesn't depend on `apply_governance`: the views
expose no masked or PII columns. In prod the views are created and owned by
`sp-dbxpoc-cicd`, which owns the gold schema, so no extra grant is needed.

To add a metric view, add a `semantics/<name>.sql` file with the same
placeholders; the task picks it up on the next run.

## `mv_sales`

One source row per order. In this shop an order has exactly one product, a
quantity and a unit price.

| Measure | Definition | Notes |
|---|---|---|
| `total_revenue` | `SUM(order_amount)` | `order_amount` = `quantity * unit_price` (silver). Before discounts, tax and returns, which the source doesn't have. |
| `order_count` | `COUNT(1)` | Number of orders. |
| `avg_order_value` | `MEASURE(total_revenue) / MEASURE(order_count)` | Computed from the two measures after aggregation, so it is correct at any grouping (not an average of averages). |
| `units_sold` | `SUM(quantity)` | Product units ordered. |

| Dimension | From | Notes |
|---|---|---|
| `order_date` | `silver_orders.order_date` | Day the order was placed. |
| `order_week` | `DATE_TRUNC('WEEK', order_date)` | Monday of the week. |
| `order_month` | `DATE_TRUNC('MONTH', order_date)` | First day of the month. |
| `category`, `product_name`, `vendor` | `silver_products` | Current product attributes (the snapshot's open rows). |
| `city`, `state`, `sales_channel` | `silver_users` | The ordering customer. `sales_channel` is the users source column `source` (Affiliate, Facebook, Google, Organic, Twitter). |

## `mv_reviews`

One source row per review. There is no `silver_reviews`, so the source is
`bronze_reviews`, the same table `gold_avg_rating__daily` reads. The reviewer
(PII) and the review text are not exposed.

| Measure | Definition | Notes |
|---|---|---|
| `review_count` | `COUNT(1)` | Number of reviews. |
| `avg_rating` | `AVG(rating)` | Mean of the 1–5 star ratings, each review weighted equally, computed from the reviews in the group (not an average of daily averages). |

| Dimension | From | Notes |
|---|---|---|
| `review_date` | `DATE(created_at)` | Day the review was written (UTC). |
| `review_month` | `DATE_TRUNC('MONTH', created_at)` | First day of the month. |
| `product_id`, `product_name`, `category`, `vendor` | `bronze_reviews.product_id`, `silver_products` | The reviewed product. |

## Querying

Measures are read with `MEASURE()`; dimensions are grouped as usual:

```sql
SELECT category, MEASURE(total_revenue), MEASURE(order_count)
FROM <catalog>.<gold_schema>.mv_sales
GROUP BY ALL;

SELECT order_month, sales_channel, MEASURE(avg_order_value)
FROM <catalog>.<gold_schema>.mv_sales
WHERE category = 'Gizmo'
GROUP BY ALL;
```

Measures can't appear in `GROUP BY` (`GROUP_BY_AGGREGATE`); to filter or sort
on a measure, aggregate in a subquery first.

## Why metric views on silver

- **Re-aggregation at any grain.** `gold_sales__daily` and
  `gold_avg_rating__daily` are pre-aggregated at a fixed grain. Ratios and
  averages can't be rolled up from them correctly: the average of daily
  averages is not the average rating, and order counts are lost. A metric view
  aggregates the row-level data at query time, for whatever grouping is asked.
- **One definition.** The joins and formulas live in one place instead of in
  every dashboard query or Genie answer.
- **Silver is the right input.** It is cleaned, typed, PII-free, and at order
  or review grain; bronze would expose PII, and gold has already lost the
  grain. The reviews view uses bronze only because there is no silver reviews
  model, and it leaves out the PII column.
- **Joins are many-to-one.** `silver_orders.product_id` and `user_id`, and
  `bronze_reviews.product_id`, each point at a unique `id` in
  `silver_products` / `silver_users` (checked in dev on 2026-11-11), so the
  joins can't multiply rows. Metric view joins are left joins, like the gold
  models' joins.

The gold tables stay for consumers that want a plain table.

## Verified in dev (2026-11-11)

Job run `1044477649508741`, all four tasks succeeded:

- `mv_sales` total revenue by category equals `SUM(total_revenue)` of
  `gold_sales__daily` for every category (Doohickey 25,047.38, Gadget
  14,576.08, Gizmo 17,689.47, Widget 13,117.44; total 70,430.37).
- At `gold_sales__daily`'s full grain (date, product, category, vendor, city,
  state, channel) there are no rows that differ.
- `order_count` is 302, the row count of `silver_orders`.
- `mv_reviews` `avg_rating` by review date and product equals
  `gold_avg_rating__daily` on all 114 rows; `review_count` totals 120.
- The comments are in `information_schema.columns`; `order_week` always falls
  on a Monday.
