import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
  type ReactNode,
} from "react";
import { formatClock } from "./operationLog";
import { seekSeconds } from "./seek";
import {
  IconFullscreen,
  IconFullscreenExit,
  IconPause,
  IconPlay,
  showToast,
} from "./ui";
import {
  bindSeekOnMetadata,
  clearVideoElement,
  type SeekBinding,
} from "./videoPlayback";

export type OpenPlayerArgs = {
  videoId: string;
  filename: string;
  tStartMs: number;
  fromLibrary?: boolean;
  hitKey?: string | null;
};

type PlayerContextValue = {
  openPlayer: (args: OpenPlayerArgs) => void;
  closePlayer: () => void;
  notifyVideoDeleted: (id: string) => void;
  playingKey: string | null;
  currentVideoId: string | null;
  visible: boolean;
};

const PlayerContext = createContext<PlayerContextValue | null>(null);

const deleteListeners = new Set<(id: string) => void>();

export function onVideoDeleted(listener: (id: string) => void): () => void {
  deleteListeners.add(listener);
  return () => {
    deleteListeners.delete(listener);
  };
}

type FsDoc = Document & {
  webkitFullscreenElement?: Element | null;
  webkitExitFullscreen?: () => Promise<void>;
};

type FsEl = HTMLElement & {
  webkitRequestFullscreen?: () => Promise<void>;
};

function fullscreenElement(): Element | null {
  const doc = document as FsDoc;
  return document.fullscreenElement ?? doc.webkitFullscreenElement ?? null;
}

function requestFs(el: HTMLElement): void {
  const node = el as FsEl;
  const req = el.requestFullscreen ?? node.webkitRequestFullscreen;
  void req?.call(el);
}

function exitFs(): void {
  if (!fullscreenElement()) return;
  const doc = document as FsDoc;
  const exit = document.exitFullscreen ?? doc.webkitExitFullscreen;
  void exit?.call(document);
}

