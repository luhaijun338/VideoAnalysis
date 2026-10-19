import { useState } from "react";
import { api, type ChainItem, type Report } from "../api";
import { useToast } from "../ui";

function ChainList({ chain }: { chain: ChainItem[] }) {
  if (chain.length === 0) {
    return (
      <div className="empty inline-empty">
        <svg viewBox="0 0 24 24">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
        </svg>
        <div className="t1">暂无证据链数据</div>
        <div className="t2">请先生成审计报告</div>
      </div>
    );
  }

  return (
    <div className="chain-list">
      {chain.map((c, i) => (
        <div key={`${c.time}-${c.title}-${i}`}>
          {i > 0 && (
            <div className="chain-join">
              <svg viewBox="0 0 24 24">
                <path d="M16 1H8a3 3 0 0 0-3 3v.5h2V4a1 1 0 0 1 1-1h8a1 1 0 0 1 1 1v.5h2V4a3 3 0 0 0-3-3z" />
              </svg>
              按时间顺序拼接 → 形成完整调用链
            </div>
          )}
          <div className="chain-item">
            <span className={`src ${c.src}`}>{c.src === "edr" ? "系统事件" : "PAM"}</span>
            <div className="ct">
              <div className="tt">{c.title}</div>
              <div className="ds">{c.description}</div>
            </div>
            <span className="tm">{c.time}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function EvidencePage() {
  const toast = useToast();
  const [from, setFrom] = useState("2026-08-27");
  const [to, setTo] = useState("2026-08-27");
  const [account, setAccount] = useState("zhang_wj");
  const [asset, setAsset] = useState("BSS-DB-01");
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);

  const filters = () => ({
    date_from: from || undefined,
    date_to: to || undefined,
    account,
    asset,
  });

  const genReport = async () => {
    if (!account.trim() && !asset.trim()) {
      toast("请至少填写涉事账号或目标资产", false);
      return;
    }
    setLoading(true);
    try {
      const r = await api.report(filters());
      setReport(r);
      toast(`报告已生成：${r.report_id}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "生成报告失败", false);
    } finally {
      setLoading(false);
    }
  };

  const exportPdf = async () => {
    setExporting(true);
    try {
      const { blob, filename } = await api.reportPdf(filters());
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      toast(`已导出 ${filename}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "导出 PDF 失败", false);
    } finally {
      setExporting(false);
    }
  };

  const chain = report?.timeline ?? [];

  return (
    <>
      <div className="card">
        <div className="card-head">
          <div className="card-title">合规审计报告生成</div>
        </div>
        <div className="card-body">
          <div className="filter-bar ev-filter">
            <span className="f-label">时间范围</span>
            <input type="date" className="f-input" value={from} onChange={(e) => setFrom(e.target.value)} />
            <span className="f-sep">至</span>
            <input type="date" className="f-input" value={to} onChange={(e) => setTo(e.target.value)} />
            <span className="f-label">涉事账号</span>
            <input type="text" className="f-input w120" value={account} onChange={(e) => setAccount(e.target.value)} />
            <span className="f-label">目标资产</span>
            <input type="text" className="f-input w120" value={asset} onChange={(e) => setAsset(e.target.value)} />
            <button className="btn primary sm" onClick={genReport} disabled={loading}>
              {loading ? "生成中…" : "生成报告"}
            </button>
            <button className="btn sm" onClick={exportPdf} disabled={exporting}>
              {exporting ? "导出中…" : "导出 PDF"}
            </button>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <div className="card-title">证据链演示（多源数据融合）</div>
          <div className="stat">谁 + 何时 + 做了什么 = 完整证据链</div>
        </div>
        <div className="card-body">
          <ChainList chain={chain} />
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <div className="card-title">标准化审计报告</div>
          {report && (
            <div className="stat">
              命中 <b>{report.matched_alert_count}</b> 条告警 · 关联 <b>{report.alert_id}</b>
            </div>
          )}
        </div>
        <div className="card-body">
          {!report ? (
            <div className="empty inline-empty">
              <svg viewBox="0 0 24 24">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 7V3.5L18.5 9H13z" />
              </svg>
              <div className="t1">尚未生成审计报告</div>
              <div className="t2">填写筛选条件后点击「生成报告」</div>
            </div>
          ) : (
            <div className="report-shell">
              <div className="report-head">
                <div className="ico">
                  <svg viewBox="0 0 24 24">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 7V3.5L18.5 9H13z" />
                  </svg>
                </div>
                <div>
                  <div className="t">特权访问行为审计报告</div>
                  <div className="s">
                    Report ID: {report.report_id} · 生成时间 {report.generated_at}
                  </div>
                </div>
              </div>
              <div className="report-body">
                <div className="rp-sec">
                  <h4>一、事件概述</h4>
                  <div className="txt">{report.summary}</div>
                </div>
                <div className="rp-sec">
                  <h4>二、攻击链时间线</h4>
                  <div className="timeline">
                    {report.timeline.map((c, i) => (
                      <div className={`tl-node ${c.src}`} key={i}>
                        <span className="dot">
                          <svg viewBox="0 0 24 24">
                            <path d="M12 2a5 5 0 0 0-5 5v3H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-1V7a5 5 0 0 0-5-5zm3 8H9V7a3 3 0 1 1 6 0v3z" />
                          </svg>
                        </span>
                        <div className="time">{c.time}</div>
                        <div className="ttl">{c.title}</div>
                        <div className="desc">{c.description}</div>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="rp-sec">
                  <h4>三、影响范围</h4>
                  <div className="txt">{report.impact}</div>
                </div>
                <div className="rp-sec">
                  <h4>四、处置建议</h4>
                  <div className="txt report-rec">{report.recommendations}</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
