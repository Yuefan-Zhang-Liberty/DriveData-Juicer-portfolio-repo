# DriveData-Juicer 项目执行计划

> 基于 Spark、Iceberg、Data-Juicer、Ray 与 VLM 的自动驾驶多模态数据质量闭环

## 1. 项目概述

### 1.1 背景与真实能力边界

当前已有真实基础：自动驾驶感知数据挖掘、具身智能多模态数据治理、视频/光流/3D 点云、相机位姿、多模态感知，以及 Python、PyTorch、OpenCV、CUDA、C++ 等算法工程能力。

本项目重点补齐：

1. Spark DataFrame、Spark SQL 和执行计划优化。
2. Iceberg 数据湖表、数据版本和数仓分层。
3. Ray Task、Actor、Ray Data 和资源调度的真实实践。
4. GitHub 上游 Issue、代码 PR、测试和社区 Review。
5. VLM LoRA/SFT 微调及数据质量到模型效果的归因。
6. Camera、LiDAR、Ego Pose、3D 标注的系统化数据处理。

### 1.2 项目目标

```text
nuScenes 原始数据
        ↓
Spark SQL + Iceberg 数仓
        ↓
自动驾驶长尾场景与高质量视频样本
        ↓
Data-Juicer 本地/Ray 分布式处理
        ↓
Camera Motion Consistency 自定义算子
        ↓
视频 Caption、去重、质量筛选
        ↓
VLM LoRA/SFT 微调
        ↓
数据质量与模型效果归因
        ↓
Docker 推理服务与 GitHub 上游 PR
```

### 1.3 核心成果

- 一个公开的 `DriveData-Juicer` GitHub 仓库。
- 一套 nuScenes Bronze/Silver/Gold Iceberg 表。
- 至少 10 条有业务含义的 Spark SQL。
- 至少 3 组 Spark 性能优化实验。
- 一个 `video_camera_motion_consistency_filter` 算子。
- 一套单元测试和异常视频注入测试。
- Data-Juicer Local 与 Ray 1/2/4 Worker Benchmark。
- 一次真实的小型 VLM LoRA/QLoRA 微调。
- 一组数据过滤前后模型效果对比。
- 一个 Data-Juicer Feature Issue 和一个上游 PR。
- 架构文档、数据模型文档和 3-5 分钟演示视频。

## 2. 项目边界

### 2.1 必须完成

- [x] nuScenes mini 全流程。
- [x] Spark SQL 和 Iceberg。
- [x] Data-Juicer 本地 Pipeline。
- [ ] Ray 单机多 Worker 执行。
- [x] Camera Motion Consistency 算子（代码/测试/报告完成；上游 PR 分支待 push，需先处理 pre-commit build-op-doc hook）。
- [x] 单元测试、Benchmark、README。
- [ ] GitHub Issue 与上游 PR。

### 2.2 推荐完成

- 较大 nuScenes 子集 Benchmark（nuScenes mini 只有 10 scenes，若补充更多数据 Spark 性能对比才有意义）。
- VLM LoRA/QLoRA 微调（见 §15 数据规模说明更新）。
- Docker Compose 一键启动。
- Data-Juicer Hub 自动驾驶 Recipe。

### 2.3 本期不作为核心目标

- Flink 生产级 Pipeline。
- Kubernetes、多机 Ray、从头训练大型模型。
- 完整 ROS 实车系统和完整 3D 检测研发。
- A/B Test 与因果推断体系。

这些内容不能影响主 PR 和主流程交付。

## 3. 技术栈

### 数据工程

- Python 3.11、PySpark、Spark SQL。
- Apache Iceberg、Parquet、MinIO。
- Docker Compose。

### 多模态处理

- Data-Juicer、OpenCV、FFmpeg。
- nuScenes Devkit、NumPy、PyArrow。

### 分布式计算

- Ray Core、Task、Actor、Ray Data。
- Data-Juicer Ray Executor / Ray Partitioned Executor。

### 模型与工程

- PyTorch、Transformers、PEFT、LoRA/QLoRA。
- FastAPI、pytest、pre-commit、GitHub Actions。

## 4. 资源规划

### 4.1 最低配置

```text
CPU：8 核
内存：32 GB
硬盘：150-250 GB SSD
GPU：可无
系统：Ubuntu 或 WSL2 Ubuntu
```

