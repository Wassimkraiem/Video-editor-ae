import { getAccessToken, refreshSession } from "./api-client";

export type ServerEvent<T> = { id: string; data: T };

/**
 * Subscribe to an SSE endpoint with an Authorization header (EventSource
 * cannot send one). Reconnects with backoff and resumes from Last-Event-ID,
 * refreshing the access token when the server answers 401.
 */
export function subscribeSSE<T>(url: string, onEvent: (event: ServerEvent<T>) => void, onError?: (error: unknown) => void) {
  const controller = new AbortController();
  let lastEventId = "";
  let attempt = 0;

  const connect = async (): Promise<void> => {
    while (!controller.signal.aborted) {
      try {
        const headers: Record<string, string> = lastEventId ? { "Last-Event-ID": lastEventId } : {};
        const token = getAccessToken();
        if (token) headers.Authorization = `Bearer ${token}`;
        const response = await fetch(url, { headers, signal: controller.signal });
        if (response.status === 401 && (await refreshSession())) continue;
        if (!response.ok || !response.body) throw new Error(`Event stream failed (${response.status})`);
        attempt = 0;
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const chunks = buffer.split("\n\n");
          buffer = chunks.pop() ?? "";
          for (const chunk of chunks) {
            const id = chunk.match(/^id: (.+)$/m)?.[1];
            const data = chunk.match(/^data: (.+)$/m)?.[1];
            if (id && data) { lastEventId = id; onEvent({ id, data: JSON.parse(data) as T }); }
          }
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        onError?.(error);
      }
      attempt += 1;
      await new Promise((resolve) => setTimeout(resolve, Math.min(10_000, 500 * 2 ** attempt)));
    }
  };
  void connect();
  return () => controller.abort();
}
