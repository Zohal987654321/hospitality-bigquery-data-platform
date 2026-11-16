{#- Fails when the combination of columns is not unique (no package dependency). -#}
{% test unique_combination(model, columns) %}
    select {{ columns | join(', ') }}, count(*) as n
    from {{ model }}
    group by {{ columns | join(', ') }}
    having count(*) > 1
{% endtest %}


{#- Fails when a numeric column falls outside [min_value, max_value]. -#}
{% test within_range(model, column_name, min_value=none, max_value=none) %}
    select *
    from {{ model }}
    where {{ column_name }} is not null
      and (
        false
        {% if min_value is not none %} or {{ column_name }} < {{ min_value }} {% endif %}
        {% if max_value is not none %} or {{ column_name }} > {{ max_value }} {% endif %}
      )
{% endtest %}
