import { useEffect, useState, type FormEvent, type MouseEvent } from "react";
import {
  searchVideos,
  type Hit,
  type SearchQuery,
  type SearchResult,
  type VideoGroup,
} from "../api";
import { formatClock, hitCaptionBody } from "../operationLog";
import { onVideoDeleted, usePlayer } from "../player";
import { IconError, IconFile, IconPlay, IconReset, IconSearch, showToast } from "../ui";

const MIN_SCORE_KEY = "va.search.minScore";
const DEFAULT_MIN_SCORE = 0.45;

type DateRangeKey = "all" | "today" | "week" | "month";

const DATE_RANGE_OPTIONS: { key: DateRangeKey; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "today", label: "当天" },
  { key: "week", label: "近 7 天" },
  { key: "month", label: "近 30 天" },
];

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function toYmd(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function datesForRange(key: DateRangeKey): { from: string; to: string } {
  if (key === "all") return { from: "", to: "" };
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  if (key === "today") return { from: toYmd(today), to: toYmd(today) };
  const from = new Date(today);
  from.setDate(from.getDate() + (key === "week" ? -6 : -29));
  return { from: toYmd(from), to: toYmd(today) };
}

function bestHit(video: VideoGroup): Hit | undefined {
  if (video.hits.length === 0) return undefined;
  return video.hits.reduce((a, b) => (b.score > a.score ? b : a));
}

function formatScore(score: number): string {
  return `${Math.round(score * 100)}%`;
}

function readStoredMinScore(): number {
  try {
    const raw = localStorage.getItem(MIN_SCORE_KEY);
    if (raw == null) return DEFAULT_MIN_SCORE;
    const n = Number(raw);
    if (!Number.isFinite(n)) return DEFAULT_MIN_SCORE;
    return Math.min(1, Math.max(0, n));
  } catch {
    return DEFAULT_MIN_SCORE;
  }
}

function dayStartIso(ymd: string): string {
  return new Date(`${ymd}T00:00:00`).toISOString();
}

function dayEndIso(ymd: string): string {
  return new Date(`${ymd}T23:59:59.999`).toISOString();
}

export default function SearchPage() {
  const { openPlayer, closePlayer, playingKey } = usePlayer();
  const [query, setQuery] = useState("");
  const [dateRange, setDateRange] = useState<DateRangeKey>("today");
  const [createdFrom, setCreatedFrom] = useState(() => datesForRange("today").from);
  const [createdTo, setCreatedTo] = useState(() => datesForRange("today").to);
  const [minScore, setMinScore] = useState(readStoredMinScore);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [openOcr, setOpenOcr] = useState<Set<string>>(new Set());
  const [applied, setApplied] = useState<SearchQuery | null>(null);

  useEffect(() => {
    return onVideoDeleted((id) => {
      setResult((cur) => {
        if (!cur) return cur;
        return { ...cur, videos: cur.videos.filter((v) => v.video_id !== id) };
      });
    });
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(MIN_SCORE_KEY, String(minScore));
    } catch {
      /* ignore quota / private mode */
    }
  }, [minScore]);

  function buildQuery(q: string, offset: number): SearchQuery {
    return {
      q,
      limit: 3,
      offset,
      minScore,
      createdFrom: createdFrom ? dayStartIso(createdFrom) : undefined,
      createdTo: createdTo ? dayEndIso(createdTo) : undefined,
    };
  }

  function applyDateRange(key: DateRangeKey) {
    const next = datesForRange(key);
    setDateRange(key);
    setCreatedFrom(next.from);
    setCreatedTo(next.to);
  }

  function onManualDate(which: "from" | "to", value: string) {
    setDateRange("all");
    if (which === "from") setCreatedFrom(value);
    else setCreatedTo(value);
  }

  function resetFilters() {
    setQuery("");
    applyDateRange("all");
    setMinScore(DEFAULT_MIN_SCORE);
    setResult(null);
    setApplied(null);
    setError(null);
    closePlayer();
    showToast("已重置筛选条件");
  }

  function playHit(video: VideoGroup, hit?: Hit) {
    const targetHit = hit ?? bestHit(video);
    if (!targetHit) return;
    openPlayer({
      videoId: video.video_id,
      filename: video.filename,
      tStartMs: targetHit.t_start_ms,
      hitKey: `${video.video_id}:${targetHit.segment_id}`,
    });
  }

  async function runSearch(e?: FormEvent) {
    e?.preventDefault();
    const q = query.trim();
    if (!q) {
      showToast("请输入搜索内容", false);
      return;
    }
    setLoading(true);
    setError(null);
    closePlayer();
    const params = buildQuery(q, 0);
    try {
      const next = await searchVideos(params);
      setApplied(params);
      setResult(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  async function loadMore() {
    if (!result || !applied) return;
    const offset = result.videos.reduce((n, video) => n + video.hits.length, 0);
    if (offset >= result.total_hits) return;
    setLoading(true);
    setError(null);
    try {
      const more = await searchVideos({ ...applied, offset, limit: result.limit_hits });
      const merged = new Map(
        result.videos.map((video) => [video.video_id, { ...video, hits: [...video.hits] }]),
      );
      for (const group of more.videos) {
        const existing = merged.get(group.video_id);
        if (existing) {
          existing.hits.push(...group.hits);
        } else {
          merged.set(group.video_id, group);
        }
      }
      setResult({
        ...more,
        videos: [...merged.values()],
        offset_hits: result.offset_hits,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  function toggleOcr(id: string, e: MouseEvent) {
    e.stopPropagation();
    setOpenOcr((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const canLoadMore =
    result != null &&
    result.videos.reduce((n, video) => n + video.hits.length, 0) < result.total_hits;

  const scorePct = Math.round(minScore * 100);

  return (
    <div>
      <div className="card">
        <form className="search-form" onSubmit={(e) => void runSearch(e)}>
          <div className="search-bar">
            <div className="search-wrap">
              <input
                className="search-input"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="用自然语言描述操作画面…"
                aria-label="搜索"
              />
            </div>
            <button type="submit" className="btn primary search-btn" disabled={loading}>
              <IconSearch />
              {loading ? "搜索中…" : "搜索"}
            </button>
            <button type="button" className="search-reset" disabled={loading} onClick={resetFilters}>
              <IconReset />
              重置
            </button>
          </div>
          <div className="search-filters">
            <div className="sf-label">
              <span>入库时间</span>
              <input
                className="sf-date-input"
                type="date"
                value={createdFrom}
                onChange={(e) => onManualDate("from", e.target.value)}
                aria-label="开始日期"
              />
              <span className="sf-sep">至</span>
              <input
                className="sf-date-input"
                type="date"
                value={createdTo}
                onChange={(e) => onManualDate("to", e.target.value)}
                aria-label="结束日期"
              />
            </div>
            <div className="sf-quick-tags" role="group" aria-label="快捷时间">
              {DATE_RANGE_OPTIONS.map((opt) => (
                <button
                  key={opt.key}
                  type="button"
                  className={dateRange === opt.key ? "active" : undefined}
                  onClick={() => applyDateRange(opt.key)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <div className="sf-slider-wrap">
              <span className="sf-label">最低相关度</span>
              <input
                className="sf-slider"
                type="range"
                min={0}
                max={100}
                step={1}
                value={scorePct}
                style={{ ["--pct" as string]: `${scorePct}%` }}
                onChange={(e) => setMinScore(Number(e.target.value) / 100)}
                aria-label="最低相关度"
              />
              <span className="sf-slider-val">{scorePct}%</span>
            </div>
          </div>
        </form>
        <div className="search-hint">
          <b>跨全部录像按相关性检索</b>
          ；低于最低相关度的片段不返回。
          <b>入库时间</b>
          为录像上传日期。
        </div>
      </div>

      {error ? (
        <div className="error-banner">
          <IconError />
          <span>{error}</span>
        </div>
      ) : null}

      <div className="result-pane">
        {result == null && !error ? (
          <div className="empty">
            <IconSearch />
            <div className="t1">用自然语言描述操作画面，全局检索录像片段</div>
            <div className="t2">例如：登录 4A 平台、导出用户列表、查询订单</div>
          </div>
        ) : null}

        {result != null && result.videos.length === 0 ? (
          <div className="empty">
            <IconSearch />
            <div className="t1">未找到与「{result.query}」相关的片段</div>
            <div className="t2">
              换个说法试试，或降低最低相关度、放宽入库时间
            </div>
          </div>
        ) : null}

        {result?.videos.map((video) => (
          <div key={video.video_id} className="hit-group">
            <button type="button" className="hit-group-head" onClick={() => playHit(video)}>
              <span className="g-file">
                <IconFile />
                {video.filename}
              </span>
              <span className="g-best">最高 {formatScore(video.best_score)}</span>
              <span className="g-play">▶ 播放最优命中</span>
            </button>
            <div className="hit-grid">
              {video.hits.map((hit) => {
                const key = `${video.video_id}:${hit.segment_id}`;
                const ocrOpen = openOcr.has(hit.segment_id);
                return (
                  <div
                    key={hit.segment_id}
                    className={`hit-card${playingKey === key ? " playing" : ""}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => playHit(video, hit)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        playHit(video, hit);
                      }
                    }}
                  >
                    <div className="hc-thumb">
                      <img src={hit.keyframe_url} alt="" />
                      <span className="hc-time-badge">{formatClock(hit.t_start_ms)}</span>
                      <div className="hc-play-badge">
                        <span className="pb">
                          <IconPlay />
                        </span>
                      </div>
                    </div>
                    <div className="hc-body">
                      <div className="hc-text">
                        <span className="tc">[{formatClock(hit.t_start_ms)}]</span>
                        {hitCaptionBody(hit.caption, hit.ocr_text)}
                      </div>
                      <div className="hc-meta">
                        <span>
                          {formatClock(hit.t_start_ms)}–{formatClock(hit.t_end_ms)}
                        </span>
                        <span>·</span>
                        <span>相关度 {formatScore(hit.score)}</span>
                        {hit.caption_degraded ? (
                          <span className="degraded">描述降级</span>
                        ) : null}
                      </div>
                      {hit.ocr_text.trim() ? (
                        <>
                          <button
                            type="button"
                            className="ocr-toggle hc-ocr"
                            onClick={(e) => toggleOcr(hit.segment_id, e)}
                          >
                            OCR
                          </button>
                          <div className={`ocr-body${ocrOpen ? " open" : ""}`}>{hit.ocr_text}</div>
                        </>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}

        {canLoadMore ? (
          <div className="more-wrap">
            <button
              type="button"
              className="btn text"
              disabled={loading}
              onClick={() => void loadMore()}
            >
              更多命中
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
