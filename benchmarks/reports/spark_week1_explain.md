# Spark Week 1 — Query Plan Walkthrough (Q6: high_pedestrian_density_scenes)

> **Note on Spark UI screenshots**: this environment is a headless shared training
> cluster with no browser access, so `plan.md`'s "Spark UI 截图" deliverable is
> substituted here with the actual `EXPLAIN EXTENDED` output (raw text in
> [`spark_week1_explain.txt`](./spark_week1_explain.txt)), annotated below.
> `EXPLAIN` shows the same DAG information the Spark UI's SQL tab renders
> (stages, exchanges, join strategy) — text form, not a rendering, but the same
> underlying plan.

Query: `spark/sql/06_high_pedestrian_density_scenes.sql` — 5-way join across
`scene`, `sample`, `sample_annotation`, `instance`, `category`, filtered to
`category.name LIKE 'human.pedestrian%'`.

## 1. Parsed → Analyzed → Optimized Logical Plan

- **Parsed**: raw AST from the SQL text — table/column names are still
  `'Unresolved`, joins are in the order written (5 nested `Join Inner`).
- **Analyzed**: Catalyst resolves every `'UnresolvedRelation` against the
  catalog (temp views backed by the bronze Parquet paths) and every column
  reference gets a unique expression id (`name#5`, `token#14`, ...) — this is
  how Spark disambiguates the same column name (`token`) appearing in five
  different tables.
- **Optimized**: two rule-based optimizations are visible —
  - **Predicate pushdown**: `Filter isnotnull(token#0)` and the
    `category.name LIKE 'human.pedestrian%'` filter are pushed down to sit
    directly above each `Relation`, before any join, instead of after all
    five joins as written in the SQL.
  - **Column pruning**: each `Project [...]` right above a `Relation` only
    keeps the columns needed downstream (e.g. `scene` keeps just
    `[token#0, name#5]` out of its 7 columns) — this shrinks what actually
    gets read/shuffled.

## 2. Physical Plan

```
AdaptiveSparkPlan isFinalPlan=false
 Sort (final ORDER BY avg_pedestrians_per_sample DESC)
  Exchange rangepartitioning(...)        <- shuffle for the global sort
   HashAggregate (final)                 <- combine partial counts per scene name
    Exchange hashpartitioning(name#5)    <- shuffle so all rows of one scene land on one task
     HashAggregate (partial, merge)
      HashAggregate (partial, distinct-count buffer)
       Exchange hashpartitioning(name#5, token#14)
        HashAggregate (partial count)
         BroadcastHashJoin x4            <- all 5 tables joined via broadcast, no shuffle
          BroadcastExchange + FileScan parquet ...  (x5, one per source table)
```

Key facts this plan demonstrates (used as the "explain a plan" completion-gate
evidence for Phase 1):

- **All 4 joins compiled to `BroadcastHashJoin`**, not `SortMergeJoin`. Catalyst
  chose this automatically because every table on the build side
  (`scene`=10 rows, `sample`=404, `sample_annotation`=18538, `instance`=911,
  `category`=23 after the pedestrian filter) is well under
  `spark.sql.autoBroadcastJoinThreshold` (default 10MB). Each `BroadcastExchange`
  materializes the smaller side once and ships it to every executor, so the
  larger side is scanned exactly once with no shuffle.
- **Distinct-count aggregation needs 3 stacked `HashAggregate`s**, not one.
  `COUNT(DISTINCT s.token)` can't be merged with a simple partial/final split
  like a plain `COUNT`, because partial results from different partitions can
  contain the same token twice. Spark's plan handles this by first grouping on
  `(name, token)` to de-duplicate per-partition, then aggregating that
  deduplicated result by `name` alone — hence the extra `Exchange
  hashpartitioning(name#5, token#14)` between two of the `HashAggregate`s.
- **Two separate shuffle boundaries** (`Exchange hashpartitioning(name#5,
  token#14)` for dedup, `Exchange hashpartitioning(name#5)` for the final
  per-scene aggregate) plus a **third** `Exchange rangepartitioning(...)` for
  the final `ORDER BY`. Three shuffle stages for one query is the direct cost
  of combining `GROUP BY` + `COUNT(DISTINCT ...)` + `ORDER BY` — each requires
  redistributing rows by a different key.
- **`AdaptiveSparkPlan isFinalPlan=false`**: Adaptive Query Execution (AQE) is
  enabled by default in Spark 3.3; this plan is the *initial* plan before AQE
  can re-optimize based on runtime statistics (e.g., it could in principle
  demote a broadcast join to sort-merge if the actual materialized side turns
  out too large — irrelevant here since all sides are tiny).

Full raw output (Parsed/Analyzed/Optimized Logical Plan + Physical Plan) is in
[`spark_week1_explain.txt`](./spark_week1_explain.txt), captured via
`df.explain(mode="extended")`.
