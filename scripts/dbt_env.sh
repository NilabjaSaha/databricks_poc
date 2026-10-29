# Source this file to point local dbt at Databricks using your CLI login:
#
#   source scripts/dbt_env.sh [cli-profile]
#
# Exports a short-lived OAuth token (re-source when it expires, ~1h) and your
# personal dev schema, matching ${workspace.current_user.short_name} used by
# the deployed dev job.

_dbt_profile="${1:-${DATABRICKS_CONFIG_PROFILE:-adb-7405619838309890}}"

DATABRICKS_TOKEN="$(databricks auth token -p "$_dbt_profile" -o json \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])')" || return 1
DBT_DEV_SCHEMA="$(databricks current-user me -p "$_dbt_profile" -o json \
  | python3 -c 'import json, re, sys; print(re.sub(r"\W", "_", json.load(sys.stdin)["userName"].split("@")[0]).lower())')" || return 1
export DATABRICKS_TOKEN DBT_DEV_SCHEMA

# Also write them to .env (git-ignored) for VS Code / dbt Power User
_dbt_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
(umask 077 && printf 'DATABRICKS_TOKEN=%s\nDBT_DEV_SCHEMA=%s\n' "$DATABRICKS_TOKEN" "$DBT_DEV_SCHEMA" > "$_dbt_root/.env")

echo "dbt: profile=$_dbt_profile dev schema=$DBT_DEV_SCHEMA (also written to .env)"
unset _dbt_root
unset _dbt_profile
