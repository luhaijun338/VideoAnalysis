# 录像分析 — 前端功能说明（重设计交接）

日期：2026-08-27  
读者：负责 UI / 交互重设计的 agent  
范围：**只改前端观感与信息架构；行为与接口约定必须保留。**

本文描述「产品现在能做什么」，不是当前页面长什么样。现有实现是功能原型，视觉可整体推翻。不要复刻现有灰底白卡片、蓝色链接顶栏。

---

## 1. 产品是什么

给合规审计用的**屏幕录像分析服务**。用户上传软件操作录像，系统切段、OCR、生成操作描述并做向量检索。审计员用自然语言搜「做了什么」，点中结果后跳到对应时间继续播放。

- 无登录、无账号、无权限
- 中文界面
- 应用标题：`录像分析`
- 开发期前端：`http://127.0.0.1:5173`，`/api` 代理到后端 `8000`

---

## 2. 信息架构

两个一级页面，顶部全局导航切换。无其它路由、无设置页、无登录页。

| 路由 | 名称 | 职责 |
|---|---|---|
| `/` | 录像库 | 上传、看分析进度、失败重跑、从 0 秒预览成片 |
| `/search` | 检索 | 自然语言搜索命中片段，点中后跳转播放 |

检索是**全局搜索**，不按录像库里当前打开的那条过滤。

---

## 3. 录像库 `/`

### 3.1 上传

- 支持拖拽文件到投放区，或点击投放区打开系统文件选择
- 格式：`.mp4` / `.webm` / `.mov`（大小写不敏感）
- 可一次选多个文件，按顺序逐个上传
- 非法扩展名：页面提示 `仅支持 .mp4 / .webm / .mov`，不发请求
- 服务端还会拒：非视频容器、超过 4GB、文件损坏/无时长（前端展示后端错误文案）

**同一文件内容（SHA-256）重复上传：**

1. 后端 `409`，文案「该录像已上传」
2. 前端弹出确认：`该录像已上传（{文件名}）。确定覆盖并重新分析吗？`
3. 取消：跳过该文件，继续下一个
4. 确定：带 `overwrite=true` 再传，覆盖原记录并整片重新分析

上传成功后刷新列表。上传过程中若某文件失败（非重复确认取消），停掉后续文件并展示错误。

### 3.2 列表

每条录像展示：

- 原始文件名
- 时长：`m:ss`（由 `duration_ms` 换算，不足两位秒数补零）
- 状态文案见下表

| `status` | 展示 |
|---|---|
| `queued` | 排队中 |
| `processing` 且 `total_segments == null` | 切段中 |
| `processing` 且已有总数 | `{done_segments}/{total_segments}` |
| `ready` | 可搜索 |
| `failed` | 失败 |

列表按后端返回顺序（创建时间倒序）。

存在 `queued` 或 `processing` 时，**每 3 秒自动刷新**列表；全部结束后停止轮询。

### 3.3 失败与重跑

仅 `failed` 显示：

- `error_message`（若有）
- 按钮「重新分析」→ `POST /api/videos/{id}/reanalyze`，`mode: "full"`（删片段、整片重跑）

### 3.4 库内预览播放

仅 `ready` 显示「播放」。

- 从 **0 秒** 起播，不 seek 到检索命中
- 使用原片流 `/api/videos/{id}/file`，原生 `<video controls>`
- 文件缺失：`play()` 失败时提示 `无法播放该录像（文件可能缺失）`
- 未点播放时不渲染播放器（或等价空态）

---

## 4. 检索 `/search`

### 4.1 搜索

- 输入框 placeholder：`用自然语言描述操作画面…`
- 提交按钮「搜索」；请求进行中按钮 disabled
- 空查询不发请求
- 新搜索成功或失败都要**清空当前播放器**（停播、卸掉 src，避免后台继续出声）
- 服务暂不可用：后端 503，前端展示错误，**不要用空列表冒充无结果**

### 4.2 结果模型（全局 Top 3 命中）

一次查询默认只要 **相似度最高的 3 条命中（片段）**，不是「3 条录像各带全部片段」。

响应仍按录像分组，便于同一录像多条命中共用一个片源：

