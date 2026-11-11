-- Reviews metric view. Applied by scripts/apply_semantics.py after dbt, with
-- {catalog}, {bronze_schema}, {silver_schema} and {gold_schema} replaced per
-- target. There is no silver_reviews, so the source is bronze_reviews; the
-- reviewer (PII) and the review text are not exposed. See docs/semantics.md.
CREATE OR REPLACE VIEW {catalog}.{gold_schema}.mv_reviews
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: >-
  Shop product reviews. One source row per review (bronze_reviews), with a
  rating from 1 to 5, joined to the current product (silver_products). Exposes
  no personal data: the reviewer and the review text are left out.
source: {catalog}.{bronze_schema}.bronze_reviews
joins:
  - name: dim_product
    source: {catalog}.{silver_schema}.silver_products
    'on': source.product_id = dim_product.id
dimensions:
  - name: review_date
    expr: DATE(source.created_at)
    display_name: Review date
    comment: Calendar day (UTC) the review was written.
    synonyms: [date, day]
  - name: review_month
    expr: "DATE(DATE_TRUNC('MONTH', source.created_at))"
    display_name: Review month
    comment: First day of the month (UTC) the review was written.
    synonyms: [month]
  - name: product_id
    expr: source.product_id
    display_name: Product ID
    comment: ID of the reviewed product.
  - name: product_name
    expr: dim_product.product_name
    display_name: Product
    comment: Name of the reviewed product.
    synonyms: [product, item, product title]
  - name: category
    expr: dim_product.category
    display_name: Product category
    comment: Category of the reviewed product, e.g. Gadget or Widget.
    synonyms: [product category, product type]
  - name: vendor
    expr: dim_product.vendor
    display_name: Vendor
    comment: Vendor of the reviewed product, e.g. Acme Corp or Globex.
    synonyms: [brand, manufacturer, supplier]
measures:
  - name: review_count
    expr: COUNT(1)
    display_name: Number of reviews
    comment: Number of reviews.
    synonyms: [reviews, number of reviews, review volume]
  - name: avg_rating
    expr: AVG(source.rating)
    display_name: Average rating
    comment: >-
      Mean star rating (1 to 5) over the reviews in the group, each review
      weighted equally. Reviews without a rating are ignored.
    synonyms: [rating, average stars, score, average score]
$$
