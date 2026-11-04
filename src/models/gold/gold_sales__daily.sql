select
    o.order_date,
    p.product_name,
    p.category,
    p.vendor,
    u.city,
    u.state,
    u.sales_channel,
    sum(o.order_amount) as total_revenue
from {{ ref("silver_orders") }} o
left join {{ ref("silver_products") }} p on o.product_id = p.id
left join {{ ref("silver_users") }} u on o.user_id = u.id
group by all
