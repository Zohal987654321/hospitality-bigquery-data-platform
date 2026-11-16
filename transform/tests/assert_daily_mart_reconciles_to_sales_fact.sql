-- The daily mart must not gain or lose money relative to the line-level fact.
with fact as (
    select business_date, sum(net_amount) as net_sales
    from {{ ref('fct_sales_lines') }}
    where transaction_status in ('completed', 'refund')
    group by 1
),

mart as (
    select business_date, sum(net_sales) as net_sales
    from {{ ref('mart_daily_location_performance') }}
    group by 1
)

select
    coalesce(f.business_date, m.business_date) as business_date,
    f.net_sales as fact_net_sales,
    m.net_sales as mart_net_sales
from fact f
full outer join mart m using (business_date)
where abs(coalesce(f.net_sales, 0) - coalesce(m.net_sales, 0)) > 0.01
