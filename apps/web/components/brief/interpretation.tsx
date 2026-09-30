"use client";
import Link from "next/link";
import { useState } from "react";
import { api, post } from "@/lib/api/client";
import type { Resource, RequirementData, PlanData } from "@/lib/api/types";
import { dateTime, shortId } from "@/lib/format";
import { ErrorNotice, Icon } from "@/components/ui/primitives";
import { SchemaEditor } from "./schema-editor";
import { TrustEditor } from "./trust-editor";
import { PlanPreview } from "@/components/workflow/plan-preview";
export function Interpretation({
  saved,
  onReload,
}: {
  saved: Resource<RequirementData>;
  onReload: () => void;
}) {
  const [current, setCurrent] = useState(saved);
  const [spec, setSpec] = useState(saved.data.requirement_spec);
  const [trust, setTrust] = useState(saved.data.trust_contract);
  const [stage, setStage] = useState<"interpret" | "trust" | "plan">(
    "interpret",
  );
  const [plan, setPlan] = useState<Resource<PlanData>>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [message, setMessage] = useState("");
  const dirty =
    JSON.stringify(spec) !== JSON.stringify(current.data.requirement_spec) ||
    JSON.stringify(trust) !== JSON.stringify(current.data.trust_contract);
  async function save(confirm: boolean) {
    setBusy(true);
    setError(undefined);
    setMessage("");
    let next = current;
    try {
      if (JSON.stringify(spec) !== JSON.stringify(next.data.requirement_spec)) {
        next = await api<Resource<RequirementData>>(
          `/v1/requirements/${saved.id}`,
          {
            method: "PATCH",
            body: JSON.stringify({
              expected_version: next.data.version,
              requirement_spec: {
                ...spec,
                geography: spec.geography.filter(Boolean),
                source_hints: spec.source_hints
                  .map((v) => v.trim())
                  .filter(Boolean),
              },
            }),
          },
        );
        setCurrent(next);
        setSpec(next.data.requirement_spec);
      }
      if (JSON.stringify(trust) !== JSON.stringify(next.data.trust_contract)) {
        next = await post<Resource<RequirementData>>(
          `/v1/requirements/${saved.id}/trust-contract`,
          { expected_version: next.data.version, trust_contract: trust },
        );
        setCurrent(next);
      }
      if (confirm) {
        next = await post<Resource<RequirementData>>(
          `/v1/requirements/${saved.id}/confirm`,
          { expected_version: next.data.version },
        );
        setCurrent(next);
        const result = await post<Resource<PlanData>>(
          `/v1/requirements/${saved.id}/plan`,
        );
        setPlan(result);
        setStage("plan");
      } else
        setMessage(
          `Contract revision ${next.data.version} saved. Review and confirm before running.`,
        );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-title">
        <div>
          <span className="eyebrow">02 / Interpretation studio</span>
          <h1>Make the brief precise.</h1>
          <p>Review the structure and the rules your evidence must satisfy.</p>
        </div>
        <Link href="/ask" className="button secondary">
          New brief
        </Link>
      </div>
      <div className="flow-tabs" aria-label="Configuration stages">
        {(["interpret", "trust", "plan"] as const).map((item, index) => (
          <button
            key={item}
            disabled={busy || (item === "plan" && (!plan || dirty))}
            className={stage === item ? "selected" : ""}
            onClick={() => setStage(item)}
          >
            <span className="mono">0{index + 1}</span>
            {item === "interpret"
              ? "Interpretation"
              : item === "trust"
                ? "Trust contract"
                : "Plan preview"}
          </button>
        ))}
      </div>
      {!!error && <ErrorNotice error={error} retry={onReload} />}
      <div role="status">
        {message && <div className="notice success">{message}</div>}
      </div>
      {stage === "plan" && plan ? (
        <PlanPreview
          plan={plan}
          title={spec.goal}
          onEdit={() => setStage("interpret")}
        />
      ) : (
        <div className="interpretation-layout">
          <aside className="brief-context">
            <span className="eyebrow">Original brief</span>
            <p>{saved.data.original_prompt}</p>
            <dl>
              <dt>Requirement</dt>
              <dd className="mono">{shortId(saved.id)}</dd>
              <dt>Contract revision</dt>
              <dd>
                {current.data.version}
                {dirty ? " · Unsaved edits" : " · Saved"}
              </dd>
              <dt>Reference date</dt>
              <dd className="mono">
                {dateTime(saved.data.compiler_metadata.compiler.reference_date)}
              </dd>
              <dt>Compiler</dt>
              <dd>{saved.data.compiler_metadata.compiler.provider_name}</dd>
            </dl>
            <div className="context-note">
              <Icon name="proof" />
              <p>
                Source collection starts only after you confirm the contract and
                run the plan.
              </p>
            </div>
            {saved.data.compiler_metadata.assumptions.length > 0 && (
              <section>
                <h3>Assumptions to review</h3>
                {saved.data.compiler_metadata.assumptions.map((a) => (
                  <p key={a.code} className="small-copy">
                    {a.description}
                  </p>
                ))}
              </section>
            )}
            {saved.data.compiler_metadata.ambiguities.map((a) => (
              <div className="notice" key={a.code}>
                {a.message}
              </div>
            ))}
          </aside>
          <form
            className="contract-editor"
            onSubmit={(e) => {
              e.preventDefault();
              if (stage === "interpret") setStage("trust");
              else void save(true);
            }}
          >
            {stage === "interpret" ? (
              <SchemaEditor value={spec} onChange={setSpec} />
            ) : (
              <TrustEditor value={trust} onChange={setTrust} />
            )}
            <div className="form-actions">
              <button
                type="button"
                className="button secondary"
                disabled={busy || !dirty}
                onClick={(e) => {
                  const form = e.currentTarget.form;
                  if (form?.reportValidity()) void save(false);
                }}
              >
                Save draft
              </button>
              <div>
                <span className="hint">
                  {stage === "trust"
                    ? "Confirmation applies to these exact rules."
                    : `${spec.fields.length} proposed fields`}
                </span>
                <button className="button primary" disabled={busy}>
                  {busy
                    ? "Saving & validating…"
                    : stage === "interpret"
                      ? "Review trust contract"
                      : "Confirm contract & build plan"}
                  <Icon name="arrow" />
                </button>
              </div>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
