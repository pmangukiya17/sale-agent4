import { useAuth } from "../auth/AuthContext";
import { Card } from "../design-system";

/**
 * Settings — M8.7 Phase E3 (Settings zone). Migrated in place per Design
 * Bible Section 9.2: identical data (useAuth's user), only the markup
 * moves onto design-system tokens/primitives.
 */
export default function Settings() {
  const { user } = useAuth();

  return (
    <div>
      <h1 className="mb-1 text-h1 font-semibold text-slate-100">Settings</h1>
      <p className="mb-6 text-body text-slate-400">Account and workspace configuration.</p>

      <Card className="max-w-md">
        <dl className="space-y-3 text-sm">
          <div>
            <dt className="text-slate-500">Signed in as</dt>
            <dd className="font-medium text-slate-100">{user?.email}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Role</dt>
            <dd className="font-medium text-slate-100">{user?.role}</dd>
          </div>
        </dl>
        <p className="mt-6 text-xs text-slate-500">
          ICP rubric editing, Outlook connection, and team management arrive in later milestones.
        </p>
      </Card>
    </div>
  );
}