export function PlayerProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<OpenPlayerArgs | null>(null);
  const [visible, setVisible] = useState(false);
  const [clock, setClock] = useState({ t: 0, d: 0, paused: true });
  const [isFullscreen, setIsFullscreen] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const currentVideoIdRef = useRef<string | null>(null);
  const playGenRef = useRef(0);
  const seekBindingRef = useRef<SeekBinding | null>(null);

  const resetMedia = useCallback(() => {
    seekBindingRef.current?.cancel();
    seekBindingRef.current = null;
    playGenRef.current += 1;
    const videoEl = videoRef.current;
    if (videoEl) clearVideoElement(videoEl);
    currentVideoIdRef.current = null;
    setClock({ t: 0, d: 0, paused: true });
  }, []);

  const closePlayer = useCallback(() => {
    exitFs();
    resetMedia();
    setVisible(false);
    setSession(null);
  }, [resetMedia]);

  const openPlayer = useCallback((args: OpenPlayerArgs) => {
    setSession({ ...args, hitKey: args.fromLibrary ? null : (args.hitKey ?? null) });
    setVisible(true);
  }, []);

  const notifyVideoDeleted = useCallback(
    (id: string) => {
      if (currentVideoIdRef.current === id) closePlayer();
      deleteListeners.forEach((fn) => fn(id));
    },
    [closePlayer],
  );

  const playSession = useCallback(
    (args: OpenPlayerArgs) => {
      const videoEl = videoRef.current;
      if (!videoEl) return;
      const switching = currentVideoIdRef.current !== args.videoId;
      const generation = ++playGenRef.current;
      seekBindingRef.current?.cancel();
      seekBindingRef.current = null;
      if (switching) {
        currentVideoIdRef.current = args.videoId;
        videoEl.src = `/api/videos/${args.videoId}/file`;
      }
      const timeSeconds = args.fromLibrary ? 0 : seekSeconds(args.tStartMs);
      seekBindingRef.current = bindSeekOnMetadata(videoEl, {
        generation,
        isCurrent: (g) => g === playGenRef.current,
        timeSeconds,
        waitForMetadata: switching,
        play: (el) => {
          void el.play().catch(() => {
            showToast("无法播放该录像（文件可能缺失）", false);
          });
        },
      });
    },
    [],
  );

  useEffect(() => {
    if (!visible || !session) return;
    playSession(session);
  }, [visible, session, playSession]);

  useEffect(() => {
    const el = videoRef.current;
    if (!el) return;
    const sync = () => {
      setClock({
        t: el.currentTime,
        d: Number.isFinite(el.duration) ? el.duration : 0,
        paused: el.paused,
      });
    };
    el.addEventListener("timeupdate", sync);
    el.addEventListener("play", sync);
    el.addEventListener("pause", sync);
    el.addEventListener("loadedmetadata", sync);
    el.addEventListener("seeked", sync);
    el.addEventListener("durationchange", sync);
    return () => {
      el.removeEventListener("timeupdate", sync);
      el.removeEventListener("play", sync);
      el.removeEventListener("pause", sync);
      el.removeEventListener("loadedmetadata", sync);
      el.removeEventListener("seeked", sync);
      el.removeEventListener("durationchange", sync);
    };
  }, [visible]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || !visible) return;
      if (fullscreenElement()) exitFs();
      else closePlayer();
    };
    const onFs = () => setIsFullscreen(Boolean(fullscreenElement()));
    document.addEventListener("keydown", onKey);
    document.addEventListener("fullscreenchange", onFs);
    document.addEventListener("webkitfullscreenchange" as "fullscreenchange", onFs);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("fullscreenchange", onFs);
      document.removeEventListener("webkitfullscreenchange" as "fullscreenchange", onFs);
    };
  }, [visible, closePlayer]);

  function togglePlay() {
    const el = videoRef.current;
    if (!el || !session) return;
    if (el.paused) void el.play().catch(() => undefined);
    else el.pause();
  }

  function onBarClick(e: MouseEvent<HTMLDivElement>) {
    const el = videoRef.current;
    if (!el || !el.duration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const pct = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    el.currentTime = pct * el.duration;
  }

  function toggleFullscreen() {
    if (fullscreenElement()) exitFs();
    else if (cardRef.current) requestFs(cardRef.current);
  }

  const pct = clock.d > 0 ? Math.min(100, (clock.t / clock.d) * 100) : 0;
  const posLabel = session?.fromLibrary
    ? "从头播放"
    : session
      ? `已定位 [${formatClock(session.tStartMs)}]`
      : "";

  const value = useMemo<PlayerContextValue>(
    () => ({
      openPlayer,
      closePlayer,
      notifyVideoDeleted,
      playingKey: session?.hitKey ?? null,
      currentVideoId: visible ? session?.videoId ?? null : null,
      visible,
    }),
    [openPlayer, closePlayer, notifyVideoDeleted, session, visible],
  );

  return (
    <PlayerContext.Provider value={value}>
      {children}
      <div
        className={`player-mask${visible ? " show" : ""}`}
        onClick={(e) => {
          if (e.target === e.currentTarget) closePlayer();
        }}
      >
        <div className="player-modal">
          <div className="pm-head">
            <span className="f">{session?.filename ?? ""}</span>
            {session ? <span className="pos">{posLabel}</span> : null}
            <button type="button" className="pm-close" title="关闭" onClick={closePlayer}>
              ✕
            </button>
          </div>
          <div className="card player-card" ref={cardRef}>
            <div className="player-screen">
              <video ref={videoRef} className="player-video" playsInline />
              {visible ? (
                <div className="rec-badge">
                  <span className="rd" />
                  <span>REC {formatClock(clock.t * 1000)}</span>
                </div>
              ) : null}
            </div>
            <div className="player-controls">
              <button type="button" className="pc-btn" title="播放/暂停" onClick={togglePlay}>
                {clock.paused ? <IconPlay /> : <IconPause />}
              </button>
              <div className="pc-time">
                <span className="cur">{formatClock(clock.t * 1000)}</span> /{" "}
                {formatClock(clock.d * 1000)}
              </div>
              <div className="pc-bar" onClick={onBarClick}>
                <i style={{ width: `${pct}%` }} />
                <span className="knob" style={{ left: `${pct}%` }} />
              </div>
              <button
                type="button"
                className="pc-btn ghost"
                title="全屏"
                onClick={toggleFullscreen}
              >
                {isFullscreen ? <IconFullscreenExit /> : <IconFullscreen />}
              </button>
            </div>
          </div>
        </div>
      </div>
    </PlayerContext.Provider>
  );
}

export function usePlayer(): PlayerContextValue {
  const ctx = useContext(PlayerContext);
  if (!ctx) throw new Error("usePlayer must be used within PlayerProvider");
  return ctx;
}
