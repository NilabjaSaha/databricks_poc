{#
    Schema naming shared with the ingestion pipeline: the landing schema built
    here (<dev_schema>_landing in dev, landing in prod) must equal
    landing_schema in databricks.yml, and dev_schema must match DBT_DEV_SCHEMA
    in scripts/dbt_env.sh. Change all three together.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}

    {%- set default_schema = target.schema -%}
    {%- if custom_schema_name is none -%}

        {{ default_schema }}

    {%- elif target.name == 'prod' -%}

        {{ custom_schema_name | trim }}

    {%- else -%}

        {# Keep each developer's objects apart: <dev_schema>_<custom schema> #}
        {{ default_schema }}_{{ custom_schema_name | trim }}

    {%- endif -%}

{%- endmacro %}