可完成 nuScenes mini、Spark Local、算子开发、测试和上游 PR。

### 4.2 推荐配置

```text
CPU：16 核以上
内存：64 GB
硬盘：1 TB NVMe SSD
GPU：24 GB 显存
```

可完成单机 Ray、多数视频处理和小型 VLM QLoRA。

### 4.3 理想配置

```text
CPU：24-32 核
内存：128 GB
硬盘：2 TB NVMe SSD
GPU：单卡 48 GB 或双卡 24 GB
```

### 4.4 资源原则

- mini 数据完整跑通前不下载完整 nuScenes。
- Spark、Iceberg、算子和测试必须能在无 GPU 环境运行。
- GPU 只用于 VLM 推理和微调。
- 所有 Benchmark 记录硬件、数据规模、软件版本和 Git commit。

## 5. 开发环境

推荐使用 Linux 或 WSL2 Ubuntu，不建议在原生 Windows 直接处理 Ray、FFmpeg、CUDA 和 Spark/Iceberg。

### 5.1 推荐目录

```text
~/projects/
├── data-juicer/
├── DriveData-Juicer/
├── data/nuscenes/
├── warehouse/iceberg/
└── models/
```

### 5.2 基础安装

```bash
sudo apt update
sudo apt install -y git ffmpeg openjdk-17-jdk build-essential
uv venv --python 3.11
source .venv/bin/activate
```

### 5.3 Data-Juicer 环境

```bash
git clone https://github.com/<your-name>/data-juicer.git
cd data-juicer
git remote add upstream https://github.com/datajuicer/data-juicer.git
uv pip install -e ".[generic]"
uv pip install -e ".[dev]"
uv pip install pre-commit
pre-commit install
```

视频、Ray 和模型依赖按阶段安装，避免第一天被环境问题阻塞。

## 6. 仓库结构

```text
DriveData-Juicer/
├── README.md
├── plan.md
├── pyproject.toml
├── docker/
├── configs/
├── spark/
│   ├── ingest_nuscenes.py
│   ├── build_bronze.py
│   ├── build_silver.py
│   ├── build_gold.py
│   └── sql/
├── iceberg/
├── nuscenes/               # 暂空；视频片段生成由 data_juicer/export_gold_manifest.py 负责（ffmpeg concat），
│                           # 3D 框投影和动态掩膜在 VLM caption 生成阶段再实现
├── data_juicer/
│   ├── custom_ops/
│   ├── process_local.yaml
│   └── process_ray.yaml
├── training/
├── serving/
├── benchmarks/
├── tests/
├── docs/
└── scripts/
```

## 7. 数据模型

### Bronze

- `bronze_scene`
- `bronze_sample`
- `bronze_sample_data`
- `bronze_ego_pose`
- `bronze_calibrated_sensor`
- `bronze_sample_annotation`
- `bronze_category`

### Silver

- `silver_sensor_frame`
- `silver_camera_frame`
- `silver_lidar_frame`
- `silver_ego_motion`
- `silver_object_annotation`
- `silver_scene_quality`
- `silver_sensor_alignment`

### Gold

- [x] `gold_long_tail_scene`（Phase 2 完成）
- [x] `gold_evaluation_slice`（Phase 2 完成）
- [ ] `gold_driving_clip`（依赖视频路径 + Phase 4 质量分，原料已就绪，待补建）
- [ ] `gold_video_quality_sample`（依赖 Phase 3/4 分数，原料已就绪，待补建）
- [ ] `gold_vlm_training_sample`（依赖 VLM caption 生成，Phase 6 前置）

Gold 样本至少包含视频路径、天气、时间、自车动作、目标类别、风险标签、对齐分数、相机运动一致性、质量分数和数据切分。

## 8. 总体时间表

- 开始日期：2026-08-24。
- 核心完成日期：2026-10-14。
- 包装与缓冲期：2026-10-15 至 2026-10-18。
- GitHub Review 时间不可控，项目完成日期与 PR 合并日期分别记录。

**实际执行进度（2026-08-28 更新）**：AI 驱动执行比原计划快约 5 周。Phase 0–4 已于 2026-08-24–25 完成；Phase 5（Ray）为下一阶段；Phase 6（VLM 微调）、Phase 7（上游 PR）、Phase 8（打包）待后续推进。阶段时间估算已不适用，以完成门槛和优先级排序为准。

