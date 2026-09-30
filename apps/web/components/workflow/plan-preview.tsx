"use client";
import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { post } from "@/lib/api/client";
import type { Resource, PlanData, PlanNode } from "@/lib/api/types";
import { humanize } from "@/lib/format";
import { ErrorNotice, Icon } from "@/components/ui/primitives";
export function graphLevels(nodes: PlanNode[]): PlanNode[][] {
  const remaining = new Map(nodes.map((n) => [n.id, n]));
  const seen = new Set<string>(),
    levels: PlanNode[][] = [];
  while (remaining.size) {
    const level = [...remaining.values()].filter((n) =>
      n.depends_on.every((id) => seen.has(id)),
    );
    if (!level.length) break;
    levels.push(level);
    for (const node of level) {
      seen.add(node.id);
      remaining.delete(node.id);
    }
  }
  return levels;
}
export function PlanPreview({
  plan,
  title,
  onEdit,
}: {
  plan: Resource<PlanData>;
  title: string;
  onEdit?: () => void;
}) {
  const router = useRouter();
  const key = useRef<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [selected, setSelected] = useState<PlanNode>();
  async function run() {
    setBusy(true);
    setError(undefined);
    key.current ||= crypto.randomUUID();
    try {
      const result = await post<Resource<{ status: string }>>(
        `/v1/workflows/${plan.id}/runs`,
        {
          workflow_version_id: plan.data.workflow_version_id,
          idempotency_key: key.current,
        },
      );
      router.push(`/runs/${result.id}`);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  }
  const levels = graphLevels(plan.data.plan.nodes);
  const graphHeight = Math.max(...levels.map((level) => level.length), 1) * 140;
  const positions = new Map(
    levels.flatMap((level, x) =>
      level.map(
        (node, y) =>
          [
            node.id,
            { x: x * 240, y: (graphHeight - level.length * 140) / 2 + y * 140 },
          ] as const,
      ),
    ),
  );

  return (
    <section className="plan-preview">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Workflow revision {plan.data.version}</span>
          <h2>{title}</h2>
        </div>
        <span className="status status-completed">✓ Validated plan</span>
      </div>
      <div className="plan-budget">
        <span>
          <strong>{plan.data.plan.nodes.length}</strong> bounded steps
        </span>
        <span>
          <strong>{plan.data.plan.expected_pages}</strong> expected pages
        </span>
        <span>
          <strong>{plan.data.plan.expected_llm_calls}</strong> expected model
          calls
        </span>
        <span>
          <strong>{plan.data.plan.expected_browser_pages}</strong> browser pages
        </span>
      </div>
      <div className="stage-rail">
        {levels.flat().map((node, i) => (
          <div key={node.id}>
            <span className="stage-index mono">
              {String(i + 1).padStart(2, "0")}
            </span>
            <strong>{humanize(node.operator)}</strong>
            <small>
              {node.critical ? "Required" : "Optional"} ·{" "}
              {node.constraints.timeout_seconds}s limit
            </small>
          </div>
        ))}
      </div>
      <div className="notice success">
        The backend validated this plan against the confirmed schema, trust
        policy, and execution budgets.
      </div>
      <details className="dag-details">
        <summary>Inspect the dependency graph</summary>
        <div className="dag-scroll">
          <div
            className="dag actual-dag"
            style={{ width: levels.length * 240 - 40, height: graphHeight }}
            aria-label="Workflow dependency graph"
          >
            <svg
              className="dag-edges"
              width="100%"
              height="100%"
              aria-hidden="true"
            >
              <defs>
                <marker
                  id="arrow"
                  markerWidth="7"
                  markerHeight="7"
                  refX="6"
                  refY="3"
                  orient="auto"
                >
                  <path d="M0,0 L0,6 L6,3 z" fill="currentColor" />
                </marker>
              </defs>
              {plan.data.plan.nodes.flatMap((node) =>
                node.depends_on.map((id) => {
                  const from = positions.get(id),
                    to = positions.get(node.id);
                  if (!from || !to) return null;
                  return (
                    <path
                      key={`${id}:${node.id}`}
                      d={`M${from.x + 195},${from.y + 50} C${from.x + 218},${from.y + 50} ${to.x - 22},${to.y + 50} ${to.x - 4},${to.y + 50}`}
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.4"
                      markerEnd="url(#arrow)"
                    />
                  );
                }),
              )}
            </svg>
            {levels.flat().map((node) => (
              <button
                type="button"
                key={node.id}
                style={{
                  left: positions.get(node.id)!.x,
                  top: positions.get(node.id)!.y,
                }}
                className={`dag-node ${selected?.id === node.id ? "selected" : ""}`}
                onClick={() => setSelected(node)}
              >
                <span className="eyebrow">{node.id}</span>
                <strong>{humanize(node.operator)}</strong>
                <small>
                  {node.depends_on.length
                    ? `From: ${node.depends_on.join(", ")}`
                    : "Entry point"}
                </small>
              </button>
            ))}
          </div>
        </div>
        <ol className="dag-mobile">
          {levels.flat().map((node) => (
            <li key={node.id}>
              <button className="text-button" onClick={() => setSelected(node)}>
                {humanize(node.operator)}
              </button>
              <small>Depends on: {node.depends_on.join(", ") || "None"}</small>
            </li>
          ))}
        </ol>
        {selected && (
          <div className="node-detail">
            <h3>{humanize(selected.operator)}</h3>
            <p>
              {selected.constraints.max_retries} retries ·{" "}
              {selected.constraints.timeout_seconds}s timeout ·{" "}
              {selected.critical ? "Critical step" : "Optional step"}
            </p>
            <pre>{JSON.stringify(selected.params, null, 2)}</pre>
          </div>
        )}
      </details>
      {plan.data.plan.rationale.length > 0 && (
        <div className="plan-rationale">
          <h3>Plan rationale</h3>
          <ul>
            {plan.data.plan.rationale.map((reason, i) => (
              <li key={i}>{reason}</li>
            ))}
          </ul>
        </div>
      )}
      {!!error && <ErrorNotice error={error} />}
      <div className="form-actions">
        {onEdit && (
          <button className="button secondary" onClick={onEdit} disabled={busy}>
            Edit contract
          </button>
        )}
        <button
          className="button primary"
          disabled={busy}
          onClick={() => void run()}
        >
          {busy ? "Starting run…" : "Run workflow"}
          <Icon name="runs" />
        </button>
      </div>
    </section>
  );
}
