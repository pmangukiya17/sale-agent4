import { useAuth } from "../auth/AuthContext";

export default function Settings() {
  const { user } = useAuth();

  return (
    <div>
      <h2 className="mb-1 text-2xl font-semibold text-slate-900">Settings</h2>
      <p className="mb-6 text-sm text-slate-500">Account and workspace configuration.</p>

      <div className="max-w-md rounded-lg border border-slate-200 bg-white p-6">
        <dl className="space-y-3 text-sm">
          <div>
            <dt className="text-slate-500">Signed in as</dt>
            <dd className="font-medium text-slate-900">{user?.email}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Role</dt>
            <dd className="font-medium text-slate-900">{user?.role}</dd>
          </div>
        </dl>
        <p className="mt-6 text-xs text-slate-400">
          ICP rubric editing, Outlook connection, and team management arrive in
          later milestones.
        </p>
      </div>
    </div>
  );
}
