# DriveData-Juicer

基于 Spark、Iceberg、Data-Juicer、Ray 与 VLM 的自动驾驶多模态数据质量闭环。

完整执行计划见 [plan.md](plan.md)。

## 状态

项目处于**阶段 4（新算子 `video_camera_motion_consistency_filter`）**，2026-08-24 启动，阶段 0/1/2/3
已完成，阶段 4 实现/测试/基线对比/端到端验证已完成（上游 PR 未开，需用户确认后再开）：

- [x] 仓库骨架与目录结构
- [x] 环境安装步骤验证
- [x] nuScenes mini 下载
- [x] Data-Juicer fork 与上游 PR 分支
- [x] Spark：11 张 nuScenes 元数据表显式 Schema 摄取为 Bronze Parquet
- [x] Spark：10 个业务 SQL 查询（含窗口函数、四元数角度计算）+ 4 组性能对比实验
- [x] Spark/Iceberg Bronze-Silver-Gold 数仓（Iceberg 部分）
- [x] Data-Juicer 本地 Pipeline（Gold Manifest 导出、4 个现有视频算子、20/100/500 三档规模、坏视频跳过、可复现性验证）
- [x] `video_camera_motion_consistency_filter` 算子（Shi-Tomasi + LK 光流 + RANSAC 单应矩阵，15 个单测、
      与帧差基线的判别力对比、tier-20 端到端联跑）
- [ ] 上游 PR（实现/测试/文档已就绪，开 PR 前需用户确认）
- [ ] VLM LoRA/SFT 微调与数据质量归因实验

Phase 1 产出见 [benchmarks/reports/spark_week1.md](benchmarks/reports/spark_week1.md)（查询结果）、
[benchmarks/reports/spark_week1_perf.md](benchmarks/reports/spark_week1_perf.md)（性能实验+解读）、
[benchmarks/reports/spark_week1_explain.md](benchmarks/reports/spark_week1_explain.md)（逻辑/物理执行计划，
因无浏览器环境用 `EXPLAIN` 文本替代 Spark UI 截图）。

Phase 2 产出见 [benchmarks/reports/iceberg_week2.md](benchmarks/reports/iceberg_week2.md)（Bronze/Silver/Gold
表清单、8 项数据质量检查结果、5 个 Iceberg 机制实验、Iceberg vs. Parquet/数据库/Hive Table 对比），
[benchmarks/reports/iceberg_week2_experiments.md](benchmarks/reports/iceberg_week2_experiments.md)（实验原始输出）。
Gold 层 5 张表中仅 2 张（`gold_long_tail_scene`、`gold_evaluation_slice`）已实现，其余 3 张依赖 Phase 3/4
才会产生的视频片段与质量分数，已在报告中明确标注为延后。

Phase 3 产出见 [benchmarks/reports/dj_week3.md](benchmarks/reports/dj_week3.md)（20/100/500 三档规模的逐算子
留存率与耗时、坏视频跳过证据、两次独立运行输出逐字节一致的可复现性验证）。Gold 层 Manifest 由
`data_juicer/export_gold_manifest.py` 生成：nuScenes mini 仅 10 个场景，通过对每个场景的 CAM_FRONT 帧序列做
滑动窗口（24 帧窗口、4 帧步长、~83% 重叠）拼出 534 个有重叠的片段以覆盖 500 档规模，报告中明确说明这不是
534 段独立录制的视频。

Phase 4 产出见 [benchmarks/reports/dj_week4.md](benchmarks/reports/dj_week4.md)：新算子
`video_camera_motion_consistency_filter`（Shi-Tomasi 角点 + LK 光流 + RANSAC 单应矩阵拟合，
`camera_motion_consistency = mean_inlier_ratio * motion_smoothness`）、开发中发现并修复的两个
量化 bug（用单应矩阵自身平移项而非 RANSAC 内点位移作运动信号；未按片段自身速度归一化平滑度）、
15 个单测、与帧差基线的判别力对比（用能拦住全部合成故障片段所需的阈值反推正常片段的误杀率：
本算子 33.33% vs. 基线 100.00%，且基线对亮度闪烁/帧乱序完全不敏感）、tier-20 端到端联跑验证
（含损坏片段跳过、5 个算子全部正常完成，exit 0）。

进度以 [plan.md](plan.md) 中各阶段的完成门槛为准。

## 架构

见 [docs/architecture.md](docs/architecture.md)。

## 环境

开发机为共享训练服务器（224 核 / 999GB 内存 / RTX 4090 24GB，NFS 存储），无 sudo 权限。相较 plan.md 中的推荐环境，做了以下调整：

- 使用已有的 OpenJDK 11 + Spark 3.3.3（`/opt/spark`），未安装 Java 17 —— Iceberg Spark Runtime 对 Spark 3.3 有官方支持，不强制要求 Java 17。
- Docker 暂缓：无 sudo 无法安装 Docker daemon，阶段 8 再评估 rootless Docker / podman 方案。
- Python 环境用 `uv` 管理，`uv venv --python 3.11` 由 uv 自行下载解释器，不依赖系统包管理器。

### 快速开始（逐步补充）

```bash
# Data-Juicer 开发环境（fork 后的 data-juicer/ 子目录中）
cd data-juicer
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[generic]"
uv pip install -e ".[dev]"
uv pip install pre-commit
pre-commit install
```

## 目录结构

```text
DriveData-Juicer/
├── README.md
├── plan.md
├── docker/
├── configs/
├── spark/
│   ├── ingest_nuscenes.py
│   ├── build_bronze.py
│   ├── build_silver.py
│   ├── build_gold.py
│   └── sql/
├── iceberg/
├── nuscenes/
│   ├── build_video_clips.py
│   ├── project_3d_boxes.py
│   ├── build_dynamic_masks.py
│   └── inject_corruptions.py
├── data_juicer/
│   ├── custom_ops/
│   ├── process_local.yaml
│   └── process_ray.yaml
├── training/
├── serving/
├── benchmarks/
├── tests/
├── docs/
├── scripts/
├── logs/            # 实验日志，不进版本控制
└── data-juicer/     # Data-Juicer fork（独立 git 仓库，见 .gitignore）
```

## 数据许可

nuScenes 数据集受其自身许可协议约束，不会提交到本仓库；本仓库只包含处理代码、配置和不含原始数据的实验结果。
