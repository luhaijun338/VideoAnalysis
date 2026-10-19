# VideoAnalysis

屏幕录像语义检索与跳转播放（MVP）。

## Docker（推荐）

把前端、API、分析 Worker 打进同一个镜像 `video-analysis:0.1.0`，和 Postgres / Redis 一起启动：

```bash
docker compose up -d --build --wait
```

打开 `http://127.0.0.1:8000`。录像文件挂在 `./data/videos`。

## 本地开发启动

1. 启动依赖中间件：

```bash
docker compose up -d db redis
```

2. 迁移并启动 API：

```bash
cd backend
alembic upgrade head
.venv/bin/uvicorn video_analysis.api:app --host 127.0.0.1 --port 8000 --reload --reload-dir src --timeout-graceful-shutdown 3 --app-dir src
```

3. 启动分析 Worker：

```bash
cd backend
PYTHONPATH=src .venv/bin/python -m celery -A video_analysis.worker.celery_app worker --loglevel=INFO --pool=solo
```

4. 启动前端：

```bash
cd frontend
npm install
npm run dev
```

前端默认 `http://localhost:5173`，`/api` 由 Vite 代理到 `http://127.0.0.1:8000`。

## 系统依赖与密钥

- 需要本机安装 **ffmpeg** / **ffprobe**
- 复制 `.env.example` 为 `.env`，填写 `ZHIPU_API_KEY`
- 视觉描述默认 `qwen3.5-flash`，文本向量默认 `text-embedding-v4`（1024 维），网关 `https://aigw.telecomjs.com/v1`
- OCR 仍用本地 RapidOCR（轻量，不依赖大模型下载）

## 验收（手工）

准备 3–5 条真实屏幕录像，上传后等待状态变为「可搜索」，在检索页用标注查询对照 [设计规格 1.1](docs/superpowers/specs/2026-08-25-video-analysis-design.md) 做端到端验收。自动化测试不调用真实 BGE / 智谱。
