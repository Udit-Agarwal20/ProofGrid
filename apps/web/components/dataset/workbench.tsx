"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { allPages, recordsQuery } from "@/lib/api/client";
import type {
  DatasetData,
  Field,
  Page,
  RecordRow,
  Resource,
  Version,
  VersionData,
  Workflow,
} from "@/lib/api/types";
import { useDebounce, useResource } from "@/lib/hooks/use-resource";
import { dateTime, formatValue } from "@/lib/format";
import {
  Empty,
  ErrorNotice,
  Icon,
  Loading,
  Pager,
} from "@/components/ui/primitives";
import {
  ProofDrawer,
  type ProofSelection,
} from "@/components/proof/proof-drawer";
import { DataGrid, GridToolbar, type GridControls } from "./grid";
import { Versions } from "./versions";
import { ExportPanel } from "./export-panel";
export function DatasetWorkbench({ id }: { id: string }) {
  const router = useRouter(),
    params = useSearchParams();
  const versionParam = params.get("version");
  const tab = params.get("tab") || "grid";
  const dataset = useResource<Resource<DatasetData>>(`/v1/datasets/${id}`);
  const [versions, setVersions] = useState<Version[]>();
  const [versionError, setVersionError] = useState<unknown>();
  const [versionAttempt, setVersionAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setVersionError(undefined);
    allPages<Version>(`/v1/datasets/${id}/versions`, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setVersions(result);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setVersionError(e);
      });
    return () => controller.abort();
  }, [id, versionAttempt]);
  const versionId = versionParam || versions?.[0]?.id;
  const version = useResource<Resource<VersionData>>(
    versionId ? `/v1/datasets/${id}/versions/${versionId}` : null,
  );
  const [controls, setControls] = useState<GridControls>({
    search: "",
    sort: "",
    trust: "",
    trustField: "",
    field: "",
    operator: "eq",
    value: "",
  });
  const [offset, setOffset] = useState(0);
  const debounced = useDebounce(controls);
  const [selection, setSelection] = useState<ProofSelection>();
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<unknown>();
  const filters = [
    ...(debounced.trust && debounced.trustField
      ? [`trust.${debounced.trustField}.eq:${debounced.trust}`]
      : []),
    ...(debounced.field && debounced.value
      ? [`${debounced.field}.${debounced.operator}:${debounced.value}`]
      : []),
  ];
  const query = recordsQuery({
    offset,
    limit: 25,
    sort: debounced.sort,
    search: debounced.search,
    filters,
  });
  const records = useResource<Page<RecordRow>>(
    versionId && tab === "grid"
      ? `/v1/datasets/${id}/versions/${versionId}/records?${query}`
      : null,
  );
  function navigate(next: { version?: string; tab?: string }) {
    const search = new URLSearchParams();
    if (next.version || versionId)
      search.set("version", next.version || versionId!);
    search.set("tab", next.tab || tab);
    setSelection(undefined);
    setOffset(0);
    if (next.version)
      setControls({
        search: "",
        sort: "",
        trust: "",
        trustField: "",
        field: "",
        operator: "eq",
        value: "",
      });
    router.push(`/datasets/${id}?${search}`);
  }
  function openProof(row: RecordRow, field: Field) {
    if (versionId)
      setSelection({
        datasetId: id,
        versionId,
        entityId: row.entity_id,
        field: field.key,
        label: field.label,
        entityName: formatValue(
          row.values[
            version.data?.data.schema.fields[0]?.key || "company_name"
          ],
        ),
      });
  }
  async function refresh() {
    setRefreshing(true);
    setRefreshError(undefined);
    try {
      const workflows = await allPages<Workflow>("/v1/workflows");
      const workflow = workflows.find(
        (w) => w.id === dataset.data?.data.workflow_id,
      );
      if (!workflow) throw new Error("Workflow not found");
      router.push(`/ask?requirement=${workflow.requirement_id}`);
    } catch (e) {
      setRefreshError(e);
      setRefreshing(false);
    }
  }
  const currentVersion = versions?.find((v) => v.id === versionId);
  return (
    <div className="page workbench">
      {dataset.error ? (
        <ErrorNotice error={dataset.error} retry={dataset.reload} />
      ) : !dataset.data ? (
        <Loading label="Opening the dataset…" />
      ) : (
        <>
          <div className="page-title">
            <div>
              <span className="eyebrow">
                <Link href="/datasets">Datasets</Link> / Evidence ledger
              </span>
              <h1>{dataset.data.data.name}</h1>
              <p>
                {currentVersion
                  ? `${currentVersion.record_count} records · ${dateTime(currentVersion.created_at)}`
                  : "A versioned body of evidence."}
              </p>
            </div>
            <div className="actions">
              <button
                className="button secondary"
                onClick={() => void refresh()}
                disabled={refreshing}
              >
                {refreshing ? "Opening contract…" : "Prepare refresh"}
                <Icon name="history" />
              </button>
              {versionId && (
                <button
                  className="button primary"
                  onClick={() => navigate({ tab: "export" })}
                >
                  Export
                  <Icon name="download" />
                </button>
              )}
            </div>
          </div>
          {!!refreshError && <ErrorNotice error={refreshError} />}
          <div className="workbench-context">
            <div className="context-tabs" aria-label="Dataset views">
              {["grid", "versions", "export"].map((view) => (
                <button
                  className={tab === view ? "selected" : ""}
                  key={view}
                  onClick={() => navigate({ tab: view })}
                  disabled={!versionId}
                >
                  {view === "grid"
                    ? "Data grid"
                    : view === "versions"
                      ? "Versions & diff"
                      : "Export"}
                </button>
              ))}
            </div>
            {versions && versions.length > 0 && (
              <label className="inline-label">
                Snapshot
                <select
                  aria-label="Dataset version"
                  value={versionId}
                  onChange={(e) => navigate({ version: e.target.value })}
                >
                  {versions.map((v, index) => (
                    <option value={v.id} key={v.id}>
                      Version {v.version}
                      {index === 0 ? " · Latest" : ""}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
          {versionError ? (
            <ErrorNotice
              error={versionError}
              retry={() => setVersionAttempt((v) => v + 1)}
            />
          ) : !versions ? (
            <Loading label="Loading immutable versions…" />
          ) : !versions.length ? (
            <Empty
              title="This dataset is waiting for its first run."
              action={
                <Link href="/runs" className="button primary">
                  View workflows
                </Link>
              }
            >
              A version appears when the worker materializes its results. Open
              Runs to inspect progress or start the confirmed workflow.
            </Empty>
          ) : version.error ? (
            <ErrorNotice error={version.error} retry={version.reload} />
          ) : !version.data ? (
            <Loading label="Loading the version schema…" />
          ) : (
            <>
              {tab === "grid" && (
                <>
                  <GridToolbar
                    fields={version.data.data.schema.fields}
                    controls={controls}
                    setControls={(value) => {
                      setControls(value);
                      setOffset(0);
                    }}
                  />
                  {records.error ? (
                    <ErrorNotice error={records.error} retry={records.reload} />
                  ) : records.loading ? (
                    <Loading label="Loading version-pinned records…" />
                  ) : !records.data?.items.length ? (
                    <Empty
                      title={
                        controls.search || filters.length
                          ? "No records match these filters."
                          : "No records passed the collection rules."
                      }
                      action={
                        controls.search || filters.length ? (
                          <button
                            className="button secondary"
                            onClick={() =>
                              setControls({
                                search: "",
                                sort: "",
                                trust: "",
                                trustField: "",
                                field: "",
                                operator: "eq",
                                value: "",
                              })
                            }
                          >
                            Clear filters
                          </button>
                        ) : currentVersion ? (
                          <Link
                            className="button secondary"
                            href={`/runs/${currentVersion.workflow_run_id}`}
                          >
                            Inspect run diagnostics
                          </Link>
                        ) : undefined
                      }
                    >
                      {controls.search || filters.length
                        ? "Try a broader search or adjust the field and trust filters."
                        : "Review source errors and the required-field policy. Missing facts are never invented."}
                    </Empty>
                  ) : (
                    <>
                      <DataGrid
                        fields={version.data.data.schema.fields}
                        rows={records.data.items}
                        offset={offset}
                        sort={controls.sort}
                        onSort={(sort) => {
                          setControls((c) => ({ ...c, sort }));
                          setOffset(0);
                        }}
                        onProof={openProof}
                      />
                      <Pager
                        offset={offset}
                        limit={25}
                        total={records.data.total}
                        onChange={setOffset}
                      />
                    </>
                  )}
                  <div className="grid-footnote">
                    <Icon name="proof" />
                    <span>
                      Values are immutable within this snapshot. Select a cell
                      to inspect sources, evidence anchors, and competing
                      claims.
                    </span>
                  </div>
                  {currentVersion && (
                    <VersionProvenance runId={currentVersion.workflow_run_id} />
                  )}
                </>
              )}
              {tab === "versions" && (
                <Versions
                  datasetId={id}
                  versions={versions}
                  fields={version.data.data.schema.fields}
                  onOpen={(version) => navigate({ version, tab: "grid" })}
                  onProof={setSelection}
                />
              )}
              {tab === "export" && currentVersion && (
                <ExportPanel key={currentVersion.id} version={currentVersion} />
              )}
            </>
          )}
        </>
      )}
      {selection && (
        <ProofDrawer
          key={`${selection.versionId}:${selection.entityId}:${selection.field}`}
          selection={selection}
          onClose={() => setSelection(undefined)}
        />
      )}
    </div>
  );
}
function VersionProvenance({ runId }: { runId: string }) {
  const run = useResource<Resource<import("@/lib/api/types").RunData>>(
    `/v1/runs/${runId}`,
  );
  return (
    <div className="version-provenance">
      {run.data && (
        <>
          <span className="tag">
            {run.data.data.mode === "FIXTURE"
              ? "Fixture evidence"
              : "Live acquisition"}
          </span>
          <span>
            {String(
              run.data.data.metrics.fixture_label || run.data.data.status,
            )}
          </span>
        </>
      )}
      <Link href={`/runs/${runId}`} className="text-button">
        Inspect source run ↗
      </Link>
      {!!run.error && (
        <span className="hint">Run provenance could not be loaded.</span>
      )}
    </div>
  );
}
