import type { Page } from "./types";
export const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public correlationId?: string,
    public retryable = false,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "The request could not be completed. Please try again.";
}
export async function responseError(response: Response): Promise<ApiError> {
  const data = await response.json().catch(() => null);
  const e = data?.error;
  const fallback: Record<number, string> = {
    401: "Workspace access is required. Check your API deployment authentication.",
    403: "This action is not permitted.",
    404: "This resource is unavailable. Return to the workspace and choose another.",
    409: "This version changed. Reload and review the latest saved contract.",
    422: "Check the fields and constraints, then try again.",
    429: "The workspace or provider limit was reached. Wait before retrying.",
  };
  // Never display arbitrary HTML/proxy responses or unsanitized provider bodies.
  const message =
    typeof e?.message === "string" && typeof e?.code === "string"
      ? e.message
      : fallback[response.status] ||
        "The service is temporarily unavailable. Your saved work is retained.";
  return new ApiError(
    response.status,
    e?.code || "REQUEST_FAILED",
    message,
    e?.correlation_id,
    e?.retryable ?? response.status >= 500,
  );
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(
      0,
      "NETWORK_UNAVAILABLE",
      "Cannot reach ProofGrid. Check that the API is running and the workspace connection is configured.",
      undefined,
      true,
    );
  }
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<T>;
}
export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, {
    method: "POST",
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
export async function allPages<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T[]> {
  const items: T[] = [];
  for (let offset = 0; ; offset += 200) {
    const page = await api<Page<T>>(
      `${path}${path.includes("?") ? "&" : "?"}limit=200&offset=${offset}`,
      { signal },
    );
    items.push(...page.items);
    if (items.length >= page.total || !page.items.length) return items;
  }
}
export function recordsQuery(input: {
  offset: number;
  limit: number;
  sort?: string;
  search?: string;
  filters?: string[];
}) {
  const query = new URLSearchParams({
    offset: String(input.offset),
    limit: String(input.limit),
  });
  if (input.sort) query.set("sort", input.sort);
  if (input.search) query.set("q", input.search);
  input.filters?.forEach((filter) => query.append("filter", filter));
  return query.toString();
}
export async function downloadExport(id: string) {
  const response = await fetch(
    `${API_BASE}/v1/exports/${encodeURIComponent(id)}/download`,
  );
  if (!response.ok) throw await responseError(response);
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `proofgrid-${id}.zip`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