- 3 条命中可能来自 1～3 个录像
- 每组：`filename`、`best_score`、该组内的 `hits`
- 每条 hit：时间区间、操作日志主文案、OCR（可折叠）、代表帧缩略图、分数、是否描述降级

`score` / `best_score` 是融合排序分，只用于排序和展示，不是余弦相似度。

**「更多命中」：** 已展示命中数 `< total_hits` 时出现。再拉下一批（仍按 `limit_hits`，默认 3），按 `video_id` 合并进已有分组（同录像追加 hits，新录像新建组）。按钮文案：`更多命中`。

无结果时：没有分组、没有「更多」；不要假装在加载。首次进入、尚未搜索：只有搜索框和播放器空态。

### 4.3 命中行展示内容

主行（操作日志，等宽/可读即可，样式可改）：

```
[m:ss] {caption 或 OCR 缩略 或 「（无描述）」}
```

- 时间码用 **段起点** `t_start_ms`，格式 `m:ss`（如 `0:30`、`1:05`）
- 优先 `caption`；空则用 OCR 压空白并截到约 80 字；都空则 `（无描述）`
- 次行：`{起点}–{终点}` · 分数三位小数；`caption_degraded` 时加「描述降级」
- 左侧缩略图：`hit.keyframe_url`（代表帧，不是视频本身）
- OCR 全文默认折叠，标题「OCR」，展开后预格式化多行文本

组头：`{filename} · best {best_score}`（三位小数）。点击组头 = 播放该组**分数最高**的那条命中。

### 4.4 播放（检索页核心行为）

布局建议：左结果、右播放器（窄屏可上下叠）。右侧未选中时文案：`点左侧录像或时间点开始播放`。

| 用户动作 | 播放行为 |
|---|---|
| 点某条命中 | 加载该录像，跳到该条 `t_start_ms`，播放 |
| 点组头 | 同上，目标为组内最高分命中 |
| 同一录像再点另一条命中 | **不换片源**，只 seek 再播 |
| 点另一条录像的命中 | 换 `src`，等 metadata，再 seek 再播 |
| 新搜索 | 停播并清空片源 |

Seek 规则：

- 播放头 = `max(0, t_start_ms - 1000) / 1000` 秒（提前约 1 秒）
- 必须等 seek 完成（或判定为原地 no-op）再 `play()`
- 连点：后一次取消前一次回调，避免旧时间盖掉新时间
- `play()` 失败：`无法播放该录像（文件可能缺失）`

播放器：原生 `<video controls>`，片源 `/api/videos/{video_id}/file`。不要自动播第一条命中。

---

## 5. 接口（前端只用这些）

无鉴权。错误时 HTTP 非 2xx，body 多为 `{ "detail": "..." }`；重复上传 409 的 `detail` 是对象。

### 上传

`POST /api/videos`  
`multipart/form-data`，字段 `file`。覆盖时 query：`overwrite=true`。

成功：`{ "id", "status": "queued" }`，覆盖时另有 `"overwritten": true`。

409：

```json
{
  "detail": {
    "code": "duplicate",
    "message": "该录像已上传",
    "video_id": "...",
    "filename": "network-log.mp4"
  }
}
```

### 列表 / 详情

`GET /api/videos` → `Video[]`（新到旧）

`GET /api/videos/{id}` → 单条 `Video`

```ts
{
  id: string
  filename: string
  duration_ms: number
  status: "queued" | "processing" | "ready" | "failed" | string
  error_message: string | null
  total_segments: number | null
  done_segments: number
}
```

### 重新分析

`POST /api/videos/{id}/reanalyze`  
`{ "mode": "resume" | "full" }`，默认 `resume`。库页失败重跑用 `full`。

返回 `{ "id", "status": "queued" }`。

### 媒体

`GET /api/videos/{id}/file` — 原片，给 `<video src>`  
`GET /api/videos/{id}/frames/{t_start_ms}.jpg` — 代表帧（文件名必须是 `{毫秒}.jpg`）

### 检索

`GET /api/search?q=&limit_hits=3&offset_hits=0`

- `q` 必填，空白 → 400
- 后端异常 → 503，`detail: "search unavailable"`

