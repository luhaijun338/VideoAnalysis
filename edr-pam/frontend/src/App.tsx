import { useCallback, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import AlertDrawer from "./components/AlertDrawer";
import AlertsPage from "./pages/AlertsPage";
import DisposePage from "./pages/DisposePage";
import EvidencePage from "./pages/EvidencePage";
import ModelsPage from "./pages/ModelsPage";
import OverviewPage from "./pages/OverviewPage";
import { ToastProvider } from "./ui";

export default function App() {
  const [alertId, setAlertId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const onUpdated = useCallback(() => setRefreshKey((k) => k + 1), []);

  return (
    <ToastProvider>
      <main>
        <div className="page-tabs">
          <NavLink to="/" end className={({ isActive }) => `tab-item${isActive ? " active" : ""}`}>
            风险总览
          </NavLink>
          <NavLink to="/alerts" className={({ isActive }) => `tab-item${isActive ? " active" : ""}`}>
            告警研判
          </NavLink>
          <NavLink to="/dispose" className={({ isActive }) => `tab-item${isActive ? " active" : ""}`}>
            处置联动
          </NavLink>
          <NavLink to="/models" className={({ isActive }) => `tab-item${isActive ? " active" : ""}`}>
            模型配置
          </NavLink>
          <NavLink to="/evidence" className={({ isActive }) => `tab-item${isActive ? " active" : ""}`}>
            审计证据链
          </NavLink>
        </div>

        <Routes>
          <Route path="/" element={<OverviewPage key={refreshKey} onOpenAlert={setAlertId} />} />
          <Route path="/alerts" element={<AlertsPage key={refreshKey} onOpenAlert={setAlertId} />} />
          <Route path="/dispose" element={<DisposePage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/evidence" element={<EvidencePage />} />
        </Routes>
      </main>

      <AlertDrawer alertId={alertId} onClose={() => setAlertId(null)} onUpdated={onUpdated} />
    </ToastProvider>
  );
}
