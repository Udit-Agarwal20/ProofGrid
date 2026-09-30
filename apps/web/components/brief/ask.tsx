"use client";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { post } from "@/lib/api/client";
import type {
  CompileResponse,
  Clarification,
  Resource,
  RequirementData,
} from "@/lib/api/types";
import { useResource } from "@/lib/hooks/use-resource";
import {
  ErrorNotice,
  Icon,
  Loading,
  TrustBadge,
} from "@/components/ui/primitives";
import { Interpretation } from "./interpretation";
export const goldenPrompt =
  "Find Indian AI startups that raised more than $1M in the last 12 months. Include company, website, founders, headquarters, funding round, funding amount, investors, funding date, and original evidence.";
const examples = [
  {
    title: "Indian AI funding",
    detail: "Companies, rounds, investors, and the original evidence.",
    prompt: goldenPrompt,
  },
  {
    title: "Manufacturing in Germany",
    detail: "A supplier shortlist with explicit scope and source rules.",
    prompt:
      "Find manufacturers in Germany with company name, website, headquarters and products. Limit to 20 companies.",
  },
  {
    title: "Refine an open question",
    detail: "Start broad and clarify the constraints that matter.",
    prompt: "Find the best recent AI startups.",
  },
];
export function Ask() {
  const params = useSearchParams(),
    router = useRouter();
  const requirementId = params.get("requirement");
  const resource = useResource<Resource<RequirementData>>(
    requirementId
      ? `/v1/requirements/${encodeURIComponent(requirementId)}`
      : null,
  );
  const [prompt, setPrompt] = useState("");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [clarification, setClarification] = useState<Clarification>();
  const [answers, setAnswers] = useState<Record<string, string>>({});
  useEffect(() => {
    try {
      setPrompt(sessionStorage.getItem("proofgrid:brief") || "");
    } catch {}
  }, []);
  const updatePrompt = (value: string) => {
    setPrompt(value);
    try {
      sessionStorage.setItem("proofgrid:brief", value);
    } catch {}
  };
  async function compile() {
    if (busy || prompt.trim().length < 3) return;
    setBusy(true);
    setError(undefined);
    const additions = clarification?.clarification_questions
      .map((q) =>
        answers[q.question_id] ? `${q.question} ${answers[q.question_id]}` : "",
      )
      .filter(Boolean)
      .join("\n");
    const fullPrompt = additions
      ? `${prompt}\n\nClarifications:\n${additions}`
      : prompt;
    try {
      const response = await post<CompileResponse>("/v1/requirements/compile", {
        prompt: fullPrompt,
        ...(reference ? { reference_date: `${reference}T00:00:00Z` } : {}),
      });
      if (response.outcome.status === "NEEDS_CLARIFICATION") {
        setClarification(response.outcome);
        setAnswers({});
      } else if (response.requirement_id) {
        updatePrompt(fullPrompt);
        setClarification(undefined);
        router.push(`/ask?requirement=${response.requirement_id}`);
      } else throw new Error("Compiled outcome missing requirement ID");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (requirementId)
    return (
      <div className="page">
        {resource.error ? (
          <ErrorNotice error={resource.error} retry={resource.reload} />
        ) : resource.data ? (
          <Interpretation
            key={`${requirementId}:${resource.data.data.version}`}
            saved={resource.data}
            onReload={resource.reload}
          />
        ) : (
          <Loading label="Opening the saved interpretation…" />
        )}
      </div>
    );
  return (
    <div className="ask-page">
      <div className="page-kicker">
        <span className="eyebrow">01 / Define the brief</span>
        <span className="mono">ASK → STRUCTURE → PROVE</span>
      </div>
      <div className="ask-heading">
        <h1>
          A dataset you can
          <br />
          <span>stand behind.</span>
        </h1>
        <p>
          Describe what you need to know.
          <br />
          Build a structured dataset with evidence behind every value.
        </p>
      </div>
      <form
        className="brief-composer"
        onSubmit={(event) => {
          event.preventDefault();
          void compile();
        }}
      >
        <label className="composer-label" htmlFor="brief">
          <Icon name="ask" />
          What dataset do you need?
        </label>
        <textarea
          id="brief"
          placeholder="Find Indian AI startups that raised more than $1M in the last 12 months. Include company, founders, funding amount, investors, date, and evidence…"
          value={prompt}
          onChange={(e) => {
            updatePrompt(e.target.value);
            setClarification(undefined);
          }}
          maxLength={12000}
          minLength={3}
          required
          rows={5}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
              e.preventDefault();
              void compile();
            }
          }}
        />
        <div className="composer-bottom">
          <span className="hint">Describe the dataset, not the answer.</span>
          <button
            className="button primary"
            disabled={busy || prompt.trim().length < 3}
          >
            {busy ? "Compiling request…" : "Compile request"}
            <Icon name="arrow" />
          </button>
        </div>
        <div className="composer-meta">
          <span>Public and permitted sources only</span>
          <span className="mono">
            {prompt.length.toLocaleString()} / 12,000{" "}
            <span className="key-hint">· ⌘ ↵</span>
          </span>
        </div>
      </form>
      {!!error && <ErrorNotice error={error} />}
      <details className="source-options">
        <summary>Dates & source constraints</summary>
        <p className="muted">
          Add source URLs or domain constraints directly to your brief.
          Collection remains subject to backend source policy.
        </p>
        <label>
          Reference date for relative phrases
          <input
            type="date"
            value={reference}
            onChange={(e) => setReference(e.target.value)}
          />
        </label>
        <small>
          Leave blank to use the current date. The synthetic showcase is
          anchored to 30 September 2026.
        </small>
      </details>
      {clarification ? (
        <section className="clarification" aria-live="polite">
          <span className="eyebrow">Clarification required</span>
          <h2>Let’s make the scope explicit.</h2>
          <p>
            A dataset contract has not been created yet. Answer the questions
            below, then compile again.
          </p>
          {clarification.ambiguities.map((a) => (
            <div className="notice" key={a.code}>
              {a.message}
            </div>
          ))}
          {clarification.clarification_questions.map((q) => (
            <label key={q.question_id} className="question">
              {q.question}
              <small>{q.impact_summary}</small>
              {q.options.length > 0 && (
                <div className="option-row">
                  {q.options.map((option) => (
                    <button
                      type="button"
                      key={option}
                      className="button secondary small"
                      onClick={() =>
                        setAnswers((a) => ({ ...a, [q.question_id]: option }))
                      }
                    >
                      {option}
                    </button>
                  ))}
                </div>
              )}
              <input
                value={answers[q.question_id] || ""}
                onChange={(e) =>
                  setAnswers((a) => ({ ...a, [q.question_id]: e.target.value }))
                }
                placeholder="Your clarification"
              />
            </label>
          ))}
          <button
            className="button primary"
            disabled={
              busy ||
              clarification.clarification_questions.some(
                (q) => !answers[q.question_id]?.trim(),
              )
            }
            onClick={() => void compile()}
          >
            Compile with clarifications
            <Icon name="arrow" />
          </button>
        </section>
      ) : (
        <section className="examples">
          <div className="section-heading">
            <h2>Start with a research brief</h2>
            <span className="eyebrow">EXAMPLES / EDIT TO FIT</span>
          </div>
          {examples.map((example, index) => (
            <button
              className="example-row"
              key={example.title}
              onClick={() => {
                updatePrompt(example.prompt);
                document.getElementById("brief")?.focus();
              }}
            >
              <span className="example-number mono">0{index + 1}</span>
              <span>
                <strong>{example.title}</strong>
                <small>{example.detail}</small>
              </span>
              <Icon name="arrow" />
            </button>
          ))}
        </section>
      )}
      <section className="ask-doctrine">
        <div>
          <span className="eyebrow">From a brief to a body of evidence</span>
          <p>
            You approve the structure.
            <br />
            Every source leaves a trail.
          </p>
        </div>
        <div className="doctrine-stages">
          <div>
            <span className="mono">01</span>
            <strong>Define the contract</strong>
            <small>Fields, scope, and trust rules</small>
          </div>
          <div>
            <span className="mono">02</span>
            <strong>Inspect the workflow</strong>
            <small>A bounded, reproducible plan</small>
          </div>
          <div>
            <span className="mono">03</span>
            <strong>Explore the proof</strong>
            <small>Claims, conflicts, and history</small>
          </div>
        </div>
      </section>
      <div className="trust-key">
        <span className="eyebrow">A shared language for evidence</span>
        <div>
          {(
            [
              "VERIFIED",
              "SUPPORTED",
              "SINGLE_SOURCE",
              "CONFLICTING",
              "NEEDS_REVIEW",
              "MISSING",
            ] as const
          ).map((status) => (
            <TrustBadge key={status} status={status} />
          ))}
        </div>
      </div>
    </div>
  );
}
