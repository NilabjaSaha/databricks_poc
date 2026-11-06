"""
Metadata-driven ingestion.

Reads config/ingestion.yml and creates one Auto Loader streaming table
per source in the target's landing schema.
"""

import yaml
from pyspark import pipelines as dp
from pyspark.sql import functions as F

# --- 1. Environment settings -------------------------------------------------
# Both values come from the pipeline "configuration" in the bundle (Step F3.3),
# so this code has no environment-specific paths in it.
LANDING_ROOT = spark.conf.get("landing_root")           # volume today, ADLS later
CONFIG_PATH = spark.conf.get("ingestion_config_path")   # deployed copy of config/ingestion.yml

# --- 2. Load the metadata ----------------------------------------------------
with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

SOURCES = CONFIG["sources"]

# --- 3. Table factory --------------------------------------------------------
def define_landing_table(src: dict) -> None:
    """Register one streaming table for one config entry."""
    source_path = LANDING_ROOT.rstrip("/") + "/" + src["path"]
    expectations = src.get("expectations", {})

    def read_source():
        return (
            spark.readStream.format("cloudFiles")                       # Auto Loader
            .option("cloudFiles.format", src["format"])
            .option("cloudFiles.schemaHints", src["schema_hints"])
            .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
            .options(**src.get("options", {}))                          # e.g. header=true
            .load(source_path)
            .withColumn("_ingested_at", F.current_timestamp())
            .withColumn("_source_file", F.col("_metadata.file_path"))
        )

    # Data quality: wrap the reader with each non-empty expectation level
    if expectations.get("warn"):
        read_source = dp.expect_all(expectations["warn"])(read_source)
    if expectations.get("drop"):
        read_source = dp.expect_all_or_drop(expectations["drop"])(read_source)
    if expectations.get("fail"):
        read_source = dp.expect_all_or_fail(expectations["fail"])(read_source)

    # Register it as a streaming table in the pipeline's target schema
    dp.table(
        name=src["target_table"],
        comment=f"Raw {src['name']} from {src['source_system']}, ingested by Auto Loader (config-driven).",
        table_properties={
            "dbxpoc.source_system": src["source_system"],
            "dbxpoc.pii_columns": ",".join(src.get("pii_columns", [])),
            **{f"dbxpoc.tag.{k}": str(v) for k, v in src.get("tags", {}).items()},
        },
    )(read_source)


# --- 4. Build everything from the config -------------------------------------
for src in SOURCES:
    define_landing_table(src)