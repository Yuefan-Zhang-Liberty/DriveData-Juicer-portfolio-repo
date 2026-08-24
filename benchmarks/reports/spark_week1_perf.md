# Spark Week 1 — Performance Experiments

## broadcast_join_vs_sort_merge_join

- broadcast_join_times_s: [1.301, 0.059, 0.054]
- sort_merge_join_times_s: [0.603, 0.035, 0.055]
- broadcast_uses_BroadcastHashJoin: True
- sort_merge_uses_SortMergeJoin: True

## cache_vs_no_cache_repeated_query

- uncached_times_s: [0.347, 0.044, 0.045]
- cached_times_s: [0.076, 0.042, 0.048]

## shuffle_partitions_2_vs_8_vs_200

- partition_2_times_s: [0.356, 0.036, 0.025]
- partition_8_times_s: [0.278, 0.023, 0.029]
- partition_200_times_s: [0.278, 0.035, 0.025]

## python_udf_vs_builtin_expression

- builtin_times_s: [0.703, 0.408, 0.393]
- python_udf_times_s: [0.926, 0.353, 0.454]

## 结果解读

以下解读基于 nuScenes **mini**（10 个 Scene、404 个 Sample、31206 条 sample_data）的实测结果，
在讨论"为什么某项优化更快"之前，先说明为什么这批实验在当前数据规模下差异不明显：

- **每组实验第一次运行都明显慢于后两次**（如 broadcast 1.301s → 0.059s → 0.054s）。这是 Spark
  在 `local[*]` 模式下的一次性开销 —— Catalyst 生成物理计划、Whole-Stage CodeGen 编译字节码、
  JVM JIT 预热 —— 而不是这几个算子本身的执行差异。三次重复取后两次更能反映稳态性能。
- **Broadcast Join vs Sort-Merge Join**：`EXPLAIN` 确认两侧计划分别落到 `BroadcastHashJoin` 和
  `SortMergeJoin`（Physical Plan 已验证，见上方 boolean 字段）。稳态耗时（0.054s vs 0.055s）几乎
  相同，原因是 `sample_annotation`(18538) / `instance`(911) / `category`(23) 三表在 mini 规模下
  数据量太小，即使走 Shuffle+Sort 也几乎不产生 I/O 或排序开销；Broadcast 省掉的 Shuffle 在这个
  数据量级下本身就不到 10ms。**结论**：两种策略在算法复杂度上确有差异（Sort-Merge 是
  O(n log n) 排序 + 全 Shuffle，Broadcast 是 O(1) 网络广播 + Map 端 Join），但要在小表 Join 上
  观测到有意义的时间差，需要把 `sample_annotation` 侧放大到百万行级（即完整 nuScenes 或人工放大
  的数据集）才能体现 —— 这是本阶段"数据规模不足以体现优化效果"的真实结论，而非优化本身无效。
- **Cache vs 无 Cache**：稳态耗时（0.042~0.048s vs 0.044~0.045s）同样接近，因为源数据是本地
  Parquet 文件，OS Page Cache 已经让重复读取几乎零 I/O 成本；Spark 层的 `.cache()` 在这种场景下
  节省的主要是重新执行 Join 的 CPU，而 Join 本身在小数据量下 CPU 成本也很低。在更大数据量或
  多次迭代（如迭代式特征工程）下，`.cache()` 的收益会随 Join 复杂度和重复次数线性放大。
- **Shuffle Partition 数量（2 / 8 / 200）**：三者稳态耗时几乎一致，原因同上 —— Shuffle 的数据量
  本身很小（几十到几千行），无论分成 2 个还是 200 个 Partition，每个 Task 的调度开销
  （几毫秒/Task）都远大于其处理的数据量本身。200 个 Partition 理论上会增加 Task 调度开销
  （更多 Task = 更多 Driver-Executor 通信),但在单机 `local[*]` 模式下这个开销也被摊薄。
  **在真实分布式集群 + 大数据量下**，too few partitions 会导致每个 Task 处理数据过多、并行度不足；
  too many partitions 会导致调度开销超过实际计算时间——这是本实验在 mini 规模下无法复现、
  但原理上确定成立的效应。
- **Python UDF vs 内置表达式**：两者稳态耗时接近（0.35~0.45s 量级）,因为数据量只有几百行，
  UDF 的 Python 进程间序列化开销（pickle 往返、逐行调用 Python 解释器）在这个行数下不足以
  被放大到可观测的量级。已知的理论机制是：内置表达式（`sqrt`/`pow`）在 JVM 内以 Whole-Stage
  CodeGen 编译执行，UDF 则必须序列化每一行数据到 Python 进程、执行、再序列化回 JVM，
  这个往返在数据量增大后会呈线性甚至更差的开销增长。

**后续行动**：待 Phase 2 完成 Iceberg 数仓、Phase 3+ 处理更大规模数据（更多 nuScenes 场景或
Silver/Gold 层展开的逐帧记录）后，在 `sample_annotation` 规模达到十万至百万行时重跑本实验，
预期能观测到 Broadcast Join、Cache、合理 Partition 数、内置表达式的优势被真实放大。
