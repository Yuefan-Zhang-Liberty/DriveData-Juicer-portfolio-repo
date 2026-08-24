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
video_camera_motion_consistency_filter（本项目新增算子）+ 现有视频质量/去重/Caption 算子
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

## 未决问题

- nuScenes mini 数据获取方式（需要人工在 nuscenes.org 完成注册与下载）。
- Data-Juicer 上游仓库地址以 `https://github.com/modelscope/data-juicer` 为准（已用 `git ls-remote` 验证可达）；个人 Fork 地址待创建后补充为 git remote。
