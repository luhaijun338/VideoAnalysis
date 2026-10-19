# 录像分析服务 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现屏幕录像上传、异步分析（OCR + 操作描述 + 文本向量）、自然语言检索，并跳到命中时间继续播放。

**Architecture:** FastAPI 只做同步接口；Celery Worker 抽帧切段、OCR、视觉描述、BGE-M3 写入 Postgres/pgvector；检索用向量近邻 + jieba/`tsvector` 做 RRF，再按录像分组返回。前端两个页面：录像库、检索与播放。模型和文件存储均走适配器。

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, pgvector, Redis, Celery, RapidOCR, DashScope Qwen-VL, BGE-M3, jieba, ffmpeg, React + Vite + TypeScript

## Global Constraints

- Python 3.12；PostgreSQL 16+ 且必须装 `pgvector`；Redis 7
- 录像格式仅 `mp4` / `webm` / `mov`；单文件上限 4GB
- Embedding 固定 1024 维（BGE-M3）；`caption(frames, ocr_text) -> str` 与 `embed(text) -> vector[1024]` 必须是可替换适配器
- 切段：每 2 秒抽帧；最短约 2 秒、最长约 8 秒；代表帧优先段末
- 检索默认 `limit_videos=3`；点哪个录像播哪个，不自动播放；seek 提前 1 秒、下限 0
- 文件存在本地 `data/videos/{video_id}/`；第一期无鉴权、无 MinIO、无独立向量库、无操作人
- 失败片段无 embedding 超过 30% 则任务 `failed`；视觉模型失败降级为仅 OCR embedding
- 规格：`docs/superpowers/specs/2026-08-25-video-analysis-design.md`

---

## File Structure

```
docker-compose.yml
.env.example
.gitignore
README.md
backend/
  pyproject.toml
  alembic.ini
  alembic/env.py
  alembic/versions/001_init.py
  src/video_analysis/
    __init__.py
    config.py
    db.py
    models.py
    storage.py
    probe.py
    playback.py
    fts.py
    segmenting.py
    search.py
    indexing.py
    analyze.py
    api.py
    worker.py
    adapters/__init__.py
    adapters/base.py
    adapters/fake.py
    adapters/ocr_rapid.py
    adapters/caption_dashscope.py
    adapters/embed_bge.py
  tests/
    conftest.py
    test_storage.py
    test_probe.py
    test_segmenting.py
    test_fts.py
    test_playback.py
    test_indexing.py
    test_analyze.py
    test_search.py
    test_api.py
    test_worker.py
frontend/
  package.json
  vite.config.ts
  tsconfig.json
  index.html
  src/main.tsx
  src/App.tsx
  src/api.ts
  src/seek.ts
  src/seek.test.ts
  src/pages/LibraryPage.tsx
  src/pages/SearchPage.tsx
```

职责：`storage.py` 只管本地目录；`segmenting.py` 只切段；`indexing.py` 处理单段 OCR/描述/向量；`analyze.py` 编排整片任务与续跑；`search.py` 只检索分组；`adapters/` 隔离云与本地模型；`api.py` 只暴露 HTTP。

---

### Task 1: 本地存储适配器

**Files:**
- Create: `backend/pyproject.toml`
- Create: `.gitignore`
- Create: `backend/src/video_analysis/__init__.py`
- Create: `backend/src/video_analysis/storage.py`
- Create: `backend/tests/test_storage.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `class LocalStorage`
  - `LocalStorage(root: Path) -> None`
  - `save_source(video_id: str, data: BinaryIO) -> Path` 写入 `{root}/{video_id}/source.mp4`
  - `source_path(video_id: str) -> Path`
  - `save_frame(video_id: str, t_start_ms: int, image: bytes) -> Path` 写入 `{root}/{video_id}/frames/{t_start_ms}.jpg`
  - `frame_path(video_id: str, t_start_ms: int) -> Path`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_storage.py
import io
from pathlib import Path

from video_analysis.storage import LocalStorage

VIDEO_ID = "11111111-1111-1111-1111-111111111111"


def test_save_source_writes_source_mp4(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    path = storage.save_source(VIDEO_ID, io.BytesIO(b"fake-bytes"))
    assert path == tmp_path / VIDEO_ID / "source.mp4"
    assert path.read_bytes() == b"fake-bytes"
    assert storage.source_path(VIDEO_ID) == path


def test_save_frame_uses_millisecond_filename(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    path = storage.save_frame(VIDEO_ID, 123000, b"jpeg-bytes")
    assert path == tmp_path / VIDEO_ID / "frames" / "123000.jpg"
    assert path.read_bytes() == b"jpeg-bytes"
    assert storage.frame_path(VIDEO_ID, 123000) == path
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_storage.py -v
```

Expected: FAIL with `ModuleNotFoundError: video_analysis` 或 `LocalStorage` 未定义。

- [ ] **Step 3: Write minimal implementation**

