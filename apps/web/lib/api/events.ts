import { API_BASE, responseError, ApiError } from "./client";
import type { RunEvent } from "./types";
export function parseEvent(block: string): RunEvent | null {
  let sequence = 0,
    event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("id:")) sequence = Number(line.slice(3).trim());
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (!Number.isSafeInteger(sequence) || sequence <= 0 || !data.length)
    return null;
  const payload: unknown = JSON.parse(data.join("\n"));
  if (!payload || typeof payload !== "object" || Array.isArray(payload))
    throw new Error("Invalid event payload");
  return { sequence, event, data: payload as RunEvent["data"] };
}
export type ConnectionState =
  "connecting" | "connected" | "reconnecting" | "closed" | "error";
export function subscribeRun(
  runId: string,
  receive: (event: RunEvent) => void,
  connection: (state: ConnectionState) => void,
  onError: (error: unknown) => void,
) {
  const controller = new AbortController();
  let cursor = 0,
    attempts = 0,
    timer: ReturnType<typeof setTimeout> | undefined;
  const connect = async () => {
    connection(attempts ? "reconnecting" : "connecting");
    try {
      const response = await fetch(
        `${API_BASE}/v1/runs/${encodeURIComponent(runId)}/events?after=${cursor}`,
        {
          signal: controller.signal,
          headers: {
            Accept: "text/event-stream",
            "Last-Event-ID": String(cursor),
          },
        },
      );
      if (!response.ok) throw await responseError(response);
      if (!response.body) throw new Error("Stream unavailable");
      connection("connected");
      let buffer = "";
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      try {
        while (!controller.signal.aborted) {
          const chunk = await reader.read();
          if (chunk.done) break;
          buffer += decoder
            .decode(chunk.value, { stream: true })
            .replace(/\r\n/g, "\n");
          let boundary: number;
          while ((boundary = buffer.indexOf("\n\n")) >= 0) {
            const block = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            const event = parseEvent(block);
            if (!event || event.sequence <= cursor) continue;
            // A gap is replayed from the last accepted sequence, never silently skipped.
            if (event.sequence !== cursor + 1)
              throw new Error("Event sequence gap");
            receive(event);
            cursor = event.sequence;
            attempts = 0;
          }
          if (buffer.length > 1024 * 1024)
            throw new Error("Event frame too large");
        }
      } finally {
        await reader.cancel().catch(() => undefined);
        reader.releaseLock();
      }
      if (!controller.signal.aborted) schedule();
    } catch (error) {
      if (controller.signal.aborted) return;
      if (
        error instanceof ApiError &&
        [401, 403, 404, 422].includes(error.status)
      ) {
        connection("error");
        onError(error);
        return;
      }
      schedule();
    }
  };
  const schedule = () => {
    connection("reconnecting");
    timer = setTimeout(connect, Math.min(1000 * 2 ** attempts++, 15000));
  };
  void connect();
  return () => {
    controller.abort();
    clearTimeout(timer);
  };
}
