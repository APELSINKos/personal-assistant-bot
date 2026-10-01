import { initData } from "../telegram";

export const AUTH_EXPIRED_EVENT = "assistant:auth-expired";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  get reason(): string | undefined {
    return typeof this.details.reason === "string" ? this.details.reason : undefined;
  }
}

type Method = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

export async function api<T>(
  path: string,
  options: { method?: Method; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const token = initData();
  if (!token) {
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    throw new ApiError(401, "no_init_data", "Not opened from Telegram");
  }
  const headers: Record<string, string> = { Authorization: `tma ${token}` };
  // A file (a Blob) goes as it is — the calendar upload; anything else as JSON.
  const raw = options.body instanceof Blob ? options.body : null;
  if (raw) headers["Content-Type"] = raw.type || "text/calendar";
  else if (options.body !== undefined) headers["Content-Type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method: options.method ?? "GET",
      headers,
      body: raw ?? (options.body === undefined ? undefined : JSON.stringify(options.body)),
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "network", "Network error");
  }
  if (response.status === 204) return undefined as T;
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const details = payload !== null && typeof payload === "object"
      ? (payload as Record<string, unknown>)
      : {};
    const code = typeof details.code === "string" ? details.code : "http_error";
    if (response.status === 401) window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    const title = typeof details.title === "string" ? details.title : response.statusText;
    throw new ApiError(response.status, code, title, details);
  }
  return payload as T;
}
