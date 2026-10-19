import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router";
import { AppShell } from "@/components/layout/AppShell";
import { LiveProvider } from "@/components/LiveProvider";
import { Spinner } from "@/components/ui";
import Play from "@/pages/Play";

const Games = lazy(() => import("@/pages/Games"));
const Players = lazy(() => import("@/pages/Players"));
const Statistics = lazy(() => import("@/pages/Statistics"));
const Cameras = lazy(() => import("@/pages/Cameras"));
const Calibration = lazy(() => import("@/pages/Calibration"));
const Detection = lazy(() => import("@/pages/Detection"));
const Settings = lazy(() => import("@/pages/Settings"));
const Developer = lazy(() => import("@/pages/Developer"));
const TvMode = lazy(() => import("@/pages/TvMode"));

function Loading() {
  return <div className="flex h-60 items-center justify-center"><Spinner /></div>;
}

export default function App() {
  return (
    <LiveProvider>
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/tv" element={<TvMode />} />
          <Route element={<AppShell />}>
            <Route index element={<Play />} />
            <Route path="games" element={<Games />} />
            <Route path="players" element={<Players />} />
            <Route path="stats" element={<Statistics />} />
            <Route path="cameras" element={<Cameras />} />
            <Route path="calibration" element={<Calibration />} />
            <Route path="detection" element={<Detection />} />
            <Route path="settings" element={<Settings />} />
            <Route path="developer" element={<Developer />} />
            <Route path="*" element={<div className="p-10 text-center text-[var(--muted)]">Nie ma takiej strony.</div>} />
          </Route>
        </Routes>
      </Suspense>
    </LiveProvider>
  );
}
