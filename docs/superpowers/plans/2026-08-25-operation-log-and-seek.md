# Operation Log Captions + Search Seek Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make segment text read as operation logs (`[mm:ss] …`), and make search clicks seek then play at the hit time (not from 0).

**Architecture:** Strengthen Zhipu caption system prompt and OCR pseudo-log on degrade (caption still stores text without clock). Frontend formats `[mm:ss]` from `t_start_ms`, restyles hit rows as log lines, and changes `bindSeekOnMetadata` to wait for `seeked` before `play()`.

**Tech Stack:** FastAPI / SQLAlchemy indexing, Zhipu caption adapter, React + Vitest, existing `seekSeconds` / Celery reanalyze (unchanged).

## Global Constraints

- Caption stored in DB must **not** include `[mm:ss]`; clock is display-only from `t_start_ms`.
- Seek lead remains `leadMs = 1000` via existing `seekSeconds`.
- Do not auto-reanalyze historical videos; rely on existing「重新分析」.
- Do not change Library page preview (may start at 0).
- No second LLM rewrite; no model-emitted timestamps.
- Spec: `docs/superpowers/specs/2026-08-25-operation-log-and-seek-design.md`.

## File map

| File | Responsibility |
|------|----------------|
| `backend/src/video_analysis/adapters/caption_zhipu.py` | Operation-log system prompt |
| `backend/src/video_analysis/indexing.py` | `ocr_pseudo_log`; use when caption degrades |
| `backend/tests/test_indexing.py` | Pseudo-log + degrade caption content |
| `backend/tests/test_caption_prompt.py` | Prompt content guards (new) |
| `frontend/src/operationLog.ts` | `formatClock` + `formatOperationLogLine` (new) |
| `frontend/src/operationLog.test.ts` | Unit tests (new) |
| `frontend/src/videoPlayback.ts` | Seek then wait `seeked` then play |
| `frontend/src/videoPlayback.test.ts` | Update/add seeked tests |
| `frontend/src/pages/SearchPage.tsx` | Log UI + best-hit play |
| `frontend/src/styles.css` | Log row styles |

---

### Task 1: OCR pseudo-log on caption degrade

**Files:**
- Modify: `backend/src/video_analysis/indexing.py`
- Test: `backend/tests/test_indexing.py`

**Interfaces:**
- Consumes: existing `index_segment`, `FakeCaptionAdapter(fail=True)`
- Produces: `ocr_pseudo_log(ocr_text: str, max_chars: int = 80) -> str`; on degrade, `Segment.caption` is pseudo-log (may be `""` if OCR empty)

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_indexing.py`, update degrade test and add:

```python
from video_analysis.indexing import ocr_pseudo_log

def test_ocr_pseudo_log_compacts_whitespace_and_truncates() -> None:
    assert ocr_pseudo_log("导出\n  客户") == "导出 客户"
    long = "字" * 100
    out = ocr_pseudo_log(long, max_chars=20)
    assert len(out) == 20
    assert out.endswith("…")

def test_index_segment_degrades_when_caption_fails(db_session, tmp_path: Path) -> None:
    # ... existing setup with FakeOcrAdapter({frame.name: "导出 客户名单"}) ...
    assert seg.caption_degraded is True
    assert seg.caption == "导出 客户名单"
    assert seg.embedding is not None
```

(Keep existing JPEG / window setup from the current degrade test; only change OCR text and assertions on `caption`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_indexing.py::test_ocr_pseudo_log_compacts_whitespace_and_truncates tests/test_indexing.py::test_index_segment_degrades_when_caption_fails -v`

Expected: FAIL (`ocr_pseudo_log` not defined and/or `caption == ""`)

- [ ] **Step 3: Write minimal implementation**

In `indexing.py`:

```python
def ocr_pseudo_log(ocr_text: str, max_chars: int = 80) -> str:
    compact = " ".join(ocr_text.split())
    if not compact:
        return ""
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1] + "…"
```

In `index_segment`, when setting degrade path (`skip_caption` or caption exception), set:

```python
caption_degraded = True
caption = ocr_pseudo_log(ocr_text)
```

