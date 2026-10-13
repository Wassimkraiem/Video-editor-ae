export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const API_ORIGIN = new URL(API_URL).origin;

let accessToken: string | null = null;
export function setAccessToken(token: string | null) { accessToken = token; }
export function getAccessToken() { return accessToken; }

/** Signed media routes come back as server-relative paths. */
export function mediaUrl(path: string) {
  return path.startsWith("http") ? path : `${API_ORIGIN}${path}`;
}

function readCookie(name: string) {
  if (typeof document === "undefined") return undefined;
  return document.cookie.split("; ").find((item) => item.startsWith(`${name}=`))?.split("=")[1];
}

/** Exchange the httpOnly refresh cookie for a new access token. */
export async function refreshSession(): Promise<string | null> {
  const csrf = readCookie("csrf_token");
  if (!csrf) return null;
  try {
    const response = await fetch(`${API_URL}/auth/refresh`, { method: "POST", credentials: "include", headers: { "X-CSRF-Token": decodeURIComponent(csrf) } });
    if (!response.ok) return null;
    const body = (await response.json()) as { access_token: string };
    setAccessToken(body.access_token);
    return body.access_token;
  } catch {
    return null;
  }
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(`${API_URL}${path}`, { ...init, headers, credentials: "include" });
  if (response.status === 401 && retry && !path.startsWith("/auth/")) {
    // Access tokens are short-lived; refresh once and replay the request.
    if (await refreshSession()) return apiFetch<T>(path, init, false);
  }
  if (!response.ok) {
    const problem = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(typeof problem.detail === "string" ? problem.detail : "Request failed", response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export type Project = { id: string; owner_id: string; name: string; workflow: string; profile: Record<string, unknown>; created_at: string; updated_at: string };
export type AssetProbe = { sha256?: string; duration_ms?: number | null; width?: number | null; height?: number | null; fps?: number | null; has_audio?: boolean };
export type Asset = { id: string; project_id: string; filename: string; kind: string; mime_type: string; size_bytes: number; storage_key: string; status: "uploaded" | "ready" | "failed" | string; probe?: AssetProbe; created_at: string };
export type RunStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled" | "waiting_for_approval" | "revision_requested";
export type Run = { id: string; project_id: string; status: RunStatus | string; brief: string; skill?: string | null; sdk_session_id?: string | null; usage: Record<string, unknown>; created_at: string };
export type Render = { id: string; project_id: string; preset: string; status: string; output_url?: string | null; error?: string | null; created_at: string };
export type Output = { name: string; path: string; size_bytes: number; modified_at: string; url: string };
export type Skill = { id: string; name: string; description: string; scope: "builtin" | "library" | "user" | "project" | string; enabled: boolean };
export type TimelineItem = { id: string; type: string; start_ms: number; end_ms: number; label?: string };
export type TimelineTrack = { id: string; type: string; items?: TimelineItem[] };
export type TimelineVersion = { version: number; data: { duration_ms?: number; fps?: number; width?: number; height?: number; tracks?: TimelineTrack[] } };
export type Health = { status: string; worker: "local" | "queue"; agent_key_configured: boolean };

const json = (body: unknown) => JSON.stringify(body);

export const api = {
  register: (email: string, password: string) => apiFetch<{ access_token: string }>("/auth/register", { method: "POST", body: json({ email, password }) }),
  login: (email: string, password: string) => apiFetch<{ access_token: string }>("/auth/login", { method: "POST", body: json({ email, password }) }),
  logout: () => apiFetch<void>("/auth/logout", { method: "POST", headers: { "X-CSRF-Token": decodeURIComponent(readCookie("csrf_token") ?? "") } }),
  me: () => apiFetch<{ id: string; email: string }>("/auth/me"),
  health: () => apiFetch<Health>("/readyz"),
  projects: () => apiFetch<Project[]>("/projects"),
  createProject: (body: { name: string; workflow: string }) => apiFetch<Project>("/projects", { method: "POST", body: json(body) }),
  assets: (projectId: string) => apiFetch<Asset[]>(`/projects/${projectId}/assets`),
  uploadAsset: (projectId: string, file: File) => { const body = new FormData(); body.append("file", file); return apiFetch<Asset>(`/projects/${projectId}/assets`, { method: "POST", body }); },
  assetUrl: (assetId: string) => apiFetch<{ url: string }>(`/assets/${assetId}/url`),
  runs: (projectId: string) => apiFetch<Run[]>(`/projects/${projectId}/runs`),
  run: (runId: string) => apiFetch<Run>(`/runs/${runId}`),
  createRun: (projectId: string, body: { brief: string; skill?: string | null; scene_count?: number; motion_graphics?: boolean }) => apiFetch<Run>(`/projects/${projectId}/runs`, { method: "POST", body: json(body) }),
  answerRun: (runId: string, answer: string) => apiFetch<{ accepted: boolean; status?: string }>(`/runs/${runId}/messages`, { method: "POST", body: json({ answer }) }),
  cancelRun: (runId: string) => apiFetch<Run>(`/runs/${runId}/cancel`, { method: "POST" }),
  renders: (projectId: string) => apiFetch<Render[]>(`/projects/${projectId}/renders`),
  createRender: (projectId: string, preset: string) => apiFetch<Render>(`/projects/${projectId}/renders`, { method: "POST", body: json({ preset }) }),
  outputs: (projectId: string) => apiFetch<Output[]>(`/projects/${projectId}/outputs`),
  timeline: (projectId: string) => apiFetch<TimelineVersion[]>(`/projects/${projectId}/timeline/versions`),
  memory: (projectId: string) => apiFetch<{ content: string }>(`/projects/${projectId}/memory`),
  saveMemory: (projectId: string, content: string) => apiFetch<{ content: string }>(`/projects/${projectId}/memory`, { method: "PUT", body: json({ content }) }),
  storyboard: (projectId: string) => apiFetch<import("../components/StoryboardPanel").Storyboard | null>(`/projects/${projectId}/storyboard`),
  skills: () => apiFetch<Skill[]>("/skills"),
};
