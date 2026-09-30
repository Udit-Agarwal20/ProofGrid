"use client";
import Link from "next/link";
import { useState } from "react";
import { allPages, post } from "@/lib/api/client";
import type { Dataset, Page, ReviewItem, Version } from "@/lib/api/types";
import { useResource } from "@/lib/hooks/use-resource";
import { formatValue, humanize, shortId } from "@/lib/format";
import {
  Empty,
  ErrorNotice,
  Loading,
  Pager,
  TrustBadge,
} from "@/components/ui/primitives";
import {
  ProofDrawer,
  type ProofSelection,
} from "@/components/proof/proof-drawer";
export function ReviewQueue() {
  const [offset, setOffset] = useState(0);
  const resource = useResource<Page<ReviewItem>>(
    `/v1/review?limit=20&offset=${offset}`,
  );
  const [selection, setSelection] = useState<ProofSelection>();
  const [busy, setBusy] = useState<string>();
  const [error, setError] = useState<unknown>();
  const [message, setMessage] = useState("");
  const [notes, setNotes] = useState<Record<string, string>>({});
  async function inspect(item: Extract<ReviewItem, { kind: "conflict" }>) {
    setBusy(item.id);
    setError(undefined);
    try {
      const datasets = await allPages<Dataset>("/v1/datasets");
      for (const dataset of datasets) {
        const versions = await allPages<Version>(
          `/v1/datasets/${dataset.id}/versions`,
        );
        if (versions.some((v) => v.id === item.dataset_version_id)) {
          setSelection({
            datasetId: dataset.id,
            versionId: item.dataset_version_id,
            entityId: item.entity_id,
            field: item.field_key,
          });
          return;
        }
      }
      throw new Error("Dataset version unavailable");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(undefined);
    }
  }
  async function decide(item: ReviewItem, decision: string) {
    setBusy(item.id);
    setError(undefined);
    try {
      await post(
        `/v1/review/${item.kind === "entity_match" ? "entity-match" : "conflict"}/${item.id}`,
        { decision, note: notes[item.id] || "" },
      );
      setMessage(
        decision === "DEFER"
          ? "Deferred. The item remains available for later review."
          : "Decision saved for subsequent dataset versions. Existing evidence is preserved.",
      );
      resource.reload();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(undefined);
    }
  }
  return (
    <div className="page">
      <div className="page-title">
        <div>
          <span className="eyebrow">Human judgment, visible provenance</span>
          <h1>Review queue</h1>
          <p>
            Resolve ambiguity while preserving the evidence behind every
            decision.
          </p>
        </div>
        <Link className="button secondary" href="/datasets">
          Back to datasets
        </Link>
      </div>
      <div className="notice">
        Display selections and entity decisions apply to subsequent dataset
        versions. Refresh after review; historical values and conflicting claims
        remain intact.
      </div>
      {!!error && <ErrorNotice error={error} />}
      <div role="status">
        {message && <div className="notice success">{message}</div>}
      </div>
      {resource.error ? (
        <ErrorNotice error={resource.error} retry={resource.reload} />
      ) : resource.loading ? (
        <Loading label="Loading conflicts and entity matches…" />
      ) : !resource.data?.items.length ? (
        <Empty title="Nothing is waiting for review.">
          New conflicts and ambiguous entity matches appear here after a
          workflow run.
        </Empty>
      ) : (
        <>
          {resource.data.items.map((item) => (
            <article className="review-item" key={item.id}>
              <div className="section-heading">
                <div>
                  <span className="eyebrow">
                    {item.kind === "conflict"
                      ? "Conflicting claims"
                      : "Entity match"}{" "}
                    / {shortId(item.id)}
                  </span>
                  <h2>
                    {item.kind === "conflict"
                      ? humanize(item.field_key)
                      : "Do these observations describe the same entity?"}
                  </h2>
                </div>
                <TrustBadge
                  status={
                    item.kind === "conflict" ? "CONFLICTING" : "NEEDS_REVIEW"
                  }
                />
              </div>
              {item.kind === "conflict" ? (
                <>
                  <p className="mono">
                    Entity {shortId(item.entity_id)} · snapshot{" "}
                    {shortId(item.dataset_version_id)}
                  </p>
                  <p>
                    Inspect all preserved claims before choosing a future
                    display value.
                  </p>
                  <div className="actions">
                    <button
                      className="button primary"
                      disabled={!!busy}
                      onClick={() => void inspect(item)}
                    >
                      {busy === item.id
                        ? "Locating evidence…"
                        : "Compare claims"}
                    </button>
                    <button
                      className="button secondary"
                      disabled={!!busy}
                      onClick={() => void decide(item, "DEFER")}
                    >
                      Defer
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div className="entity-comparison">
                    <div>
                      <span className="eyebrow">Observation A</span>
                      <strong className="mono break">{item.left}</strong>
                    </div>
                    <div>
                      <span className="eyebrow">Observation B</span>
                      <strong className="mono break">{item.right}</strong>
                    </div>
                  </div>
                  <h3>Matching signals</h3>
                  <dl className="claim-metadata">
                    {Object.entries(item.signals).map(([key, value]) => (
                      <div key={key}>
                        <dt>{humanize(key)}</dt>
                        <dd>{formatValue(value)}</dd>
                      </div>
                    ))}
                  </dl>
                  <details>
                    <summary>Decision rationale</summary>
                    <pre>{JSON.stringify(item.reason, null, 2)}</pre>
                  </details>
                  <label>
                    Review note
                    <textarea
                      rows={2}
                      maxLength={1000}
                      value={notes[item.id] || ""}
                      onChange={(e) =>
                        setNotes((n) => ({ ...n, [item.id]: e.target.value }))
                      }
                    />
                  </label>
                  <div className="actions">
                    <button
                      className="button primary"
                      disabled={!!busy}
                      onClick={() => void decide(item, "HUMAN_MERGE")}
                    >
                      Merge in next version
                    </button>
                    <button
                      className="button secondary"
                      disabled={!!busy}
                      onClick={() => void decide(item, "HUMAN_SEPARATE")}
                    >
                      Keep separate
                    </button>
                    <button
                      className="text-button"
                      disabled={!!busy}
                      onClick={() => void decide(item, "DEFER")}
                    >
                      Defer
                    </button>
                  </div>
                </>
              )}
            </article>
          ))}
          <Pager
            offset={offset}
            limit={20}
            total={resource.data.total}
            onChange={setOffset}
          />
        </>
      )}
      {selection && (
        <ProofDrawer
          selection={selection}
          onClose={() => setSelection(undefined)}
          onReviewed={resource.reload}
        />
      )}
    </div>
  );
}
