import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthLayout } from "../components/AuthLayout";
import { TextField } from "../components/TextField";
import { Button } from "../components/Button";
import { useAuthStore } from "../store/authStore";

export function Register() {
  const navigate = useNavigate();
  const register = useAuthStore((s) => s.register);
  const error = useAuthStore((s) => s.error);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [matchError, setMatchError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (password !== confirmPassword) {
      setMatchError("Those passwords don't match.");
      return;
    }
    setMatchError(null);
    setLoading(true);
    try {
      await register(email, password);
      navigate("/home", { replace: true });
    } catch {
      // error is already in the store; nothing else to do here.
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout title="Create your account" subtitle="Takes less than a minute. No CV required yet.">
      <form onSubmit={onSubmit} className="flex flex-col gap-5" noValidate>
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
        {error && (
          <p role="alert" className="rounded-[10px] bg-signal-soft px-4 py-3 text-sm font-medium text-signal">
            {error}
          </p>
        )}
        <Button type="submit" loading={loading} className="mt-1 w-full">
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
