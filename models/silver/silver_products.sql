SELECT
    id,
    created_at,
    title as product_name,
    category,
    ean,
    vendor,
    price
FROM
{{ ref('products_snapshot') }}
WHERE dbt_valid_to is null