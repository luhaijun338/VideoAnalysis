import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  DuplicateUploadError,
  UploadAbortedError,
  deleteVideo,
  listVideos,
  reanalyze,
  uploadVideo,
  type Video,
} from "../api";
import { formatClock } from "../operationLog";
import { analysisPercent } from "../analysisProgress";
import { usePlayer } from "../player";
import { IconFile, IconTrash, IconUpload, IconVideo, IconWarn, showToast } from "../ui";

export function statusLabel(video: Video): string {
  if (video.status === "queued") return "排队中";
  if (video.status === "processing") return `${analysisPercent(video)}%`;
  if (video.status === "ready") return "可搜索";
  if (video.status === "failed") return "失败";
  return video.status;
}

function StatusCell({ video }: { video: Video }) {
  if (video.status === "queued" || video.status === "processing") {
    const pct = analysisPercent(video);
    return (
      <div className="progress">
        <span className="bar">
          <i style={{ width: `${pct}%` }} />
        </span>
        <span className="num">{video.status === "queued" ? "排队中" : `${pct}%`}</span>
      </div>
    );
  }
  if (video.status === "failed") {
    return (
      <div>
        <span className="tag failed">失败</span>
        {video.error_message ? (
          <div className="err-msg" title={video.error_message}>
            {video.error_message}
          </div>
        ) : null}
      </div>
    );
  }
  if (video.status === "ready") return <span className="tag ready">可搜索</span>;
  return <span className="tag processing">{video.status}</span>;
}

