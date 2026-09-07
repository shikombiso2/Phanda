import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { Mark } from "./Mark";

export function RequireAuth({ children }: { children: ReactNode }) {
  const status = useAuthStore((s) => s.status);

  if (status === "checking") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4">
        <Mark size={32} />
        <div className="h-1 w-32 overflow-hidden rounded-full bg-mist">
          <div className="h-full w-1/3 animate-pulse rounded-full bg-phanda-green" />
        </div>
      </div>
    );
  }

  if (status === "anonymous") return <Navigate to="/login" replace />;

  return <>{children}</>;
}
