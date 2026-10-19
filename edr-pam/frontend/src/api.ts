export type Alert = {
  id: string;
  name: string;
  model_id: number;
  model_name?: string;
  level: string;
  risk: number;
  account: string;
  asset: string;
  src_ip: string;
  discovered_at: string;
  status: string;
  description: string;
};

export type AlertDetail = Alert & {
  timeline: { src: string; time: string; title: string; description: string; badge?: string | null }[];
  evidence: { src: string; field_name: string; value: string }[];
  logs: { time: string; operator: string; operation: string }[];
};

export type Overview = {
  today_alerts: number;
  today_alerts_delta: number;
  high_risk_accounts: number;
  high_risk_pending: number;
  today_disposals: number;
  auto_disposals: number;
  models_running: number;
  models_total: number;
  false_positive_rate: string;
  trend: { day_label: string; alert_count: number; high_count: number; dispose_count: number }[];
  level_distribution: { high: number; mid: number; low: number; total: number };
  model_hits: { id: number; name: string; hit7: number; pct: number }[];
  top_accounts: { account: string; risk: number; model_label: string; status: string }[];
  latest_alerts: Alert[];
};

export type Model = {
  id: number;
  name: string;
  description: string;
  enabled: boolean;
  hit7: number;
  fp_rate: string;
  disposed_rate: string;
  steps: string[];
  scene: string;
  edr_fields: string[];
  pam_fields: string[];
};

export type Linkage = {
  id: number;
  name: string;
  slug: string;
  severity: string;
  subtitle: string;
  enabled: boolean;
  triggers: string[];
  actions: string[];
  recovery_condition: string;
  icon_color: string;
  last_trigger_label: string;
};

export type Disposal = {
  id: number;
  disposed_at: string;
  alert_id: string;
  action: string;
  target: string;
  operator: string;
  result: string;
};

export type ChainItem = {
  src: string;
  time: string;
  title: string;
  description: string;
};

export type Report = {
  report_id: string;
  generated_at: string;
  account: string;
  asset: string;
  alert_id: string;
  alert_name: string;
  risk: number;
  level: string;
  summary: string;
  impact: string;
  recommendations: string;
  timeline: ChainItem[];
  matched_alert_count: number;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  overview: () => request<Overview>("/api/overview"),
  alerts: (params: Record<string, string>) => {
    const qs = new URLSearchParams(params).toString();
    return request<{ total: number; pending: number; items: Alert[] }>(`/api/alerts?${qs}`);
  },
  alert: (id: string) => request<AlertDetail>(`/api/alerts/${id}`),
  dispose: (id: string, action: string) =>
    request<AlertDetail>(`/api/alerts/${id}/dispose`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),
  models: () => request<Model[]>("/api/models"),
  toggleModel: (id: number, enabled: boolean) =>
    request<Model>(`/api/models/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    }),
  linkages: () => request<Linkage[]>("/api/linkages"),
  toggleLinkage: (id: number, enabled: boolean) =>
    request<Linkage>(`/api/linkages/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    }),
  disposals: () => request<Disposal[]>("/api/disposals"),
  chain: () => request<ChainItem[]>("/api/evidence/chain"),
  report: (body: { date_from?: string; date_to?: string; account: string; asset: string }) =>
    request<Report>("/api/evidence/report", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  reportPdf: async (body: { date_from?: string; date_to?: string; account: string; asset: string }) => {
    const res = await fetch("/api/evidence/report/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || res.statusText);
    }
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") ?? "";
    const match = disposition.match(/filename="?([^";]+)"?/);
    const filename = match?.[1] ?? "audit-report.pdf";
    return { blob, filename };
  },
};