```ts
{
  query: string
  total_hits: number
  limit_hits: number
  offset_hits: number
  total_videos: number
  videos: {
    video_id: string
    filename: string
    duration_ms: number
    best_score: number
    hits: {
      segment_id: string
      t_start_ms: number
      t_end_ms: number
      caption: string
      ocr_text: string
      keyframe_url: string  // 如 /api/videos/{id}/frames/30000.jpg
      score: number
      caption_degraded: boolean
    }[]
  }[]
}
```

`offset_hits` 按**命中条数**分页，不是按录像组。

---

## 6. 状态与文案清单（可改措辞，语义要在）

| 场景 | 当前文案（可优化，勿丢语义） |
|---|---|
| 导航 | 录像库 / 检索 |
| 上传区 | 拖拽或选择屏幕录像上传（.mp4 / .webm / .mov） |
| 格式错误 | 仅支持 .mp4 / .webm / .mov |
| 重复文件 | 该录像已上传（{filename}）。确定覆盖并重新分析吗？ |
| 状态 | 排队中 / 切段中 / n/m / 可搜索 / 失败 |
| 失败操作 | 重新分析 |
| 库内播放 | 播放 |
| 搜索提示 | 用自然语言描述操作画面… |
| 搜索按钮 | 搜索 |
| 播放器空态 | 点左侧录像或时间点开始播放 |
| 加载更多 | 更多命中 |
| 播放失败 | 无法播放该录像（文件可能缺失） |
| 无描述 | （无描述） |
| 降级标记 | 描述降级 |
| OCR 折叠 | OCR |

无障碍：搜索框需要可访问名称（当前 `aria-label="搜索"`）。

---

## 7. 重设计约束

**必须保留**

- 两页：库（上传+进度+从 0 预览）与检索（搜+跳转播放）
- 全局 Top 3 命中 + 可加载更多命中
- 点命中跳到对应时间（提前 1s），同片只 seek、换片才换 src
- 新搜索停止并卸掉正在播的视频
- 重复上传：先提示，用户选取消或覆盖
- 分析中自动刷新进度
- 失败可整片重新分析
- 不引入登录

**可以改**

- 布局、字体、色彩、组件、动效、空态插画
- 确认框可换成正规对话框（语义仍是取消 / 覆盖）
- 命中列表是「按录像分组」还是「扁平 3 条」：扁平也可以，但同片切换必须仍只 seek
- 进度展示可以是进度条，不必纯文字 `3/11`
- 检索页左右分栏可改成主从、抽屉、底部播放条等，只要播放器与命中列表同时可操作

**不要做（本期产品范围）**

- 账号 / 权限 / 多租户
- 按当前录像过滤搜索
- 剪辑导出、分享链接
- 独立向量库或对象存储 UI
- 改后端检索算法、切段、模型（除非设计需要新字段，先标出来）

---

## 8. 代码入口（实现时可对照，设计时可不看）

| 文件 | 内容 |
|---|---|
| `frontend/src/App.tsx` | 顶栏导航 + 路由 |
| `frontend/src/pages/LibraryPage.tsx` | 录像库 |
| `frontend/src/pages/SearchPage.tsx` | 检索与播放 |
| `frontend/src/api.ts` | 全部 API 与类型 |
| `frontend/src/operationLog.ts` | `[m:ss]` 日志行、时钟格式 |
| `frontend/src/seek.ts` | 提前 1 秒 seek |
| `frontend/src/videoPlayback.ts` | 换片/seek/取消竞态 |
| `frontend/src/styles.css` | 现有简陋样式，**不要当视觉规范** |

技术栈：React 19 + Vite + React Router。无 UI 组件库、无设计 token。

---

## 9. 验收（重设计后功能仍要成立）

1. 上传 mp4，列表出现「排队中 / 切段中 / n/m / 可搜索」
2. 同一文件再传：弹出已上传，取消则仍一条；覆盖则仍一条并重新分析
3. `ready` 点播放从 0 秒播
4. `failed` 能重新分析
5. 检索返回至多 3 条命中；主文案带 `[m:ss]`；点一条从对应时间（约提前 1s）起播
6. 同片再点另一命中不重新拉流
7. 再搜一枪，旧视频停止且不再出声
8. 后端 503 时检索页报错，不是空白当「没有结果」
