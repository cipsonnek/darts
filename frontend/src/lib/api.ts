// Thin, typed wrapper around the REST API. The admin token (needed for administrative
// actions from other devices) is kept in localStorage and sent as X-Admin-Token.

const TOKEN_KEY = "dartsense.adminToken";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

export function getAdminToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setAdminToken(token: string): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable */
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getAdminToken();
  if (token) headers["X-Admin-Token"] = token;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch (e) {
    throw new ApiError(0, "Brak połączenia z serwerem. Sprawdź, czy komputer tarczy jest włączony.", e);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: any = undefined;
  try {
    data = text ? JSON.parse(text) : undefined;
  } catch {
    data = text;
  }
  if (!res.ok) {
    // The operator panel listens for this to show the sign-in screen again.
    if (res.status === 401 && (path.startsWith("/api/fleet") || path.startsWith("/api/auth/me"))) {
      window.dispatchEvent(new Event("dartsense:signed-out"));
    }
    const detail = data?.detail;
    const msg =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: any) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ")
          : `${res.status} ${res.statusText}`;
    throw new ApiError(res.status, msg, data);
  }
  return data as T;
}

export const api = {
  get: <T>(p: string) => request<T>("GET", p),
  post: <T>(p: string, body?: unknown) => request<T>("POST", p, body ?? {}),
  put: <T>(p: string, body?: unknown) => request<T>("PUT", p, body ?? {}),
  patch: <T>(p: string, body?: unknown) => request<T>("PATCH", p, body ?? {}),
  del: <T>(p: string) => request<T>("DELETE", p),
};

export function streamUrl(cameraId: string, opts: { overlay?: string[]; width?: number; fps?: number; view?: string } = {}): string {
  const q = new URLSearchParams();
  if (opts.overlay?.length) q.set("overlay", opts.overlay.join(","));
  if (opts.width) q.set("width", String(Math.round(opts.width)));
  if (opts.fps) q.set("fps", String(opts.fps));
  if (opts.view && opts.view !== "raw") q.set("view", opts.view);
  return `/api/cameras/${encodeURIComponent(cameraId)}/stream.mjpg?${q.toString()}`;
}

export function snapshotUrl(cameraId: string, opts: { overlay?: string[]; width?: number; view?: string } = {}, bust = 0): string {
  const q = new URLSearchParams();
  if (opts.overlay?.length) q.set("overlay", opts.overlay.join(","));
  if (opts.width) q.set("width", String(Math.round(opts.width)));
  if (opts.view && opts.view !== "raw") q.set("view", opts.view);
  q.set("_", String(bust));
  return `/api/cameras/${encodeURIComponent(cameraId)}/snapshot.jpg?${q.toString()}`;
}
