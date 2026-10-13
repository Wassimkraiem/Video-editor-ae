export type ServerEvent<T> = { id: string; data: T };

export function subscribeSSE<T>(url: string, onEvent: (event: ServerEvent<T>) => void, onError?: (error: unknown) => void, token?: string | null) {
  const controller = new AbortController();
  let lastEventId = "";
  const connect = async () => {
    try {
      const headers: Record<string, string> = lastEventId ? { "Last-Event-ID": lastEventId } : {};
      if (token) headers.Authorization = `Bearer ${token}`;
      const response = await fetch(url, { headers, signal: controller.signal });
      if (!response.body) throw new Error("SSE response has no body");
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
          if (id && data) { lastEventId = id; onEvent({ id, data: JSON.parse(data) }); }
        }
      }
    } catch (error) { if (!controller.signal.aborted) onError?.(error); }
  };
  void connect();
  return () => controller.abort();
}
