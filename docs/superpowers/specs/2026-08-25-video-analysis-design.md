# 录像分析服务设计（MVP）

日期：2026-08-25  
状态：待实现

## 1. 背景与目标

做一套屏幕录像分析服务：用户上传软件操作录像，系统用多模态模型识别界面上的操作，把操作描述和界面文字写成文本向量；审计人员用自然语言检索，点中结果后跳到对应时间继续播放。

第一期场景是合规审计，检索目标是「做了什么、在哪个时间点」。不识别操作人。

### 1.1 成功标准

用 3–5 条真实屏幕录像作固定评测集，每条事先标好 5–10 个「问题 → 应跳到的时间区间」。同时满足：

1. 上传后能分析完成，状态变为 `ready`
2. 自然语言能搜到对应录像；点击某条录像或其下某条命中后，能跳到标注区间内（允许前后 5 秒误差）
3. 命中项能展示操作描述或 OCR，能对上画面
4. 至少有一条只能靠界面文字命中的查询（例如「客户名单」）必须由 OCR 全文检索命中
5. 分析中途杀掉 Worker 再启动，能从断点续跑，不整片重做

第一期不卡分析时延，准比快重要。

### 1.2 明确不做（第一期）

- 操作人识别、账号体系、权限
- MinIO / S3 等对象存储（本地目录即可）
- 独立向量库（Qdrant / Milvus）
- 视频原生多模态 embedding 作为主检索
- GUI 控件树 / 鼠标点击检测
- 实时或分钟级分析 SLA
- 剪辑导出、分享链接

## 2. 约束与规模

| 项 | 取值 |
|---|---|
| 录像类型 | 软件屏幕录像（点击、表单、跳转、弹窗、报错） |
| 检索方式 | 完全开放的自然语言 |
| 部署 | 开发期用云 API，上线再私有化；模型必须可替换 |
| 规模 | 单条最长约 1 小时；每天约 100 条 |
| 存储 | 本地目录 |
| 向量 | Postgres + pgvector，与元数据同一库 |

## 3. 技术选型

主路径：**抽帧 → OCR + 视觉模型写操作描述 → 文本向量 + 关键词混合检索 → 播放器按时间跳转。**

不把视频片段直接编成向量。屏幕录像的有效信息在界面文字和操作语义；文本向量可解释、可做关键词检索、也更容易换成本地模型。

### 3.1 模型

| 职责 | 开发期 | 私有化期 |
|---|---|---|
| 操作描述 | 通义千问 VL（DashScope） | 本地 Qwen2.5-VL / Qwen3-VL |
| Embedding | BGE-M3（1024 维，中英） | 同一模型本地跑 |
| OCR | RapidOCR | 本地 ONNX，不依赖云；私有化不变 |

系统只依赖两个模型接口，云厂商和权重都不泄漏到业务层：

- `caption(frames, ocr_text) -> str`
- `embed(text) -> vector[1024]`

视觉模型不可用时，该片段降级为「只用 OCR 文本做 embedding」，caption 标记为降级，检索仍可用。

### 3.2 数据与运行时

| 职责 | 选型 | 说明 |
|---|---|---|
| 元数据 + 向量 + 全文 | PostgreSQL 16+，扩展 `pgvector` | 向量用 HNSW；关键词用 jieba + `tsvector`，不另装中文分词插件 |
| 任务队列 | Redis + Celery | 分析是慢任务，必须异步、可续跑 |
| 对象文件 | 本地目录 | `data/videos/{video_id}/` |
| 后端 | Python 3.12 + FastAPI | 对接模型生态 |
| 前端 | React + Vite，原生 `<video>` | 上传、列表、检索、跳转播放 |
| 抽帧 | ffmpeg | 按 2 秒抽帧并探测时长 |

检索接口保持稳定。若日后向量量到千万级或需要更强的稀疏向量混合检索，再把 `VectorIndex` 换成 Qdrant / Milvus；文件存储同理，日后把 `Storage` 换成 S3 / MinIO。

### 3.3 为什么不用独立向量库（MVP）

