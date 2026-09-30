import type { Json, TrustStatus } from "./api/types";
export const trustInfo: Record<
  TrustStatus,
  { label: string; symbol: string; description: string }
> = {
  VERIFIED: {
    label: "Verified",
    symbol: "✓",
    description: "Evidence meets the active verification policy.",
  },
  SUPPORTED: {
    label: "Supported",
    symbol: "≈",
    description: "Supporting evidence passes validation.",
  },
  SINGLE_SOURCE: {
    label: "Single source",
    symbol: "1",
    description: "One eligible independent source supports this value.",
  },
  CONFLICTING: {
    label: "Conflicting",
    symbol: "!",
    description: "Preserved claims materially disagree.",
  },
  NEEDS_REVIEW: {
    label: "Needs review",
    symbol: "?",
    description: "Evidence or identity needs human review.",
  },
  MISSING: {
    label: "Missing",
    symbol: "○",
    description: "No usable canonical value was found.",
  },
};
export function formatValue(value: Json | undefined): string {
  if (value === null || value === undefined) return "Not found";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value))
    return value.length ? value.map(formatValue).join(", ") : "None reported";
  if (typeof value === "object") {
    if ("amount" in value && "currency" in value) {
      // Group the decimal string without a lossy floating-point conversion or FX inference.
      const [whole, fraction] = String(value.amount).split(".");
      return `${value.currency} ${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}${fraction ? "." + fraction : ""}`;
    }
    if ("value" in value && "precision" in value)
      return `${formatValue(value.value)} (${value.precision})`;
    if ("name" in value) return formatValue(value.name);
    return Object.entries(value)
      .map(([k, v]) => `${humanize(k)}: ${formatValue(v)}`)
      .join(" · ");
  }
  return String(value);
}
export const humanize = (value: string) =>
  value
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/^./, (c) => c.toUpperCase());
export const shortId = (value: string) => value.slice(0, 8);
export function dateTime(value: string | null | undefined) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "UTC",
      }) + " UTC";
}
export function safeSourceUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) &&
      !url.username &&
      !url.password
      ? url.href
      : null;
  } catch {
    return null;
  }
}
export function sourceName(value: string) {
  const safe = safeSourceUrl(value);
  return safe
    ? new URL(safe).hostname.replace(/^www\./, "")
    : "Source URL unavailable";
}
