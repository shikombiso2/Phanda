import { Link } from "react-router-dom";
import { Mark } from "../components/Mark";
import { Button } from "../components/Button";
import { InstallButton } from "../components/InstallButton";
import { CheckIcon } from "../components/icons";

const SAMPLE_MATCHES = [
  { title: "Retail Learnership", company: "Pick n Pay", location: "Durban", match: 92 },
  { title: "Junior IT Support", company: "Vodacom", location: "Remote", match: 88 },
  { title: "Admin Internship", company: "Old Mutual", location: "Johannesburg", match: 81 },
];

const STEPS = [
  {
    title: "Build your profile",
    body: "Tell us your skills, experience and where you're willing to work. Two minutes, and you can stop anywhere.",
  },
  {
    title: "We match and tailor",
    body: "Phanda scores you against real openings and rewrites your CV to speak to each one -- not a generic copy sent everywhere.",
  },
  {
    title: "Apply with confidence",
    body: "Send a CV built for that job, from a platform that already knows what you're good at.",
  },
];

export function Landing() {
  return (
    <div className="min-h-screen bg-paper">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5 sm:px-8">
        <Mark />
        <nav className="flex items-center gap-3 sm:gap-5">
          <a href="#how-it-works" className="hidden font-body text-sm font-medium text-ink/70 hover:text-ink sm:inline">
            How it works
          </a>
          <Link to="/login" className="font-body text-sm font-medium text-ink/70 hover:text-ink">
            Log in
          </Link>
          <Link
            to="/register"
            className="rounded-[10px] bg-phanda-green px-4 py-2.5 font-body text-sm font-semibold text-white hover:bg-phanda-green-dark"
          >
            Get started
          </Link>
        </nav>
      </header>

      <main>
        {/* HERO -- left-aligned and asymmetric on purpose: a centered hero
            with a centered subhead and a centered button is the templated
            default for this kind of page. The right side is a real product
            demo, not stock illustration. */}
        <section className="mx-auto grid max-w-6xl gap-12 px-5 pb-16 pt-10 sm:px-8 sm:pt-16 lg:grid-cols-[1.1fr_0.9fr] lg:items-center lg:gap-8">
          <div>
            <h1 className="font-display text-[40px] font-black leading-[1.05] tracking-tight text-ink sm:text-[52px] lg:text-[58px]">
              South Africa isn't
              <br />
              advertising to you.
              <br />
              Phanda goes digging.
            </h1>
            <p className="mt-6 max-w-md font-body text-lg leading-relaxed text-ink/70">
              Learnerships, internships and entry-level jobs, matched to your actual CV -- not just
              listed next to a thousand others.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link to="/register">
                <Button variant="primary" className="px-6 py-3.5 text-base">
                  Get started free
                </Button>
              </Link>
              <a href="#how-it-works">
                <Button variant="secondary" className="px-6 py-3.5 text-base">
                  See how it works
                </Button>
              </a>
            </div>
            <div className="mt-8">
              <InstallButton variant="hero" />
              <p className="mt-2 font-body text-sm text-ink/50">
                Works like an app on your phone. Small download, no app store needed.
              </p>
            </div>
          </div>

          <div className="rounded-2xl border border-hairline bg-mist p-5 sm:p-6">
            <p className="font-body text-sm font-semibold uppercase text-ink/40" style={{ letterSpacing: "0" }}>
              Matched for you
            </p>
            <ul className="mt-4 flex flex-col gap-3">
              {SAMPLE_MATCHES.map((m) => (
                <li key={m.title} className="rounded-xl border border-hairline bg-paper p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-body text-[15px] font-semibold text-ink">{m.title}</p>
                      <p className="font-body text-sm text-ink/60">
                        {m.company} &middot; {m.location}
                      </p>
                    </div>
                    <span className="shrink-0 rounded-full bg-phanda-green/10 px-2.5 py-1 font-body text-xs font-bold text-phanda-green-dark">
                      {m.match}% match
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* Honest framing, no invented statistic dressed up as fact. */}
        <section className="border-y border-hairline bg-ink">
          <div className="mx-auto max-w-6xl px-5 py-14 sm:px-8">
            <p className="max-w-2xl font-display text-2xl font-bold leading-snug text-white sm:text-3xl">
              Getting your first job in South Africa often isn't about being the most qualified
              person who applied. It's about who gets seen first.
            </p>
            <p className="mt-4 max-w-xl font-body text-white/60">
              Phanda exists to put you in front of the roles that actually fit you, and to make sure
              your CV is the one that gets a second look.
            </p>
          </div>
        </section>

        {/* Numbered steps: legitimate here, because the content genuinely
            is a sequence -- profile, then match, then apply. */}
        <section id="how-it-works" className="mx-auto max-w-6xl px-5 py-16 sm:px-8">
          <h2 className="font-display text-3xl font-black tracking-tight text-ink sm:text-4xl">How it works</h2>
          <div className="mt-10 grid gap-10 sm:grid-cols-3 sm:gap-8">
            {STEPS.map((step, i) => (
              <div key={step.title}>
                <span className="font-display text-4xl font-black text-phanda-gold-dark">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <h3 className="mt-3 font-body text-lg font-semibold text-ink">{step.title}</h3>
                <p className="mt-2 font-body text-[15px] leading-relaxed text-ink/65">{step.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* What makes it different, stated plainly rather than as a card grid of icons. */}
        <section className="bg-mist">
          <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8">
            <h2 className="font-display text-3xl font-black tracking-tight text-ink sm:text-4xl">
              Not another job board
            </h2>
            <div className="mt-8 grid gap-6 sm:grid-cols-2">
              <div className="flex gap-3">
                <CheckIcon className="mt-1 h-5 w-5 shrink-0 text-phanda-green" />
                <p className="font-body text-[15px] leading-relaxed text-ink/75">
                  <span className="font-semibold text-ink">Matching, not just listing.</span> We score
                  every opening against your actual skills and experience, so you're not scrolling
                  through hundreds of roles that were never going to fit.
                </p>
              </div>
              <div className="flex gap-3">
                <CheckIcon className="mt-1 h-5 w-5 shrink-0 text-phanda-green" />
                <p className="font-body text-[15px] leading-relaxed text-ink/75">
                  <span className="font-semibold text-ink">A CV tailored per job.</span> Phanda rewrites
                  your CV to speak directly to each role you apply for, using what's actually true about you.
                </p>
              </div>
              <div className="flex gap-3">
                <CheckIcon className="mt-1 h-5 w-5 shrink-0 text-phanda-green" />
                <p className="font-body text-[15px] leading-relaxed text-ink/75">
                  <span className="font-semibold text-ink">Built for entry-level.</span> Learnerships,
                  internships, graduate roles and general work -- the openings a generic job board
                  buries under senior listings.
                </p>
              </div>
              <div className="flex gap-3">
                <CheckIcon className="mt-1 h-5 w-5 shrink-0 text-phanda-green" />
                <p className="font-body text-[15px] leading-relaxed text-ink/75">
                  <span className="font-semibold text-ink">Light on your data.</span> Phanda installs
                  like an app and is built to load fast, even on an older phone or a thin signal.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-5 py-20 text-center sm:px-8">
          <h2 className="font-display text-3xl font-black tracking-tight text-ink sm:text-4xl">
            Your next job is out there.
            <br />
            Let's go find it.
          </h2>
          <Link to="/register" className="mt-8 inline-block">
            <Button variant="primary" className="px-8 py-4 text-base">
              Create your free account
            </Button>
          </Link>
        </section>
      </main>

      <footer className="border-t border-hairline px-5 py-8 sm:px-8">
        <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
          <Mark size={22} />
          <p className="font-body text-sm text-ink/50">Built for South African jobseekers.</p>
        </div>
      </footer>
    </div>
  );
}
