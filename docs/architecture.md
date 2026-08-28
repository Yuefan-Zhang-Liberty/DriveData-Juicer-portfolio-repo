# 架构文档

## 数据流

```text
nuScenes 原始数据（Camera / LiDAR / Ego Pose / 3D 标注）
        ↓
Spark SQL 元数据 ETL
        ↓
Iceberg Bronze 表（原始结构，逐传感器/逐 JSON 落表）
        ↓
清洗、时间对齐、标定检查、3D 框投影、异常检测
        ↓
Iceberg Silver 表（对齐后的 sensor_frame / ego_motion / object_annotation / scene_quality）
        ↓
长尾场景挖掘、质量评分、训练样本生成
        ↓
Iceberg Gold 表（driving_clip / long_tail_scene / video_quality_sample / vlm_training_sample / evaluation_slice）
        ↓
JSONL Manifest 导出
        ↓
Data-Juicer（Local Executor → Ray Executor）
        ↓
video_camera_motion_consistency_filter（本项目新增算子，Phase 4 已实现/测试/验证，见
benchmarks/reports/dj_week4.md）+ 现有视频质量/去重/Caption 算子
        ↓
VLM LoRA/QLoRA 微调（结构化驾驶场景 Caption）
        ↓
数据质量 → 模型效果归因实验（A: 无过滤 / B: 已有算子 / C: + 新算子）
        ↓
FastAPI 推理服务（Docker，阶段 8）
```

## 分层职责

- **Spark + Iceberg**：负责结构化/半结构化元数据的 ETL、Join、窗口函数、数据版本（Snapshot / Time Travel / Schema Evolution），产出可复现的训练数据切分（Gold 层）。
- **Data-Juicer + Ray**：负责非结构化视频数据的处理 —— 质量过滤、去重、Caption、自定义算子，本地 Executor 验证正确性，Ray Executor 验证分布式扩展性。
- **两者的边界**：Gold 层 JSONL Manifest 是唯一的交接点。Spark/Iceberg 端不处理像素级视频内容；Data-Juicer/Ray 端不做结构化 Join 或历史版本管理。

## 数据模型（对应 Iceberg 表）

### Bronze（原始落表，逐 nuScenes JSON 表对应一张表）

`bronze_scene`、`bronze_sample`、`bronze_sample_data`、`bronze_ego_pose`、`bronze_calibrated_sensor`、`bronze_sample_annotation`、`bronze_category`

### Silver（清洗、对齐、质量标注）

`silver_sensor_frame`、`silver_camera_frame`、`silver_lidar_frame`、`silver_ego_motion`、`silver_object_annotation`、`silver_scene_quality`、`silver_sensor_alignment`

### Gold（训练/评测就绪）

`gold_driving_clip`、`gold_long_tail_scene`、`gold_video_quality_sample`、`gold_vlm_training_sample`、`gold_evaluation_slice`

Gold 样本字段至少包含：视频路径、天气、时间、自车动作、目标类别、风险标签、对齐分数、相机运动一致性分数、质量分数、数据切分（train/val/test）。

## 技术栈

| 领域 | 组件 |
|---|---|
| 数据工程 | Python 3.11、PySpark、Spark SQL、Apache Iceberg、Parquet |
| 多模态处理 | Data-Juicer、OpenCV、FFmpeg、nuScenes Devkit、NumPy、PyArrow |
| 分布式计算 | Ray Core（Task/Actor/Data）、Data-Juicer Ray Executor |
| 模型与工程 | PyTorch、Transformers、PEFT（LoRA/QLoRA）、FastAPI、pytest、pre-commit |

## 本机环境偏离说明

开发机是共享训练服务器，无 sudo：

