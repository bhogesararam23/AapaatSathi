import { Navigate, Route, Routes } from "react-router-dom";
import type { ReactElement, ReactNode } from "react";

import { tokenStore } from "./api/client";
import { Layout } from "./components/Layout";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { LiveProvider } from "./state/live";
import { SessionProvider, useSession } from "./state/session";
import { ToastProvider } from "./components/ui";

import Home from "./pages/Home";
import WardPage from "./pages/WardPage";
import ReportPage from "./pages/ReportPage";
import SheltersPage from "./pages/SheltersPage";
import RoadsPage from "./pages/RoadsPage";
import ModelPage from "./pages/ModelPage";
import SignIn from "./pages/SignIn";
import Responder from "./pages/Responder";
import Console from "./pages/Console";

function StaffOnly({ children }: { children: ReactElement }) {
  const { user, ready } = useSession();
  if (!ready) return null;
  if (!user) return <Navigate to="/signin" replace />;
  if (user.role === "citizen") return <Navigate to="/" replace />;
  return children;
}

function OpsLive({ children }: { children: ReactNode }) {
  const { user } = useSession();
  // Staff pages open the ops channel; citizens only ever get anonymised risk.
  const staff = !!user && user.role !== "citizen";
  // The ops channel is authorisation-gated server-side, so the socket needs the
  // same bearer token the REST client sends. Without it the handshake is closed
  // with 4403 and the console silently stops updating.
  const token = staff ? tokenStore.get() ?? "" : "";
  return (
    <LiveProvider key={staff ? `ops:${user?.id ?? 0}` : "public"} channel={staff ? "ops" : "public"} token={token}>
      {children}
    </LiveProvider>
  );
}

export default function App() {
  return (
    <SessionProvider>
      <ToastProvider>
        <OpsLive>
          <Layout>
            <ErrorBoundary>
              <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/ward/:code" element={<WardPage />} />
                <Route path="/report" element={<ReportPage />} />
                <Route path="/shelters" element={<SheltersPage />} />
                <Route path="/roads" element={<RoadsPage />} />
                <Route path="/model" element={<ModelPage />} />
                <Route path="/signin" element={<SignIn />} />
                <Route
                  path="/responder"
                  element={
                    <StaffOnly>
                      <Responder />
                    </StaffOnly>
                  }
                />
                <Route
                  path="/console"
                  element={
                    <StaffOnly>
                      <Console />
                    </StaffOnly>
                  }
                />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </ErrorBoundary>
          </Layout>
        </OpsLive>
      </ToastProvider>
    </SessionProvider>
  );
}