## 9. 阶段 0：项目初始化

时间：2026-08-24 至 2026-08-26。

### 任务

- 修正简历中未真实完成的 Ray/Spark 表述。
- 创建公开仓库并 Fork Data-Juicer。
- 创建目录结构和架构草图。
- 下载 nuScenes mini。
- 配置 Python、Java、Spark 和 FFmpeg。
- 建立实验日志模板。

### 交付物

- `README.md`
- `plan.md`
- `docs/architecture.md`
- 可重复执行的环境安装步骤。

### 完成门槛

- 仓库可公开访问。
- 环境能从零重复安装。
- 不包含公司代码、公司数据或内部字段。

## 10. 阶段 1：Spark SQL 与 nuScenes 元数据

时间：2026-08-27 至 2026-09-02。

### 学习目标

- Driver、Executor、Job、Stage、Task。
- Transformation、Action、宽窄依赖和 Shuffle。
- DataFrame、Spark SQL、Partition、Cache。
- Broadcast Join、Sort Merge Join。
- `EXPLAIN` 与物理执行计划。

### 实现任务

- 读取 `scene.json`、`sample.json`、`sample_data.json`、`ego_pose.json`、`calibrated_sensor.json`、`sample_annotation.json` 和 `category.json`。
- 使用明确 Schema，正式实现中不依赖自动推断。
- 完成 Scene、Sample、Sample Data、Ego Pose、Annotation 关联。
- 编写至少 10 条业务 SQL。

### 必须完成的 SQL

1. 每个 Scene 的持续时间与 Sample 数。
2. 各类别 3D 标注数量。
3. 每个相机的数据完整率。
4. Camera 与 LiDAR 时间差分布。
5. Ego Pose 相邻帧位移与旋转变化。
6. 高行人密度场景。
7. 大车、骑行者等长尾类别场景。
8. 不同时间段的目标分布。
9. 训练集/验证集 Scene 泄漏检查。
10. 缺失标定或 Sensor Data 检查。

### 性能实验

- Broadcast Join 对比普通 Join。
- Cache 前后重复查询耗时。
- 分区数变化对 Shuffle 和耗时的影响。
- Python UDF 对比 Spark 内置表达式。

### 交付物

- `spark/ingest_nuscenes.py`
- `spark/sql/*.sql`
- Spark UI 截图。
- `benchmarks/reports/spark_week1.md`

### 完成门槛

- 能解释一次查询的逻辑计划和物理计划。
- 所有 SQL 有输入规模、输出规模和执行耗时。
- 至少一个优化有明确的性能变化原因。

## 11. 阶段 2：Iceberg 与数仓分层

时间：2026-09-03 至 2026-09-09。

### 实现任务

- 建立 Bronze/Silver/Gold 表。
- 支持幂等写入。
- 使用 Iceberg Snapshot 管理数据版本。
- 演示 Time Travel、Schema Evolution 和 Partition Evolution。
- 执行小文件合并实验。
- 建立数据质量审计表。

### 数据质量检查

- Scene 外键完整性。
- Sensor 数据缺失率。
- 时间戳单调性。
- Ego Pose 跳变。
- 标定矩阵合法性。
- Camera/LiDAR 时间同步偏差。
- 视频帧重复率。
- 数据切分泄漏。

### 完成门槛

- 同一批数据重复执行不会产生重复结果。
- 能恢复到历史 Snapshot。
- 能解释 Iceberg 与 Parquet、数据库、Hive Table 的区别。

## 12. 阶段 3：Data-Juicer 本地 Pipeline

时间：2026-09-10 至 2026-09-16。

### 实现任务

- 将 Gold 数据导出为 Data-Juicer JSONL Manifest。
- 从前视相机序列生成视频片段。
- 先运行已有轻量视频算子。
- 记录每个算子的保留率和耗时。
- 对损坏视频实现跳过和错误记录。

### 运行规模

```text
20 条视频：功能验证
100 条视频：稳定性验证
500 条视频：初步性能验证
```

### 交付物

- `data_juicer/process_local.yaml`
- Gold Manifest 导出工具。
- 处理前后样本对比。
- 算子级耗时报告。