- Java 11 + Spark 3.3.3（`/opt/spark`，系统已装）保留使用，未升级到 plan.md 建议的 Java 17 —— Iceberg 官方 Spark Runtime 对 Spark 3.3 有对应版本，不强制 Java 17。
- Docker 相关交付物（阶段 8）推迟决策，届时评估 rootless Docker / podman。
- `data-juicer/` fork 作为本仓库内的独立 git 子目录（未用 submodule，避免流程复杂化），已加入 `.gitignore`。
- Iceberg 使用 Hadoop catalog（纯文件系统，无 Hive metastore 进程）—— 无 sudo 环境下无法部署 metastore，且本项目单机运行不需要多引擎共享元数据的场景，Hadoop catalog 已足够展示 snapshot/time travel/schema evolution/partition evolution 等核心机制。见 [benchmarks/reports/iceberg_week2.md](../benchmarks/reports/iceberg_week2.md)。
- Data-Juicer manifest 中的相对视频路径按 `dataset_path` **所在目录**（即 manifest 文件自身的目录）解析，不是项目根目录或 cwd（`data-juicer/data_juicer/format/formatter.py`）—— `export_gold_manifest.py` 按此约定写相对路径。
- `av` 必须锁定在 `13.1.0`（与 `data-juicer/pyproject.toml` 自身的锁定版本一致），不能装最新版：更新版本会破坏 `mm_utils.py` 里 `close_video()` 用到的 `VideoCodecContext.close()` API。
- **所有 dj-process yaml 里每个算子都必须显式写 `auto_op_parallelism: false`，不能漏。** 原因：`auto_op_parallelism` 默认 `True`，为 `True` 时 `num_proc` 由 `calculate_np()`（`data-juicer/data_juicer/utils/process_utils.py`）自动计算——若算子未声明 `memory`/`num_cpus` 需求（多数视频/文本过滤算子都没声明），该函数会退化成 `num_proc = psutil.cpu_count()`；`available_memories()` 同样读 `psutil.virtual_memory()`（`data-juicer/data_juicer/utils/resource_utils.py`）。这两者都是**主机级**资源探测，不感知容器 cgroup 内存上限。本机是 224 核/999GB 的共享服务器，但运行容器通常有几十到上百 GB 的内存上限，若某个 yaml 漏写 `auto_op_parallelism: false`，Data-Juicer 会按主机核数 fork 出上百个并发 cv2 视频解码子进程，足以在容器内触发 OOM Kill（`exit_code=137`，内核直接杀进程，没有 Python traceback）——曾在 `data_juicer/process_local.yaml` 上实际发生过一次（该文件当时缺了这个字段，已修复并补充了行内注释）。新增/修改任何 dj-process 配置前，先确认每个算子都带这个字段。
- 本机（共享、224 核、多用户训练服务器）上运行 `dj-process` 需要显式设置环境变量 `MP_START_METHOD=fork`。原因：Data-Juicer 对注册在 `UNFORKABLE`（如 `video_motion_score_filter`，用了 cv2）里的算子会强制使用 `forkserver`/`spawn` 起多进程，但这两种方式在本机上都会触发 `multiprocessing.context.AuthenticationError: digest sent was rejected`（推测是与其他用户并发的多进程作业争抢 socket/semaphore 导致，未完全定位，仅做了充分的经验验证）；而普通 `fork` 在本机上对所有算子都稳定可用。已给 `data-juicer/` fork 的 `data_juicer/utils/process_utils.py` 打了一个最小、可选启用的 patch：只有显式设置 `MP_START_METHOD` 时才覆盖 Data-Juicer 强制指定的候选启动方式列表，不设置该环境变量时行为不变。见 [benchmarks/reports/dj_week3.md](../benchmarks/reports/dj_week3.md)。

## 未决问题

- nuScenes mini 数据获取方式（需要人工在 nuscenes.org 完成注册与下载）。
- Data-Juicer 上游仓库地址以 `https://github.com/modelscope/data-juicer` 为准（已用 `git ls-remote` 验证可达）；个人 Fork 地址待创建后补充为 git remote。
