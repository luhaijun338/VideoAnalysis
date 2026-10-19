import type { Overview } from "../api";

const COLORS = ["#409eff", "#f56c6c", "#67c23a"];

export function TrendChart({ trend }: { trend: Overview["trend"] }) {
  const w = 640;
  const h = 190;
  const padL = 34;
  const padB = 24;
  const padT = 12;
  const padR = 8;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;
  const max = 20;
  const x = (i: number) => padL + innerW * (i / (trend.length - 1));
  const y = (v: number) => padT + innerH * (1 - v / max);

  const series: [number[], number[], number[]] = [
    trend.map((d) => d.alert_count),
    trend.map((d) => d.high_count),
    trend.map((d) => d.dispose_count),
  ];

  const line = (arr: number[]) =>
    arr.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");

  const area = (arr: number[], color: string) => {
    const pts = arr.map((v, i) => `${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
    return (
      <polygon
        points={`${padL} ${y(0)} ${pts} ${x(arr.length - 1)} ${y(0)}`}
        fill={color}
        opacity={0.08}
      />
    );
  };

  const grid = Array.from({ length: 5 }, (_, i) => {
    const gv = Math.round((max / 4) * i);
    const gy = y(gv);
    return (
      <g key={i}>
        <line x1={padL} y1={gy} x2={w - padR} y2={gy} stroke="#f0f2f5" strokeWidth={1} />
        <text x={padL - 6} y={gy + 3} textAnchor="end" fill="#c0c4cc" fontSize={10} fontFamily="monospace">
          {gv}
        </text>
      </g>
    );
  });

  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: "auto", display: "block" }}>
      {grid}
      {series.map((arr, si) => area(arr, COLORS[si]))}
      {series.map((arr, si) => (
        <polyline
          key={si}
          points={line(arr)}
          fill="none"
          stroke={COLORS[si]}
          strokeWidth={2}
          strokeLinejoin="round"
          strokeDasharray={si === 2 ? "5 3" : undefined}
        />
      ))}
      {series.flatMap((arr, si) =>
        arr.map((v, i) => (
          <circle
            key={`${si}-${i}`}
            cx={x(i)}
            cy={y(v)}
            r={3.2}
            fill="#fff"
            stroke={COLORS[si]}
            strokeWidth={2}
          />
        )),
      )}
      {trend.map((d, i) => (
        <text key={d.day_label} x={x(i)} y={h - 8} textAnchor="middle" fill="#909399" fontSize={11} fontFamily="monospace">
          {d.day_label}
        </text>
      ))}
    </svg>
  );
}

export function DonutChart({ dist }: { dist: Overview["level_distribution"] }) {
  const total = dist.total || 1;
  const seg = [
    { v: dist.high, c: "#f56c6c", t: "高风险" },
    { v: dist.mid, c: "#e6a23c", t: "中风险" },
    { v: dist.low, c: "#67c23a", t: "低风险" },
  ];
  const r = 54;
  const C = 2 * Math.PI * r;
  let off = 0;
  const arcs = seg.map((s) => {
    const len = (C * s.v) / total;
    const arc = (
      <circle
        key={s.t}
        r={r}
        cx={66}
        cy={66}
        fill="none"
        stroke={s.c}
        strokeWidth={14}
        strokeDasharray={`${len} ${C - len}`}
        strokeDashoffset={-off}
      />
    );
    off += len;
    return arc;
  });

  return (
    <div className="donut-wrap">
      <div className="donut">
        <svg viewBox="0 0 132 132">
          <circle r={r} cx={66} cy={66} fill="none" stroke="#f0f2f5" strokeWidth={14} />
          {arcs}
        </svg>
        <div className="center">
          <div className="n">{dist.total}</div>
          <div className="t">今日告警</div>
        </div>
      </div>
      <div className="donut-legend">
        {seg.map((s) => (
          <div className="dl-item" key={s.t}>
            <i style={{ background: s.c }} />
            {s.t}
            <span className="v">{s.v}</span>
            <span className="pct">{Math.round((s.v / total) * 100)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const BAR_COLORS = ["#409eff", "#e6a23c", "#7b3fe4", "#67c23a"];

export function ModelBar({ hits }: { hits: Overview["model_hits"] }) {
  return (
    <div className="hbar">
      {hits.map((m, i) => (
        <div className="hb-item" key={m.id}>
          <span className="nm">
            <svg viewBox="0 0 24 24">
              <path d="M12 2L1 21h22L12 2z" />
            </svg>
            <span className="nm-txt">
              模型{m.id} · {m.name}
            </span>
          </span>
          <div className="hb-track">
            <div className="hb-fill" style={{ width: `${m.pct}%`, background: BAR_COLORS[i] }} />
          </div>
          <span className="cnt">{m.hit7}</span>
          <span className="pct">{m.pct}%</span>
        </div>
      ))}
    </div>
  );
}
