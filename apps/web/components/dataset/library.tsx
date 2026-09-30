"use client";
import Link from "next/link";
import { useState } from "react";
import { useResource } from "@/lib/hooks/use-resource";
import type { Dataset, Workflow, Page } from "@/lib/api/types";
import {
  ErrorNotice,
  Empty,
  Loading,
  Pager,
  Icon,
} from "@/components/ui/primitives";
import { shortId } from "@/lib/format";
import { RunHistory } from "@/components/workflow/run-monitor";
export function DatasetList() {
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useResource<Page<Dataset>>(
    `/v1/datasets?limit=20&offset=${offset}`,
  );
  return (
    <div className="page">
      <div className="page-title">
        <div>
          <span className="eyebrow">Your research library</span>
          <h1>Datasets</h1>
          <p>Persistent research. Inspectable down to the field.</p>
        </div>
        <Link href="/ask" className="button primary">
          <Icon name="plus" />
          New dataset
        </Link>
      </div>
      {error ? (
        <ErrorNotice error={error} retry={reload} />
      ) : loading ? (
        <Loading label="Loading your datasets…" />
      ) : !data?.items.length ? (
        <Empty
          title="Your first dataset starts with a brief."
          action={
            <Link href="/ask" className="button primary">
              Create a research brief
              <Icon name="arrow" />
            </Link>
          }
        >
          Define the fields and trust rules, then collect evidence into a
          versioned dataset.
        </Empty>
      ) : (
        <>
          <div className="library-header eyebrow">
            <span>Dataset / research objective</span>
            <span>Open ledger</span>
          </div>
          {data.items.map((dataset, index) => (
            <Link
              className="dataset-row"
              href={`/datasets/${dataset.id}`}
              key={dataset.id}
            >
              <span className="row-number mono">
                {String(offset + index + 1).padStart(2, "0")}
              </span>
              <div>
                <h2>{dataset.name}</h2>
                <span className="mono">
                  DATASET {shortId(dataset.id)} · WORKFLOW{" "}
                  {shortId(dataset.workflow_id)}
                </span>
              </div>
              <Icon name="arrow" />
            </Link>
          ))}
          <Pager
            offset={offset}
            limit={20}
            total={data.total}
            onChange={setOffset}
          />
        </>
      )}
    </div>
  );
}
export function Workflows({ history = false }: { history?: boolean }) {
  const [offset, setOffset] = useState(0);
  const [expanded, setExpanded] = useState<string>();
  const resource = useResource<Page<Workflow>>(
    `/v1/workflows?limit=20&offset=${offset}`,
  );
  return (
    <div className="page">
      <div className="page-title">
        <div>
          <span className="eyebrow">Reproducible research</span>
          <h1>{history ? "Workflow history" : "Runs & workflows"}</h1>
          <p>Reopen a saved contract or inspect its execution history.</p>
        </div>
        <Link href="/ask" className="button primary">
          New brief
          <Icon name="plus" />
        </Link>
      </div>
      {resource.error ? (
        <ErrorNotice error={resource.error} retry={resource.reload} />
      ) : resource.loading ? (
        <Loading />
      ) : !resource.data?.items.length ? (
        <Empty
          title="No workflows yet."
          action={
            <Link className="button primary" href="/ask">
              Write a brief
            </Link>
          }
        >
          A confirmed brief becomes a reusable workflow.
        </Empty>
      ) : (
        <>
          {resource.data.items.map((workflow) => (
            <section className="workflow-row" key={workflow.id}>
              <div className="section-heading">
                <div>
                  <span className="eyebrow">
                    Workflow {shortId(workflow.id)}
                  </span>
                  <h2>{workflow.name}</h2>
                </div>
                <div className="actions">
                  <Link
                    className="button secondary small"
                    href={`/ask?requirement=${workflow.requirement_id}`}
                  >
                    Open contract
                  </Link>
                  <button
                    className="button secondary small"
                    aria-expanded={expanded === workflow.id}
                    onClick={() =>
                      setExpanded(
                        expanded === workflow.id ? undefined : workflow.id,
                      )
                    }
                  >
                    {expanded === workflow.id ? "Hide runs" : "View runs"}
                  </button>
                </div>
              </div>
              {expanded === workflow.id && (
                <RunHistory workflowId={workflow.id} />
              )}
            </section>
          ))}
          <Pager
            offset={offset}
            limit={20}
            total={resource.data.total}
            onChange={setOffset}
          />
        </>
      )}
    </div>
  );
}
