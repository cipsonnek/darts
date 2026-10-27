import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router";
import { AppShell } from "@/components/layout/AppShell";
import { LiveProvider } from "@/components/LiveProvider";
import { Logo, Spinner } from "@/components/ui";
import Play from "@/pages/Play";
import { ServiceGate } from "@/pages/Service";
import { useLive } from "@/store/live";

const NewGame = lazy(() => import("@/pages/Games"));
const History = lazy(() => import("@/pages/History"));
const Service = lazy(() => import("@/pages/Service"));
const CalibrationWizard = lazy(() => import("@/pages/CalibrationWizard"));
const Players = lazy(() => import("@/pages/Players"));
const Statistics = lazy(() => import("@/pages/Statistics"));
const Cameras = lazy(() => import("@/pages/Cameras"));
const Calibration = lazy(() => import("@/pages/Calibration"));
const Detection = lazy(() => import("@/pages/Detection"));
const Settings = lazy(() => import("@/pages/Settings"));
const Developer = lazy(() => import("@/pages/Developer"));
const TvMode = lazy(() => import("@/pages/TvMode"));
const OperatorApp = lazy(() => import("@/operator/OperatorShell").then((m) => ({ default: m.OperatorApp })));
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

function Starting() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4">
      <div className="backdrop" />
      <div className="animate-float"><Logo size={88} /></div>
      <div className="flex items-center gap-2 text-[var(--muted)]"><Spinner /> Łączenie z serwerem…</div>
    </div>
  );
}

/** Pages only venue staff (service PIN) can open. */
const svc = (el: React.ReactNode) => <ServiceGate>{el}</ServiceGate>;

/** The operator's central server: only the operator panel (behind sign-in). */
function CentralRoutes() {
  return (
    <Routes>
      <Route path="/operator" element={<OperatorApp />}>
        <Route index element={<OpDashboard />} />
        <Route path="venues" element={<OpVenues />} />
        <Route path="venues/:id" element={<OpVenueDetail />} />
        <Route path="boards" element={<OpBoards />} />
        <Route path="boards/:id" element={<OpBoardDetail />} />
        <Route path="stats" element={<OpStats />} />
        <Route path="settlements" element={<OpSettlements />} />
        <Route path="tickets" element={<OpTickets />} />
      </Route>
      <Route path="*" element={<Navigate to="/operator" replace />} />
    </Routes>
  );
}

/** A board in a venue: playing for everyone, calibration and service pages behind the PIN.
 *  The operator panel does not exist here. */
function BoardRoutes() {
  return (
    <Routes>
      <Route path="/tv" element={<TvMode />} />
      <Route element={<AppShell />}>
        <Route index element={<Play />} />
        <Route path="games" element={<NewGame />} />
        <Route path="calibration" element={svc(<CalibrationWizard />)} />
        <Route path="service" element={<Service />} />
        <Route path="service/calibration" element={svc(<Calibration />)} />
        <Route path="service/cameras" element={svc(<Cameras />)} />
        <Route path="service/history" element={svc(<History />)} />
        <Route path="service/players" element={svc(<Players />)} />
        <Route path="service/stats" element={svc(<Statistics />)} />
        <Route path="service/detection" element={svc(<Detection />)} />
        <Route path="service/settings" element={svc(<Settings />)} />
        <Route path="service/developer" element={svc(<Developer />)} />
        <Route path="operator/*" element={<Navigate to="/" replace />} />
        <Route path="*" element={<div className="p-10 text-center text-[var(--muted)]">Nie ma takiej strony.</div>} />
      </Route>
    </Routes>
  );
}

function Routed() {
  const mode = useLive((s) => s.mode);
  if (mode === null) return <Starting />;
  return (
    <Suspense fallback={<Loading />}>
      {mode === "central" ? <CentralRoutes /> : <BoardRoutes />}
    </Suspense>
  );
}

export default function App() {
  return (
    <LiveProvider>
      <Routed />
    </LiveProvider>
  );
}
