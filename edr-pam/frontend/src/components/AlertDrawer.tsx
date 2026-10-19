import { useEffect, useState } from "react";
import { api, type AlertDetail } from "../api";
import { StatusTag, useToast } from "../ui";

type Props = {
  alertId: string | null;
  onClose: () => void;
  onUpdated: () => void;
};

const LV: Record<string, { cls: string; txt: string }> = {
  high: { cls: "high", txt: "高风险" },
  mid: { cls: "mid", txt: "中风险" },
  low: { cls: "low", txt: "低风险" },
};

function badgeEl(badge?: string | null) {
  if (badge === "match") return <span className="match">✓ 正常会话</span>;
  if (badge === "mismatch") return <span className="mismatch">✗ 未走 PAM</span>;
  return null;
}

export default function AlertDrawer({ alertId, onClose, onUpdated }: Props) {
  const toast = useToast();
  const [detail, setDetail] = useState<AlertDetail | null>(null);

  useEffect(() => {
    if (!alertId) {
      setDetail(null);
      return;
    }
    api.alert(alertId).then(setDetail).catch((e) => toast(String(e), false));
  }, [alertId, toast]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!alertId) return null;

  const dispose = async (action: string) => {
    if (!alertId) return;
    try {
      const d = await api.dispose(alertId, action);
      setDetail(d);
      onUpdated();
      toast(`已触发联动「${action}」，处置任务执行中`);
    } catch (e) {
      toast(String(e), false);
    }
  };

  const disabled = detail ? !["pending", "processing"].includes(detail.status) : true;
  const lv = detail ? LV[detail.level] : LV.high;

  return (
    <>
      <div className={`drawer-mask${alertId ? " show" : ""}`} onClick={onClose} />
      <aside className={`drawer${alertId ? " show" : ""}`}>
        <div className="dw-head">
          {detail && <span className={`tag ${lv.cls}`}>{lv.txt}</span>}
          <span className="t">{detail?.name ?? "告警详情"}</span>
          <button className="close" onClick={onClose}>
            ✕
          </button>
        </div>
        <div className="dw-body">
          {!detail ? (
            <p>加载中…</p>
          ) : (
            <>
              <h4>告警信息</h4>
              <div className="info-grid">
                <div className="info-cell">
                  <div className="k">告警编号</div>
                  <div className="v">{detail.id}</div>
                </div>
                <div className="info-cell">
                  <div className="k">分析模型</div>
                  <div className="v">
                    模型{detail.model_id} · {detail.model_name}
                  </div>
                </div>
                <div className="info-cell">
                  <div className="k">涉事账号</div>
                  <div className="v">{detail.account}</div>
                </div>
                <div className="info-cell">
                  <div className="k">目标资产</div>
                  <div className="v">{detail.asset}</div>
                </div>
                <div className="info-cell">
                  <div className="k">来源 IP</div>
                  <div className="v">{detail.src_ip}</div>
                </div>
                <div className="info-cell">
                  <div className="k">发现时间</div>
                  <div className="v">{detail.discovered_at.replace("T", " ").slice(0, 19)}</div>
                </div>
                <div className="info-cell">
                  <div className="k">风险分</div>
                  <div
                    className="v"
                    style={{
                      color: detail.risk >= 80 ? "#f56c6c" : detail.risk >= 60 ? "#e6a23c" : "#67c23a",
                      fontWeight: 600,
                    }}
                  >
                    {detail.risk} / 100
                  </div>
                </div>
                <div className="info-cell">
                  <div className="k">处理状态</div>
                  <div className="v">
                    <StatusTag status={detail.status} />
                  </div>
                </div>
              </div>
              <div className="dispose-row">
                <button className="btn danger" disabled={disabled} onClick={() => dispose("账号即时冻结")}>
                  冻结账号
                </button>
                <button className="btn warning" disabled={disabled} onClick={() => dispose("密码自动轮换")}>
                  轮换密码
                </button>
                <button className="btn" disabled={disabled} onClick={() => dispose("增强认证")}>
                  增强认证
                </button>
                <button className="btn" disabled={disabled} onClick={() => dispose("标记忽略")}>
                  标记忽略
                </button>
              </div>
              <h4>攻击链时间线（安全事件还原）</h4>
              <div className="timeline">
                {detail.timeline.map((t, i) => (
                  <div className={`tl-node ${t.src}`} key={i}>
                    <span className="dot">
                      <svg viewBox="0 0 24 24">
                        <path d="M12 2a5 5 0 0 0-5 5v3H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-1V7a5 5 0 0 0-5-5zm3 8H9V7a3 3 0 1 1 6 0v3z" />
                      </svg>
                    </span>
                    <div className="time">{t.time}</div>
                    <div className="ttl">
                      {t.title} {badgeEl(t.badge)}
                    </div>
                    <div className="desc" dangerouslySetInnerHTML={{ __html: t.description }} />
                  </div>
                ))}
              </div>
              <h4>研判证据字段</h4>
              <table className="ev-table">
                <thead>
                  <tr>
                    <th style={{ width: 70 }}>来源</th>
                    <th style={{ width: "40%" }}>字段</th>
                    <th>值</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.evidence.map((e, i) => (
                    <tr key={i}>
                      <td>
                        <span className={`tag ${e.src === "sys" ? "edr" : "pam"}`}>
                          {e.src === "sys" ? "系统事件" : "PAM"}
                        </span>
                      </td>
                      <td>
                        <span className="f">{e.field_name}</span>
                      </td>
                      <td>{e.value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <h4>处置记录</h4>
              <div className="disp-log">
                {detail.logs.map((l, i) => (
                  <div className="dl2-item" key={i}>
                    <span className="tm">{l.time}</span>
                    <span className="who">{l.operator}</span>
                    <span className="op" dangerouslySetInnerHTML={{ __html: l.operation }} />
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </aside>
    </>
  );
}
