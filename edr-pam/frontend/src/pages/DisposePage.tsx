import { useEffect, useState } from "react";
import { api, type Disposal, type Linkage } from "../api";
import { ResultTag, Switch, useToast } from "../ui";

const ICONS: Record<string, string> = {
  blue: "M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zM9 8V6c0-1.66 1.34-3 3-3s3 1.34 3 3v2H9z",
  orange:
    "M7.5 8.5a4.5 4.5 0 0 1 9 0V10h1a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-11a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h1V8.5zM12 3.5A2.5 2.5 0 0 0 9.5 6V10h5V6A2.5 2.5 0 0 0 12 3.5zm0 9a1.8 1.8 0 0 0-1 3.3v1.2h2v-1.2a1.8 1.8 0 0 0-1-3.3z",
  purple:
    "M12 2a5 5 0 0 0-5 5v3H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-1V7a5 5 0 0 0-5-5zm3 8H9V7a3 3 0 1 1 6 0v3z",
  green: "M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z",
};

const SEV_TAG: Record<string, string> = {
  high: "tag high",
  mid: "tag mid",
  info: "tag",
};

const SEV_LABEL: Record<string, string> = {
  high: "高风险",
  mid: "高价值",
  info: "持续运行",
};

export default function DisposePage() {
  const toast = useToast();
  const [linkages, setLinkages] = useState<Linkage[]>([]);
  const [disposals, setDisposals] = useState<Disposal[]>([]);

  useEffect(() => {
    api.linkages().then(setLinkages);
    api.disposals().then(setDisposals);
  }, []);

  const toggle = async (id: number, enabled: boolean, slug: string) => {
    const r = await api.toggleLinkage(id, enabled);
    setLinkages((prev) => prev.map((l) => (l.id === id ? r : l)));
    toast(enabled ? `「${slug}」已启用` : `「${slug}」已停用`, enabled);
  };

  return (
    <>
      <div className="card">
        <div className="card-head">
          <div className="card-title">PAM 联动处置能力</div>
          <div className="stat">自动联动开关 · 全部启用</div>
        </div>
        <div className="card-body">
          <div className="link-grid">
            {linkages.map((l) => (
              <div className="link-card" key={l.id}>
                <div className={`link-ico lc-${l.icon_color}`}>
                  <svg viewBox="0 0 24 24">
                    <path d={ICONS[l.icon_color] ?? ICONS.blue} />
                  </svg>
                </div>
                <div style={{ flex: 1 }}>
                  <div className="t">
                    {l.name} <span className={SEV_TAG[l.severity] ?? "tag mid"}>{SEV_LABEL[l.severity] ?? l.severity}</span>
                  </div>
                  <div className="sub">{l.subtitle}</div>
                  <div className="triggers">
                    {l.triggers.map((t) => (
                      <span className="tag edr" key={t}>
                        {t}
                      </span>
                    ))}
                  </div>
                  {l.actions.map((a) => (
                    <div className="act-row arrow" key={a}>
                      <svg viewBox="0 0 24 24">
                        <path d="M8 5v14l11-7z" />
                      </svg>
                      {a}
                    </div>
                  ))}
                  <div className="cond">
                    恢复条件：<b>{l.recovery_condition}</b>
                  </div>
                </div>
                <div className="card-right">
                  <Switch
                    on={l.enabled}
                    onToggle={() => toggle(l.id, !l.enabled, l.slug)}
                    title="启用/停用"
                  />
                  <span className="last-trigger">
                    最近触发
                    <br />
                    {l.last_trigger_label}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-head">
            <div className="card-title">风险评分权重配置</div>
          </div>
          <div className="card-body">
            <div className="weight-bar">
              <div style={{ flex: 40, background: "#409eff" }} title="终端行为异常分 40%">
                40% 行为
              </div>
              <div style={{ flex: 30, background: "#7b3fe4" }} title="PAM 权限异常分 30%">
                30% 权限
              </div>
              <div style={{ flex: 20, background: "#e6a23c" }} title="外部威胁情报 20%">
                20% 情报
              </div>
              <div style={{ flex: 10, background: "#67c23a" }} title="历史违规记录 10%">
                10% 违规
              </div>
            </div>
            <div className="weight-legend">
              <span>
                <i style={{ background: "#409eff" }} />
                终端行为异常分
              </span>
              <span>
                <i style={{ background: "#7b3fe4" }} />
                PAM 权限异常分
              </span>
              <span>
                <i style={{ background: "#e6a23c" }} />
                外部威胁情报
              </span>
              <span>
                <i style={{ background: "#67c23a" }} />
                历史违规记录
              </span>
            </div>
          </div>
        </div>
        <div className="card">
          <div className="card-head">
            <div className="card-title">自适应监控增强</div>
          </div>
          <div className="card-body" style={{ paddingTop: 8 }}>
            <div className="chain-item boxed">
              <span className="src pam">PAM 触发</span>
              <div className="ct">
                <div className="tt">检测到非授权凭据签发</div>
                <div className="ds">→ 开启 lsass.exe / 凭据管理器进程密集监控</div>
              </div>
            </div>
            <div className="chain-item boxed">
              <span className="src pam">PAM 触发</span>
              <div className="ct">
                <div className="tt">检测到跨资产高频操作</div>
                <div className="ds">→ 对该账号终端开启进程注入 / 远程线程专项检测</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <div className="card-title">联动处置记录</div>
        </div>
        <div className="card-body no-pad">
          <table>
            <thead>
              <tr>
                <th>处置时间</th>
                <th>触发告警</th>
                <th>处置动作</th>
                <th>执行对象</th>
                <th>执行人 / 方式</th>
                <th>结果</th>
              </tr>
            </thead>
            <tbody>
              {disposals.map((d) => (
                <tr key={d.id}>
                  <td>
                    <span className="mono time-sm">{d.disposed_at.replace("T", " ").slice(0, 16)}</span>
                  </td>
                  <td>
                    <span className="mono time-sm alert-id">{d.alert_id}</span>
                  </td>
                  <td className="action-cell">{d.action}</td>
                  <td>
                    <span className="mono time-sm">{d.target}</span>
                  </td>
                  <td>{d.operator}</td>
                  <td>
                    <ResultTag result={d.result} />
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
