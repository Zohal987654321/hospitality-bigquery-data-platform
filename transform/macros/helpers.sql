{#- Deterministic surrogate key from one or more columns. -#}
{% macro surrogate_key(fields) -%}
    to_hex(md5(concat(
        {%- for f in fields %}
        coalesce(cast({{ f }} as string), '_null_'){% if not loop.last %}, '|',{% endif %}
        {%- endfor %}
    )))
{%- endmacro %}


{#- Trading (business) date: local time minus the cutoff, e.g. 1:30am Sat -> Friday. -#}
{% macro business_date(timestamp_col, timezone_col) -%}
    date(timestamp_sub(
        timestamp(datetime({{ timestamp_col }}, {{ timezone_col }})),
        interval {{ var('trading_day_cutoff_hour') }} hour
    ))
{%- endmacro %}


{#- Latest version of each record in an append-only raw table. -#}
{% macro latest_version(source_relation) -%}
    select *
    from {{ source_relation }}
    where true  -- explicit WHERE keeps QUALIFY valid on every BigQuery edition
    qualify row_number() over (
        partition by _record_key
        order by _source_updated_at desc, _ingested_at desc
    ) = 1
{%- endmacro %}


{#- Typed accessors for the JSON payload column. -#}
{% macro j_str(path) -%} json_value(payload, '$.{{ path }}') {%- endmacro %}
{% macro j_num(path) -%} safe_cast(json_value(payload, '$.{{ path }}') as numeric) {%- endmacro %}
{% macro j_ts(path) -%} safe_cast(json_value(payload, '$.{{ path }}') as timestamp) {%- endmacro %}
