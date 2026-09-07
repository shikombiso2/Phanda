import { useNavigate } from "react-router-dom";
import { Mark } from "./Mark";
import { useAuthStore } from "../store/authStore";

export function AppHeader() {
  const navigate = useNavigate();
  const logout = useAuthStore((s) => s.logout);

  return (
    <header className="flex items-center justify-between border-b border-hairline px-5 py-4 sm:px-8">
      <Mark />
      <button
        onClick={() => {
          logout();
          navigate("/login", { replace: true });
        }}
        className="font-body text-sm font-medium text-ink/70 hover:text-ink"
      >
        Sign out
      </button>
    </header>
  );
}
