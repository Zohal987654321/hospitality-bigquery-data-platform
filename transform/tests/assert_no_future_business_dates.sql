-- Sales dated in the future usually mean a timezone or clock problem at the source.
select transaction_line_key, business_date
from {{ ref('fct_sales_lines') }}
where business_date > date_add(current_date('Australia/Sydney'), interval 1 day)
