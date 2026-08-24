"""Shared SparkSession builder with the Iceberg Hadoop catalog configured.

No Hive metastore is available on this shared, no-sudo cluster, so we use
Iceberg's Hadoop catalog: a pure filesystem catalog with no metastore process,
identified by the catalog name "local" and rooted at --warehouse-dir. Every
Phase-2 script imports build_spark() from here instead of re-declaring the
Iceberg jars/extensions/catalog config.
"""
import os

from pyspark.sql import SparkSession

ICEBERG_PACKAGE = "org.apache.iceberg:iceberg-spark-runtime-3.3_2.12:1.4.3"


def build_spark(warehouse_dir, app_name="nuscenes-iceberg", shuffle_partitions="8"):
    warehouse_dir = os.path.abspath(warehouse_dir)
    return (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.jars.packages", ICEBERG_PACKAGE)
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        .config("spark.sql.catalog.local", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.local.type", "hadoop")
        .config("spark.sql.catalog.local.warehouse", warehouse_dir)
        .config("spark.sql.shuffle.partitions", shuffle_partitions)
        .getOrCreate()
    )
