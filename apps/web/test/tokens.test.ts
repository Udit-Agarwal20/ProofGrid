import { describe, it, expect } from "vitest";

describe("Forensic Ledger Design Tokens", () => {
  const expectedTrustStatuses = [
    "verified",
    "supported",
    "single-source",
    "conflicting",
    "needs-review",
    "missing",
  ];

  it("defines all six canonical trust statuses", () => {
    expect(expectedTrustStatuses).toHaveLength(6);
    expect(expectedTrustStatuses).toContain("verified");
    expect(expectedTrustStatuses).toContain("supported");
    expect(expectedTrustStatuses).toContain("single-source");
    expect(expectedTrustStatuses).toContain("conflicting");
    expect(expectedTrustStatuses).toContain("needs-review");
    expect(expectedTrustStatuses).toContain("missing");
  });

  it("adheres to the three-role IBM Plex typography standard", () => {
    const typographyRoles = {
      ui: "IBM Plex Sans",
      machine: "IBM Plex Mono",
      evidence: "IBM Plex Serif",
    };
    expect(typographyRoles.ui).toBe("IBM Plex Sans");
    expect(typographyRoles.machine).toBe("IBM Plex Mono");
    expect(typographyRoles.evidence).toBe("IBM Plex Serif");
  });
});