### 完成门槛

- 一条命令完成 Gold Manifest 到清洗结果的处理。
- 一条坏视频不会导致全任务退出。
- 输出结果可重复生成。

## 13. 阶段 4：Camera Motion Consistency 算子

时间：2026-09-17 至 2026-09-23。

### 算子名称

```text
video_camera_motion_consistency_filter
```

### 算法流程

1. 按 `sampling_fps` 采样相邻帧。
2. Resize 到受控分辨率。
3. 使用 Shi-Tomasi 提取背景候选角点。
4. 使用 Lucas-Kanade Optical Flow 跟踪。
5. 使用 RANSAC 估计 Homography 或主运动。
6. 计算 Inlier Ratio、Warp Error 和运动参数。
7. 计算相机运动速度、加速度与 Jerk。
8. 聚合为 Camera Motion Consistency Score。
9. 根据阈值过滤样本。

### 设计原则

- 第一版不引入深度模型和额外 GPU 依赖。
- 逐帧流式处理，不保存整段光流。
- 峰值内存复杂度目标为 `O(H × W)`。
- 支持视频路径和预抽帧字段。
- 支持单视频、多视频和 `any/all` 策略。
- Stats 结果可缓存。

### 输出字段

```json
{
  "camera_motion_consistency": 0.91,
  "motion_smoothness": 0.93,
  "mean_inlier_ratio": 0.86,
  "mean_warp_error": 0.07,
  "max_motion_jerk": 0.14
}
```

### 故障注入测试

- 重复帧、丢帧、帧顺序交换。
- 亮度闪烁和场景突然切换。
- 时间戳跳变、Ego Pose 跳变、标定参数扰动。

### 单元测试

- 静态视频应保持高一致性。
- 平滑平移和旋转不应被大量误杀。
- 闪烁、突变和帧交换应降低分数。
- 无效路径、损坏视频、单帧视频行为明确。
- 多视频 `any/all` 和 Stats 缓存正确。

### 完成门槛

- 新测试全部通过，相邻视频算子测试不回归。
- 正常相机运动误杀率低于普通 Frame Difference。
- 算法、参数和限制可完整解释。

## 14. 阶段 5：Ray 真实实践

时间：2026-09-24 至 2026-09-30。

### 基础练习

必须独立完成：

- 一个 Ray Task 视频处理示例。
- 一个 Ray Actor 资源复用示例。
- 一个 Ray Data `map_batches` 示例。
- 一个失败任务自动重试示例。
- 一个 CPU/GPU 资源声明示例。

### Data-Juicer Benchmark

同一批数据分别运行：

```text
Local Executor
Ray 1 Worker
Ray 2 Workers
Ray 4 Workers
```

### 记录指标

- 总耗时和 videos/min。
- p50/p95 单视频耗时。
- CPU/GPU 利用率和峰值内存。
- 失败任务、重试次数和输出一致性。
- Worker 增加后的扩展效率。

### 完成门槛

- 能解释 Task、Actor、ObjectRef、Object Store。
- 能解释 `map` 与 `map_batches`。
- 能解释为什么视频/VLM 使用 Ray，而表型 SQL 使用 Spark。
- 简历中的 Ray 表述必须来自该阶段的真实代码和实验。

## 15. 阶段 6：VLM 数据构建与微调

时间：2026-10-01 至 2026-10-07。

### 任务定义

输入驾驶视频关键帧，输出结构化场景描述：

```json
{
  "road_type": "urban_intersection",
  "ego_action": "turning_left",
  "weather": "rainy",
  "important_objects": [
    {
      "type": "pedestrian",
      "relative_position": "front_left",
      "motion": "crossing"
    }
  ],
  "risk_level": "high",
  "risk_reason": "pedestrian crossing during left turn"
}
```

### 数据规模

nuScenes mini 实际可用样本：10 scenes × CAM_FRONT 滑窗 → ~534 clips → 过滤后 **~490 条**（Phase 3/4 验证数字）。与原计划 3,000-10,000 的差距来自数据集规模，非实现问题。

```text
训练集：~350-400（约 80% 可用样本）
验证集：~50-60
测试集：~50-60
```

