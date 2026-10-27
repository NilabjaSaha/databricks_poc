# dbt Core + Databricks Demo

Local development setup for dbt Core and Databricks Connect against Databricks.

## Versions

| Component | Version | Notes |
|---|---|---|
| Databricks Runtime | 18 LTS (Spark 4.1.0) | Or serverless environment v5 |
| Python | 3.12 | Required by databricks-connect (`==3.12.*`) |
| dbt-databricks | 1.12.8 | Pulls in dbt-core 1.12.x |
| databricks-connect | 18.3.7 | Must not be newer than the cluster's DBR version |
| Databricks CLI | v1.22.1 or later | Used for OAuth login |
| Java (JDK) | 21 (17 works on DBR 18) | Only needed for Scala/Java development |

## Setup

Prerequisites: [uv](https://docs.astral.sh/uv/) and the [Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/install).

```bash
uv python install 3.12
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

Authenticate with your workspace:

```bash
databricks auth login --host https://<your-workspace-url>
```

Verify the installation:

```bash
dbt --version
python -c "from databricks.connect import DatabricksSession; print(DatabricksSession.builder.serverless().getOrCreate().range(3).collect())"
```

## Notes

- dbt-databricks runs SQL through the Databricks SQL connector; Databricks Connect is for running PySpark code locally against Databricks compute.
- Do not install `pyspark` separately; it conflicts with `databricks-connect`.
- Python UDFs require the local Python minor version to match the compute's (3.12 for DBR 16.4 LTS and later).
