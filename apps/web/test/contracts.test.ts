import { describe, it, expect, vi } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { ApiError, api, recordsQuery, responseError } from "@/lib/api/client";
import { formatValue, safeSourceUrl, trustInfo, dateTime } from "@/lib/format";
import { trustStates } from "@/lib/api/types";
import { parseEvent, subscribeRun } from "@/lib/api/events";
import { graphLevels } from "@/components/workflow/plan-preview";
import { applyRunEvent } from "@/components/workflow/run-monitor";

describe("proof formatting and tokens", () => {
  it("maps every canonical trust state to text, a symbol and a real CSS token", () => {
    const css = readFileSync(path.resolve("app/globals.css"), "utf8");
    expect(trustStates).toHaveLength(6);
    for (const state of trustStates) {
      expect(trustInfo[state].label).toBeTruthy();
      expect(trustInfo[state].symbol).toBeTruthy();
      expect(css).toContain(
        `--trust-${state.toLowerCase().replaceAll("_", "-")}:`,
      );
    }
  });
  it("preserves exact monetary decimal strings, currency and date precision", () => {
    expect(
      formatValue({ amount: "9007199254740993123.45", currency: "INR" }),
    ).toBe("INR 9,007,199,254,740,993,123.45");
    expect(formatValue({ value: "2026-05", precision: "month" })).toBe(
      "2026-05 (month)",
    );
    expect(formatValue(null)).toBe("Not found");
    expect(formatValue(false)).toBe("No");
    expect(dateTime(null)).toBe("Not recorded");
  });
  it.each([
    "javascript:alert(1)",
    "data:text/html,evil",
    "file:///tmp/data",
    "https://user:pass@example.com",
  ])("rejects unsafe source link %s", (value) =>
    expect(safeSourceUrl(value)).toBeNull(),
  );
  it("allows ordinary HTTPS source links", () =>
    expect(safeSourceUrl("https://example.com/a")).toBe(
      "https://example.com/a",
    ));
});
describe("API boundaries", () => {
  it("encodes repeated typed filters and untrusted query text", () => {
    const params = new URLSearchParams(
      recordsQuery({
        offset: 25,
        limit: 25,
        search: "A&B?",
        filters: ["trust.money.eq:CONFLICTING", "money.gt:1000000"],
      }),
    );
    expect(params.get("q")).toBe("A&B?");
    expect(params.getAll("filter")).toHaveLength(2);
  });
  it.each([401, 403, 404, 409, 422, 429, 500, 503])(
    "returns safe error for status %s",
    async (status) => {
      const error = await responseError(
        new Response("<script>proxy stack</script>", { status }),
      );
      expect(error).toBeInstanceOf(ApiError);
      expect(error.message).not.toContain("script");
      expect(error.status).toBe(status);
    },
  );
  it("preserves sanitized API code and correlation reference", async () => {
    const error = await responseError(
      new Response(
        JSON.stringify({
          error: {
            code: "VERSION_CONFLICT",
            message: "Reload the latest version.",
            correlation_id: "test-ref",
            retryable: false,
          },
        }),
        { status: 409 },
      ),
    );
    expect(error.code).toBe("VERSION_CONFLICT");
    expect(error.correlationId).toBe("test-ref");
  });
  it("explains a network failure without leaking the raw exception", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("secret internals")),
    );
    await expect(api("/v1/datasets")).rejects.toMatchObject({
      code: "NETWORK_UNAVAILABLE",
    });
  });
});
describe("persisted event replay", () => {
  it("parses multiline data and ignores heartbeats", () => {
    expect(parseEvent(": heartbeat")).toBeNull();
    expect(
      parseEvent(
        'id: 7\nevent: step.progress\ndata: {"status":\ndata: "SUCCEEDED"}',
      ),
    ).toEqual({
      sequence: 7,
      event: "step.progress",
      data: { status: "SUCCEEDED" },
    });
  });
  it("reconnects with cursor, suppresses duplicates, and cleans up", async () => {
    vi.useFakeTimers();
    const encoder = new TextEncoder();
    const receive = vi.fn(),
      connection = vi.fn();
    let pending: ReadableStreamDefaultController<Uint8Array>;
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          new ReadableStream({
            start(c) {
              c.enqueue(
                encoder.encode(
                  'id: 1\nevent: step.started\ndata: {"node_id":"fetch"}\n\n',
                ),
              );
              c.close();
            },
          }),
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          new ReadableStream({
            start(c) {
              pending = c;
              c.enqueue(
                encoder.encode(
                  'id: 1\nevent: step.started\ndata: {}\n\nid: 2\nevent: step.progress\ndata: {"status":"SUCCEEDED"}\n\n',
                ),
              );
            },
          }),
        ),
      );
    vi.stubGlobal("fetch", fetch);
    const close = subscribeRun("run-test", receive, connection, vi.fn());
    await vi.advanceTimersByTimeAsync(1050);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch.mock.calls[1][0]).toContain("after=1");
    expect(fetch.mock.calls[1][1].headers["Last-Event-ID"]).toBe("1");
    expect(receive.mock.calls.map((call) => call[0].sequence)).toEqual([1, 2]);
    close();
    pending!.close();
    await vi.advanceTimersByTimeAsync(30000);
    expect(fetch).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });
  it("does not advance over a sequence gap", async () => {
    vi.useFakeTimers();
    const receive = vi.fn();
    const fetch = vi.fn().mockResolvedValue(
      new Response(
        new ReadableStream({
          start(c) {
            c.enqueue(
              new TextEncoder().encode(
                "id: 2\nevent: step.started\ndata: {}\n\n",
              ),
            );
            c.close();
          },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetch);
    const close = subscribeRun("run", receive, vi.fn(), vi.fn());
    await vi.advanceTimersByTimeAsync(50);
    expect(receive).not.toHaveBeenCalled();
    close();
    vi.useRealTimers();
  });
  it("uses server status and metrics when a step completes", () => {
    const run = applyRunEvent(
      {
        status: "RUNNING",
        mode: "FIXTURE",
        metrics: { sources_fetched: 2 },
        started_at: null,
        finished_at: null,
        steps: [
          {
            id: "step",
            node_id: "fetch",
            operator: "FETCH_HTTP",
            status: "RUNNING",
            attempt: 1,
            error_code: null,
          },
        ],
      },
      {
        sequence: 2,
        event: "step.progress",
        data: {
          step_id: "step",
          status: "SUCCEEDED",
          metrics: { claims_proposed: 8 },
        },
      },
    );
    expect(run.steps[0].status).toBe("SUCCEEDED");
    expect(run.metrics).toEqual({ sources_fetched: 2, claims_proposed: 8 });
    expect(run.status).toBe("RUNNING");
  });
  it("lays out dependencies independent of input ordering", () => {
    const base = {
      operator: "EXTRACT",
      params: {},
      critical: true,
      constraints: { timeout_seconds: 30, max_retries: 1 },
    };
    expect(
      graphLevels([
        { ...base, id: "c", depends_on: ["a", "b"] },
        { ...base, id: "b", depends_on: [] },
        { ...base, id: "a", depends_on: [] },
      ]).map((level) => level.map((n) => n.id)),
    ).toEqual([["b", "a"], ["c"]]);
  });
});