若需要更大规模：
- 下载 nuScenes trainval subset（850 scenes）可达到 3,000+ 训练样本，需人工从 nuscenes.org 注册下载（~300GB）。
- 或使用 Waymo Open Dataset / BDD100K 等公开数据集扩充，但需要重新实现 annotation 解析管线。

**当前 mini 数据规模下的微调定性**：属于概念验证（proof-of-concept），用于展示数据过滤前后 A/B/C 归因实验逻辑，而非生产级模型训练。模型质量指标值以相对改变量（过滤后 vs 未过滤的 delta）为主，而非绝对性能。

### 数据生成原则

- 目标类别来自真实 nuScenes Annotation。
- Ego Action 来自相邻 Ego Pose。
- 相对位置来自 3D 坐标和相机投影。
- 自然语言 Caption 可由 VLM 生成。
- 结构化关键字段由规则或真实标签校验。
- 不允许把 VLM 幻觉直接写入训练集。

### 微调方案

本机 GPU：RTX 4090 24GB（已确认），符合推荐配置要求。

模型选型（按资源消耗排序，均支持 QLoRA 4-bit）：
- **首选**：`Qwen2-VL-2B-Instruct`（2B，QLoRA 后约 4-6GB 显存，适合小数据集快速迭代）
- **备选**：`LLaVA-1.5-7B`（7B QLoRA 约 8-12GB，质量稍高但训练更慢）
- 不建议用 7B 以上模型（训练时间 × 数据量不成比例）

其余约束：
- 优先 LoRA/QLoRA，不做全量微调。
- 使用低分辨率（224×224）、每 clip 抽 3-5 帧、梯度累积 4–8 步控制资源。
- 保存训练配置、随机种子和 Iceberg Snapshot。

### 评测指标

- 目标类别 Precision/Recall/F1。
- 相对位置准确率和 Ego Action 准确率。
- 风险等级 F1、JSON 合法率和幻觉率。
- 推理吞吐量和显存占用。

### 归因实验

```text
A：未经过 Data-Juicer 筛选
B：仅使用现有质量算子
C：加入 Camera Motion Consistency 算子
```

验证时序描述 F1、风险事件 F1 和幻觉率是否改善。

### 完成门槛

- 训练和评测代码可复现。
- 至少完成一次过滤前后对照实验。
- 不以主观案例代替定量指标。

## 16. 阶段 7：上游 Issue 与 PR

时间：2026-10-08 至 2026-10-14。

Feature Issue 应在算子原型稳定后尽早提出，不必等到本阶段。

### Issue 标题

```text
[Feat]: Add a flow-based video camera motion consistency filter
```

### 上游修改范围

```text
data_juicer/ops/filter/video_camera_motion_consistency_filter.py
tests/ops/filter/test_video_camera_motion_consistency_filter.py
data_juicer/utils/constant.py
data_juicer/config/config_all.yaml
```

### PR 必须包含

- Motivation 与应用场景。
- 与现有 Motion Score 算子的区别。
- 算法流程、复杂度、输入输出和参数。
- 单元测试和无效输入行为。
- 内存设计和本地/Ray兼容性。
- nuScenes 自动驾驶 Benchmark。
- 不增加强制大型依赖的说明。
- Feature Issue 链接。

### 测试命令

```bash
pytest tests/ops/filter/test_video_camera_motion_consistency_filter.py -q
pytest tests/ops/filter/test_video_motion_score_filter.py -q
pre-commit run --all-files
```

### Git 工作流

```bash
git fetch upstream
git checkout main
git rebase upstream/main
git checkout -b feat/video-camera-motion-consistency-filter

# 开发、测试、提交后
git fetch upstream
git rebase upstream/main
git push --force-with-lease
```

严禁使用普通 `git push --force`。

### 完成门槛

- CI 通过，PR 描述完整。
- 至少收到一次有效社区 Review，或已经合并。
- 对 Review 意见逐条回复并修改。
- 不在 PR 中加入大数据、模型权重和生成视频。

## 17. 阶段 8：包装与交付

时间：2026-10-15 至 2026-10-18。

### Docker 服务

建议提供：

```text
spark-iceberg
minio
data-juicer
ray-head
ray-worker
inference-api
```

### API

```text
POST /score-video-quality
POST /analyze-driving-scene
POST /mine-long-tail-scenes
GET  /health
```

