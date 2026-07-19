import { Sparkles } from "lucide-react";
import { Badge, Button, Card, Input, StatusIndicator } from "../design-system";

/**
 * TEMPORARY, M8.1-ONLY preview page. Exists purely so the M8.1 Design
 * System Foundation milestone is reviewable visually rather than as raw
 * token/component code - it renders on its own dark canvas
 * (`bg-surface-0`) because that canvas is intentionally NOT applied
 * globally yet (see index.css's own comment: the global canvas flip is
 * scoped to M8.2, landing together with the restyled Sidebar/top strip).
 *
 * Remove this file and its route in App.tsx once M8.2+ has real pages
 * exercising these primitives inside actual navigation - it should never
 * become a permanent part of the product.
 */
export default function DesignSystemPreview() {
  return (
    <div className="min-h-screen bg-surface-0 p-10 text-slate-100">
      <h1 className="mb-1 text-2xl font-semibold">M8.1 — Design System Foundation preview</h1>
      <p className="mb-8 text-sm text-slate-400">Temporary review page — not part of the product.</p>

      <section className="mb-10">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">Buttons</h2>
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary">Primary action</Button>
          <Button variant="secondary">Secondary action</Button>
          <Button variant="ghost">Ghost action</Button>
          <Button variant="destructive">Destructive action</Button>
          <Button variant="primary" isLoading>
            Generating research
          </Button>
          <Button variant="primary" disabled>
            Disabled
          </Button>
        </div>
      </section>

      <section className="mb-10">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">Badges</h2>
        <div className="flex flex-wrap items-center gap-3">
          <Badge tone="neutral">Neutral</Badge>
          <Badge tone="primary">Primary</Badge>
          <Badge tone="ai">
            <Sparkles className="h-3 w-3" /> AI Recommendation
          </Badge>
          <Badge tone="success">Won</Badge>
          <Badge tone="warning">Medium impact</Badge>
          <Badge tone="danger">High impact</Badge>
          <Badge tone="info">In progress</Badge>
        </div>
      </section>

      <section className="mb-10">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">Status indicators</h2>
        <div className="flex flex-wrap items-center gap-6">
          <StatusIndicator kind="active" label="Researching" />
          <StatusIndicator kind="waiting" label="Waiting for buyer" />
          <StatusIndicator kind="success" label="Completed" />
          <StatusIndicator kind="failed" label="Failed" />
          <StatusIndicator kind="idle" label="Idle" />
          <StatusIndicator kind="paused" label="Paused (no backend support yet)" />
        </div>
      </section>

      <section className="mb-10">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">Inputs</h2>
        <div className="max-w-sm space-y-3">
          <Input placeholder="Search anything…" />
          <Input placeholder="Disabled" disabled />
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">Cards + elevation/glow</h2>
        <div className="grid max-w-3xl grid-cols-1 gap-4 sm:grid-cols-3">
          <Card>
            <p className="text-sm font-medium text-slate-100">Resting card</p>
            <p className="mt-1 text-xs text-slate-400">elevation-1, no glow</p>
          </Card>
          <Card elevated>
            <p className="text-sm font-medium text-slate-100">Elevated card</p>
            <p className="mt-1 text-xs text-slate-400">elevation-2, no glow</p>
          </Card>
          <Card elevated glow="ai">
            <p className="text-sm font-medium text-accent-ai-soft">AI-touched, live</p>
            <p className="mt-1 text-xs text-slate-400">glow reserved for live/active only</p>
          </Card>
        </div>
      </section>
    </div>
  );
}
