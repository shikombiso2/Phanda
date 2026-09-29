import { NavLink, useNavigate } from "react-router-dom";
import { Mark } from "./Mark";
import { useAuthStore } from "../store/authStore";
import { HomeIcon, SearchIcon, HeartIcon, TrackIcon, UserIcon } from "./icons";

/** badge is the unread count to show on that tab -- 0/undefined renders no
 * badge at all. Applications has no real source for this yet (no backend
 * notification/status-change feed), so it's wired up but hardcoded to 0
 * rather than a guessed number, ready for a real count later. */
const TABS: { to: string; label: string; icon: typeof HomeIcon; end?: boolean; badge?: number }[] = [
  { to: "/home", label: "Home", icon: HomeIcon, end: true },
  { to: "/find", label: "Find", icon: SearchIcon },
  { to: "/track", label: "Applications", icon: TrackIcon, badge: 0 },
  { to: "/saved", label: "Saved", icon: HeartIcon },
  { to: "/profile", label: "Profile", icon: UserIcon },
];

/**
 * Replaces the single-purpose AppHeader now that there's more than one
 * screen: a top bar everywhere (brand + sign out), and on mobile a second,
 * fixed bottom tab bar -- the standard place a thumb expects primary
 * navigation on a phone-sized screen, which is this product's primary
 * device. Desktop gets the same five destinations as inline top-bar links
 * instead of duplicating a bottom bar nobody's thumb needs there.
 */
export function AppNav() {
  const navigate = useNavigate();
  const logout = useAuthStore((s) => s.logout);

  function signOut() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <>
      <header className="flex items-center justify-between border-b border-hairline px-5 py-4 sm:px-8">
        <Mark />
        <nav className="hidden items-center gap-6 sm:flex">
          {TABS.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              end={tab.end}
              className={({ isActive }) =>
                `font-body text-sm font-medium transition-colors ${isActive ? "text-phanda-green-dark" : "text-ink/60 hover:text-ink"}`
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
        <button onClick={signOut} className="font-body text-sm font-medium text-ink/70 hover:text-ink">
          Sign out
        </button>
      </header>

      <nav
        className="fixed inset-x-0 bottom-0 z-10 flex border-t border-hairline bg-paper pb-[env(safe-area-inset-bottom)] sm:hidden"
        aria-label="Primary"
      >
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) =>
              `flex flex-1 flex-col items-center gap-1 py-2.5 font-body text-xs font-medium transition-colors ${
                isActive ? "text-phanda-green-dark" : "text-ink/50"
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span className="relative">
                  <tab.icon className="h-5 w-5" filled={isActive} />
                  {!!tab.badge && (
                    <span
                      aria-label={`${tab.badge} unread`}
                      className="absolute -right-1.5 -top-1.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-signal text-[9px] font-bold text-white"
                    >
                      {tab.badge > 9 ? "9+" : tab.badge}
                    </span>
                  )}
                </span>
                {tab.label}
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </>
  );
}

/** Bottom padding for page content on mobile, so the fixed tab bar never
 * covers the last item in a list. Import this className rather than
 * guessing the bar's height per page. */
export const BOTTOM_NAV_SPACER_CLASS = "pb-20 sm:pb-0";
