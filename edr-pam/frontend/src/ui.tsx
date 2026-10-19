import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type ToastState = { msg: string; ok: boolean } | null;

const ToastCtx = createContext<(msg: string, ok?: boolean) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastState>(null);

  const show = useCallback((msg: string, ok = true) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 2600);
  }, []);

  return (
    <ToastCtx.Provider value={show}>
      {children}
      {toast && (
        <div className={`toast show ${toast.ok ? "ok" : "err"}`}>
          <svg className="ti" viewBox="0 0 24 24">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" />
          </svg>
          <span>{toast.msg}</span>
        </div>
      )}
    </ToastCtx.Provider>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}

const LV: Record<string, { cls: string; txt: string }> = {
  high: { cls: "high", txt: "高风险" },
  mid: { cls: "mid", txt: "中风险" },
  low: { cls: "low", txt: "低风险" },
};

export function LevelTag({ level }: { level: string }) {
  const lv = LV[level] ?? LV.mid;
  return <span className={`tag ${lv.cls}`}>{lv.txt}</span>;
}

export function RiskBadge({ risk }: { risk: number }) {
  const c = risk >= 80 ? "#f56c6c" : risk >= 60 ? "#e6a23c" : "#67c23a";
  return (
    <span className="risk" style={{ color: c }}>
      <svg viewBox="0 0 24 24">
        <path d="M12 2L1 21h22L12 2zm1 14h-2v-2h2v2zm0-4h-2v-4h2v4z" />
      </svg>
      {risk}
    </span>
  );
}

export function StatusTag({ status }: { status: string }) {
  const map: Record<string, string> = {
    pending: "tag pending",
    processing: "tag processing",
    done: "tag done",
    ignored: "tag ignored",
  };
  const labels: Record<string, string> = {
    pending: "待处置",
    processing: "处置中",
    done: "已处置",
    ignored: "已忽略",
  };
  return <span className={map[status] ?? "tag"}>{labels[status] ?? status}</span>;
}

export function ResultTag({ result }: { result: string }) {
  const map: Record<string, string> = {
    done: "tag done",
    processing: "tag processing",
  };
  const labels: Record<string, string> = {
    done: "成功",
    processing: "进行中",
  };
  return <span className={map[result] ?? "tag done"}>{labels[result] ?? result}</span>;
}

export function Switch({
  on,
  onToggle,
  title,
}: {
  on: boolean;
  onToggle: () => void;
  title?: string;
}) {
  return (
    <div
      className={`switch${on ? " on" : ""}`}
      onClick={onToggle}
      title={title ?? "启用/停用"}
      role="switch"
      aria-checked={on}
    />
  );
}

export function fmtTime(iso: string) {
  return iso.replace("T", " ").slice(0, 19);
}

export function fmtShort(iso: string) {
  return iso.slice(5, 16).replace("T", " ");
}
