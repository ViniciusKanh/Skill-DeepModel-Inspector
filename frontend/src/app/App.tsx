import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { AppProvider, useApp } from "./AppState";
import { Footer, Header, NAV, Sidebar, Toasts } from "../components/layout";
import { Loader } from "../components/ui";

const Dashboard = lazy(() => import("../pages/Dashboard"));
const Training = lazy(() => import("../pages/Training"));
const Dataset = lazy(() => import("../pages/Dataset"));
const Tokenizer = lazy(() => import("../pages/Tokenizer"));
const Generation = lazy(() => import("../pages/Generation"));
const Compare = lazy(() => import("../pages/Compare"));
const Investigate = lazy(() => import("../pages/Investigate"));
const Reports = lazy(() => import("../pages/Reports"));
const Projects = lazy(() => import("../pages/Projects"));
const SettingsPage = lazy(() => import("../pages/Settings"));

function Shell() {
  const { t } = useApp();
  const loc = useLocation();
  const nav = NAV.find((n) => (n.to === "/" ? loc.pathname === "/" : loc.pathname.startsWith(n.to)));
  return (
    <div className="h-full flex gap-3 p-3 max-sm:p-1.5 max-sm:gap-1.5">
      <Sidebar />
      <div className="bezel flex-1 min-w-0 flex flex-col">
        <div className="screen flex-1 min-h-0 flex flex-col">
          <Header title={nav ? t(nav.key) : "DeepModel Inspector"} />
          <main className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-4 pb-4 relative z-0" id="main">
            <Suspense fallback={<Loader label="Booting module" />}>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/training" element={<Training />} />
                <Route path="/dataset" element={<Dataset />} />
                <Route path="/tokenizer" element={<Tokenizer />} />
                <Route path="/generation" element={<Generation />} />
                <Route path="/compare" element={<Compare />} />
                <Route path="/investigate" element={<Investigate />} />
                <Route path="/reports" element={<Reports />} />
                <Route path="/projects" element={<Projects />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="*" element={<Dashboard />} />
              </Routes>
            </Suspense>
          </main>
        </div>
        <Footer />
      </div>
      <Toasts />
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Shell />
      </BrowserRouter>
    </AppProvider>
  );
}