Keep embed input as today: when degraded, `embed_input = ocr_text` (full OCR), not necessarily the truncated caption.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_indexing.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/video_analysis/indexing.py backend/tests/test_indexing.py
git commit -m "feat: store OCR pseudo-log when caption degrades"
```

---

### Task 2: Operation-log caption system prompt

**Files:**
- Modify: `backend/src/video_analysis/adapters/caption_zhipu.py`
- Create: `backend/tests/test_caption_prompt.py`

**Interfaces:**
- Consumes: none
- Produces: module-level `_SYSTEM_PROMPT` (or exported `CAPTION_SYSTEM_PROMPT`) with operation-log rules; `ZhipuCaptionAdapter.caption` unchanged signature

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_caption_prompt.py
from video_analysis.adapters.caption_zhipu import CAPTION_SYSTEM_PROMPT

def test_caption_prompt_requires_operation_log_style() -> None:
    p = CAPTION_SYSTEM_PROMPT
    assert "操作" in p or "动作" in p
    assert "OCR" in p or "界面" in p
    assert "时间" in p or "时间戳" in p  # ban timestamps
    assert "Markdown" in p or "markdown" in p.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_caption_prompt.py -v`

Expected: FAIL (import / old prompt)

- [ ] **Step 3: Write minimal implementation**

In `caption_zhipu.py`, replace prompt and export alias:

```python
CAPTION_SYSTEM_PROMPT = (
    "你是软件操作录屏的标注器。只输出一句中文操作日志，不要 Markdown，不要时间戳。"
    "句式：在「页面或模块名」· 动作 · 关键对象或输入内容。"
    "必须优先使用 OCR 文本中的真实按钮/菜单/字段文案；不要空泛形容界面。"
    "不要写「用户可能」「似乎」等推测套话。"
)
_SYSTEM_PROMPT = CAPTION_SYSTEM_PROMPT
```

Keep `messages=[{"role":"system","content": _SYSTEM_PROMPT}, ...]`.

- [ ] **Step 4: Run tests**

Run: `cd backend && .venv/bin/pytest tests/test_caption_prompt.py tests/test_worker.py tests/test_indexing.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/video_analysis/adapters/caption_zhipu.py backend/tests/test_caption_prompt.py
git commit -m "feat: require operation-log style in Zhipu caption prompt"
```

---

### Task 3: Frontend operation log line formatter

**Files:**
- Create: `frontend/src/operationLog.ts`
- Create: `frontend/src/operationLog.test.ts`

**Interfaces:**
- Consumes: none
- Produces:
  - `formatClock(tStartMs: number): string` → `m:ss` (same as current SearchPage `formatTime`)
  - `formatOperationLogLine(tStartMs: number, caption: string, ocrText: string): string` → `[m:ss] body` where `body` is trimmed caption, else whitespace-compacted OCR (truncate ~80), else `（无描述）`

- [ ] **Step 1: Write the failing test**

```typescript
import { describe, expect, it } from "vitest";
import { formatClock, formatOperationLogLine } from "./operationLog";

describe("formatClock", () => {
  it("formats mm:ss from ms", () => {
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(65000)).toBe("1:05");
  });
});

describe("formatOperationLogLine", () => {
  it("prefers caption over OCR", () => {
    expect(formatOperationLogLine(12000, "在「网元」· 修改网元 · IP", "噪声")).toBe(
      "[0:12] 在「网元」· 修改网元 · IP",
    );
  });

  it("falls back to compacted OCR", () => {
    expect(formatOperationLogLine(5000, "", "导出\n客户")).toBe("[0:05] 导出 客户");
  });

  it("uses placeholder when empty", () => {
    expect(formatOperationLogLine(0, "  ", "")).toBe("[0:00] （无描述）");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run src/operationLog.test.ts`

Expected: FAIL (module missing)

- [ ] **Step 3: Write minimal implementation**

```typescript
// frontend/src/operationLog.ts
export function formatClock(tStartMs: number): string {
  const totalSec = Math.floor(tStartMs / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function compactText(text: string, maxChars = 80): string {
  const compact = text.trim().split(/\s+/).join(" ");
  if (!compact) return "";
  if (compact.length <= maxChars) return compact;
  return compact.slice(0, maxChars - 1) + "…";
}

export function formatOperationLogLine(
  tStartMs: number,
  caption: string,
  ocrText: string,
): string {
  const body =
    caption.trim() || compactText(ocrText) || "（无描述）";
  return `[${formatClock(tStartMs)}] ${body}`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run src/operationLog.test.ts`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/operationLog.ts frontend/src/operationLog.test.ts
