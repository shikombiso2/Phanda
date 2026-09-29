import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Mark } from "./Mark";

export function AuthLayout({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[0.85fr_1fr]">
      <div className="hidden flex-col justify-between bg-phanda-green p-10 text-white lg:flex">
        <Link to="/" className="inline-flex items-center gap-2.5">
          <svg width={28} height={28} viewBox="0 0 32 32" aria-hidden="true">
            <rect width="32" height="32" rx="6" fill="white" />
            <path fill="#0B8F55" d="M9 5h13v3H9zM9 8h3v19H9zM19 8h3v11h-3zM9 16h13v3H9zM12 11h4v3h-4z" />
          </svg>
          <span className="font-display text-xl font-black tracking-tight">Phanda</span>
        </Link>
        <p className="max-w-sm font-display text-3xl font-bold leading-snug">
          Your CV, tailored for every job you apply to. Not one generic copy sent everywhere.
        </p>
        <p className="font-body text-sm text-white/70">Built for South African jobseekers.</p>
      </div>

      <div className="flex flex-col justify-center px-6 py-12 sm:px-12 lg:px-16">
        <div className="mx-auto w-full max-w-sm">
          <div className="mb-8 lg:hidden">
            <Link to="/">
              <Mark />
            </Link>
          </div>
          <h1 className="font-display text-3xl font-black tracking-tight text-ink">{title}</h1>
          <p className="mt-2 font-body text-[15px] text-ink/60">{subtitle}</p>
          <div className="mt-8">{children}</div>
        </div>
      </div>
    </div>
  );
}
