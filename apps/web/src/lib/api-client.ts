import type { EditDoc } from "./manual-edit";

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
export type Asset = { id: string; project_id: string; filename: string; kind: string; mime_type: string; size_bytes: number; storage_key: string; status: "uploaded" | "ready" | "failed" | string; probe?: AssetProbe; thumbnail_url?: string | null; transcript_status?: "transcribing" | "cleaning" | "ready" | "failed" | null; transcript_language?: string | null; transcript_reviewed?: boolean; role?: "clip" | "resource" | string; created_at: string };
export type TranscriptWord = { id: string; text: string; start_ms: number; end_ms: number; segment?: number };
export type Transcript = { asset_id: string; words: TranscriptWord[]; language?: string | null; reviewed: boolean; status?: string | null };
export type RunStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled" | "waiting_for_approval" | "revision_requested";
export type Run = { id: string; project_id: string; status: RunStatus | string; brief: string; skill?: string | null; sdk_session_id?: string | null; usage: Record<string, unknown>; created_at: string; mode?: "fast" | "agent" | string; asset_id?: string | null };
export type Render = { id: string; project_id: string; preset: string; status: string; output_url?: string | null; error?: string | null; created_at: string };
export type Output = { name: string; path: string; size_bytes: number; modified_at: string; url: string; composition?: string | null; skill?: string | null; title?: string | null; run_id?: string | null; edit_id?: string | null };
export type BrandKit = { colors: string[]; fonts: string[]; notes: string };
export type Skill = { id: string; name: string; description: string; scope: "builtin" | "library" | "user" | "project" | string; enabled: boolean; fast?: boolean; fast_engine?: "style" | "generic" | string | null; preview_url?: string | null; cover_url?: string | null };
export type TimelineItem = { id: string; type: string; start_ms: number; end_ms: number; label?: string };
export type TimelineTrack = { id: string; type: string; items?: TimelineItem[] };
export type TimelineVersion = { version: number; source?: string; data: { duration_ms?: number; fps?: number; width?: number; height?: number; tracks?: TimelineTrack[] } };
export type StudioState = { status: "closed" | "starting" | "ready" | "failed"; url?: string | null; composition?: string | null; error?: string | null };
export type StyleClone = { id: string; status: "queued" | "downloading" | "analyzing" | "completed" | "failed" | string; urls: string[]; name: string; notes: string; kind?: "clone" | "edit" | string; base?: string | null; skill_name?: string | null; error?: string | null; created_at?: string | null };
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
  uploadAsset: (projectId: string, file: File, role: "clip" | "resource" = "clip") => { const body = new FormData(); body.append("file", file); body.append("role", role); return apiFetch<Asset>(`/projects/${projectId}/assets`, { method: "POST", body }); },
  transcript: (assetId: string) => apiFetch<Transcript>(`/assets/${assetId}/transcript`),
  saveTranscript: (assetId: string, words: TranscriptWord[], language: string | null) => apiFetch<Transcript>(`/assets/${assetId}/transcript`, { method: "PUT", body: json({ words, language }) }),
  alignTranscript: (assetId: string, text: string) => apiFetch<Transcript>(`/assets/${assetId}/transcript/align`, { method: "POST", body: json({ text }) }),
  transcribe: (assetId: string, language: string | null, vocabulary = "") => apiFetch<{ status: string }>(`/assets/${assetId}/transcribe`, { method: "POST", body: json({ language, vocabulary }) }),
  assetUrl: (assetId: string) => apiFetch<{ url: string }>(`/assets/${assetId}/url`),
  edits: (projectId: string) => apiFetch<EditDoc[]>(`/projects/${projectId}/edits`),
  edit: (projectId: string, editId: string) => apiFetch<EditDoc>(`/projects/${projectId}/edits/${editId}`),
  createEdit: (projectId: string, body: { name: string; asset_ids: string[] }) => apiFetch<EditDoc>(`/projects/${projectId}/edits`, { method: "POST", body: json(body) }),
  saveEdit: (projectId: string, doc: EditDoc) => apiFetch<EditDoc>(`/projects/${projectId}/edits/${doc.id}`, { method: "PUT", body: json(doc) }),
  deleteEdit: (projectId: string, editId: string) => apiFetch<void>(`/projects/${projectId}/edits/${editId}`, { method: "DELETE" }),
  rebuildCaptions: (projectId: string, editId: string) => apiFetch<EditDoc>(`/projects/${projectId}/edits/${editId}/captions`, { method: "POST" }),
  exportEdit: (projectId: string, editId: string) => apiFetch<Render>(`/projects/${projectId}/edits/${editId}/render`, { method: "POST" }),
  runs: (projectId: string) => apiFetch<Run[]>(`/projects/${projectId}/runs`),
  run: (runId: string) => apiFetch<Run>(`/runs/${runId}`),
  createRun: (projectId: string, body: { brief: string; skill?: string | null; scene_count?: number; motion_graphics?: boolean; mode?: "fast" | "agent"; asset_id?: string | null; quick?: boolean; resources?: string[]; kind?: "people" | "motion" | "product"; intensity?: "minimal" | "balanced" | "bold"; clips?: string[]; cut?: boolean; script?: string; caption_skill?: string | null; brand?: BrandKit | null }) => apiFetch<Run>(`/projects/${projectId}/runs`, { method: "POST", body: json(body) }),
  answerRun: (runId: string, answer: string, resources: string[] = []) => apiFetch<{ accepted: boolean; status?: string }>(`/runs/${runId}/messages`, { method: "POST", body: json({ answer, resources }) }),
  cancelRun: (runId: string) => apiFetch<Run>(`/runs/${runId}/cancel`, { method: "POST" }),
  renders: (projectId: string) => apiFetch<Render[]>(`/projects/${projectId}/renders`),
  createRender: (projectId: string, preset: string, composition?: string | null) => apiFetch<Render>(`/projects/${projectId}/renders`, { method: "POST", body: json({ preset, composition: composition ?? null }) }),
  outputs: (projectId: string) => apiFetch<Output[]>(`/projects/${projectId}/outputs`),
  compositionTimeline: (projectId: string, composition?: string | null) => apiFetch<TimelineVersion | null>(`/projects/${projectId}/timeline/composition${composition ? `?composition=${encodeURIComponent(composition)}` : ""}`),
  timeline: (projectId: string) => apiFetch<TimelineVersion[]>(`/projects/${projectId}/timeline/versions`),
  memory: (projectId: string) => apiFetch<{ content: string }>(`/projects/${projectId}/memory`),
  saveMemory: (projectId: string, content: string) => apiFetch<{ content: string }>(`/projects/${projectId}/memory`, { method: "PUT", body: json({ content }) }),
  storyboard: (projectId: string) => apiFetch<import("../components/StoryboardPanel").Storyboard | null>(`/projects/${projectId}/storyboard`),
  skills: () => apiFetch<Skill[]>("/skills"),
  studio: (projectId: string) => apiFetch<StudioState>(`/projects/${projectId}/studio`),
  openStudio: (projectId: string, composition?: string | null) => apiFetch<StudioState>(`/projects/${projectId}/studio`, { method: "POST", body: json({ composition: composition ?? null }) }),
  styleClones: () => apiFetch<StyleClone[]>("/style-extractions"),
  setSkillPreview: (name: string, body: { project_id: string; path: string }) => apiFetch<{ status: string }>(`/skills/${name}/preview`, { method: "POST", body: json(body) }),
  generateSkillPreview: (name: string) => apiFetch<Run>(`/skills/${name}/preview/generate`, { method: "POST" }),
  editSkill: (body: { skill: string; request: string; save_as?: string | null }) => apiFetch<StyleClone>("/skill-edits", { method: "POST", body: json(body) }),
  skillVersions: (name: string) => apiFetch<{ id: string; saved_at: string }[]>(`/skills/${name}/versions`),
  restoreSkill: (name: string) => apiFetch<Skill>(`/skills/${name}/restore`, { method: "POST" }),
  cloneStyle: (body: { urls: string[]; name: string; notes?: string; base?: string | null }) => apiFetch<StyleClone>("/style-extractions", { method: "POST", body: json(body) }),
};
