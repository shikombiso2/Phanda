import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Landing } from "./pages/Landing";
import { SignupWizard } from "./features/onboarding/SignupWizard";
import { Login } from "./pages/Login";
import { Home } from "./pages/Home";
import { ProfileView } from "./pages/ProfileView";
import { Find } from "./pages/Find";
import { ListingDetail } from "./pages/ListingDetail";
import { Saved } from "./pages/Saved";
import { Track } from "./pages/Track";
import { SkillGapDetail } from "./pages/SkillGapDetail";
import { ProfileWizard } from "./features/onboarding/ProfileWizard";
import { CvUpload } from "./features/onboarding/CvUpload";
import { RequireAuth } from "./components/RequireAuth";
import { useAuthStore } from "./store/authStore";

export default function App() {
  const bootstrap = useAuthStore((s) => s.bootstrap);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/register" element={<SignupWizard />} />
        <Route path="/login" element={<Login />} />
        <Route
          path="/home"
          element={
            <RequireAuth>
              <Home />
            </RequireAuth>
          }
        />
        <Route
          path="/find"
          element={
            <RequireAuth>
              <Find />
            </RequireAuth>
          }
        />
        <Route
          path="/listings/:id"
          element={
            <RequireAuth>
              <ListingDetail />
            </RequireAuth>
          }
        />
        <Route
          path="/saved"
          element={
            <RequireAuth>
              <Saved />
            </RequireAuth>
          }
        />
        <Route
          path="/track"
          element={
            <RequireAuth>
              <Track />
            </RequireAuth>
          }
        />
        <Route
          path="/skill-gap"
          element={
            <RequireAuth>
              <SkillGapDetail />
            </RequireAuth>
          }
        />
        <Route
          path="/profile"
          element={
            <RequireAuth>
              <ProfileView />
            </RequireAuth>
          }
        />
        <Route
          path="/onboarding/profile"
          element={
            <RequireAuth>
              <ProfileWizard />
            </RequireAuth>
          }
        />
        <Route
          path="/onboarding/cv"
          element={
            <RequireAuth>
              <CvUpload />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