`backend/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "video-analysis"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "sqlalchemy>=2.0.36",
  "psycopg[binary]>=3.2",
  "pgvector>=0.3",
  "alembic>=1.14",
  "celery[redis]>=5.4",
  "redis>=5.2",
  "pydantic-settings>=2.6",
  "python-multipart>=0.0.17",
  "httpx>=0.27",
  "jieba>=0.42",
  "pillow>=11.0",
  "openai>=1.55",
  "rapidocr-onnxruntime>=1.4",
  "FlagEmbedding>=1.3",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

`.gitignore`:

```
__pycache__/
.venv/
data/
*.pyc
.env
frontend/node_modules/
frontend/dist/
backend/*.egg-info/
```

`backend/src/video_analysis/storage.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import BinaryIO


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _video_dir(self, video_id: str) -> Path:
        return self.root / video_id

    def source_path(self, video_id: str) -> Path:
        return self._video_dir(video_id) / "source.mp4"

    def frame_path(self, video_id: str, t_start_ms: int) -> Path:
        return self._video_dir(video_id) / "frames" / f"{t_start_ms}.jpg"

    def save_source(self, video_id: str, data: BinaryIO) -> Path:
        path = self.source_path(video_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.read())
        return path

    def save_frame(self, video_id: str, t_start_ms: int, image: bytes) -> Path:
        path = self.frame_path(video_id, t_start_ms)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image)
        return path
```

空文件 `backend/src/video_analysis/__init__.py`。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pip install -e ".[dev]" && python -m pytest tests/test_storage.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .gitignore backend/pyproject.toml backend/src/video_analysis/__init__.py backend/src/video_analysis/storage.py backend/tests/test_storage.py
git commit -m "feat: add local video and frame storage"
```

---

### Task 2: 数据模型与 Postgres

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `backend/src/video_analysis/config.py`
- Create: `backend/src/video_analysis/db.py`
- Create: `backend/src/video_analysis/models.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/001_init.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `Video.status`: `"queued" | "processing" | "ready" | "failed"`
  - `Video(id, filename, duration_ms, status, error_message, total_segments, done_segments)`
  - `AnalysisJob(id, video_id, status, attempt, last_segment_index, worker_id)`
  - `Segment(id, video_id, t_start_ms, t_end_ms, keyframe_path, ocr_text, caption, caption_degraded, embedding, fts, model_caption, model_embed)`
  - `get_session() -> Iterator[Session]`
  - `Settings.database_url: str`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_models.py
from pgvector.sqlalchemy import Vector
from sqlalchemy import select

from video_analysis.models import Segment, Video


def test_insert_video_and_segment_with_embedding(db_session) -> None:
    video = Video(filename="a.mp4", duration_ms=10_000, status="queued")
    db_session.add(video)
    db_session.flush()
    seg = Segment(
        video_id=video.id,
        t_start_ms=0,
        t_end_ms=4000,
        keyframe_path="frames/0.jpg",
        ocr_text="导出 客户名单",
        caption="点击导出",
        caption_degraded=False,
        embedding=[0.01] * 1024,
        fts="导出 客户 名单 点击 导出",
        model_caption="fake",
        model_embed="fake",
    )
    db_session.add(seg)
    db_session.commit()
    loaded = db_session.scalar(select(Segment).where(Segment.video_id == video.id))
    assert loaded is not None
    assert len(loaded.embedding) == 1024
    assert video.status == "queued"
```

`backend/tests/conftest.py`（本步先写，Task 2 Step 3 补齐引擎）：

```python
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from video_analysis.models import Base


@pytest.fixture(scope="session")
def engine():
    url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://va:va@localhost:5432/video_analysis_test",
    )
    eng = create_engine(url)
    with eng.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def db_session(engine) -> Session:
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_models.py -v
```

Expected: FAIL（`video_analysis.models` 不存在）

- [ ] **Step 3: Write minimal implementation**

`docker-compose.yml`（仓库根目录）：

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: va
      POSTGRES_PASSWORD: va
      POSTGRES_DB: video_analysis
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
  redis:
    image: redis:7
    ports:
      - "6379:6379"
volumes:
  pgdata:
```

`.env.example`:

```
DATABASE_URL=postgresql+psycopg://va:va@localhost:5432/video_analysis
TEST_DATABASE_URL=postgresql+psycopg://va:va@localhost:5432/video_analysis_test
REDIS_URL=redis://localhost:6379/0
DATA_DIR=./data/videos
DASHSCOPE_API_KEY=
CAPTION_MODEL=qwen-vl-plus
```

`backend/src/video_analysis/config.py`:

```python
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://va:va@localhost:5432/video_analysis"
    redis_url: str = "redis://localhost:6379/0"
    data_dir: Path = Path("./data/videos")
    dashscope_api_key: str = ""
    caption_model: str = "qwen-vl-plus"
    max_upload_bytes: int = 4 * 1024 * 1024 * 1024
    allowed_suffixes: tuple[str, ...] = (".mp4", ".webm", ".mov")


settings = Settings()
```

`backend/src/video_analysis/models.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(512))
    duration_ms: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_segments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    done_segments: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    segments: Mapped[list[Segment]] = relationship(back_populates="video")
    jobs: Mapped[list[AnalysisJob]] = relationship(back_populates="video")


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    last_segment_index: Mapped[int] = mapped_column(Integer, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    video: Mapped[Video] = relationship(back_populates="jobs")


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id"), index=True)
    t_start_ms: Mapped[int] = mapped_column(Integer)
    t_end_ms: Mapped[int] = mapped_column(Integer)
    keyframe_path: Mapped[str] = mapped_column(String(1024))
    ocr_text: Mapped[str] = mapped_column(Text, default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    caption_degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    fts: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    model_caption: Mapped[str] = mapped_column(String(128), default="")
    model_embed: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    video: Mapped[Video] = relationship(back_populates="segments")
```

`backend/src/video_analysis/db.py`:

```python
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from video_analysis.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

Alembic：`alembic.ini` 的 `script_location = alembic`，`sqlalchemy.url` 留空由 `env.py` 读 `settings.database_url`。`env.py` 导入 `Base.metadata`。`001_init.py` 用 `op.execute("CREATE EXTENSION IF NOT EXISTS vector")`，再 `CreateTable` 三张表，并：

```python
op.create_index("ix_segments_video_t_start", "segments", ["video_id", "t_start_ms"])
op.execute(
    "CREATE INDEX ix_segments_embedding ON segments USING hnsw (embedding vector_cosine_ops)"
)
op.execute("CREATE INDEX ix_segments_fts ON segments USING gin (fts)")
```

`fts` 列类型 `TSVECTOR`。HNSW 在 embedding 可空时仍可建（pgvector 忽略 NULL）。

先启动测试库：

```bash
docker compose up -d db
docker compose exec db psql -U va -d postgres -c "CREATE DATABASE video_analysis_test;"
```

若数据库已存在则忽略错误。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && TEST_DATABASE_URL=postgresql+psycopg://va:va@localhost:5432/video_analysis_test python -m pytest tests/test_models.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml .env.example backend/src/video_analysis/config.py backend/src/video_analysis/db.py backend/src/video_analysis/models.py backend/alembic.ini backend/alembic backend/tests/conftest.py backend/tests/test_models.py
git commit -m "feat: add postgres models with pgvector segments"
```

---

### Task 3: 上传探测与校验

**Files:**
- Create: `backend/src/video_analysis/probe.py`
- Create: `backend/tests/test_probe.py`

**Interfaces:**
- Consumes: `settings.max_upload_bytes`, `settings.allowed_suffixes`
- Produces:
  - `class ProbeError(ValueError)`
  - `probe_video(path: Path) -> int` 返回 `duration_ms`
  - `validate_upload(filename: str, size_bytes: int) -> None` 非法则 `ProbeError`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

import pytest

from video_analysis.probe import ProbeError, probe_video, validate_upload


def test_reject_bad_suffix() -> None:
    with pytest.raises(ProbeError, match="format"):
        validate_upload("note.txt", 100)


def test_reject_oversize() -> None:
    with pytest.raises(ProbeError, match="size"):
        validate_upload("a.mp4", 4 * 1024 * 1024 * 1024 + 1)


def test_accept_mp4_under_limit() -> None:
    validate_upload("操作.mp4", 1024)


def test_probe_raises_when_ffprobe_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr("video_analysis.probe.subprocess.run", fake_run)
    with pytest.raises(ProbeError, match="duration"):
        probe_video(tmp_path / "missing.mp4")


def test_probe_parses_duration_seconds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Result:
        returncode = 0
        stdout = "12.5"
        stderr = ""

    monkeypatch.setattr("video_analysis.probe.subprocess.run", lambda *a, **k: Result())
    assert probe_video(tmp_path / "a.mp4") == 12500
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_probe.py -v
```

Expected: FAIL（模块不存在）

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

import subprocess
from pathlib import Path

from video_analysis.config import settings


class ProbeError(ValueError):
    pass


def validate_upload(filename: str, size_bytes: int) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix not in settings.allowed_suffixes:
        raise ProbeError("unsupported format")
    if size_bytes > settings.max_upload_bytes:
        raise ProbeError("file exceeds size limit")


def probe_video(path: Path) -> int:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise ProbeError("cannot read duration") from exc
    if result.returncode != 0:
        raise ProbeError("cannot read duration")
    try:
        seconds = float(result.stdout.strip())
    except ValueError as exc:
        raise ProbeError("cannot read duration") from exc
    if seconds <= 0:
        raise ProbeError("cannot read duration")
    return int(seconds * 1000)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_probe.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/video_analysis/probe.py backend/tests/test_probe.py
git commit -m "feat: validate upload format size and duration"
```

---

### Task 4: 切段

**Files:**
- Create: `backend/src/video_analysis/segmenting.py`
- Create: `backend/tests/test_segmenting.py`

**Interfaces:**
- Consumes: `LocalStorage`（本任务测试不依赖，只对已抽好的帧路径分组）
- Produces:
  - `@dataclass(frozen=True) class SegmentWindow(t_start_ms: int, t_end_ms: int, keyframe_t_ms: int, frame_paths: list[Path])`
  - `parse_frame_t_ms(path: Path) -> int` 文件名 `{t_ms}.jpg`
  - `group_segments(frame_paths: list[Path], min_ms: int = 2000, max_ms: int = 8000, diff_threshold: float = 12.0) -> list[SegmentWindow]`
  - `extract_frames(source: Path, dest_dir: Path, interval_s: float = 2.0) -> list[Path]`（ffmpeg；单测 mock subprocess）

- [ ] **Step 1: Write the failing test**

用 Pillow 生成纯色 JPG：连续 3 张红、再 3 张蓝。文件名 `0.jpg, 2000.jpg, 4000.jpg, 6000.jpg, 8000.jpg, 10000.jpg`。期望两段：0–6000（keyframe 4000 或段末 4000 因为红段最后一帧 4000）、以及 6000–12000。规则：连续相似帧收成一段，段时长 = 最后一帧时间 + interval；最短 2s、最长 8s；keyframe 为段内最后一帧。

```python
from pathlib import Path

from PIL import Image

from video_analysis.segmenting import group_segments


def _solid(path: Path, color: tuple[int, int, int]) -> None:
    Image.new("RGB", (32, 32), color).save(path, "JPEG")


def test_group_similar_frames_and_split_on_change(tmp_path: Path) -> None:
    colors = [(255, 0, 0)] * 3 + [(0, 0, 255)] * 3
    paths = []
    for i, color in enumerate(colors):
        p = tmp_path / f"{i * 2000}.jpg"
        _solid(p, color)
        paths.append(p)
    segs = group_segments(paths)
    assert len(segs) == 2
    assert segs[0].t_start_ms == 0
    assert segs[0].t_end_ms == 6000
    assert segs[0].keyframe_t_ms == 4000
    assert segs[1].t_start_ms == 6000
    assert segs[1].t_end_ms == 12000
    assert segs[1].keyframe_t_ms == 10000


def test_long_static_scene_splits_at_8s(tmp_path: Path) -> None:
    paths = []
    for i in range(6):
        p = tmp_path / f"{i * 2000}.jpg"
        _solid(p, (10, 10, 10))
        paths.append(p)
    segs = group_segments(paths)
    assert all((s.t_end_ms - s.t_start_ms) <= 8000 for s in segs)
    assert segs[0].t_start_ms == 0
    assert segs[0].t_end_ms == 8000
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_segmenting.py -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
import numpy as np


@dataclass(frozen=True)
class SegmentWindow:
    t_start_ms: int
    t_end_ms: int
    keyframe_t_ms: int
    frame_paths: list[Path]


def parse_frame_t_ms(path: Path) -> int:
    return int(path.stem)


def _mean_abs_diff(a: Path, b: Path) -> float:
    ia = np.asarray(Image.open(a).convert("RGB"), dtype=np.float32)
    ib = np.asarray(Image.open(b).convert("RGB"), dtype=np.float32)
    return float(np.mean(np.abs(ia - ib)))


def group_segments(
    frame_paths: list[Path],
    min_ms: int = 2000,
    max_ms: int = 8000,
    diff_threshold: float = 12.0,
    interval_ms: int = 2000,
) -> list[SegmentWindow]:
    if not frame_paths:
        return []
    ordered = sorted(frame_paths, key=parse_frame_t_ms)
    groups: list[list[Path]] = [[ordered[0]]]
    for prev, cur in zip(ordered, ordered[1:]):
        same = _mean_abs_diff(prev, cur) < diff_threshold
        start = parse_frame_t_ms(groups[-1][0])
        cur_t = parse_frame_t_ms(cur)
        duration = (cur_t + interval_ms) - start
        if same and duration <= max_ms:
            groups[-1].append(cur)
        else:
            groups.append([cur])
    windows: list[SegmentWindow] = []
    for group in groups:
        t_start = parse_frame_t_ms(group[0])
        t_end = parse_frame_t_ms(group[-1]) + interval_ms
        if t_end - t_start < min_ms and windows:
            merged_paths = windows[-1].frame_paths + group
            t_start = windows[-1].t_start_ms
            t_end = parse_frame_t_ms(merged_paths[-1]) + interval_ms
            windows[-1] = SegmentWindow(
                t_start_ms=t_start,
                t_end_ms=t_end,
                keyframe_t_ms=parse_frame_t_ms(merged_paths[-1]),
                frame_paths=merged_paths,
            )
        else:
            windows.append(
                SegmentWindow(
                    t_start_ms=t_start,
                    t_end_ms=t_end,
                    keyframe_t_ms=parse_frame_t_ms(group[-1]),
                    frame_paths=group,
                )
            )
    return windows


def extract_frames(source: Path, dest_dir: Path, interval_s: float = 2.0) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    pattern = dest_dir / "%d.jpg"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vf",
            f"fps=1/{interval_s}",
            str(pattern),
        ],
        check=True,
        capture_output=True,
    )
    raw = sorted(dest_dir.glob("*.jpg"), key=lambda p: int(p.stem))
    renamed: list[Path] = []
    for p in raw:
        idx = int(p.stem)
        t_ms = int((idx - 1) * interval_s * 1000) if idx >= 1 else 0
        # ffmpeg %d 从 1 开始
        t_ms = int((idx - 1) * interval_s * 1000)
        target = dest_dir / f"{t_ms}.jpg"
        p.rename(target)
        renamed.append(target)
    return renamed
```

`pyproject.toml` 的 `dependencies` 增加 `"numpy>=2.0"`。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_segmenting.py -v
```

Expected: PASS。若 `test_group_similar_frames` 因 JPEG 压缩导致红/蓝被判为相似，把 `diff_threshold` 降到 8，或测试图用 PNG 再在函数里 `Image.open`（函数已兼容）。不要为过测试放宽到失去切段意义。

- [ ] **Step 5: Commit**

```bash
git add backend/src/video_analysis/segmenting.py backend/tests/test_segmenting.py backend/pyproject.toml
git commit -m "feat: group screen-recording frames into 2-8s segments"
```

---

### Task 5: FTS、播放时间、假模型适配器

**Files:**
- Create: `backend/src/video_analysis/fts.py`
- Create: `backend/src/video_analysis/playback.py`
- Create: `backend/src/video_analysis/adapters/base.py`
- Create: `backend/src/video_analysis/adapters/fake.py`
- Create: `backend/src/video_analysis/adapters/__init__.py`
- Create: `backend/tests/test_fts.py`
- Create: `backend/tests/test_playback.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `tokenize_fts(*parts: str) -> str` jieba 空格分词，供 `to_tsvector('simple')`
  - `player_seek_seconds(t_start_ms: int, lead_ms: int = 1000) -> float`
  - `class OcrAdapter(Protocol): def recognize(self, image_path: Path) -> str`
  - `class CaptionAdapter(Protocol): def caption(self, frames: list[Path], ocr_text: str) -> str`
  - `class EmbedAdapter(Protocol): def embed(self, text: str) -> list[float]` 长度 1024
  - `FakeOcrAdapter(mapping: dict[str, str])`
  - `FakeCaptionAdapter(text: str | None = None, fail: bool = False)`
  - `FakeEmbedAdapter`：对文本 utf-8 做稳定伪向量（hash 填充 1024 维并 L2 归一化）。相同字符串必须得到相同向量；明显不同的中文串余弦应低于相同串。

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_fts.py
from video_analysis.fts import tokenize_fts


def test_tokenize_keeps_export_keywords() -> None:
    tokens = tokenize_fts("点击导出", "客户名单.xlsx")
    assert "客户" in tokens or "客户名单" in tokens
    assert "导出" in tokens
```

```python
# backend/tests/test_playback.py
from video_analysis.playback import player_seek_seconds


def test_seek_minus_one_second() -> None:
    assert player_seek_seconds(123000) == 122.0


def test_seek_floor_zero() -> None:
    assert player_seek_seconds(400) == 0.0
```

再在 `test_fts.py` 增加：

```python
from video_analysis.adapters.fake import FakeEmbedAdapter


def test_fake_embed_is_1024_and_deterministic() -> None:
    emb = FakeEmbedAdapter()
    a = emb.embed("导出 客户名单")
    b = emb.embed("导出 客户名单")
    assert len(a) == 1024
    assert a == b
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_fts.py tests/test_playback.py -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

`fts.py`：`jieba.cut` 过滤空白，`" ".join`。

`playback.py`：`return max(0, t_start_ms - lead_ms) / 1000.0`

`adapters/base.py`：三个 Protocol。

`adapters/fake.py`：

```python
import hashlib
import math
from pathlib import Path


class FakeOcrAdapter:
    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self.mapping = mapping or {}

    def recognize(self, image_path: Path) -> str:
        return self.mapping.get(image_path.name, self.mapping.get(str(image_path), ""))


class FakeCaptionAdapter:
    def __init__(self, text: str = "执行了界面操作", fail: bool = False) -> None:
        self.text = text
        self.fail = fail

    def caption(self, frames: list[Path], ocr_text: str) -> str:
        if self.fail:
            raise RuntimeError("caption failed")
        if ocr_text:
            return f"{self.text}：{ocr_text}"
        return self.text


class FakeEmbedAdapter:
    def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = []
        seed = digest
        while len(values) < 1024:
            for b in seed:
                values.append((b / 127.5) - 1.0)
                if len(values) == 1024:
                    break
            seed = hashlib.sha256(seed).digest()
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_fts.py tests/test_playback.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/video_analysis/fts.py backend/src/video_analysis/playback.py backend/src/video_analysis/adapters backend/tests/test_fts.py backend/tests/test_playback.py
git commit -m "feat: add fts tokenization, seek helper, and fake model adapters"
```

---

### Task 6: 单段索引与整片分析续跑

**Files:**
- Create: `backend/src/video_analysis/indexing.py`
- Create: `backend/src/video_analysis/analyze.py`
- Create: `backend/tests/test_indexing.py`
- Create: `backend/tests/test_analyze.py`

**Interfaces:**
- Consumes: `LocalStorage`, `SegmentWindow`, `OcrAdapter`, `CaptionAdapter`, `EmbedAdapter`, `tokenize_fts`, `Video`, `AnalysisJob`, `Segment`, `Session`
- Produces:
  - `index_segment(session, video, window, ocr, captioner, embedder, storage) -> Segment`
    - OCR 失败则 `ocr_text=""` 仍 caption
    - caption 最多重试 2 次（共 3 次尝试）；仍失败则 `caption_degraded=True`，`caption=""`，embedding 只用 `ocr_text`；若 OCR 也空则 embedding=None
    - embed 最多重试 2 次；仍失败 embedding=None
    - embedding 输入：`caption + "\n" + ocr_text`，降级时只用 `ocr_text`
    - `fts = tokenize_fts(caption, ocr_text)` 写入 TSVECTOR：使用 `sqlalchemy.func.to_tsvector("simple", tokenize_fts(...))`
  - `analyze_video(session, video_id, windows, ocr, captioner, embedder, storage, start_index: int = 0) -> str` 返回最终 status
    - 将 `video.status` 设为 `processing`，`total_segments=len(windows)`
    - 从 `start_index` 处理；每成功写一段 `last_segment_index += 1`，`done_segments += 1`（仅当该段被写入，无论有无 embedding）
    - 全部结束后，若 `embedding is None` 的段数 / total > 0.30 则 `failed`，否则 `ready`
    - 抽帧失败不在本函数：由 Task 9 在调用前把 video 标 failed

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_indexing.py
from pathlib import Path

from PIL import Image
from sqlalchemy import select

from video_analysis.adapters.fake import FakeCaptionAdapter, FakeEmbedAdapter, FakeOcrAdapter
from video_analysis.indexing import index_segment
from video_analysis.models import Segment, Video
from video_analysis.segmenting import SegmentWindow
from video_analysis.storage import LocalStorage


def _jpeg(path: Path) -> Path:
    Image.new("RGB", (16, 16), (255, 0, 0)).save(path, "JPEG")
    return path


def test_index_segment_writes_caption_embedding_fts(db_session, tmp_path: Path) -> None:
    frame = _jpeg(tmp_path / "0.jpg")
    video = Video(filename="a.mp4", duration_ms=8000, status="processing")
    db_session.add(video)
    db_session.flush()
    storage = LocalStorage(tmp_path)
    window = SegmentWindow(0, 4000, 0, [frame])
    seg = index_segment(
        db_session,
        video,
        window,
        FakeOcrAdapter({frame.name: "导出 客户名单"}),
        FakeCaptionAdapter("点击导出"),
        FakeEmbedAdapter(),
        storage,
    )
    db_session.commit()
    loaded = db_session.scalar(select(Segment).where(Segment.id == seg.id))
    assert "导出" in loaded.caption
    assert len(loaded.embedding) == 1024
    assert loaded.fts is not None
    assert loaded.caption_degraded is False


def test_index_segment_degrades_when_caption_fails(db_session, tmp_path: Path) -> None:
    frame = _jpeg(tmp_path / "0.jpg")
    video = Video(filename="a.mp4", duration_ms=8000, status="processing")
    db_session.add(video)
    db_session.flush()
    window = SegmentWindow(0, 4000, 0, [frame])
    seg = index_segment(
        db_session,
        video,
        window,
        FakeOcrAdapter({frame.name: "导出"}),
        FakeCaptionAdapter(fail=True),
        FakeEmbedAdapter(),
        LocalStorage(tmp_path),
    )
    assert seg.caption_degraded is True
    assert seg.embedding is not None
```

```python
# backend/tests/test_analyze.py
from pathlib import Path
from uuid import uuid4

from PIL import Image

from video_analysis.adapters.fake import FakeCaptionAdapter, FakeEmbedAdapter, FakeOcrAdapter
from video_analysis.analyze import analyze_video
from video_analysis.models import Segment, Video
from video_analysis.segmenting import SegmentWindow
from video_analysis.storage import LocalStorage


def _windows(tmp_path: Path, n: int) -> list[SegmentWindow]:
    frame = tmp_path / "0.jpg"
    Image.new("RGB", (16, 16), (1, 2, 3)).save(frame, "JPEG")
    return [
        SegmentWindow(i * 4000, i * 4000 + 4000, i * 4000, [frame])
        for i in range(n)
    ]


def test_analyze_resumes_from_start_index(db_session, tmp_path: Path) -> None:
    video = Video(id=uuid4(), filename="a.mp4", duration_ms=16000, status="queued")
    db_session.add(video)
    db_session.commit()
    status = analyze_video(
        db_session,
        video.id,
        _windows(tmp_path, 4),
        FakeOcrAdapter(),
        FakeCaptionAdapter(),
        FakeEmbedAdapter(),
        LocalStorage(tmp_path),
        start_index=2,
    )
    assert status == "ready"
    rows = db_session.query(Segment).filter(Segment.video_id == video.id).all()
    assert len(rows) == 2


class FailingEmbed:
    def embed(self, text: str) -> list[float]:
        raise RuntimeError("embed down")


def test_analyze_fails_when_too_many_missing_embeddings(db_session, tmp_path: Path) -> None:
    video = Video(id=uuid4(), filename="a.mp4", duration_ms=16000, status="queued")
    db_session.add(video)
    db_session.commit()
    status = analyze_video(
        db_session,
        video.id,
        _windows(tmp_path, 4),
        FakeOcrAdapter(),
        FakeCaptionAdapter(),
        FailingEmbed(),
        LocalStorage(tmp_path),
        start_index=0,
    )
    assert status == "failed"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_indexing.py tests/test_analyze.py -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

`indexing.py` 实现重试循环 `for attempt in range(3)`，捕获 Exception。`analyze.py` 循环 windows[start_index:]，每段 `session.commit()` 以便续跑。更新或创建 `AnalysisJob`。同一 `video_id` 若已有 `status in ("queued","processing")` 的 job 则复用。

`analyze_video` 在 `start_index==0` 且 mode 由调用方清空 segments 时不再负责删除；删除放在 `reset_video_segments(session, video_id)`：

```python
def reset_video_segments(session: Session, video_id: UUID) -> None:
    session.query(Segment).filter(Segment.video_id == video_id).delete()
    job = session.scalar(select(AnalysisJob).where(AnalysisJob.video_id == video_id).order_by(AnalysisJob.created_at.desc()))
    if job:
        job.last_segment_index = 0
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_indexing.py tests/test_analyze.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/video_analysis/indexing.py backend/src/video_analysis/analyze.py backend/tests/test_indexing.py backend/tests/test_analyze.py
git commit -m "feat: index segments with caption fallback and resumable analyze"
```

---

### Task 7: 混合检索、RRF、按录像分组

**Files:**
- Create: `backend/src/video_analysis/search.py`
- Create: `backend/tests/test_search.py`

**Interfaces:**
- Consumes: `Session`, `EmbedAdapter`, `Video`, `Segment`, `tokenize_fts`
- Produces:
  - `@dataclass class Hit(segment_id: str, video_id: str, t_start_ms: int, t_end_ms: int, caption: str, ocr_text: str, keyframe_url: str, score: float, caption_degraded: bool)`
  - `@dataclass class VideoGroup(video_id: str, filename: str, duration_ms: int, best_score: float, hits: list[Hit])`
  - `@dataclass class SearchResult(query: str, total_videos: int, limit_videos: int, offset_videos: int, videos: list[VideoGroup])`
  - `rrf_merge(ranked_ids: list[list[str]], k: int = 60) -> dict[str, float]`
  - `merge_overlapping_hits(hits: list[Hit]) -> list[Hit]` 同一 video 内区间重叠则合并：`t_start` 最早、`t_end` 最晚、caption 取 score 最高
  - `search_videos(session, embedder, query: str, limit_videos: int = 3, offset_videos: int = 0) -> SearchResult`
    - 只搜 `Video.status == "ready"` 且 `Segment.embedding IS NOT NULL`
    - 向量路：`ORDER BY embedding <=> query_vec` LIMIT 50
    - 全文路：`fts @@ plainto_tsquery('simple', tokenize_fts(query))` LIMIT 50
    - RRF 合并；分组；默认 3 个录像；`keyframe_url = f"/api/videos/{video_id}/frames/{Path(keyframe_path).name}"`

- [ ] **Step 1: Write the failing test**

`test_rrf_prefers_items_high_in_both_lists`

`test_search_returns_top_3_videos_with_all_hits`：插入 4 个 ready video。video A 两条高相似片段（embedding 用 `FakeEmbedAdapter().embed("导出 客户名单")` 与查询相同），video B/C 用相近但不相同文本，video D 用不相关文本 `"完全无关的界面"`。查询 `"有没有把客户名单导出去"`。断言 `len(result.videos)==3`，A 排第一且 `len(hits)>=1`，D 不在默认 3 个里。`total_videos >= 3`。

`test_keyword_path_hits_ocr_only`：video 的 caption 为 `"点击按钮"`，ocr 为 `"客户名单"`，embedding 用无关文本 `"zzzz-unrelated"`（让向量路排很后），查询 `"客户名单"`。断言该 video 出现在结果中（全文路召回）。

`test_offset_videos_pages`：`limit_videos=3, offset_videos=3` 时不包含第一页的 video_id。

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_search.py -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

向量查询用 pgvector 的 `Segment.embedding.cosine_distance(query_vec)` 或 `embedding.op("<=>")(query_vec)`。`rrf` 分数 `1/(k+rank)`，rank 从 1 开始。只对有 embedding 的段建向量列表；全文命中的 id 与向量 id 做字符串化 UUID。

`merge_overlapping_hits`：按 `t_start_ms` 排序，若 `hit.t_start_ms <= acc.t_end_ms` 则合并。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_search.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/video_analysis/search.py backend/tests/test_search.py
git commit -m "feat: hybrid search with rrf and top-3 video grouping"
```

---

### Task 8: FastAPI 接口

**Files:**
- Create: `backend/src/video_analysis/api.py`
- Create: `backend/tests/test_api.py`
- Modify: `backend/tests/conftest.py`（增加 `client` fixture：覆盖 `get_session`、注入 `LocalStorage(tmp_path)`、`FakeEmbedAdapter`，不启动 Celery，upload 后不自动分析或分析改用依赖注入的 `enqueue` mock）

**Interfaces:**
- Consumes: `LocalStorage`, `validate_upload`, `probe_video`, `search_videos`, `get_session`, `Video`, `analyze` 入队函数
- Produces: FastAPI `app`
  - `POST /api/videos` multipart `file` → `{id, status}`；校验失败 400；成功 `queued` 并调用 `enqueue_analyze(video_id, mode="resume")`
  - `GET /api/videos` 列表
  - `GET /api/videos/{id}` 详情，含进度
  - `POST /api/videos/{id}/reanalyze` body `{ "mode": "resume" | "full" }` 默认 resume；`full` 时调 `reset_video_segments` 再入队
  - `GET /api/videos/{id}/file` FileResponse；文件不存在 404
  - `GET /api/videos/{id}/frames/{name}` 仅允许 `{digits}.jpg`，防止路径穿越
  - `GET /api/search?q=&limit_videos=3&offset_videos=0`；DB 异常返回 503 JSON `{detail: "search unavailable"}`；空 q 返回 400

- [ ] **Step 1: Write the failing tests**

用 `TestClient`：

- 上传 `.txt` → 400
- 上传假 mp4 但 probe mock 返回 12500 → 201/200，`status==queued`，`enqueue` 被调用一次
- `GET /api/videos` 含该文件名
- 构造 ready video + segment 后 `GET /api/search?q=客户名单` 返回 `videos` 数组
- `GET /api/videos/{id}/file` 无文件 → 404
- `GET /api/search` 让 session.execute raise → 503

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_api.py -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

`api.py` 创建 `app = FastAPI()`。`Depends(get_session)`。本任务同时创建 `worker.py` 的最小桩，避免 import 失败；Task 9 替换 task 函数体：

```python
# backend/src/video_analysis/worker.py  （Task 8 桩）
from celery import Celery
from video_analysis.config import settings

celery_app = Celery("video_analysis", broker=settings.redis_url, backend=settings.redis_url)

@celery_app.task(bind=True)
def analyze_video_task(self, video_id: str, mode: str = "resume") -> str:
    return "queued"
```

```python
# backend/src/video_analysis/api.py
def enqueue_analyze(video_id: str, mode: str = "resume") -> None:
    from video_analysis.worker import analyze_video_task
    analyze_video_task.delay(video_id, mode)
```

测试通过 `monkeypatch.setattr("video_analysis.api.enqueue_analyze", lambda *a, **k: None)`。

上传：`UploadFile`，先 `validate_upload(file.filename, 0)` 不够（size 未知）。读取到 spoold 文件后 `stat().st_size`，超限删除并 400。写 `LocalStorage.save_source`（无论扩展名都存 `source.mp4`，与 spec 一致）。`probe_video` 失败则删文件、不写 DB、400。

CORS 允许 `http://localhost:5173`。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_api.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/video_analysis/api.py backend/tests/test_api.py backend/tests/conftest.py
git commit -m "feat: add upload list search and media HTTP APIs"
```

---

### Task 9: Celery Worker 与真实适配器接线

**Files:**
- Create: `backend/src/video_analysis/worker.py`
- Create: `backend/src/video_analysis/adapters/ocr_rapid.py`
- Create: `backend/src/video_analysis/adapters/caption_dashscope.py`
- Create: `backend/src/video_analysis/adapters/embed_bge.py`
- Create: `backend/tests/test_worker.py`

**Interfaces:**
- Consumes: `extract_frames`, `group_segments`, `analyze_video`, `reset_video_segments`, `LocalStorage`, `SessionLocal`
- Produces:
  - `celery_app = Celery("video_analysis", broker=settings.redis_url, backend=settings.redis_url)`
  - `@celery_app.task(bind=True) def analyze_video_task(self, video_id: str, mode: str = "resume") -> str`
    1. 取 Video；`full` 则 `reset_video_segments` 且 `last_segment_index=0`
    2. `extract_frames(source, frames_dir)`；失败则 `status=failed`，`error_message` 给人看，return `"failed"`
    3. `windows = group_segments(frames)`
    4. `start = job.last_segment_index`
    5. `analyze_video(..., start_index=start)` 注入真实或测试适配器
  - `build_adapters() -> tuple[OcrAdapter, CaptionAdapter, EmbedAdapter]`
    - OCR：`RapidOcrAdapter`
    - Caption：`settings.dashscope_api_key` 非空用 `DashScopeCaptionAdapter`，否则仍用会 raise 的路径让每段降级（开发无 key 时 OCR 仍可检索）。不要在生产静默用 FakeCaption 假装成功。
    - Embed：`BgeM3EmbedAdapter`（单例懒加载）
  - `DashScopeCaptionAdapter.caption`：OpenAI SDK，`base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"`，模型 `settings.caption_model`，多图 base64 + OCR 文本。系统提示要求输出一句中文操作描述，包含可见界面文字与推断动作，不要 Markdown。
  - `BgeM3EmbedAdapter.embed` 返回 1024 维 list[float]

- [ ] **Step 1: Write the failing test**

`test_worker.py` 使用 `celery_app.conf.task_always_eager = True`，monkeypatch `extract_frames` 返回已有 jpeg 列表，`group_segments` 返回两个 window，`build_adapters` 返回三个 Fake。断言 video 最终 `ready` 且 segments 数为 2。

`test_extract_frames_failure_marks_failed`：`extract_frames` raise，status `failed`，`source.mp4` 仍在。

`test_resume_skips_completed_windows`：预先插入 1 条 segment、`last_segment_index=1`、两个 window，最终 segments 仍为 2 不是 3。

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_worker.py -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

`ocr_rapid.py`：`from rapidocr_onnxruntime import RapidOCR`，`ocr(str(path))` 拼所有文本行。

`caption_dashscope.py`：读帧 bytes → base64 image_url。

`embed_bge.py`：

```python
class BgeM3EmbedAdapter:
    _model = None

    def embed(self, text: str) -> list[float]:
        if type(self)._model is None:
            from FlagEmbedding import BGEM3FlagModel
            type(self)._model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False)
        out = type(self)._model.encode([text], return_dense=True)
        vec = out["dense_vecs"][0]
        return [float(x) for x in vec.tolist()]
```

`worker.py` 实现 task。eager 测试不加载 BGE：必须 mock `build_adapters`。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_worker.py -v
```

Expected: PASS（不下载 BGE、不调用 DashScope）

- [ ] **Step 5: Commit**

```bash
git add backend/src/video_analysis/worker.py backend/src/video_analysis/adapters/ocr_rapid.py backend/src/video_analysis/adapters/caption_dashscope.py backend/src/video_analysis/adapters/embed_bge.py backend/tests/test_worker.py
git commit -m "feat: wire celery analyze task and swappable model adapters"
```

---

### Task 10: 前端录像库与检索播放

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`（`server.proxy."/api" -> http://127.0.0.1:8000`）
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.app.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/seek.ts`
- Create: `frontend/src/seek.test.ts`
- Create: `frontend/src/pages/LibraryPage.tsx`
- Create: `frontend/src/pages/SearchPage.tsx`
- Create: `frontend/vitest.config.ts`
- Create: `README.md`

**Interfaces:**
- Consumes: Task 8 的 API JSON 形状（字段名必须一致：`videos[].best_score`, `hits[].t_start_ms`, `keyframe_url`）
- Produces:
  - `seekSeconds(tStartMs: number): number` 与后端 `player_seek_seconds` 同一公式
  - `LibraryPage`：上传、列表、状态文案（queued=排队中，processing 且 total_segments 空=切段中，否则 `done/total`，ready=可搜索，failed=失败+重新分析）、`reanalyze(id, "resume")`
  - `SearchPage`：搜索框；默认展示最多 3 组；每组列出全部 hits；空态「点左侧录像或时间点开始播放」；点击组或 hit 才给 `<video src={/api/videos/id/file}>` 设 `currentTime = seekSeconds(t_start_ms)` 并 `play()`；同 video 只改 currentTime
  - 路由：`/` 库，`/search` 检索。无登录。

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/seek.test.ts
import { describe, expect, it } from "vitest";
import { seekSeconds } from "./seek";

describe("seekSeconds", () => {
  it("subtracts one second", () => {
    expect(seekSeconds(123000)).toBe(122);
  });
  it("floors at zero", () => {
    expect(seekSeconds(400)).toBe(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npm install && npx vitest run src/seek.test.ts
```

Expected: FAIL（`seek` 未定义）。先写 `package.json` 含 `react`, `react-dom`, `react-router-dom`, `vitest`, `jsdom`, `typescript`, `vite`, `@vitejs/plugin-react`。

- [ ] **Step 3: Write minimal implementation**

`seek.ts`：`export function seekSeconds(tStartMs: number, leadMs = 1000): number { return Math.max(0, tStartMs - leadMs) / 1000; }`

`api.ts`：`uploadVideo`, `listVideos`, `getVideo`, `reanalyze`, `searchVideos(q, limit=3, offset=0)`，类型与 spec 第 7.1 节 JSON 一致。

`LibraryPage.tsx`：`<input type="file" accept=".mp4,.webm,.mov">` + dragover；轮询 `GET /api/videos` 每 3 秒当存在 queued/processing。

`SearchPage.tsx`：左侧 map `result.videos`；「更多录像」调用 `offset_videos += videos.length` 追加。右侧 `<video controls />`，`useRef`。点击 handler：

```ts
if (currentVideoId !== video.video_id) {
  currentVideoId = video.video_id;
  videoEl.src = `/api/videos/${video.video_id}/file`;
}
const t = hit ? hit.t_start_ms : video.hits[0].t_start_ms;
videoEl.currentTime = seekSeconds(t);
void videoEl.play();
```

未选择时不渲染 `<video>` 或 src 为空，显示空态文字。

`README.md` 写清：

1. `docker compose up -d db redis`
2. `cd backend && alembic upgrade head && uvicorn video_analysis.api:app --reload --app-dir src`
3. `cd backend && celery -A video_analysis.worker.celery_app worker --loglevel=info`
4. `cd frontend && npm run dev`
5. 系统依赖：ffmpeg、ffprobe
6. `DASHSCOPE_API_KEY`；首次 Worker 会下载 `BAAI/bge-m3`
7. 验收：3–5 条真实屏幕录像 + 标注查询，对照 spec 1.1

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/seek.test.ts
cd backend && python -m pytest -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend README.md
git commit -m "feat: add library and search playback UI"
```

---

## 实现时不要做的事

- 不要加登录、MinIO、Qdrant、视频原生 embedding、操作人、GUI 解析
- 不要把 BGE 或 DashScope 写进单测网络路径
- 不要默认自动播放第一条检索结果

---

## Self-review（对照 spec）

| Spec 节 | 对应任务 |
|---|---|
| 1.1 验收 1–5、OCR 关键词 | Task 6–10 + README 手工评测 |
| 1.2 / 11 不做项 | 「不要做的事」 |
| 3 适配器、Qwen-VL、BGE-M3、RapidOCR | Task 5、9 |
| 4 四层架构 | Task 8 API + Task 9 Worker + Task 10 前端 |
| 5.1 上传 | Task 3、8 |
| 5.2 切段 2–8s | Task 4 |
| 5.3 OCR/描述/向量/jieba FTS | Task 5、6 |
| 5.4 双路 RRF、默认 3 录像 | Task 7 |
| 5.5 点哪个播哪个、提前 1 秒 | Task 5 playback、Task 10 |
| 6 表结构、续跑游标 | Task 2、6 |
| 7 API 全表 | Task 8 |
| 8 两页前端 | Task 10 |
| 9 失败、30% 阈值、503、404 | Task 6、8、9 |
| 10.1 自动化 | 各任务测试 |
| 10.2 手工评测集 | README，不自动化真实模型 |

无 TBD。类型名全程：`SegmentWindow`、`Hit`、`VideoGroup`、`SearchResult`、`analyze_video_task(video_id, mode)`、`limit_videos` / `offset_videos`。
