import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthLayout } from "../components/AuthLayout";
import { TextField } from "../components/TextField";
import { Button } from "../components/Button";
import { useAuthStore } from "../store/authStore";

export function Login() {
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);
  const error = useAuthStore((s) => s.error);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    try {
      await login(email, password);
      navigate("/home", { replace: true });
    } catch {
      // error is already in the store
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout title="Welcome back" subtitle="Log in to see your matches and pick up where you left off.">
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
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && (
          <p role="alert" className="rounded-[10px] bg-signal-soft px-4 py-3 text-sm font-medium text-signal">
            {error}
          </p>
        )}
        <Button type="submit" loading={loading} className="mt-1 w-full">
          Log in
        </Button>
      </form>
      <p className="mt-6 text-center font-body text-sm text-ink/60">
        New to Phanda?{" "}
        <Link to="/register" className="font-semibold text-phanda-green-dark hover:underline">
          Create an account
        </Link>
      </p>
    </AuthLayout>
  );
}
