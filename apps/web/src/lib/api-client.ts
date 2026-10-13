export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

let accessToken: string | null = null;
export function setAccessToken(token: string | null) { accessToken = token; }

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(`${API_URL}${path}`, { ...init, headers, credentials: "include" });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(problem.detail ?? "Request failed");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export type Project = { id: string; owner_id: string; name: string; workflow: string; profile: Record<string, unknown>; created_at: string; updated_at: string };
export type Asset = { id: string; project_id: string; filename: string; kind: string; mime_type: string; size_bytes: number; storage_key: string; status: string; probe?: Record<string, unknown>; created_at: string };
export type Run = { id: string; project_id: string; status: string; brief: string; usage: Record<string, unknown> };
export type Render = { id: string; project_id: string; preset: string; status: string; output_url?: string };

export const api = {
  register: (email: string, password: string) => apiFetch<{ access_token: string }>("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }),
  login: (email: string, password: string) => apiFetch<{ access_token: string }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  projects: () => apiFetch<Project[]>("/projects"),
  createProject: (body: { name: string; workflow: string }) => apiFetch<Project>("/projects", { method: "POST", body: JSON.stringify(body) }),
  uploadAsset: (projectId: string, file: File) => { const body = new FormData(); body.append("file", file); return apiFetch<Asset>(`/projects/${projectId}/assets`, { method: "POST", body }); },
  createRun: (projectId: string, brief: string, sceneCount = 1, motionGraphics = false) => apiFetch<Run>(`/projects/${projectId}/runs`, { method: "POST", body: JSON.stringify({ brief, scene_count: sceneCount, motion_graphics: motionGraphics }) }),
  answerRun: (runId: string, answer: string) => apiFetch<{ accepted: boolean }>(`/runs/${runId}/messages`, { method: "POST", body: JSON.stringify({ answer }) }),
  createRender: (projectId: string, preset: string) => apiFetch<Render>(`/projects/${projectId}/renders`, { method: "POST", body: JSON.stringify({ preset }) }),
  timeline: (projectId: string) => apiFetch<unknown[]>(`/projects/${projectId}/timeline/versions`),
};
