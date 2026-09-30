"use client";
import { useState } from "react";
import type { Claim, Proof } from "@/lib/api/types";
import { post } from "@/lib/api/client";
import { useResource } from "@/lib/hooks/use-resource";
import {
  dateTime,
  formatValue,
  humanize,
  safeSourceUrl,
  sourceName,
} from "@/lib/format";
import {
  ErrorNotice,
  Loading,
  Modal,
  TrustBadge,
} from "@/components/ui/primitives";
export type ProofSelection = {
  datasetId: string;
  versionId: string;
  entityId: string;
  field: string;
  label?: string;
  entityName?: string;
};
export function ProofDrawer({
  selection,
  onClose,
  onReviewed,
}: {
  selection: ProofSelection;
  onClose: () => void;
  onReviewed?: () => void;
}) {
  const path = `/v1/datasets/${selection.datasetId}/versions/${selection.versionId}/records/${selection.entityId}/proof/${encodeURIComponent(selection.field)}`;
  const resource = useResource<Proof>(path);
  return (
    <Modal
      drawer
      title={selection.label || humanize(selection.field)}
      onClose={onClose}
    >
      <p className="proof-context">
        {selection.entityName || selection.entityId}
        <span className="mono">Version {selection.versionId.slice(0, 8)}</span>
      </p>
      {resource.error ? (
        <ErrorNotice error={resource.error} retry={resource.reload} />
      ) : !resource.data || resource.loading ? (
        <Loading label="Retrieving the claims behind this value…" />
      ) : (
        <ProofContent
          proof={resource.data}
          onReviewed={() => {
            resource.reload();
            onReviewed?.();
          }}
        />
      )}
    </Modal>
  );
}
export function ClaimView({
  claim,
  selected = false,
}: {
  claim: Claim;
  selected?: boolean;
}) {
  const source = safeSourceUrl(claim.source_url);
  return (
    <article className="claim">
      <div className="section-heading">
        <span className="eyebrow">{sourceName(claim.source_url)}</span>
        {selected && <span className="tag">Display claim</span>}
      </div>
      <strong className="claim-value">
        {formatValue(claim.normalized_value)}
      </strong>
      {claim.evidence.quote ? (
        <blockquote>{claim.evidence.quote}</blockquote>
      ) : (
        <div className="structured-evidence">
          <span className="eyebrow">Structured evidence</span>
          <code>{formatValue(claim.raw_value)}</code>
        </div>
      )}
      <div className="evidence-status">
        <span className="tag">
          {humanize(claim.evidence.verification_status)}
        </span>
        <span className="mono">{claim.evidence.type}</span>
      </div>
      {claim.acquisition.synthetic === true && (
        <div className="notice compact">
          Synthetic showcase evidence · not live business facts
        </div>
      )}
      {claim.acquisition.fixture_label && (
        <p className="hint">{String(claim.acquisition.fixture_label)}</p>
      )}
      <dl className="claim-metadata">
        <dt>Raw value</dt>
        <dd>{formatValue(claim.raw_value)}</dd>
        <dt>Normalized value</dt>
        <dd>{formatValue(claim.normalized_value)}</dd>
        <dt>Retrieved</dt>
        <dd className="mono">{dateTime(claim.retrieved_at)}</dd>
        <dt>Extraction</dt>
        <dd className="mono">{claim.extraction_method}</dd>
        <dt>Source class</dt>
        <dd>
          {claim.acquisition.first_party === true
            ? "First party"
            : claim.acquisition.first_party === false
              ? "Secondary source"
              : "Not recorded"}
        </dd>
      </dl>
      {source ? (
        <a
          className="source-link"
          href={source}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open source ↗<span className="mono">{source}</span>
        </a>
      ) : (
        <p className="muted">This source URL cannot be opened safely.</p>
      )}
      <details>
        <summary>Anchor, document & transformation details</summary>
        <dl className="claim-metadata">
          <dt>Claim ID</dt>
          <dd className="mono break">{claim.id}</dd>
          <dt>Document ID</dt>
          <dd className="mono break">{claim.raw_document_id}</dd>
          <dt>Content hash</dt>
          <dd className="mono break">{claim.content_hash}</dd>
          <dt>Source ID</dt>
          <dd className="mono break">{claim.source_id}</dd>
        </dl>
        <pre>{JSON.stringify(claim.evidence.locator, null, 2)}</pre>
        <p className="hint">
          Raw → normalized values above record the exposed transformation. No
          additional transformation log is supplied by this API.
        </p>
        <p>
          Validation flags:{" "}
          {claim.validation_flags.length
            ? claim.validation_flags.map(humanize).join(", ")
            : "None reported"}
        </p>
      </details>
    </article>
  );
}
export function ProofContent({
  proof,
  onReviewed,
}: {
  proof: Proof;
  onReviewed: () => void;
}) {
  const [selected, setSelected] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [message, setMessage] = useState("");
  async function review(decision: "SELECT_DISPLAY" | "DEFER") {
    if (!proof.conflict) return;
    setBusy(true);
    setError(undefined);
    try {
      await post(`/v1/review/conflict/${proof.conflict.id}`, {
        decision,
        ...(decision === "SELECT_DISPLAY"
          ? { selected_claim_id: selected }
          : {}),
        note,
      });
      setMessage(
        decision === "DEFER"
          ? "Deferred. This item remains in the review queue."
          : "Display preference saved for subsequent dataset versions. Refresh to apply it; historical evidence and disagreement remain.",
      );
      onReviewed();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function copyCitation() {
    try {
      await navigator.clipboard.writeText(
        [
          `ProofGrid: ${proof.field_key} = ${formatValue(proof.canonical_value)}`,
          `Dataset version: ${proof.dataset_version_id}`,
          `Trust: ${proof.trust_status}`,
          ...proof.claims.map(
            (c) =>
              `${c.source_url} (retrieved ${c.retrieved_at}; SHA-256 ${c.content_hash})`,
          ),
        ].join("\n"),
      );
      setMessage("Citation copied.");
    } catch {
      setMessage(
        "Clipboard unavailable. Select and copy the source metadata below.",
      );
    }
  }
  const conflicts = Array.isArray(proof.resolution.conflicting_claim_ids)
    ? proof.resolution.conflicting_claim_ids
    : [];
  return (
    <>
      <section className="canonical">
        <span className="eyebrow">Canonical display value</span>
        <h3>{formatValue(proof.canonical_value)}</h3>
        <TrustBadge status={proof.trust_status} />
        <p>
          {typeof proof.resolution.reason === "string"
            ? humanize(proof.resolution.reason)
            : "Inspect the claims and resolution details below."}
        </p>
        {typeof proof.resolution.independent_sources === "number" && (
          <span className="mono">
            {proof.resolution.independent_sources} independent source clusters
          </span>
        )}
        <button className="text-button" onClick={() => void copyCitation()}>
          Copy citation
        </button>
      </section>
      {proof.trust_status === "CONFLICTING" && (
        <div className="notice">
          <strong>These sources disagree.</strong>
          <p>
            The display value does not settle the conflict. All competing claims
            are retained.
          </p>
        </div>
      )}
      <div className="section-heading">
        <h3>Claim ledger</h3>
        <span className="mono">{proof.claims.length} preserved</span>
      </div>
      {proof.claims.length ? (
        proof.claims.map((claim) => (
          <div key={claim.id}>
            {conflicts.includes(claim.id) && (
              <span className="tag conflict-tag">Competing claim</span>
            )}
            <ClaimView
              claim={claim}
              selected={proof.resolution.selected_claim_id === claim.id}
            />
          </div>
        ))
      ) : (
        <div className="notice">
          No usable claim was found. Missing values are never filled with a
          guessed fact.
        </div>
      )}
      <details className="ruled-section">
        <summary>Canonical resolution details</summary>
        <pre>{JSON.stringify(proof.resolution, null, 2)}</pre>
      </details>
      {proof.conflict && (
        <section className="review-form">
          <h3>Display preference</h3>
          <p>
            This version stays immutable. A selection applies to subsequent
            dataset versions and preserves the Conflicting state.
          </p>
          {proof.conflict.status === "RESOLVED" ? (
            <div className="notice success">
              Reviewed · selected claim {proof.conflict.selected_claim_id}
            </div>
          ) : (
            <>
              <label>
                Choose a preserved claim
                <select
                  value={selected}
                  onChange={(e) => setSelected(e.target.value)}
                >
                  <option value="">Select a claim…</option>
                  {proof.claims
                    .filter(
                      (c) =>
                        Array.isArray(proof.conflict?.details.claim_ids) &&
                        proof.conflict.details.claim_ids.includes(c.id),
                    )
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {formatValue(c.normalized_value)} ·{" "}
                        {sourceName(c.source_url)}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Review note
                <textarea
                  maxLength={1000}
                  rows={2}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
              </label>
              <div className="actions">
                <button
                  className="button primary"
                  disabled={!selected || busy}
                  onClick={() => void review("SELECT_DISPLAY")}
                >
                  {busy ? "Saving…" : "Save display preference"}
                </button>
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={() => void review("DEFER")}
                >
                  Defer
                </button>
              </div>
            </>
          )}
          {!!error && <ErrorNotice error={error} />}
        </section>
      )}
      <div role="status">
        {message && <div className="notice success">{message}</div>}
      </div>
    </>
  );
}
