import { useEffect, useState } from "react";
import { api, type Model } from "../api";
import { Switch, useToast } from "../ui";

const COLORS = ["#409eff", "#e6a23c", "#7b3fe4", "#67c23a"];

export default function ModelsPage() {
  const toast = useToast();
  const [models, setModels] = useState<Model[]>([]);

  useEffect(() => {
    api.models().then(setModels);
  }, []);

  return (
    <div className="model-grid">
      {models.map((m, i) => (
        <div className="model-card" key={m.id}>
          <div className="mc-head">
            <div className="mc-num" style={{ background: `${COLORS[i]}22`, color: COLORS[i] }}>
              {m.id}
            </div>
            <div>
              <div className="t">
                模型{m.id} · {m.name}
              </div>
              <div className="d">{m.description}</div>
            </div>
            <div className="right">
              <Switch
                on={m.enabled}
                onToggle={async () => {
                  const r = await api.toggleModel(m.id, !m.enabled);
                  setModels((prev) => prev.map((x) => (x.id === m.id ? r : x)));
                  toast(r.enabled ? `「模型${m.id}」已启用` : `「模型${m.id}」已停用`, r.enabled);
                }}
              />
            </div>
          </div>
          <div className="mc-body open">
            <div className="mc-stat">
              <div className="ms-item">
                <div className="n primary">{m.hit7}</div>
                <div className="t">近7日命中</div>
              </div>
              <div className="ms-item">
                <div className="n error">{m.fp_rate}</div>
                <div className="t">误报率</div>
              </div>
              <div className="ms-item">
                <div className="n success">{m.disposed_rate}</div>
                <div className="t">处置率</div>
              </div>
              <div className="ms-item">
                <div className="n warning">{100 - parseInt(m.fp_rate)}%</div>
                <div className="t">有效检出</div>
              </div>
            </div>
            <div className="mc-sec-title">检测逻辑</div>
            {m.steps.map((s, j) => (
              <div className="mc-step" key={j}>
                <span className="idx">{j + 1}</span>
                <span>{s}</span>
              </div>
            ))}
            <div className="mc-sec-title">覆盖场景</div>
            <div className="mc-step">
              <span className="idx pam-flag">⚑</span>
              <span>{m.scene}</span>
            </div>
            <div className="mc-sec-title">关键字段（数据来源）</div>
            <div className="field-cloud">
              {m.edr_fields.map((f) => (
                <span className="tag edr" key={f}>
                  {f}
                </span>
              ))}
              {m.pam_fields.map((f) => (
                <span className="tag pam" key={f}>
                  {f}
                </span>
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