git commit -m "feat: add operation log line formatter for search hits"
```

---

### Task 4: Seek then wait for `seeked` before play

**Files:**
- Modify: `frontend/src/videoPlayback.ts`
- Modify: `frontend/src/videoPlayback.test.ts`

**Interfaces:**
- Consumes: existing `bindSeekOnMetadata` opts (`generation`, `isCurrent`, `timeSeconds`, `waitForMetadata`, `play`)
- Produces: same function name/signature; behavior: after setting `currentTime`, wait for `seeked` (or apply play immediately only if `currentTime` already equals target within epsilon), then call `play`; `cancel` removes both `loadedmetadata` and `seeked` listeners

- [ ] **Step 1: Write the failing tests**

Replace/extend tests so play does **not** run until `seeked`:

```typescript
it("waits for seeked before play when metadata ready", () => {
  const el = fakeVideo(1);
  const play = vi.fn();
  bindSeekOnMetadata(el as unknown as HTMLMediaElement, {
    generation: 1,
    isCurrent: () => true,
    timeSeconds: 5,
    waitForMetadata: false,
    play,
  });
  expect(el.currentTime).toBe(5);
  expect(play).not.toHaveBeenCalled();
  el.dispatch("seeked");
  expect(play).toHaveBeenCalledTimes(1);
});

it("after loadedmetadata, seeks then plays on seeked", () => {
  const el = fakeVideo(0);
  const play = vi.fn();
  bindSeekOnMetadata(el as unknown as HTMLMediaElement, {
    generation: 1,
    isCurrent: () => true,
    timeSeconds: 12,
    waitForMetadata: true,
    play,
  });
  el.dispatch("loadedmetadata");
  expect(el.currentTime).toBe(12);
  expect(play).not.toHaveBeenCalled();
  el.dispatch("seeked");
  expect(play).toHaveBeenCalledTimes(1);
});

it("ignores stale seeked after cancel / newer generation", () => {
  const el = fakeVideo(0);
  let generation = 1;
  const play = vi.fn();
  const first = bindSeekOnMetadata(el as unknown as HTMLMediaElement, {
    generation: 1,
    isCurrent: (g) => g === generation,
    timeSeconds: 10,
    waitForMetadata: true,
    play,
  });
  generation = 2;
  first.cancel();
  bindSeekOnMetadata(el as unknown as HTMLMediaElement, {
    generation: 2,
    isCurrent: (g) => g === generation,
    timeSeconds: 42,
    waitForMetadata: true,
    play,
  });
  el.dispatch("loadedmetadata");
  el.dispatch("seeked");
  expect(el.currentTime).toBe(42);
  expect(play).toHaveBeenCalledTimes(1);
});
```

Update `fakeVideo` if needed so assigning `currentTime` works (already does).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- --run src/videoPlayback.test.ts`

Expected: FAIL (play called too early / old expectations)

- [ ] **Step 3: Write minimal implementation**

Rewrite `bindSeekOnMetadata` core:

```typescript
export function bindSeekOnMetadata(
  videoEl: HTMLMediaElement,
  opts: {
    generation: number;
    isCurrent: (generation: number) => boolean;
    timeSeconds: number;
    waitForMetadata: boolean;
    play: (el: HTMLMediaElement) => void;
  },
): SeekBinding {
  let cancelled = false;
  let onLoaded: (() => void) | null = null;
  let onSeeked: (() => void) | null = null;

  const clearSeeked = () => {
    if (onSeeked) {
      videoEl.removeEventListener("seeked", onSeeked);
      onSeeked = null;
    }
  };

  const cancel = () => {
    cancelled = true;
    if (onLoaded) {
      videoEl.removeEventListener("loadedmetadata", onLoaded);
      onLoaded = null;
    }
    clearSeeked();
  };

  const playIfCurrent = () => {
    if (cancelled || !opts.isCurrent(opts.generation)) return;
    opts.play(videoEl);
  };

  const seekThenPlay = () => {
    if (cancelled || !opts.isCurrent(opts.generation)) return;
    clearSeeked();
    onSeeked = () => {
      onSeeked = null;
      playIfCurrent();
    };
    videoEl.addEventListener("seeked", onSeeked, { once: true });
    videoEl.currentTime = opts.timeSeconds;
    // If the browser does not fire seeked when already at target:
    if (Math.abs(videoEl.currentTime - opts.timeSeconds) < 0.001) {
      clearSeeked();
      playIfCurrent();
    }
  };

  if (!opts.waitForMetadata && videoEl.readyState >= 1) {
    seekThenPlay();
    return { cancel };
  }

  onLoaded = () => {
    onLoaded = null;
    seekThenPlay();
  };
  videoEl.addEventListener("loadedmetadata", onLoaded, { once: true });
  if (opts.waitForMetadata) {
    videoEl.load();
  }
  return { cancel };
}
```

