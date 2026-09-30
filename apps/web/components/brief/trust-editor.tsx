"use client";
import type { TrustContract } from "@/lib/api/types";
const boolControls: {
  key: keyof TrustContract;
  title: string;
  detail: string;
  locked?: boolean;
}[] = [
  {
    key: "require_evidence_anchor",
    title: "Require verified evidence anchors",
    detail:
      "A source link alone is not enough. Claims must point to stored evidence.",
    locked: true,
  },
  {
    key: "prefer_first_party",
    title: "Prefer first-party sources",
    detail: "Give direct company and authoritative announcements priority.",
  },
  {
    key: "allow_secondary_sources",
    title: "Allow secondary sources",
    detail: "Use eligible independent reporting alongside direct sources.",
  },
  {
    key: "allow_single_source_output",
    title: "Allow single-source output",
    detail: "Retain useful values with an explicit Single source label.",
  },
  {
    key: "preserve_conflicts",
    title: "Preserve conflicting claims",
    detail: "Disagreement remains visible in the grid and review queue.",
    locked: true,
  },
  {
    key: "strict_required_fields",
    title: "Require every mandatory field",
    detail: "Exclude incomplete rows without deleting their evidence.",
  },
];
export function TrustEditor({
  value,
  onChange,
}: {
  value: TrustContract;
  onChange: (value: TrustContract) => void;
}) {
  return (
    <>
      <div className="section-heading">
        <div>
          <h2>What counts as trustworthy?</h2>
          <p className="muted">
            These explicit rules are stored with your workflow.
          </p>
        </div>
      </div>
      <div className="option-row">
        {["Balanced", "Strict", "Exploratory"].map((preset) => (
          <button
            type="button"
            className="button secondary"
            key={preset}
            onClick={() =>
              onChange({
                ...value,
                minimum_independent_sources: preset === "Strict" ? 2 : 1,
                allow_single_source_output: preset !== "Strict",
                strict_required_fields: preset === "Strict",
                prefer_first_party: true,
                allow_secondary_sources: true,
                require_evidence_anchor: true,
                preserve_conflicts: true,
              })
            }
          >
            {preset}
          </button>
        ))}
      </div>
      <div className="policy-rows">
        {boolControls.map((control) => (
          <label className="policy-row" key={control.key}>
            <div>
              <strong>
                {control.title}
                {control.locked && <span className="tag">Required</span>}
              </strong>
              <small>{control.detail}</small>
            </div>
            <input
              type="checkbox"
              checked={!!value[control.key]}
              disabled={control.locked}
              onChange={(e) =>
                onChange({ ...value, [control.key]: e.target.checked })
              }
            />
          </label>
        ))}
      </div>
      <div className="form-grid">
        <label>
          Minimum independent sources
          <input
            type="number"
            min={1}
            max={5}
            required
            value={value.minimum_independent_sources}
            onChange={(e) =>
              onChange({
                ...value,
                minimum_independent_sources: Number(e.target.value),
              })
            }
          />
        </label>
        <label>
          Maximum source age in days
          <input
            type="number"
            min={1}
            placeholder="No age limit"
            value={value.max_source_age_days ?? ""}
            onChange={(e) =>
              onChange({
                ...value,
                max_source_age_days: e.target.value
                  ? Number(e.target.value)
                  : null,
              })
            }
          />
          <small>Backend freshness uses retrieval or capture time.</small>
        </label>
      </div>
      <details className="ruled-section" open>
        <summary>Execution budgets</summary>
        <div className="form-grid three">
          {(
            [
              { key: "max_pages", label: "Pages", min: 1, max: 500 },
              {
                key: "max_search_queries",
                label: "Search queries",
                min: 1,
                max: 20,
              },
              { key: "max_llm_calls", label: "Model calls", min: 1, max: 500 },
              {
                key: "max_run_seconds",
                label: "Run time (seconds)",
                min: 10,
                max: 600,
              },
              {
                key: "max_estimated_cost_usd",
                label: "Estimated cost cap (USD)",
                min: 0,
                max: undefined,
              },
            ] as const
          ).map((item) => (
            <label key={item.key}>
              {item.label}
              <input
                type="number"
                required
                min={item.min}
                max={item.max}
                step={item.key === "max_estimated_cost_usd" ? "0.01" : "1"}
                value={value[item.key]}
                onChange={(e) =>
                  onChange({
                    ...value,
                    [item.key]:
                      item.key === "max_estimated_cost_usd"
                        ? e.target.value
                        : Number(e.target.value),
                  })
                }
              />
            </label>
          ))}
          <label>
            Browser page budget
            <input type="number" value={value.max_browser_pages} disabled />
            <small>
              Browser acquisition is not configured in this backend.
            </small>
          </label>
        </div>
      </details>
      <div className="notice">
        Conflicting values remain visible even after a display claim is chosen.
        Review decisions affect subsequent dataset versions.
      </div>
    </>
  );
}
