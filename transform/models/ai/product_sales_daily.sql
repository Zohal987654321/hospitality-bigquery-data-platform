select
    l.location_name,
    f.business_date,
    p.product_category,
    p.product_name,
    sum(f.quantity)                     as quantity_sold,
    sum(f.net_amount)                   as net_sales,
    sum(f.estimated_cost_of_goods)      as estimated_cogs
from {{ ref('fct_sales_lines') }} f
join {{ ref('dim_location') }} l using (location_key)
join {{ ref('dim_product') }} p using (product_key)
where f.transaction_status in ('completed', 'refund')
group by 1, 2, 3, 4
