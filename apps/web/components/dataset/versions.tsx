"use client";
import Link from "next/link";
import { useState } from "react";
import type { Diff, Page, Version, Field } from "@/lib/api/types";
import { useResource } from "@/lib/hooks/use-resource";
import { dateTime, formatValue, humanize } from "@/lib/format";
import {
  Empty,
  ErrorNotice,
  Loading,
  Pager,
  TrustBadge,
} from "@/components/ui/primitives";
import type { ProofSelection } from "@/components/proof/proof-drawer";
export function Versions({
  datasetId,
  versions,
  fields,
  onOpen,
  onProof,
}: {
  datasetId: string;
  versions: Version[];
  fields: Field[];
  onOpen: (id: string) => void;
  onProof: (selection: ProofSelection) => void;
}) {
  const [before, setBefore] = useState(versions[1]?.id || "");
  const [after, setAfter] = useState(versions[0]?.id || "");
  const [offset, setOffset] = useState(0);
  const diff = useResource<Page<Diff>>(
    before && after && before !== after
      ? `/v1/datasets/${datasetId}/diff?before=${before}&after=${after}&limit=20&offset=${offset}`
      : null,
  );
  return (
    <section>
      <div className="section-heading">
        <div>
          <h2>Version history</h2>
          <p className="muted">
            Immutable snapshots. A missing record means it was not found in that
            run.
          </p>
        </div>
      </div>
      <div className="version-timeline">
        {versions.map((version) => (
          <article key={version.id}>
            <span className="version-dot" />
            <div>
              <button
                className="text-button"
                onClick={() => onOpen(version.id)}
              >
                Version {version.version}
              </button>
              <span className="mono">{dateTime(version.created_at)}</span>
            </div>
            <span>{version.record_count} records</span>
            <Link
              href={`/runs/${version.workflow_run_id}`}
              className="text-button"
            >
              Inspect run ↗
            </Link>
          </article>
        ))}
      </div>
      {versions.length < 2 ? (
        <Empty title="One snapshot, a clear starting point.">
          Refresh the workflow to create another version and compare what
          changed.
        </Empty>
      ) : (
        <>
          <div className="diff-controls">
            <label>
              Before
              <select
                value={before}
                onChange={(e) => {
                  setBefore(e.target.value);
                  setOffset(0);
                }}
              >
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    Version {v.version}
                  </option>
                ))}
              </select>
            </label>
            <span aria-hidden="true">→</span>
            <label>
              After
              <select
                value={after}
                onChange={(e) => {
                  setAfter(e.target.value);
                  setOffset(0);
                }}
              >
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    Version {v.version}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {before === after ? (
            <div className="notice">
              Choose two different snapshots to compare.
            </div>
          ) : diff.error ? (
            <ErrorNotice error={diff.error} retry={diff.reload} />
          ) : diff.loading ? (
            <Loading label="Comparing values, trust, conflicts, and evidence…" />
          ) : (
            diff.data && (
              <>
                <div className="diff-summary">
                  <span className="eyebrow">This page</span>
                  {["ADDED", "CHANGED", "MISSING_LATEST", "UNCHANGED"].map(
                    (state) => (
                      <span key={state}>
                        {humanize(state)}{" "}
                        <strong>
                          {
                            diff.data!.items.filter(
                              (row) => row.state === state,
                            ).length
                          }
                        </strong>
                      </span>
                    ),
                  )}
                </div>
                {!diff.data.items.length && (
                  <Empty title="No records to compare.">
                    Both snapshots are empty.
                  </Empty>
                )}
                {diff.data.items.map((row) => (
                  <article className="diff-row" key={row.entity_id}>
                    <div className="section-heading">
                      <h3>
                        {formatValue(
                          (row.after || row.before)?.values[fields[0]?.key],
                        )}
                      </h3>
                      <span className={`tag diff-${row.state.toLowerCase()}`}>
                        {humanize(row.state)}
                      </span>
                    </div>
                    {row.state === "UNCHANGED" && (
                      <p className="muted">
                        Values, trust, and evidence fingerprints are unchanged.
                      </p>
                    )}
                    {row.state === "MISSING_LATEST" && (
                      <p className="muted">
                        Not rediscovered in the later run. This does not imply
                        the entity no longer exists.
                      </p>
                    )}
                    {(row.fields.length
                      ? row.fields.map((f) => f.field)
                      : row.state === "UNCHANGED"
                        ? []
                        : Object.keys((row.after || row.before)?.values || {})
                    ).map((key) => (
                      <div className="diff-field" key={key}>
                        <span>
                          {fields.find((f) => f.key === key)?.label ||
                            humanize(key)}
                          <small>
                            {row.fields
                              .find((f) => f.field === key)
                              ?.changes.map(humanize)
                              .join(" · ")}
                          </small>
                        </span>
                        {(["before", "after"] as const).map((side) => (
                          <div key={side}>
                            {row[side] ? (
                              <button
                                className="diff-value"
                                onClick={() =>
                                  onProof({
                                    datasetId,
                                    versionId:
                                      side === "before" ? before : after,
                                    entityId: row.entity_id,
                                    field: key,
                                  })
                                }
                              >
                                <span>
                                  {formatValue(row[side]!.values[key])}
                                </span>
                                <TrustBadge
                                  compact
                                  status={row[side]!.trust[key] || "MISSING"}
                                />
                              </button>
                            ) : (
                              <span className="muted">Not in snapshot</span>
                            )}
                          </div>
                        ))}
                      </div>
                    ))}
                  </article>
                ))}
                <Pager
                  offset={offset}
                  limit={20}
                  total={diff.data.total}
                  onChange={setOffset}
                />
              </>
            )
          )}
        </>
      )}
    </section>
  );
}
