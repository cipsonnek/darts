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
const OperatorShell = lazy(() => import("@/operator/OperatorShell").then((m) => ({ default: m.OperatorShell })));
const OpDashboard = lazy(() => import("@/operator/pages/Dashboard"));
const OpVenues = lazy(() => import("@/operator/pages/Venues"));
const OpVenueDetail = lazy(() => import("@/operator/pages/VenueDetail"));
const OpBoards = lazy(() => import("@/operator/pages/Boards"));
const OpBoardDetail = lazy(() => import("@/operator/pages/BoardDetail"));
const OpStats = lazy(() => import("@/operator/pages/Stats"));
const OpSettlements = lazy(() => import("@/operator/pages/Settlements"));
const OpTickets = lazy(() => import("@/operator/pages/Tickets"));

function Loading() {
  return <div className="flex h-60 items-center justify-center"><Spinner /></div>;
}

export default function App() {
  return (
    <LiveProvider>
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/tv" element={<TvMode />} />
          <Route path="/operator" element={<OperatorShell />}>
            <Route index element={<OpDashboard />} />
            <Route path="venues" element={<OpVenues />} />
            <Route path="venues/:id" element={<OpVenueDetail />} />
            <Route path="boards" element={<OpBoards />} />
            <Route path="boards/:id" element={<OpBoardDetail />} />
            <Route path="stats" element={<OpStats />} />
            <Route path="settlements" element={<OpSettlements />} />
            <Route path="tickets" element={<OpTickets />} />
          </Route>
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