每天约 100 条、按 3–8 秒切段，大约每天 5–12 万条向量。这个量级 Postgres HNSW 足够。片段时间轴、任务状态本来就要进关系表，pgvector 避免再运维一套向量服务。

关键词检索不用等 pgvector 的稀疏向量能力：OCR 和描述里的原词（「导出」「客户名单」）用分词后的 `tsvector` 即可。

## 4. 架构

四层，模型和存储都走适配器。

```
浏览器
  ├─ 录像库（上传 / 状态 / 重新分析）
  └─ 检索与播放（搜索 / 命中列表 / 播放器）
        │
        ▼
FastAPI（同步 API：上传、列表、搜索、拉流）
        │
        ├─ PostgreSQL（videos / jobs / segments + embedding + FTS）
        ├─ 本地目录（原片、代表帧）
        └─ Redis + Celery Worker
                ├─ ffmpeg 抽帧、切段
                ├─ OCR
                ├─ CaptionAdapter（Qwen-VL）
                └─ EmbedAdapter（BGE-M3）
```

第一期无用户体系。单机 API + 1 个或多个 Worker 即可覆盖 MVP 规模。

## 5. 数据流

### 5.1 上传

1. `POST /api/videos` 接收 `mp4` / `webm` / `mov`，单文件上限 4GB
2. 分配 `video_id`，原片写入 `data/videos/{video_id}/source.mp4`
3. 用 ffmpeg 探测时长；探测失败则拒绝，不入队
4. 写入 `videos`（`status=queued`），投入 Celery 队列
5. 接口立即返回 `video_id`，不等分析完成

### 5.2 切段

屏幕录像几乎静止，不能只靠镜头切换。

1. 每 2 秒抽一帧
2. 用画面差异把连续相似帧收成一段
3. 最短约 2 秒（合并闪烁碎段），最长约 8 秒（同一页久留也要切开）
4. 每段保留 1–3 张代表帧，优先段末帧（通常是操作结果）
5. 代表帧存 `data/videos/{video_id}/frames/{t_start_ms}.jpg`

第一期不做鼠标轨迹或点击检测。

### 5.3 每段抽文字并索引

对代表帧 OCR，得到界面原文。把代表帧和 OCR 交给视觉模型，生成一句中文操作描述，例如：「在客户列表页点击导出，对话框文件名为客户名单.xlsx」。

写入 `segments` 一行，字段见第 6 节。`embedding` 的输入文本为 `caption + "\n" + ocr_text`（caption 降级时只用 `ocr_text`）。

中文全文：写入时用 jieba 对 `caption` 和 `ocr_text` 分词，空格拼接后 `to_tsvector('simple')`。不依赖 Postgres 中文分词插件，私有化时少装一个扩展。

全部应处理片段结束后，`videos.status = ready`，才允许出现在搜索结果里。未 `ready` 的录像只出现在录像库，展示进度。

### 5.4 检索

1. 查询文本走同一套 BGE-M3，得到 query 向量
2. 两路召回，每路最多 50 条片段：
   - pgvector 余弦近邻（语义，如「改过权限」）
   - `tsvector` 匹配（OCR/描述原词，如「客户名单」）
3. Reciprocal Rank Fusion 合并，得到片段级排序。API 里的 `score` / `best_score` 是融合分，只用于排序和展示，不是余弦相似度原值
4. 按 `video_id` 分组；每个录像的 `best_score` 为组内最高片段分
5. 录像组按 `best_score` 降序
6. 默认只返回前 3 个录像；每个录像内带上合并结果里该片的全部命中片段（先召回再分组，全局片段上限 50）
7. 可通过 `offset_videos` 取更多录像组

相邻且时间重叠的片段在同一录像内合并展示（合并后 `t_start` 取最早，`t_end` 取最晚，caption 保留分数最高的一条）。

### 5.5 播放

用户点哪个录像，就加载哪个原片；点该录像下的哪条命中，就把播放头设到该条 `t_start`（提前 1 秒，下限 0），然后播放。