### README 必须包含

- 问题定义、系统架构和数据模型。
- 环境安装和最小运行示例。
- Spark 优化结果和 Ray Benchmark。
- 算子算法、模型评测和 PR 链接。
- 已知限制、数据许可和模型许可。

### 演示视频

3-5 分钟内展示：

1. Spark/Iceberg 表和 SQL。
2. 数据质量检查。
3. Data-Juicer Pipeline。
4. Ray Dashboard。
5. 正常与异常视频打分。
6. VLM 结构化输出。
7. GitHub PR。

## 18. Benchmark 规范

### 18.1 通用要求

每个 Benchmark 记录：日期、Git commit、操作系统、CPU/内存/GPU、数据规模、Worker 数量、参数、运行次数、平均值和波动范围。

### 18.2 Spark 指标

- 总耗时、输入/输出行数。
- Shuffle Read/Write、扫描文件数和分区数。
- Join 策略和 Cache 情况。

### 18.3 Ray 指标

- videos/min、p50/p95 延迟。
- Worker 利用率和峰值内存。
- 失败、重试和扩展效率。

### 18.4 算法指标

- 正常相机运动误杀率。
- 重复帧、丢帧、帧交换和突变检测率。
- Precision、Recall、F1。

### 18.5 模型指标

- 结构化字段 F1、幻觉率和 JSON 合法率。
- 数据过滤前后变化。
- 推理吞吐和显存占用。

## 19. 风险与应对

### 环境安装耗时过长

- 先安装最小依赖，不在第一阶段安装全部模型依赖。
- 锁定 Python 3.11，保存 lock 文件和成功安装日志。

### 项目范围失控

- Flink、Kubernetes、多机 Ray 全部后置。
- 首先保证 mini 数据、算子、测试和 PR。
- 微调失败不能阻塞上游 PR。

### 算子过于自动驾驶专用

- 上游算子保持通用视频接口。
- 自动驾驶逻辑放在 Demo、Benchmark 和 Recipe。
- Issue 阶段先确认命名与接口。

### 与现有 Motion Score 重复

- 明确 Motion Magnitude 与 Motion Consistency 的差异。
- 用平滑相机运动实验展示普通帧差的误杀。
- 提供 RANSAC 主运动、Inlier Ratio 和 Warp Error。

### Ray 再次成为只会写名词

- 保留 Task、Actor、Ray Data 最小实验。
- 保存 Ray Dashboard、日志和 Benchmark。
- 面试前能现场解释资源调度和失败重试。

### VLM 资源不足

- 先完成数据、PR 和预训练模型推理。
- 使用最小模型和 QLoRA（首选 Qwen2-VL-2B，24GB 显卡足够）。
- nuScenes mini 只有 ~490 可用样本，以归因实验 delta 为核心指标，不追求绝对性能。
- 如需更大规模：下载 nuScenes trainval（~850 scenes，需注册）。

### pre-commit build-op-doc hook 网络依赖

data-juicer fork 的 pre-commit 包含 `build-op-doc` hook，调用阿里云翻译 API（`translators==6.0.1`）自动翻译算子 docstring 到中文并更新 `docs/Operators.md`。该 host 上该域名不可达，导致 hook 挂死而非快速失败（try/except 只包裹了 translate 调用，不包括 DNS/连接超时）。
**解决方案**：提交时使用 `SKIP=build-op-doc git commit ...`（只跳过该 hook，isort/black/flake8/detect-secrets 仍正常运行），并在提交信息里注明原因。不使用 `--no-verify`（会跳过所有 hook）。

### PR 长期未合并

- Issue 先行，保持修改范围小。
- 测试和文档一次提交齐全。
- 简历如实写“PR Review 中”，不能写“已合并”。

## 20. 每周执行方式

```text
周一：确定本周 Gate 和 Issue
周二至周四：实现与测试
周五：Benchmark 和文档
周六：代码整理、Commit、Review
周日：复盘和准备下一周
```

每天记录：

- 今天完成了什么。
- 遇到什么问题。
- 关键命令和日志在哪里。
- 哪个结论有实验支持。
- 明天的最小下一步是什么。

## 21. Definition of Done

项目只有同时满足以下条件，才能视为核心完成：