Note: In unit tests, after setting `currentTime`, fake element already equals target — the epsilon branch may call `play` immediately. Prefer **not** using the epsilon short-circuit in production if it breaks the test intent; instead make the fake **not** update `currentTime` until a setter, or remove epsilon and always require `seeked` in tests by dispatching it. **Preferred for tests:** always wait for `seeked` only (no epsilon). Real browsers fire `seeked` after programmatic seek.

Use **always wait for seeked** (no epsilon) to match tests and real media elements.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- --run src/videoPlayback.test.ts`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/videoPlayback.ts frontend/src/videoPlayback.test.ts
git commit -m "fix: wait for seeked before playing search hits"
```

---

### Task 5: Search page operation-log UI + best-hit play

**Files:**
- Modify: `frontend/src/pages/SearchPage.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: `formatOperationLogLine`, `formatClock` from `operationLog.ts`; `bindSeekOnMetadata` (Task 4); `seekSeconds`; `Hit.score` for best hit
- Produces: Search hit primary line is operation log; `playHit(video)` uses highest-score hit (`hits[0]` already sorted by API, but select explicitly with `reduce`/`Math.max` for clarity)

- [ ] **Step 1: Adjust SearchPage display and playHit**

Remove local `formatTime` (use `formatClock` / log helper).

Hit button body:

```tsx
<div className="log-line">
  {formatOperationLogLine(hit.t_start_ms, hit.caption, hit.ocr_text)}
</div>
<div className="meta">
  {formatClock(hit.t_start_ms)}–{formatClock(hit.t_end_ms)} · {hit.score.toFixed(3)}
  {hit.caption_degraded ? " · 描述降级" : ""}
</div>
{hit.ocr_text.trim() ? (
  <details className="ocr-fold">
    <summary>OCR</summary>
    <pre>{hit.ocr_text}</pre>
  </details>
) : null}
```

In `playHit`:

```typescript
function bestHit(video: VideoGroup): Hit | undefined {
  if (video.hits.length === 0) return undefined;
  return video.hits.reduce((a, b) => (b.score > a.score ? b : a));
}

function playHit(video: VideoGroup, hit?: Hit) {
  const targetHit = hit ?? bestHit(video);
  if (!targetHit || !videoRef.current) return;
  // ... existing switching / bindSeekOnMetadata using seekSeconds(targetHit.t_start_ms)
}
```

Keep `waitForMetadata: switching` behavior; do not call `load()` when not switching.

- [ ] **Step 2: Styles**

In `styles.css`, add roughly:

```css
.log-line {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.95rem;
  line-height: 1.4;
  white-space: pre-wrap;
}
.ocr-fold {
  margin-top: 0.25rem;
  font-size: 0.8rem;
  color: #666;
}
.ocr-fold pre {
  white-space: pre-wrap;
  margin: 0.25rem 0 0;
}
```

- [ ] **Step 3: Run frontend tests**

Run: `cd frontend && npm test -- --run`

Expected: PASS (all existing + new)

- [ ] **Step 4: Manual smoke (if API/worker up)**

1. Open检索, search a known phrase.
2. Click group head → player time ≈ `seekSeconds(best.t_start_ms)`.
3. Click another hit → time updates to that hit (not 0).
4. Optional: full reanalyze one video after deploy to see new caption style.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/SearchPage.tsx frontend/src/styles.css
git commit -m "feat: show search hits as operation log lines"
```

---

## Spec coverage (self-review)

| Spec requirement | Task |
|------------------|------|
| Operation-log VLM prompt | Task 2 |
| Caption without `[mm:ss]` in DB | Task 2 (prompt forbids); display Task 3/5 |
| OCR pseudo-log on degrade | Task 1 |
| Display `[mm:ss] …` | Task 3 + 5 |
| OCR folded/weakened | Task 5 |
| Whole-card → best hit seek | Task 5 `bestHit` |
| Single hit seek + 1s lead | Task 5 + existing `seekSeconds` |
| seeked-before-play + cancel | Task 4 |
| No auto reanalyze / library unchanged | Global constraints |

## Placeholder scan

No TBD / “implement later” left in tasks.

## Type consistency

- `formatOperationLogLine(tStartMs, caption, ocrText)` used in Task 5 as defined in Task 3.
- `bindSeekOnMetadata` opts unchanged across Task 4–5.
- `CAPTION_SYSTEM_PROMPT` exported name used in Task 2 tests.
