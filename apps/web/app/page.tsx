export default function Page() {
  const trustStatuses = [
    { key: "verified", label: "Verified", symbol: "✓", color: "text-trust-verified" },
    { key: "supported", label: "Supported", symbol: "≈", color: "text-trust-supported" },
    { key: "single-source", label: "Single Source", symbol: "1", color: "text-trust-single-source" },
    { key: "conflicting", label: "Conflicting", symbol: "!", color: "text-trust-conflicting" },
    { key: "needs-review", label: "Needs Review", symbol: "?", color: "text-trust-needs-review" },
    { key: "missing", label: "Missing", symbol: "○", color: "text-trust-missing" },
  ];

  return (
    <div className="min-h-screen flex flex-col bg-canvas text-ink">
      {/* Minimal Top Context Bar */}
      <header className="h-14 border-b border-border bg-paper px-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-5 h-5 bg-ink text-paper flex items-center justify-center font-mono text-xs font-semibold rounded-sm">
            P
          </div>
          <span className="font-sans font-semibold tracking-tight text-base text-ink">
            ProofGrid
          </span>
          <span className="text-xs font-mono text-ink-muted px-2 py-0.5 border border-border rounded-sm bg-surface-muted">
            v0.1.0-foundation
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-trust-verified" />
          <span className="font-mono text-xs text-ink-muted uppercase tracking-wider">
            System Standby
          </span>
        </div>
      </header>

      {/* Main Forensic Ledger Canvas */}
      <main className="flex-1 p-8 max-w-4xl mx-auto w-full flex flex-col gap-8">
        <div>
          <h1 className="font-sans text-2xl font-semibold tracking-tight text-ink mb-2">
            Forensic Ledger Foundation
          </h1>
          <p className="font-sans text-sm text-ink-muted leading-relaxed">
            ProofGrid analytical workbench foundation is initialized. This minimal application shell
            verifies the typography hierarchy, Forensic Ledger design tokens, and trust status grammar.
          </p>
        </div>

        {/* Core Architecture Doctrine */}
        <section className="border border-border bg-surface rounded p-5">
          <div className="text-[11px] font-mono uppercase tracking-wider text-ink-muted mb-3">
            Core Architecture Doctrine
          </div>
          <p className="font-serif italic text-base text-ink leading-relaxed">
            &ldquo;LLM plans. Code executes. Evidence proves. PostgreSQL owns truth.&rdquo;
          </p>
        </section>

        {/* Token Verification: Typography Roles */}
        <section className="border border-border bg-surface rounded p-5 flex flex-col gap-4">
          <div className="text-[11px] font-mono uppercase tracking-wider text-ink-muted">
            Typography System
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
            <div className="p-3 border border-border bg-paper rounded-sm">
              <span className="text-[10px] font-mono text-copper uppercase block mb-1">
                IBM Plex Sans
              </span>
              <p className="font-sans text-sm text-ink font-medium">UI &amp; Brief Text</p>
              <p className="font-sans text-ink-muted mt-1">Interface controls and data navigation</p>
            </div>

            <div className="p-3 border border-border bg-paper rounded-sm">
              <span className="text-[10px] font-mono text-copper uppercase block mb-1">
                IBM Plex Mono
              </span>
              <p className="font-mono text-sm text-ink font-medium">0x4F7A9B &bull; 142ms</p>
              <p className="font-mono text-ink-muted mt-1">Hashes, IDs, and provenance values</p>
            </div>

            <div className="p-3 border border-border bg-paper rounded-sm">
              <span className="text-[10px] font-mono text-copper uppercase block mb-1">
                IBM Plex Serif
              </span>
              <p className="font-serif italic text-sm text-ink">Quoted source excerpt</p>
              <p className="font-serif text-ink-muted mt-1">Deterministic evidence anchor quotes</p>
            </div>
          </div>
        </section>

        {/* Token Verification: Trust Grammar */}
        <section className="border border-border bg-surface rounded p-5">
          <div className="text-[11px] font-mono uppercase tracking-wider text-ink-muted mb-3">
            Trust Status Grammar
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2">
            {trustStatuses.map((status) => (
              <div
                key={status.key}
                className="flex items-center gap-2 p-2 border border-border bg-paper rounded-sm"
              >
                <span className={`font-mono font-bold text-sm ${status.color}`}>
                  {status.symbol}
                </span>
                <span className="font-sans text-xs text-ink">{status.label}</span>
              </div>
            ))}
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="h-10 border-t border-border bg-paper px-6 flex items-center justify-between text-xs font-mono text-ink-muted">
        <span>ProofGrid &mdash; Phase 1 Foundation</span>
        <span>Ready for Phase 2 Persistence</span>
      </footer>
    </div>
  );
}
