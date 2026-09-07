import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Landing } from "./pages/Landing";
import { SignupWizard } from "./features/onboarding/SignupWizard";
import { Login } from "./pages/Login";
import { Home } from "./pages/Home";
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