- [x] nuScenes mini 全流程可复现。
- [x] Spark SQL 至少 10 条。
- [x] 至少 3 组 Spark 优化实验。
- [x] Iceberg Bronze/Silver 完成；Gold 2/5 表已建，3 张剩余表原料已就绪待补建。
- [x] Snapshot、Time Travel、Schema Evolution 演示完成。
- [x] Data-Juicer Local Pipeline 完成。
- [x] 自定义算子代码和单元测试完成。
- [ ] Ray 1/2/4 Worker Benchmark 完成。
- [ ] Feature Issue 已提交。
- [ ] 上游 PR 已提交并通过 CI。
- [ ] 数据过滤前后模型或质量指标对比完成（VLM 归因实验，数据规模见 §15 更新）。
- [x] README、架构图、数据模型文档完成。
- [x] 不包含公司数据、内部代码和不可公开信息。

## 22. 简历表述规则

### PR 未提交

> 基于 Data-Juicer 与 nuScenes 开发自动驾驶多模态数据质量 Pipeline。

### PR 已提交但未合并

> 向 Data-Juicer 提交视频相机运动一致性算子 PR，当前处于社区 Review 阶段。

### PR 合并后

> 向 Data-Juicer 贡献并合并视频相机运动一致性算子，完成算法、单元测试、配置和文档。

### 项目完成后的候选描述

以下 `XX` 必须替换为真实实验结果：

- 基于 Spark SQL 与 Iceberg 构建 nuScenes 自动驾驶多模态数据湖，完成 Camera、LiDAR、Ego Pose 及 3D 标注的 Bronze/Silver/Gold 分层、质量校验与训练集版本管理，处理 `XX` 个场景和 `XX` 帧数据。
- 向 Data-Juicer 贡献 `video_camera_motion_consistency_filter`，基于 LK 光流、RANSAC 主运动估计和 Warp Error 检测重复帧、异常跳变及相机运动不连续，正常转弯场景误杀率由 `XX%` 降至 `XX%`。
- 使用 Data-Juicer Ray Executor 构建视频质量、时序一致性、Caption 和去重 Pipeline，在 `XX` 个 Worker 下达到 `XX videos/min`，相较本地执行吞吐提升 `XX` 倍。
- 使用筛选后的自动驾驶视频进行 VLM LoRA/QLoRA 微调，使结构化驾驶场景理解 F1 由 `XX` 提升至 `XX`，幻觉率降低 `XX%`。
- 提交并合并 Data-Juicer 上游 PR `#XX`，根据维护者 Review 完成接口、测试和内存优化迭代。

## 23. 面试准备清单

### Spark

- Job、Stage、Task 如何划分。
- 宽依赖、窄依赖和 Shuffle。
- Broadcast Join、数据倾斜和 Partition 选择。
- `EXPLAIN` 如何阅读。

### Iceberg

- Iceberg 与 Parquet 的区别。
- Snapshot、Time Travel、Schema/Partition Evolution。
- 为什么适合训练数据版本管理。

### Ray

- Task、Actor、ObjectRef、Object Store。
- CPU/GPU 资源声明、`map_batches`、重试和幂等。
- Ray 与 Spark 的选型差异。

### Data-Juicer

- Operator 生命周期。
- Filter、Mapper、Deduplicator 区别。
- Stats 缓存和 Local/Ray Executor。
- 新算子为什么不与 Motion Score 重复。

### 自动驾驶

- nuScenes 坐标系和 Ego Pose。
- Camera 内外参和 3D 框投影。
- 时间同步、标定质量和动态目标对光流的影响。

### VLM

- LoRA/QLoRA、SFT 数据格式和数据泄漏。
- 幻觉评测。
- 为什么数据过滤能够改变模型效果。

## 24. 最终原则

1. 不提前把未完成的技术写进简历。
2. 不使用公司数据和内部实现。
3. 不用技术名词替代真实代码与指标。
4. 优先完成上游 PR，不无限扩展功能。
5. 每个性能结论必须有可复现实验。
6. Spark 负责结构化数据和 SQL，Ray 负责非结构化视频与模型任务。
7. 上游算子保持通用，自动驾驶特色放在数据、Benchmark 和 Recipe 中。
8. 项目价值以代码、测试、PR、指标和文档衡量，而不是技术栈数量。