不自动播放第一条。同一录像内切换命中只改 `currentTime`，不重新拉流；换另一条录像才切换片源。

## 6. 数据模型

### 6.1 本地目录

```
data/videos/{video_id}/
  source.mp4
  frames/{t_start_ms}.jpg
```

`video_id` 使用 UUID。

### 6.2 `videos`

| 列 | 说明 |
|---|---|
| id | UUID |
| filename | 原始文件名 |
| duration_ms | 时长 |
| status | `queued` / `processing` / `ready` / `failed` |
| error_message | 失败原因，给人看 |
| total_segments | 计划片段数，可空直到切段完成 |
| done_segments | 已成功写入的片段数 |
| created_at / updated_at | 时间 |

### 6.3 `analysis_jobs`

| 列 | 说明 |
|---|---|
| id | UUID |
| video_id | 外键 |
| status | 与视频状态同步的任务视图 |
| attempt | 重试次数 |
| last_segment_index | 续跑游标：下一个要处理的片段下标 |
| worker_id | 可选，便于排查 |
| created_at / updated_at | 时间 |

同一录像同时只允许一个活跃任务。`POST /api/videos/{id}/reanalyze` 接受 `mode`：`resume`（默认，从 `last_segment_index` 续跑）或 `full`（删除该录像全部 `segments` 后整片重跑）。

### 6.4 `segments`

| 列 | 说明 |
|---|---|
| id | UUID |
| video_id | 外键 |
| t_start_ms / t_end_ms | 播放区间 |
| keyframe_path | 相对本地路径 |
| ocr_text | 界面原文 |
| caption | 操作描述；降级时为空或占位说明 |
| caption_degraded | bool，视觉模型失败时为 true |
| embedding | `vector(1024)` |
| fts | `tsvector`，jieba 分词结果 |
| model_caption | 描述所用模型标识 |
| model_embed | embedding 所用模型标识 |
| created_at | 时间 |

索引：

- `(video_id, t_start_ms)`
- `embedding`：HNSW，余弦距离
- `fts`：GIN

## 7. API

第一期无鉴权。前端只调用下列接口。

| 方法 | 路径 | 行为 |
|---|---|---|
| `POST` | `/api/videos` | multipart 上传，立即返回 `{id, status}` |
| `GET` | `/api/videos` | 列表：文件名、时长、状态、进度 |
| `GET` | `/api/videos/{id}` | 详情，含 `done_segments/total_segments`、错误信息 |
| `POST` | `/api/videos/{id}/reanalyze` | 入队重跑；body `{ "mode": "resume" \| "full" }`，默认 `resume` |
| `GET` | `/api/videos/{id}/file` | 原片流，供 `<video src>` |
| `GET` | `/api/videos/{id}/frames/{name}` | 代表帧，供缩略图 |
| `GET` | `/api/search` | 见下 |

### 7.1 `GET /api/search`

Query：

- `q`：自然语言，必填
- `limit_videos`：默认 3
- `offset_videos`：默认 0

未 `ready` 的录像不参与检索。服务暂时不可用时返回 503，不返回空列表冒充「无结果」。

响应：

```json
{
  "query": "有没有把客户名单导出去",
  "total_videos": 7,
  "limit_videos": 3,
  "offset_videos": 0,
  "videos": [
    {
      "video_id": "...",
      "filename": "操作-0812.mp4",
      "duration_ms": 2400000,
      "best_score": 0.81,
      "hits": [
        {
          "segment_id": "...",
          "t_start_ms": 123000,
          "t_end_ms": 131000,
          "caption": "在客户列表页点击导出，文件名为客户名单.xlsx",
          "ocr_text": "导出 客户名单.xlsx",
          "keyframe_url": "/api/videos/.../frames/123000.jpg",
          "score": 0.81,
          "caption_degraded": false
        }
      ]
    }
  ]
}
```

`videos` 按 `best_score` 降序。每个 `hits` 是该录像在本查询下的全部命中片段，按片段 `score` 降序。

## 8. 前端

两个页面，无登录。

