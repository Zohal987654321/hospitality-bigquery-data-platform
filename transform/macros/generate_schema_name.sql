{#-
  prod: models land in clean dataset names (staging, marts, ai ...).
  dev:  everything is prefixed with the developer's dataset (dbt_alex_marts ...),
        so nobody can overwrite production while building.
-#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- elif target.name == 'prod' -%}
        {{ custom_schema_name | trim }}
    {%- else -%}
        {{ target.schema }}_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
