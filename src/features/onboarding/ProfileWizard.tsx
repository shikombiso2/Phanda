import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppHeader } from "../../components/AppHeader";
import { api } from "../../lib/api";
import { ApiError } from "../../lib/apiError";
import { useAuthStore } from "../../store/authStore";
import type { ProfileOut } from "../../types/api";
import { ProfileQuestionnaire } from "./ProfileQuestionnaire";
import { emptyProfileAnswers, profileAnswersFromProfile, profileAnswersToUpdate, type ProfileAnswers } from "./profileAnswers";

/** Authenticated edit flow: reachable from Home's "Complete profile" /
 * "Edit profile" action. Saves immediately via PUT /profile on finish, then
 * chains into the CV upload step -- unchanged from before this file was
 * split out into ProfileQuestionnaire (see that file for the field UI). */
export function ProfileWizard() {
  const navigate = useNavigate();
  const profile = useAuthStore((s) => s.profile);
  const setProfile = useAuthStore((s) => s.setProfile);

  // Seeded from the existing profile, not blank defaults: PUT /profile is a
  // full replace on the backend, so starting from blanks would silently
  // wipe whatever the user had already saved the moment they reopened this
  // to tweak one field. See profileAnswers.ts.
  const [answers, setAnswers] = useState<ProfileAnswers>(() =>
    profile ? profileAnswersFromProfile(profile) : emptyProfileAnswers,
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function finish() {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.put<ProfileOut>("/profile", profileAnswersToUpdate(answers));
      setProfile(updated);
      navigate("/onboarding/cv");
    } catch (err) {
      setError(err instanceof ApiError ? err.displayMessage : "Couldn't save your profile. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-screen bg-paper">
      <AppHeader />
      <main className="mx-auto max-w-md px-5 py-12 sm:px-8">
        <ProfileQuestionnaire
          values={answers}
          onChange={setAnswers}
          onFinish={finish}
          onSkip={() => navigate("/home", { replace: true })}
          saving={saving}
          error={error}
        />
      </main>
    </div>
  );
}
