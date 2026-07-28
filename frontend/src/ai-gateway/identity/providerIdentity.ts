import { Braces, Cpu, MessageSquare, Sparkles, Zap, type LucideIcon } from "lucide-react";
import type { AccentColor } from "../../design-system";
import type { ProviderKey, ProviderTier } from "../types";

/**
 * ProviderIdentity — the single source of truth mapping a provider key to
 * its label/icon/accent, so "Claude" (or any other provider) looks
 * identical everywhere it's referenced across this zone: `ProviderCard`,
 * `ProviderChip`, `ActivityDetailDrawer`, routing nodes, etc. Per the
 * approved AI Gateway UI architecture doc (Section 7.1): each accent is a
 * fixed, permanent identity for that provider, and none of them reuse
 * `violet`/`purple` - the design system already reserves that hue
 * exclusively for "the AI produced this content" (Badge's `ai` tone,
 * Card's `accent="violet"` on AI Workforce) and a provider identity must
 * never be confusable with that separate meaning.
 *
 * All six accent names used below (`emerald`, `teal`, `cyan`, `indigo`,
 * `gold`, `royal-blue`) already exist in `Card`'s `AccentColor` union - no
 * design-system change was needed to support this mapping.
 *
 * Icons are plain Lucide line-icons (the app's existing icon set), never
 * brand marks/logos - consistent with the rest of the app's icon
 * discipline and avoids any trademark/likeness concern.
 */
export interface ProviderIdentity {
  key: ProviderKey;
  label: string;
  tier: ProviderTier;
  accent: AccentColor;
  icon: LucideIcon;
  /** Plain hex for small inline elements (e.g. ProviderChip's leading
   * dot/icon) that can't use Card's `accent` prop directly. Mirrors the
   * exact same rgb triplet Card.tsx's own (unexported) ACCENT_RGB uses for
   * this accent name, so a chip's dot always matches that provider's
   * Card glow color exactly - Card.tsx only exports box-shadow-shaped
   * helpers (`ambientGlowStyle`/`activeGlowStyle`), not a plain color, so
   * this is restated here rather than computed from an import. */
  dotHex: string;
}

export const PROVIDER_IDENTITIES: Record<ProviderKey, ProviderIdentity> = {
  local_ollama: { key: "local_ollama", label: "Ollama", tier: "local", accent: "emerald", icon: Cpu, dotHex: "#10B981" },
  groq: { key: "groq", label: "Groq", tier: "free", accent: "teal", icon: Zap, dotHex: "#14B8A6" },
  gemini_ai_studio: {
    key: "gemini_ai_studio",
    label: "Gemini AI Studio",
    tier: "free",
    accent: "cyan",
    icon: Sparkles,
    dotHex: "#06B6D4",
  },
  gemini: { key: "gemini", label: "Gemini", tier: "premium", accent: "indigo", icon: Sparkles, dotHex: "#6366F1" },
  claude: { key: "claude", label: "Claude", tier: "premium", accent: "gold", icon: MessageSquare, dotHex: "#D4AF37" },
  openai: { key: "openai", label: "OpenAI", tier: "premium", accent: "royal-blue", icon: Braces, dotHex: "#2563EB" },
};

export function getProviderIdentity(key: ProviderKey): ProviderIdentity {
  return PROVIDER_IDENTITIES[key];
}
