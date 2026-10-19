# 操作日志文案 + 检索精确 seek

日期：2026-08-25  
状态：已批准（brainstorming）

## 背景

1. 录像段描述（VLM caption + OCR）可读性差，不像「在做什么操作」。
2. 检索页点击整卡或命中行时，播放常从 0 秒开始，未定位到命中时间。

已选方案：**生成侧操作日志提示词 + 展示侧时间线样式 + 修复 seek**（时间码由系统用 `t_start_ms` 写入，不靠模型编造）。

## 目标

- 检索命中以操作日志呈现：`[mm:ss] 在「页面/模块」· 动作 · 关键对象/输入`
- 点整卡 → 该片最佳命中起点起播；点单条 → 该条起点起播（约 1s 提前量）
- 旧数据不自动重跑；用户通过「重新分析」换新文案

## 非目标

- 不自动批量重分析历史录像
- 不改录像库页预览（仍可从 0 起播）
- 不引入二次 LLM 改写、不让模型输出时间戳

## 生成与存储

### VLM 提示词

`ZhipuCaptionAdapter`（及同等 caption 适配器）系统提示改为强制操作日志风格：

- 一句中文，结构接近：`在「页面/模块」· 动作 · 关键对象/输入`
- 优先采用 OCR 中的真实文案（按钮、菜单、IP 等）
- 禁止 Markdown、禁止时间戳、禁止空泛推测套话

### 落库

| 字段 | 内容 |
|------|------|
| `caption` | **不含** `[mm:ss]` 的动作句，供 FTS / 向量 |
| 展示时间码 | 由 `t_start_ms` 在 API 或前端格式化，不入库为模型输出 |

### 降级

caption 失败时：`caption_degraded=true`，用 OCR 缩成一行伪日志；展示仍可加 `[mm:ss]`。

### 已有数据

旧 `caption` 保持原样直至用户满量「重新分析」。前端对旧文案仍套 `[mm:ss]`，句式可能仍偏口语，属预期。

## 检索页展示

- 主文案：`[mm:ss] {caption}`；无 caption 时用 OCR 伪日志
- `[mm:ss]` 与 seek 使用同一 `t_start_ms`（与现有 `seekSeconds` / `lead_ms≈1000` 一致：展示可用段起点，seek 为 `max(0, t_start_ms - lead_ms)`）
- 次要信息：分数、降级标记；OCR 全文弱化或折叠，避免盖过主句
- 整卡点击：`hit ?? hits` 中最佳/首条命中（与当前 `playHit(video)` 语义对齐：无显式 hit 时用 `hits[0]`，若列表已按分数排序则等价最佳；若否，显式选 `best` 命中）

## Seek 修复

统一路径：

1. 解析目标 `t_start_ms` → `seekSeconds`
2. 换片：设 `src`，等 `loadedmetadata`
3. 设 `currentTime`，等 `seeked`
4. 再 `play()`

约束：

- 同片切换命中：不重载，只 seek + `seeked`
- 快速连点：generation / cancel，丢弃过期回调
- 回归测试：同片两点、换片一点、连点取消

根因假设（实现时验证）：`currentTime` 赋值后立即 `play()`，或换片/`load()` 竞态导致时间被重置为 0。

## 测试与上线

### 测试

- 后端：假 captioner 下提示行为/降级伪日志；时间格式化纯函数
- 前端：seek 辅助（同片 / 换片 / 取消）；日志行文案拼接
- 手测：满量重分析 → 搜索 → 整卡与命中行均从对应秒起播

### 上线

- 不自动重跑；依赖现有「重新分析」
- 未重分析片：仅展示层加时间码

## 主要改动面

- `backend/.../adapters/caption_zhipu.py`：提示词
- `backend/.../indexing.py`（可选）：OCR 伪日志辅助
- `frontend/src/videoPlayback.ts`（及测试）：`seeked` 后再 play
- `frontend/src/pages/SearchPage.tsx` + 样式：操作日志列表
- 可选共享：`formatLogLine(tStartMs, caption)`（前后端或仅前端）

## 验收标准

1. 新分析段的 `caption` 读起来像操作日志（无模型时间戳）。
2. 检索列表主行形如 `[mm:ss] …`。
3. 整卡与命中行点击后，播放头落在目标秒附近（含 1s 提前量），而非片头。
4. 连点不同命中时，最终停在最后一次点击对应时间。
