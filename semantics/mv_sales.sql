-- Sales metric view. Applied by scripts/apply_semantics.py after dbt, with
-- {catalog}, {silver_schema} and {gold_schema} replaced per target.
-- See docs/semantics.md.
CREATE OR REPLACE VIEW {catalog}.{gold_schema}.mv_sales
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: >-
  Shop sales. One source row per order (silver_orders: one product, a quantity
  and a unit price per order), joined to the current product (silver_products)
  and the ordering customer (silver_users). Revenue is quantity times unit
  price. Contains no personal data.
source: {catalog}.{silver_schema}.silver_orders
joins:
  - name: dim_product
    source: {catalog}.{silver_schema}.silver_products
    'on': source.product_id = dim_product.id
  - name: dim_user
    source: {catalog}.{silver_schema}.silver_users
    'on': source.user_id = dim_user.id
dimensions:
  - name: order_date
    expr: source.order_date
    display_name: Order date
    comment: Calendar day the order was placed.
    synonyms: [date, day, order day, sales date]
  - name: order_week
    expr: "DATE(DATE_TRUNC('WEEK', source.order_date))"
    display_name: Order week
    comment: Monday of the week the order was placed.
    synonyms: [week, sales week]
  - name: order_month
    expr: "DATE(DATE_TRUNC('MONTH', source.order_date))"
    display_name: Order month
    comment: First day of the month the order was placed.
    synonyms: [month, sales month]
  - name: category
    expr: dim_product.category
    display_name: Product category
    comment: Category of the ordered product, e.g. Gadget or Widget.
    synonyms: [product category, product type]
  - name: product_name
    expr: dim_product.product_name
    display_name: Product
    comment: Name of the ordered product.
    synonyms: [product, item, product title]
  - name: vendor
    expr: dim_product.vendor
    display_name: Vendor
    comment: Vendor of the ordered product, e.g. Acme Corp or Globex.
    synonyms: [brand, manufacturer, supplier]
  - name: city
    expr: dim_user.city
    display_name: Customer city
    comment: City of the customer who placed the order.
    synonyms: [customer city, town]
  - name: state
    expr: dim_user.state
    display_name: Customer state
    comment: State of the customer who placed the order.
    synonyms: [customer state, region]
  - name: sales_channel
    expr: dim_user.sales_channel
    display_name: Sales channel
    comment: >-
      Channel through which the customer signed up (the users source column
      `source`), e.g. Affiliate, Facebook, Google, Organic or Twitter.
    synonyms: [channel, source, acquisition channel, marketing channel]
measures:
  - name: total_revenue
    expr: SUM(source.order_amount)
    display_name: Total revenue
    comment: >-
      Sum of quantity times unit price over all orders, in the shop's currency.
      Before discounts, tax and returns (the source has none).
    synonyms: [revenue, sales, turnover, sales amount, gmv]
  - name: order_count
    expr: COUNT(1)
    display_name: Number of orders
    comment: Number of orders. Each order has exactly one product.
    synonyms: [orders, number of orders, order volume]
  - name: avg_order_value
    expr: MEASURE(total_revenue) / MEASURE(order_count)
    display_name: Average order value
    comment: Total revenue divided by the number of orders, in the shop's currency.
    synonyms: [aov, average basket, revenue per order]
  - name: units_sold
    expr: SUM(source.quantity)
    display_name: Units sold
    comment: Sum of the ordered quantity (number of product units) over all orders.
    synonyms: [units, quantity, items sold, volume]
$$
