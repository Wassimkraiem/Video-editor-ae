/** Generated-client boundary. Run the OpenAPI export job to replace this file. */
export type ProblemDetail = { type: string; title: string; status: number; detail: string };
export type Project = { id: string; owner_id: string; name: string; workflow: string; profile: Record<string, unknown>; created_at: string; updated_at: string };
export type Asset = { id: string; project_id: string; filename: string; kind: string; mime_type: string; size_bytes: number; storage_key: string; status: string };
export type TimelineVersion = { version: number; parent_version: number | null; schema_version: string; data: Record<string, unknown>; diff: Record<string, unknown>[] };
export type Run = { id: string; project_id: string; status: string; brief: string; usage: Record<string, unknown> };

export function createApiClient(baseUrl: string, token?: () => string | null) {
  return async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("Content-Type", "application/json");
    const value = token?.();
    if (value) headers.set("Authorization", `Bearer ${value}`);
    const response = await fetch(`${baseUrl}${path}`, { ...init, headers, credentials: "include" });
    if (!response.ok) throw new Error((await response.text()) || response.statusText);
    return response.status === 204 ? undefined as T : response.json() as Promise<T>;
  };
}
