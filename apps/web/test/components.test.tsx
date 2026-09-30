import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TrustBadge } from "@/components/ui/primitives";
import { ProofContent } from "@/components/proof/proof-drawer";
import { SchemaEditor } from "@/components/brief/schema-editor";
import { TrustEditor } from "@/components/brief/trust-editor";
import { Ask } from "@/components/brief/ask";
import { ExportPanel } from "@/components/dataset/export-panel";
import { proof, requirement } from "./fixtures";
const navigation = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => navigation,
  useSearchParams: () => new URLSearchParams(),
}));
function response(value: unknown) {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
describe("trust and proof", () => {
  it("renders trust as visible text and a symbol", () => {
    render(<TrustBadge status="CONFLICTING" />);
    expect(screen.getByText("Conflicting")).toBeTruthy();
    expect(screen.getByText("!")).toBeTruthy();
  });
  it("preserves raw, normalized, competing evidence and safe source links", () => {
    render(<ProofContent proof={proof} onReviewed={() => {}} />);
    expect(screen.getByText("Test company raised $5M.")).toBeTruthy();
    expect(screen.getByText("Test company raised $4.5M.")).toBeTruthy();
    expect(screen.getByText("Competing claim")).toBeTruthy();
    expect(screen.getAllByText("USD 4,500,000").length).toBeGreaterThan(0);
    expect(screen.getByText("$4.5M")).toBeTruthy();
    const link = screen.getAllByRole("link")[0];
    expect(link.getAttribute("rel")).toContain("noopener");
  });
  it("saves only the selected preserved claim and keeps historical explanation", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        response({ id: "conflict-test", data: { status: "RESOLVED" } }),
      );
    vi.stubGlobal("fetch", fetch);
    const reviewed = vi.fn();
    render(<ProofContent proof={proof} onReviewed={reviewed} />);
    await userEvent.selectOptions(
      screen.getByLabelText("Choose a preserved claim"),
      "claim-b",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Save display preference" }),
    );
    await waitFor(() => expect(reviewed).toHaveBeenCalledOnce());
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toMatchObject({
      decision: "SELECT_DISPLAY",
      selected_claim_id: "claim-b",
    });
    expect(
      screen.getByText(/Display preference saved for subsequent/),
    ).toBeTruthy();
    expect(screen.getByText("Test company raised $4.5M.")).toBeTruthy();
  });
  it("keeps missing values explicit", () => {
    render(
      <ProofContent
        proof={{
          ...proof,
          canonical_value: null,
          trust_status: "MISSING",
          claims: [],
          conflict: null,
        }}
        onReviewed={() => {}}
      />,
    );
    expect(screen.getByText("Not found")).toBeTruthy();
    expect(screen.getByText(/No usable claim was found/)).toBeTruthy();
  });
});
describe("compiler and contract", () => {
  it("keeps clarification separate without a schema or run action", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          response({
            requirement_id: null,
            outcome: {
              status: "NEEDS_CLARIFICATION",
              ambiguities: [{ code: "SCOPE", message: "Choose a scope." }],
              assumptions: [],
              clarification_questions: [
                {
                  question_id: "scope",
                  question: "Which country?",
                  options: ["India", "Germany"],
                  impact_summary: "Defines geography.",
                },
              ],
              metadata: {},
              requires_confirmation: true,
              partial_context: null,
            },
          }),
        ),
    );
    render(<Ask />);
    fireEvent.change(screen.getByLabelText("What dataset do you need?"), {
      target: { value: "Find good companies" },
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Compile request" }),
    );
    expect(await screen.findByText("Which country?")).toBeTruthy();
    expect(screen.queryByText("Proposed fields")).toBeNull();
    expect(screen.queryByText("Run workflow")).toBeNull();
    expect(
      screen
        .getByRole("button", { name: "Compile with clarifications" })
        .hasAttribute("disabled"),
    ).toBe(true);
  });
  it("opens only a persisted compiled requirement", async () => {
    navigation.push.mockClear();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          response({
            requirement_id: "req-test",
            outcome: { status: "COMPILED" },
          }),
        ),
    );
    render(<Ask />);
    fireEvent.change(screen.getByLabelText("What dataset do you need?"), {
      target: { value: "Find Indian companies" },
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Compile request" }),
    );
    await waitFor(() =>
      expect(navigation.push).toHaveBeenCalledWith("/ask?requirement=req-test"),
    );
  });
  it("adds a real user-owned field", async () => {
    const changed = vi.fn();
    render(
      <SchemaEditor
        value={requirement.data.requirement_spec}
        onChange={changed}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "+ Add field" }));
    expect(changed.mock.calls[0][0].fields[1]).toMatchObject({
      origin: "user",
      data_type: "text",
    });
  });
  it("presets remain explicit and preserve mandatory invariants", async () => {
    const changed = vi.fn();
    render(
      <TrustEditor
        value={requirement.data.trust_contract}
        onChange={changed}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Strict" }),
    );
    expect(changed.mock.calls[0][0]).toMatchObject({
      minimum_independent_sources: 2,
      allow_single_source_output: false,
      preserve_conflicts: true,
      require_evidence_anchor: true,
    });
  });
  it("pins exports to the selected immutable version", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        response({ id: "export-test", data: { status: "READY" } }),
      )
      .mockResolvedValueOnce(new Response("service down", { status: 503 }));
    vi.stubGlobal("fetch", fetch);
    render(
      <ExportPanel
        version={{
          id: "version-old",
          version: 2,
          record_count: 3,
          status: "FINALIZED",
          workflow_run_id: "run",
          created_at: "",
        }}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Download ZIP bundle" }),
    );
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
      dataset_version_id: "version-old",
      format: "csv",
    });
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});
