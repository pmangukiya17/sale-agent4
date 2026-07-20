import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Button, Input, Card } from "../design-system";

/**
 * Login — M8.7 Phase E4 (Auth shell). Restyled only, per the approved
 * implementation plan's reconciliation table: identical login() call and
 * redirect behavior, moved onto the dark design-system tokens/primitives
 * so the sign-in screen isn't the one light-mode page left in the app.
 */
export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) {
    return <Navigate to="/" replace />;
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/");
    } catch {
      setError("Incorrect email or password.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0">
      <Card elevated className="w-full max-w-sm">
        <form onSubmit={handleSubmit}>
          <h1 className="mb-1 text-xl font-semibold text-slate-100">Sales Agent</h1>
          <p className="mb-6 text-sm text-slate-400">Sign in to continue</p>

          <label className="mb-1 block text-sm font-medium text-slate-300">Email</label>
          <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="mb-4" />

          <label className="mb-1 block text-sm font-medium text-slate-300">Password</label>
          <Input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className="mb-4" />

          {error && <p className="mb-4 text-sm text-status-danger">{error}</p>}

          <Button type="submit" className="w-full" isLoading={submitting}>
            Sign in
          </Button>
        </form>
      </Card>
    </div>
  );
}
