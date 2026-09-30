"use client";
import { useState } from "react";
import { post, downloadExport } from "@/lib/api/client";
import type { Resource, Version } from "@/lib/api/types";
import { ErrorNotice, Icon } from "@/components/ui/primitives";
export function ExportPanel({ version }: { version: Version }) {
  const [format, setFormat] = useState<"csv" | "json">("csv");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [message, setMessage] = useState("");
  async function exportBundle() {
    setBusy(true);
    setError(undefined);
    try {
      const result = await post<Resource<{ status: string }>>("/v1/exports", {
        dataset_version_id: version.id,
        format,
      });
      await downloadExport(result.id);
      setMessage(`Version ${version.version} evidence bundle downloaded.`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="export-panel">
      <span className="eyebrow">Take the evidence with you</span>
      <h2>Export version {version.version}</h2>
      <p>
        Download the complete snapshot with stable entity IDs, preserved claims,
        and a manifest that connects every file to this version.
      </p>
      <div className="export-files">
        <div>
          <Icon name="grid" />
          <strong>dataset.{format}</strong>
          <span>{version.record_count} records · full snapshot</span>
        </div>
        <div>
          <Icon name="proof" />
          <strong>evidence.json</strong>
          <span>Source claims, anchors, hashes & trust</span>
        </div>
        <div>
          <Icon name="history" />
          <strong>manifest.json</strong>
          <span>Dataset and version identifiers</span>
        </div>
      </div>
      <label>
        Dataset format
        <select
          value={format}
          onChange={(e) => setFormat(e.target.value as typeof format)}
        >
          <option value="csv">CSV</option>
          <option value="json">JSON</option>
        </select>
      </label>
      <p className="hint">
        Export includes all records in this version. Grid filters do not change
        the bundle.
      </p>
      <button
        className="button primary"
        disabled={busy}
        onClick={() => void exportBundle()}
      >
        <Icon name="download" />
        {busy ? "Preparing evidence bundle…" : "Download ZIP bundle"}
      </button>
      {!!error && <ErrorNotice error={error} />}
      <div role="status">
        {message && <div className="notice success">{message}</div>}
      </div>
    </section>
  );
}
