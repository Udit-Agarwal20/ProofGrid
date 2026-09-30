"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, post, allPages } from "@/lib/api/client";
import { subscribeRun, type ConnectionState } from "@/lib/api/events";
import {
  terminalRuns,
  type Dataset,
  type RunData,
  type RunEvent,
  type Resource,
  type RunStatus,
  type Version,
} from "@/lib/api/types";
import { useResource } from "@/lib/hooks/use-resource";
import { dateTime, formatValue, humanize, shortId } from "@/lib/format";
import { ErrorNotice, Loading, Status, Icon } from "@/components/ui/primitives";
export function applyRunEvent(run: RunData, event: RunEvent): RunData {
  const data = event.data;
  const metrics =
    data.metrics &&
    typeof data.metrics === "object" &&
    !Array.isArray(data.metrics)
      ? data.metrics
      : {};
  const status =
    event.event.startsWith("run.") && typeof data.status === "string"
      ? (data.status as RunStatus)
      : run.status;
  const stepStatus =
    event.event === "step.started"
      ? "RUNNING"
      : event.event === "step.failed"
        ? "FAILED"
        : event.event === "step.retry_scheduled"
          ? "RETRY_WAIT"
          : typeof data.status === "string"
            ? data.status
            : undefined;
  return {
    ...run,
    status,
    metrics: { ...run.metrics, ...metrics },
    steps: run.steps.map((step) =>
      step.id === data.step_id
        ? {
            ...step,
            ...(stepStatus ? { status: stepStatus } : {}),
            ...(typeof data.attempt === "number"
              ? { attempt: data.attempt }
              : {}),
          }
        : step,
    ),
  };
}
export function RunMonitor({ id }: { id: string }) {
  const [run, setRun] = useState<RunData>();
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [error, setError] = useState<unknown>();
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState(false);
  const [dataset, setDataset] = useState<string>();
  const [lookupError, setLookupError] = useState<unknown>();
  useEffect(() => {
    const controller = new AbortController();
    let close: (() => void) | undefined;
    setError(undefined);
    api<Resource<RunData>>(`/v1/runs/${id}`, { signal: controller.signal })
      .then((response) => {
        if (controller.signal.aborted) return;
        setRun(response.data);
        if (terminalRuns.includes(response.data.status)) {
          setConnection("closed");
          return;
        }
        close = subscribeRun(
          id,
          (event) => {
            setEvents((previous) => [...previous, event].slice(-200));
            setRun((previous) =>
              previous ? applyRunEvent(previous, event) : previous,
            );
            if (
              event.event.startsWith("run.") &&
              terminalRuns.includes(event.data.status as RunStatus)
            ) {
              close?.();
              setConnection("closed");
              void api<Resource<RunData>>(`/v1/runs/${id}`, {
                signal: controller.signal,
              })
                .then((final) => setRun(final.data))
                .catch((e) => {
                  if (!controller.signal.aborted) setError(e);
                });
            }
          },
          setConnection,
          setError,
        );
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e);
      });
    return () => {
      controller.abort();
      close?.();
    };
  }, [id, attempt]);
  const versionId =
    typeof run?.metrics.dataset_version_id === "string"
      ? run.metrics.dataset_version_id
      : undefined;
  useEffect(() => {
    if (!versionId) return;
    const controller = new AbortController();
    setLookupError(undefined);
    if (typeof run?.metrics.dataset_id === "string") {
      setDataset(run.metrics.dataset_id);
      return;
    }
    // Fall back to resolving that association through paginated dataset/version APIs.
    void (async () => {
      const datasets = await allPages<Dataset>(
        "/v1/datasets",
        controller.signal,
      );
      for (const item of datasets) {
        const versions = await allPages<Version>(
          `/v1/datasets/${item.id}/versions`,
          controller.signal,
        );
        if (versions.some((version) => version.id === versionId)) {
          setDataset(item.id);
          return;
        }
      }
    })().catch((e) => {
      if (!controller.signal.aborted) setLookupError(e);
    });
    return () => controller.abort();
  }, [versionId, attempt]);
  async function cancel() {
    setBusy(true);
    try {
      const result = await post<Resource<RunData>>(`/v1/runs/${id}/cancel`);
      setRun(result.data);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (!run)
    return (
      <div className="page">
        {error ? (
          <ErrorNotice error={error} retry={() => setAttempt((v) => v + 1)} />
        ) : (
          <Loading label="Opening the persisted run…" />
        )}
      </div>
    );
  const finished = terminalRuns.includes(run.status);
  const completed = run.steps.filter((s) => s.status === "SUCCEEDED").length;
  return (
    <div className="page run-page">
      <div className="page-title">
        <div>
          <span className="eyebrow">04 / Execution ledger</span>
          <h1>
            {run.status === "COMPLETED"
              ? "The evidence is ready."
              : run.status === "PARTIAL"
                ? "Useful results. Visible gaps."
                : finished
                  ? "Run finished."
                  : "Following the evidence."}
          </h1>
          <p className="mono">
            Run {shortId(id)} · {dateTime(run.started_at)}
          </p>
        </div>
        <Status value={run.status} />
      </div>
      {!!error && (
        <ErrorNotice error={error} retry={() => setAttempt((v) => v + 1)} />
      )}
      <div className="run-mode">
        <span className="tag">
          {run.mode === "FIXTURE" ? "Fixture evidence" : "Live acquisition"}
        </span>
        <span>
          {String(
            run.metrics.fixture_label ||
              "Permitted public sources · backend policy enforced",
          )}
        </span>
      </div>
      {run.status === "PARTIAL" && (
        <div className="notice">
          Some collection or execution steps could not complete. Available
          records and their evidence remain inspectable below.
        </div>
      )}
      {run.status === "FAILED" && (
        <div className="notice error">
          The run failed. Inspect step errors and source diagnostics before
          starting another run.
        </div>
      )}
      <div className="run-layout">
        <section>
          <div className="section-heading">
            <h2>Execution stages</h2>
            <span className="mono">
              {completed}/{run.steps.length} complete
            </span>
          </div>
          <progress
            max={run.steps.length || 1}
            value={completed}
            aria-label="Completed workflow steps"
          />
          <ol className="run-steps">
            {run.steps.map((step, index) => (
              <li key={step.id}>
                <span className="step-count mono">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <strong>{humanize(step.operator)}</strong>
                  <small className="mono">
                    {step.node_id} · attempt {step.attempt}
                  </small>
                  {step.error_code && (
                    <span className="error-code mono">{step.error_code}</span>
                  )}
                </div>
                <Status value={step.status} />
              </li>
            ))}
          </ol>
          <div className="run-actions">
            {!finished && (
              <button
                className="button secondary"
                disabled={busy || run.status === "CANCEL_REQUESTED"}
                onClick={() => void cancel()}
              >
                {run.status === "CANCEL_REQUESTED"
                  ? "Cancellation requested"
                  : busy
                    ? "Requesting cancellation…"
                    : "Cancel run"}
              </button>
            )}
            {dataset && (
              <Link
                className="button primary"
                href={`/datasets/${dataset}?version=${versionId}`}
              >
                Open dataset
                <Icon name="arrow" />
              </Link>
            )}
            {versionId && !dataset && !lookupError && (
              <span className="muted" role="status">
                Locating the materialized dataset…
              </span>
            )}
            <Link href="/runs" className="text-button">
              All workflows
            </Link>
          </div>
          {!!lookupError && (
            <ErrorNotice
              error={lookupError}
              retry={() => setAttempt((v) => v + 1)}
            />
          )}
        </section>
        <aside className="run-inspector">
          <div className="section-heading">
            <h2>Run signals</h2>
            <span className="tag" role="status">
              {connection === "closed"
                ? "Final snapshot"
                : humanize(connection)}
            </span>
          </div>
          <dl className="metric-list">
            {Object.entries(run.metrics)
              .filter(
                ([key, value]) =>
                  ![
                    "fixture_label",
                    "fixture_set",
                    "acquisition_mode",
                    "dataset_version_id",
                    "source_errors",
                  ].includes(key) &&
                  ["string", "number", "boolean"].includes(typeof value),
              )
              .map(([key, value]) => (
                <div key={key}>
                  <dt>{humanize(key)}</dt>
                  <dd className="mono">{formatValue(value)}</dd>
                </div>
              ))}
          </dl>
          {!Object.keys(run.metrics).some(
            (key) => !key.startsWith("fixture") && key !== "acquisition_mode",
          ) && (
            <p className="muted">
              Counters appear as execution steps report results.
            </p>
          )}
          <p className="hint" aria-live="polite">
            {connection === "reconnecting"
              ? "Connection interrupted. Keeping the last known state and replaying missed events."
              : finished
                ? `Run ${humanize(run.status).toLowerCase()}.`
                : "Persisted events update this ledger as work completes."}
          </p>
          <details>
            <summary>Event ledger ({events.length} received)</summary>
            <ol className="event-list">
              {events.map((event) => (
                <li key={event.sequence}>
                  <span className="mono">
                    #{event.sequence} {event.event}
                  </span>
                  <small>
                    {String(event.data.node_id || event.data.status || "")}
                  </small>
                </li>
              ))}
            </ol>
            {!events.length && (
              <p className="muted">This run was loaded as a saved snapshot.</p>
            )}
          </details>
        </aside>
      </div>
      {Array.isArray(run.metrics.source_errors) &&
        run.metrics.source_errors.length > 0 && (
          <section className="ruled-section">
            <h2>Source diagnostics</h2>
            {run.metrics.source_errors.map((value, i) => (
              <div className="notice" key={i}>
                {formatValue(value)}
              </div>
            ))}
          </section>
        )}
    </div>
  );
}
export function RunHistory({ workflowId }: { workflowId: string }) {
  const { data, error, loading, reload } = useResource<
    import("@/lib/api/types").Page<import("@/lib/api/types").RunSummary>
  >(`/v1/workflows/${workflowId}/runs?limit=50`);
  return (
    <div className="run-history">
      {error ? (
        <ErrorNotice error={error} retry={reload} />
      ) : loading ? (
        <Loading label="Loading runs…" />
      ) : !data?.items.length ? (
        <p className="muted">
          No runs yet. Open the contract to preview and run this workflow.
        </p>
      ) : (
        data.items.map((run) => (
          <Link href={`/runs/${run.id}`} key={run.id} className="list-row">
            <span className="mono">{shortId(run.id)}</span>
            <span>{dateTime(run.created_at)}</span>
            <span className="tag">{run.mode}</span>
            <Status value={run.status} />
            <Icon name="arrow" />
          </Link>
        ))
      )}
    </div>
  );
}