export default function LibraryPage() {
  const navigate = useNavigate();
  const { openPlayer, notifyVideoDeleted } = usePlayer();
  const [videos, setVideos] = useState<Video[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [dupName, setDupName] = useState<string | null>(null);
  const [delVideo, setDelVideo] = useState<Video | null>(null);
  const [uploads, setUploads] = useState<{ id: string; name: string; controller: AbortController }[]>(
    [],
  );
  const inputRef = useRef<HTMLInputElement>(null);
  const dupResolveRef = useRef<((ok: boolean) => void) | null>(null);

  const refresh = useCallback(async () => {
    try {
      const list = await listVideos();
      setVideos(list);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const busy = videos.some((v) => v.status === "queued" || v.status === "processing");
    if (!busy) return;
    const timer = window.setInterval(() => {
      void refresh();
    }, 1000);
    return () => window.clearInterval(timer);
  }, [videos, refresh]);

  function confirmOverwrite(filename: string): Promise<boolean> {
    return new Promise((resolve) => {
      dupResolveRef.current = resolve;
      setDupName(filename);
    });
  }

  function closeDup(ok: boolean) {
    dupResolveRef.current?.(ok);
    dupResolveRef.current = null;
    setDupName(null);
  }

  async function handleFiles(files: FileList | File[]) {
    const accepted = Array.from(files).filter((f) => /\.(mp4|webm|mov)$/i.test(f.name));
    if (accepted.length === 0) {
      showToast("仅支持 .mp4 / .webm / .mov", false);
      return;
    }
    setError(null);
    for (const file of accepted) {
      const controller = new AbortController();
      const localId = `${file.name}-${file.size}-${Date.now()}`;
      setUploads((cur) => [...cur, { id: localId, name: file.name, controller }]);
      try {
        await uploadVideo(file, false, controller.signal);
        showToast(`「${file.name}」上传成功，开始分析`);
      } catch (err) {
        if (err instanceof UploadAbortedError) {
          showToast(`「${file.name}」已取消上传`);
          continue;
        }
        if (err instanceof DuplicateUploadError) {
          const ok = await confirmOverwrite(err.filename || file.name);
          if (ok) {
            try {
              await uploadVideo(file, true, controller.signal);
              showToast(`「${file.name}」将覆盖原记录并重新分析`);
            } catch (overwriteErr) {
              if (overwriteErr instanceof UploadAbortedError) {
                showToast(`「${file.name}」已取消上传`);
                continue;
              }
              const msg =
                overwriteErr instanceof Error ? overwriteErr.message : String(overwriteErr);
              setError(msg);
              showToast(msg, false);
              break;
            }
          }
          continue;
        }
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        showToast(msg, false);
        break;
      } finally {
        setUploads((cur) => cur.filter((u) => u.id !== localId));
      }
    }
    await refresh();
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files?.length) {
      void handleFiles(e.dataTransfer.files);
    }
  }

  async function onReanalyze(id: string) {
    try {
      await reanalyze(id, "full");
      showToast("已提交重新分析");
      await refresh();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      showToast(msg, false);
    }
  }

  function playVideo(video: Video) {
    openPlayer({
      videoId: video.id,
      filename: video.filename,
      tStartMs: 0,
      fromLibrary: true,
    });
    navigate("/");
    showToast("已开始播放（从 0 秒起播）");
  }

  async function onRemove() {
    if (!delVideo) return;
    const busy = delVideo.status === "queued" || delVideo.status === "processing";
    try {
      await deleteVideo(delVideo.id);
      showToast(busy ? `「${delVideo.filename}」已取消分析` : `「${delVideo.filename}」已移除`);
      notifyVideoDeleted(delVideo.id);
      setDelVideo(null);
      await refresh();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      showToast(msg, false);
    }
  }

  function isBusy(video: Video) {
    return video.status === "queued" || video.status === "processing";
  }

  const readyCount = videos.filter((v) => v.status === "ready").length;

  return (
    <div>
      <div className="card">
        <div className="card-head">
          <div className="card-title">上传录像</div>
        </div>
        <div className="card-body">
          <div
            className={`dropzone${dragging ? " dragover" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
          >
            <IconUpload />
            <div className="dz-title">
              将屏幕录像拖拽到此处，或<b>点击选择文件</b>
            </div>
            <div className="dz-tip">支持 .mp4 / .webm / .mov，单个文件不超过 4GB</div>
            <input
              ref={inputRef}
              type="file"
              accept=".mp4,.webm,.mov"
              multiple
              hidden
              onChange={(e) => {
                if (e.target.files) void handleFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </div>
          {uploads.length > 0 ? (
            <div className="upload-jobs">
              {uploads.map((item) => (
                <div key={item.id} className="upload-job">
                  <span>正在上传 {item.name}</span>
                  <button
                    type="button"
                    className="btn danger-text"
                    onClick={(e) => {
                      e.stopPropagation();
                      item.controller.abort();
                    }}
                  >
                    取消上传
                  </button>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      {error ? (
        <div className="error-banner">
          <IconWarn />
          <span>{error}</span>
        </div>
      ) : null}

      <div className="card">
        <div className="card-head">
          <div className="card-title">录像列表</div>
          <div className="stat">
            共 <b>{videos.length}</b> 条 · 可搜索 <b className="ready">{readyCount}</b> 条
          </div>
        </div>
        <div className="card-body flush">
          {videos.length === 0 ? (
            <div className="empty plain">
              <IconVideo />
              <div className="t1">还没有录像</div>
              <div className="t2">上传屏幕录像后，将自动进行切段与操作识别</div>
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: "42%" }}>文件名</th>
                  <th style={{ width: "12%" }}>时长</th>
                  <th style={{ width: "26%" }}>分析状态</th>
                  <th style={{ width: "20%" }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {videos.map((video) => (
                  <tr key={video.id}>
                    <td>
                      <div className="fname">
                        <IconFile />
                        {video.filename}
                      </div>
                    </td>
                    <td>
                      <span className="duration">{formatClock(video.duration_ms)}</span>
                    </td>
                    <td>
                      <StatusCell video={video} />
                    </td>
                    <td>
                      {isBusy(video) ? (
                        <button
                          type="button"
                          className="btn danger-text"
                          onClick={() => setDelVideo(video)}
                        >
                          取消分析
                        </button>
                      ) : (
                        <>
                          {video.status === "ready" ? (
                            <button
                              type="button"
                              className="btn text"
                              onClick={() => playVideo(video)}
                            >
                              播放
                            </button>
                          ) : null}
                          {video.status === "failed" ? (
                            <button
                              type="button"
                              className="btn danger-text"
                              onClick={() => void onReanalyze(video.id)}
                            >
                              重新分析
                            </button>
                          ) : null}
                          <button
                            type="button"
                            className="btn danger-text"
                            onClick={() => setDelVideo(video)}
                          >
                            移除
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className={`modal-mask${dupName ? " show" : ""}`}>
        <div className="modal" role="dialog" aria-modal="true" aria-labelledby="dup-title">
          <div className="modal-head" id="dup-title">
            <IconWarn />
            提示
          </div>
          <div className="modal-body">
            该录像已上传（<b>{dupName}</b>）。
            <br />
            确定覆盖并重新分析吗？
          </div>
          <div className="modal-foot">
            <button type="button" className="btn" onClick={() => closeDup(false)}>
              取消
            </button>
            <button type="button" className="btn primary" onClick={() => closeDup(true)}>
              确定覆盖并重新分析
            </button>
          </div>
        </div>
      </div>

      <div className={`modal-mask${delVideo ? " show" : ""}`}>
        <div className="modal" role="dialog" aria-modal="true" aria-labelledby="del-title">
          <div className="modal-head danger" id="del-title">
            <IconTrash />
            {delVideo && isBusy(delVideo) ? "取消分析" : "移除录像"}
          </div>
          <div className="modal-body">
            {delVideo && isBusy(delVideo) ? (
              <>
                确定取消「<b>{delVideo.filename}</b>」的分析吗？
                <br />
                已上传的文件和分析进度都会被移除。
              </>
            ) : (
              <>
                确定移除录像 <b>{delVideo?.filename}</b> 吗？
                <br />
                移除后该录像及其分析片段将不可再检索与播放。
              </>
            )}
          </div>
          <div className="modal-foot">
            <button type="button" className="btn" onClick={() => setDelVideo(null)}>
              返回
            </button>
            <button type="button" className="btn danger" onClick={() => void onRemove()}>
              {delVideo && isBusy(delVideo) ? "取消分析" : "移除"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
