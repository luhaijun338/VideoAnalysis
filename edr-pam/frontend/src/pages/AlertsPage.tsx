import { useCallback, useEffect, useState } from "react";
import { api, type Alert } from "../api";
import { RiskBadge, StatusTag } from "../ui";

type Props = { onOpenAlert: (id: string) => void };

export default function AlertsPage({ onOpenAlert }: Props) {
  const [items, setItems] = useState<Alert[]>([]);
  const [total, setTotal] = useState(0);
  const [pending, setPending] = useState(0);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [model, setModel] = useState("");
  const [level, setLevel] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");

  const load = useCallback(() => {
    const params: Record<string, string> = {};
    if (from) params.date_from = from;
    if (to) params.date_to = to;
    if (model) params.model_id = model;
    if (level) params.level = level;
    if (status) params.status = status;
    if (q.trim()) params.q = q.trim();
    api.alerts(params).then((r) => {
      setItems(r.items);
      setTotal(r.total);
      setPending(r.pending);
    });
  }, [from, to, model, level, status, q]);

  useEffect(() => {
    load();
  }, [load]);

  const reset = () => {
    setFrom("");
    setTo("");
    setModel("");
    setLevel("");
    setStatus("");
    setQ("");
  };

  return (
    <div className="card">
      <div className="card-head">
        <div className="card-title">PAM 安全风险告警研判</div>
        <div className="stat">
          共 <b>{total}</b> 条 · 未处置 <b style={{ color: "var(--error)" }}>{pending}</b> 条
        </div>
      </div>
      <div className="filter-bar">
        <span className="f-label">发现时间</span>
        <input type="date" className="f-input" value={from} onChange={(e) => setFrom(e.target.value)} />
        <span className="f-sep">至</span>
        <input type="date" className="f-input" value={to} onChange={(e) => setTo(e.target.value)} />
        <span className="f-label">分析模型</span>
        <select className="f-select" value={model} onChange={(e) => setModel(e.target.value)}>
          <option value="">全部模型</option>
          <option value="1">模型1 · 绕过PAM登录</option>
          <option value="2">模型2 · 凭据窃取</option>
          <option value="3">模型3 · 横向移动</option>
          <option value="4">模型4 · 基线偏离</option>
        </select>
        <span className="f-label">风险等级</span>
        <select className="f-select" value={level} onChange={(e) => setLevel(e.target.value)}>
          <option value="">全部</option>
          <option value="high">高风险</option>
          <option value="mid">中风险</option>
          <option value="low">低风险</option>
        </select>
        <span className="f-label">状态</span>
        <select className="f-select" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">全部</option>
          <option value="pending">待处置</option>
          <option value="processing">处置中</option>
          <option value="done">已处置</option>
          <option value="ignored">已忽略</option>
        </select>
        <div className="f-search">
          <input
            type="text"
            className="f-input"
            placeholder="搜索账号 / 资产 / IP"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <button className="btn primary sm" onClick={load}>
            查询
          </button>
          <button className="btn sm" onClick={reset}>
            重置
          </button>
        </div>
      </div>
      <div className="card-body no-pad">
        {items.length === 0 ? (
          <div className="empty inline-empty">
            <svg viewBox="0 0 24 24">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
            </svg>
            <div className="t1">暂无符合条件的风险告警</div>
            <div className="t2">调整筛选条件后重试</div>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th style={{ width: "28%" }}>告警名称</th>
                <th>分析模型</th>
                <th>涉事账号</th>
                <th>目标资产</th>
                <th>来源IP</th>
                <th>风险分</th>
                <th>发现时间</th>
                <th>状态</th>
                <th style={{ width: 90 }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((a) => (
                <tr key={a.id} className="clickable" onClick={() => onOpenAlert(a.id)}>
                  <td>
                    <span className="t-ellipsis alert-name" title={a.name}>
                      {a.name}
                    </span>
                  </td>
                  <td>
                    <span className="tag edr">模型{a.model_id}</span>
                  </td>
                  <td>
                    <span className="mono">{a.account}</span>
                  </td>
                  <td>
                    <span className="mono time-sm">{a.asset}</span>
                  </td>
                  <td>
                    <span className="mono time-sm">{a.src_ip}</span>
                  </td>
                  <td>
                    <RiskBadge risk={a.risk} />
                  </td>
                  <td>
                    <span className="mono time-sm">{a.discovered_at.replace("T", " ").slice(0, 19)}</span>
                  </td>
                  <td>
                    <StatusTag status={a.status} />
                  </td>
                  <td>
                    <button
                      className="btn mini-plain"
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpenAlert(a.id);
                      }}
                    >
                      详情
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
