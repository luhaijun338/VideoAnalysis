import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Overview } from "../api";
import { DonutChart, ModelBar, TrendChart } from "../components/Charts";
import { RiskBadge, StatusTag, fmtShort } from "../ui";

type Props = { onOpenAlert: (id: string) => void };

export default function OverviewPage({ onOpenAlert }: Props) {
  const nav = useNavigate();
  const [data, setData] = useState<Overview | null>(null);

  useEffect(() => {
    api.overview().then(setData);
  }, []);

  if (!data) return <p className="loading">加载中…</p>;

  const deltaSign = data.today_alerts_delta >= 0 ? "▲" : "▼";
  const deltaCls = data.today_alerts_delta >= 0 ? "up" : "down";

  return (
    <>
      <div className="stat-row">
        <div className="stat-card ic-error" onClick={() => nav("/alerts")}>
          <div className="ico">
            <svg viewBox="0 0 24 24">
              <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" />
            </svg>
          </div>
          <div>
            <div className="num">
              {data.today_alerts}
              <small>条</small>
            </div>
            <div className="lab">今日风险告警</div>
            <div className={`trend ${deltaCls}`}>
              {deltaSign} 较昨日 {data.today_alerts_delta >= 0 ? "+" : ""}
              {data.today_alerts_delta}
            </div>
          </div>
        </div>
        <div className="stat-card ic-error" onClick={() => nav("/alerts")}>
          <div className="ico">
            <svg viewBox="0 0 24 24">
              <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-1 6h2v6h-2V7zm0 8h2v2h-2v-2z" />
            </svg>
          </div>
          <div>
            <div className="num">
              {data.high_risk_accounts}
              <small>个</small>
            </div>
            <div className="lab">高风险账号（≥80分）</div>
            <div className="trend up">▲ 含 {data.high_risk_pending} 个待处置</div>
          </div>
        </div>
        <div className="stat-card ic-warn" onClick={() => nav("/dispose")}>
          <div className="ico">
            <svg viewBox="0 0 24 24">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
            </svg>
          </div>
          <div>
            <div className="num">
              {data.today_disposals}
              <small>次</small>
            </div>
            <div className="lab">今日联动处置</div>
            <div className="trend down">▼ 自动处置 {data.auto_disposals} 次</div>
          </div>
        </div>
        <div className="stat-card ic-ok" onClick={() => nav("/models")}>
          <div className="ico">
            <svg viewBox="0 0 24 24">
              <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" />
            </svg>
          </div>
          <div>
            <div className="num">
              {data.models_running}/{data.models_total}
            </div>
            <div className="lab">分析模型运行中</div>
            <div className="trend down">▼ 近7日误报率 {data.false_positive_rate}</div>
          </div>
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-head">
            <div className="card-title">风险趋势（近 7 日）</div>
            <div className="chart-legend">
              <span>
                <i style={{ background: "var(--primary)" }} />风险告警
              </span>
              <span>
                <i style={{ background: "var(--error)" }} />高风险告警
              </span>
              <span>
                <i style={{ background: "var(--success)" }} />联动处置
              </span>
            </div>
          </div>
          <div className="card-body">
            <TrendChart trend={data.trend} />
          </div>
        </div>
        <div className="card">
          <div className="card-head">
            <div className="card-title">今日告警风险等级分布</div>
          </div>
          <div className="card-body">
            <DonutChart dist={data.level_distribution} />
          </div>
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-head">
            <div className="card-title">分析模型命中分布（近 7 日）</div>
            <span className="link-btn" onClick={() => nav("/models")}>
              模型配置
              <svg viewBox="0 0 24 24">
                <path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z" />
              </svg>
            </span>
          </div>
          <div className="card-body">
            <ModelBar hits={data.model_hits} />
          </div>
        </div>
        <div className="card">
          <div className="card-head">
            <div className="card-title">高风险账号 Top 5</div>
            <span className="link-btn" onClick={() => nav("/alerts")}>
              全部告警
              <svg viewBox="0 0 24 24">
                <path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z" />
              </svg>
            </span>
          </div>
          <div className="card-body no-pad">
            <table>
              <thead>
                <tr>
                  <th>账号</th>
                  <th>风险分</th>
                  <th>触发模型</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {data.top_accounts.map((r) => (
                  <tr key={r.account}>
                    <td>
                      <span className="mono account-name">{r.account}</span>
                    </td>
                    <td>
                      <RiskBadge risk={r.risk} />
                    </td>
                    <td>{r.model_label}</td>
                    <td>
                      <StatusTag status={r.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <div className="card-title">最新风险告警</div>
          <span className="link-btn" onClick={() => nav("/alerts")}>
            查看全部
            <svg viewBox="0 0 24 24">
              <path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z" />
            </svg>
          </span>
        </div>
        <div className="card-body no-pad">
          <table>
            <thead>
              <tr>
                <th style={{ width: "30%" }}>告警名称</th>
                <th>分析模型</th>
                <th>涉事账号</th>
                <th>风险分</th>
                <th>发现时间</th>
                <th>状态</th>
                <th style={{ width: 110 }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {data.latest_alerts.map((a) => (
                <tr key={a.id} className="clickable" onClick={() => onOpenAlert(a.id)}>
                  <td>
                    <span className="t-ellipsis alert-name" title={a.name}>
                      {a.name}
                    </span>
                  </td>
                  <td>模型{a.model_id}</td>
                  <td>
                    <span className="mono">{a.account}</span>
                  </td>
                  <td>
                    <RiskBadge risk={a.risk} />
                  </td>
                  <td>
                    <span className="mono time-sm">{fmtShort(a.discovered_at)}</span>
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
        </div>
      </div>
    </>
  );
}
