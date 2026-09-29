import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthLayout } from "../../components/AuthLayout";
import { Button } from "../../components/Button";
import { Mark } from "../../components/Mark";
import { ProgressState } from "../../components/ProgressState";
import { TextField } from "../../components/TextField";
import { CheckIcon } from "../../components/icons";
import { api } from "../../lib/api";
import { useAuthStore } from "../../store/authStore";
import type { CvUploadOut, ProfileOut } from "../../types/api";
import { CvFilePicker, validateCvFile } from "./CvFilePicker";
import { pollCvVersionUntilTerminal } from "./cvPolling";
import { ProfileQuestionnaire } from "./ProfileQuestionnaire";
import { emptyProfileAnswers, isProfileAnswersEmpty, profileAnswersToUpdate, type ProfileAnswers } from "./profileAnswers";

type MacroStep = "profile" | "cv" | "account" | "submitting";

/**
 * Registration, restructured as one flow: profile preferences (skippable),
 * then a CV (skippable), then the account details that actually create it.
 * The first two steps never touch the network -- there's no account and no
 * auth token yet, so their answers just live in this component's state
 * until step 3 succeeds and gives the rest of the app something to save
 * them against.
 */
export function SignupWizard() {
  const navigate = useNavigate();
  const register = useAuthStore((s) => s.register);
  const setProfile = useAuthStore((s) => s.setProfile);
  const reloadProfile = useAuthStore((s) => s.reloadProfile);
  const registerError = useAuthStore((s) => s.error);

  const [macroStep, setMacroStep] = useState<MacroStep>("profile");
  const [profileAnswers, setProfileAnswers] = useState<ProfileAnswers>(emptyProfileAnswers);
  const [cvFile, setCvFile] = useState<File | null>(null);
  const [cvError, setCvError] = useState<string | null>(null);
  const [submitLabel, setSubmitLabel] = useState("Creating your account...");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [matchError, setMatchError] = useState<string | null>(null);

  function pickCvFile(file: File) {
    const validationError = validateCvFile(file);
    if (validationError) {
      setCvError(validationError);
      return;
    }
    setCvError(null);
    setCvFile(file);
  }

  async function submitAccount(event: FormEvent) {
    event.preventDefault();
    if (password !== confirmPassword) {
      setMatchError("Those passwords don't match.");
      return;
    }
    setMatchError(null);
    setMacroStep("submitting");
    setSubmitLabel("Creating your account...");

    try {
      // The only point an account gets created. If this fails (e.g. the
      // email is already registered), register() has already put the
      // error in the store -- drop back to the account step with the
      // step 1/2 answers (profileAnswers, cvFile) still intact, since
      // neither of those was ever sent anywhere yet.
      await register(email, password);
    } catch {
      setMacroStep("account");
      return;
    }

    // The account exists; that's the part that matters. Everything past
    // here is best-effort -- a failure here must not strand the user on
    // this screen, since Home already has a UI for "profile/CV not done
    // yet" that covers exactly this case.
    let issue: "profile" | "cv" | "both" | null = null;

    if (!isProfileAnswersEmpty(profileAnswers)) {
      setSubmitLabel("Saving your profile...");
      try {
        const updated = await api.put<ProfileOut>("/profile", profileAnswersToUpdate(profileAnswers));
        setProfile(updated);
      } catch {
        issue = "profile";
      }
    }

    if (cvFile) {
      setSubmitLabel("Uploading your CV...");
      try {
        const body = new FormData();
        body.append("file", cvFile);
        const result = await api.post<CvUploadOut>("/profile/cv-upload", body);
        if (result.status !== "ready") {
          setSubmitLabel("Reading your CV...");
          const { promise } = pollCvVersionUntilTerminal(result.cv_version_id);
          const version = await promise;
          if (version.status === "failed") issue = issue === "profile" ? "both" : "cv";
        }
        await reloadProfile();
      } catch {
        issue = issue === "profile" ? "both" : "cv";
      }
    }

    navigate("/home", { replace: true, state: issue ? { onboardingIssue: issue } : undefined });
  }

  if (macroStep === "profile") {
    return (
      <WizardShell>
        <ProfileQuestionnaire
          values={profileAnswers}
          onChange={setProfileAnswers}
          onFinish={() => setMacroStep("cv")}
          onSkip={() => setMacroStep("cv")}
          finishLabel="Continue"
        />
      </WizardShell>
    );
  }

  if (macroStep === "cv") {
    return (
      <WizardShell>
        <div className="mb-8 flex justify-end">
          <button
            onClick={() => setMacroStep("account")}
            className="font-body text-sm font-medium text-ink/50 hover:text-ink"
          >
            Skip for now
          </button>
        </div>
        <h1 className="font-display text-2xl font-black tracking-tight text-ink">Add your CV</h1>
        <p className="mt-1.5 font-body text-[15px] text-ink/60">
          We'll use it to match you to jobs and tailor it for each one you apply to.
        </p>
        <div className="mt-8">
          {cvFile ? (
            <div className="flex flex-col items-center gap-4 rounded-2xl border border-hairline px-6 py-12 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-phanda-green text-white">
                <CheckIcon className="h-6 w-6" />
              </span>
              <p className="font-body text-[15px] font-semibold text-ink">{cvFile.name}</p>
              <Button className="w-full" onClick={() => setMacroStep("account")}>
                Continue
              </Button>
              <button
                onClick={() => setCvFile(null)}
                className="font-body text-sm font-medium text-ink/60 hover:text-ink"
              >
                Choose a different file
              </button>
            </div>
          ) : (
            <CvFilePicker onFileSelected={pickCvFile} error={cvError} />
          )}
        </div>
      </WizardShell>
    );
  }

  if (macroStep === "submitting") {
    return (
      <AuthLayout title="Setting up your account" subtitle="This only takes a moment.">
        <ProgressState label={submitLabel} />
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Create your account" subtitle="Takes less than a minute.">
      <form onSubmit={submitAccount} className="flex flex-col gap-5" noValidate>
        <TextField
          label="Email address"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <TextField
          label="Password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <TextField
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          required
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          error={matchError ?? undefined}
        />
        {registerError && (
          <p role="alert" className="rounded-[10px] bg-signal-soft px-4 py-3 text-sm font-medium text-signal">
            {registerError}
          </p>
        )}
        <Button type="submit" className="mt-1 w-full">
          Create account
        </Button>
      </form>
      <p className="mt-6 text-center font-body text-sm text-ink/60">
        Already have an account?{" "}
        <Link to="/login" className="font-semibold text-phanda-green-dark hover:underline">
          Log in
        </Link>
      </p>
    </AuthLayout>
  );
}

function WizardShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-paper">
      <header className="flex items-center border-b border-hairline px-5 py-4 sm:px-8">
        <Link to="/">
          <Mark />
        </Link>
      </header>
      <main className="mx-auto max-w-md px-5 py-12 sm:px-8">{children}</main>
    </div>
  );
}
