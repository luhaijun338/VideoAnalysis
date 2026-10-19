import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { PlayerProvider } from "./player";
import LibraryPage from "./pages/LibraryPage";
import SearchPage from "./pages/SearchPage";
import { ToastHost } from "./ui";

export default function App() {
  return (
    <PlayerProvider>
      <div className="app">
        <main className="app-main">
          <nav className="page-tabs">
            <NavLink to="/" end className={({ isActive }) => `tab-item${isActive ? " active" : ""}`}>
              检索
            </NavLink>
            <NavLink
              to="/library"
              className={({ isActive }) => `tab-item${isActive ? " active" : ""}`}
            >
              录像库
            </NavLink>
          </nav>
          <Routes>
            <Route path="/" element={<SearchPage />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/search" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        <ToastHost />
      </div>
    </PlayerProvider>
  );
}