**录像库**

- 拖拽或选择文件上传
- 列表展示文件名、时长、状态（排队中 / 分析中 / 可搜索 / 失败）
- 分析中：若 `total_segments` 仍为空，显示「切段中」；有总数后显示 `done_segments / total_segments`
- 失败项提供「重新分析」
- 点已 `ready` 的条目：打开播放器从 0 秒播放该片。检索只在检索页进行，是全局搜索，不按当前打开的录像过滤

**检索与播放**

- 顶部搜索框
- 左侧默认展示相似度最高的 3 个录像组；每组列出该片全部命中片段（时间、描述、OCR 摘要、缩略图、分数）
- 「更多录像」用 `offset_videos` 加载后续组
- 右侧播放器；未选择时为空态（「点左侧录像或时间点开始播放」）
- 点录像组或其中某条命中：加载该录像，跳到对应 `t_start_ms`（提前 1 秒）并播放
- 同一录像内再点其他命中：只 seek；点另一录像：换片源再 seek

## 9. 失败处理

**上传**

- 扩展名或探测到的容器不在 `mp4` / `webm` / `mov`：400
- 超过 4GB：400
- 文件损坏、无时长：400，不入队

**分析**

| 失败点 | 处理 |
|---|---|
| 抽帧失败 | 任务 `failed`，保留原片，可重新分析 |
| 某段 OCR 失败 | 该段 `ocr_text` 为空，仍请求视觉模型 |
| 某段视觉模型失败 | 重试 2 次（指数退避）；仍失败则 `caption_degraded=true`，只用 OCR embedding |
| 某段 embedding 失败 | 重试 2 次；仍失败则本段不入检索（无 embedding），任务继续 |
| 进程中断 | 用 `last_segment_index` 续跑 |

若无 embedding 的片段超过切段总数的 30%，任务标 `failed`，已写入片段保留。

**搜索与播放**

- 录像非 `ready`：不出现在 `/api/search`
- 原片文件缺失：`/file` 返回 404，前端提示，不让播放器空转
- Postgres / Redis / 模型适配器不可用：搜索返回 503

## 10. 测试

### 10.1 自动化（无真实大模型也可跑）

- 上传校验：格式、大小、损坏文件
- 切段：给定固定抽帧目录，断言最短/最长时长、段数
- 检索合并：构造 segments + 假 embedding，断言分组、默认 3 个录像、组内 hits 完整、RRF 排序
- 续跑：写入部分 segments 后模拟中断，再跑任务只处理剩余段
- 播放时间：`t_start_ms` 转播放器秒数，含提前 1 秒和 0 下限

视觉模型和 OCR 用 fake adapter 注入，评测集跑通流水线形状，不依赖外网。

### 10.2 手工评测集（验收用）

3–5 条真实屏幕录像 + 标注查询。对真实 CaptionAdapter / OCR / BGE-M3 跑通第 1.1 节五条标准。其中至少一条查询依赖 OCR 原词命中。

## 11. 以后可以加、现在不实现

- `Storage` 换成 MinIO / S3
- `VectorIndex` 换成 Qdrant / Milvus
- 上传元数据或画面识别补上操作人
- 画面差异之外增加点击检测
- GUI 解析（OmniParser 等）作为第三路召回
- 账号与审计权限
- 分析时延优化（更激进抽帧、批量调用、GPU）

## 12. 决策摘要

| 决策 | 选择 |
|---|---|
| 向量内容 | 操作描述 + OCR 的文本向量，不是视频片段向量 |
| 向量存储 | Postgres + pgvector，与元数据同一库 |
| 文件存储 | 本地目录 |
| 检索 | 语义近邻 + 中文全文，RRF 合并，再按录像分组 |
| 默认结果 | 相似度最高的 3 个录像；点哪个播哪个，不自动播放 |
| 模型 | 适配器隔离；开发期 Qwen-VL + BGE-M3，上线可换本地 |
| 切段 | 2 秒抽帧，2–8 秒一段，优先段末代表帧 |
| 身份 | 第一期不做 |
