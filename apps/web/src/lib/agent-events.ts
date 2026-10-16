/**
 * Turn the worker's run events (raw Claude Agent SDK messages tagged with
 * `_type`) into conversation items the studio can render.
 */

export type RunEvent = { id: string; type: string; [key: string]: unknown };

type Block = { _type?: string; text?: string; thinking?: string; id?: string; name?: string; input?: Record<string, unknown>; tool_use_id?: string; content?: unknown; is_error?: boolean | null };
type SdkMessage = { _type?: string; content?: string | Block[]; subtype?: string; is_error?: boolean; total_cost_usd?: number | null; num_turns?: number; duration_ms?: number; result?: string | null; data?: Record<string, unknown> };

export type ToolCall = { id: string; name: string; label: string; detail: string; input: Record<string, unknown>; result?: string; isError?: boolean };

export type ChatItem =
  | { kind: "user"; key: string; text: string; skill?: string | null }
  | { kind: "assistant"; key: string; text: string }
  | { kind: "thinking"; key: string; text: string }
  | { kind: "tool"; key: string; call: ToolCall }
  | { kind: "status"; key: string; tone: "info" | "success" | "error"; text: string; meta?: string }
  | { kind: "question"; key: string; question: string; options: string[] };

const MCP_PREFIX = "mcp__video-editing__";

function short(value: unknown, max = 90) {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (!text) return "";
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function fileName(path: unknown) {
  return typeof path === "string" ? path.replace(/\\/g, "/").split("/").slice(-2).join("/") : "";
}

/** Human labels for the tools the editing agent uses most. */
function describeTool(name: string, input: Record<string, unknown>): { label: string; detail: string } {
  const domain = name.startsWith(MCP_PREFIX) ? name.slice(MCP_PREFIX.length) : null;
  if (name === "Skill") return { label: "Using skill", detail: String(input.skill ?? input.name ?? input.command ?? "") };
  if (name === "Bash") return { label: "Running", detail: short(input.command, 120) };
  if (name === "Write") return { label: "Writing", detail: fileName(input.file_path) };
  if (name === "Edit" || name === "MultiEdit") return { label: "Editing", detail: fileName(input.file_path) };
  if (name === "Read") return { label: "Reading", detail: fileName(input.file_path) };
  if (name === "Glob" || name === "Grep") return { label: name === "Glob" ? "Finding files" : "Searching", detail: short(input.pattern) };
  if (name === "TodoWrite") return { label: "Planning", detail: `${Array.isArray(input.todos) ? input.todos.length : 0} steps` };
  if (domain) return { label: domain.replace(/_/g, " "), detail: short(input, 100) };
  return { label: name, detail: short(input, 100) };
}

function resultText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) return content.map((part) => (typeof part === "object" && part && "text" in part ? String((part as { text: unknown }).text) : "")).join("\n");
  return content == null ? "" : JSON.stringify(content);
}

function formatCost(value: unknown) {
  return typeof value === "number" ? `$${value.toFixed(value < 1 ? 3 : 2)}` : undefined;
}

export function buildChat(events: RunEvent[]): ChatItem[] {
  const items: ChatItem[] = [];
  const tools = new Map<string, ToolCall>();

  for (const event of events) {
    const key = event.id;
    switch (event.type) {
      case "run.created":
        if (typeof event.brief === "string") items.push({ kind: "user", key, text: event.brief, skill: event.skill as string | null });
        if (event.status === "waiting_for_approval") items.push({ kind: "status", key: `${key}-plan`, tone: "info", text: "Storyboard ready: approve it to start the edit" });
        break;
      case "user.answer":
        items.push({ kind: "user", key, text: String(event.answer ?? "") + (Array.isArray(event.resources) && event.resources.length ? `\n📎 ${event.resources.join(", ")}` : "") });
        break;
      case "fast.step": {
        // One row per step: later updates of the same step replace it.
        const step = String(event.step ?? key);
        const tone = event.status === "failed" ? "error" : event.status === "done" ? "success" : "info";
        const cost = typeof event.cost === "number" && event.cost > 0 ? `$${event.cost.toFixed(3)}` : undefined;
        const row: ChatItem = { kind: "status", key: `fast-${step}`, tone, text: `${event.status === "running" ? "…" : ""}${String(event.label ?? step)}`, meta: event.status === "failed" ? short(event.detail, 400) : cost };
        const existing = items.findIndex((item) => item.key === row.key);
        if (existing >= 0) items[existing] = row;
        else items.push(row);
        break;
      }
      case "fast.plan":
        if (event.notes) items.push({ kind: "assistant", key, text: String(event.notes) });
        break;
      case "agent.waiting":
        items.push({ kind: "status", key, tone: "info", text: "Waiting for the clip's transcription to finish before editing" });
        break;
      case "run.cancelled":
        items.push({ kind: "status", key, tone: "error", text: "Run cancelled" });
        break;
      case "agent.failed":
        items.push({ kind: "status", key, tone: "error", text: "The agent stopped", meta: short(event.reason, 400) });
        break;
      case "agent.succeeded": {
        const usage = (event.usage ?? {}) as Record<string, unknown>;
        items.push({ kind: "status", key, tone: "success", text: "Turn complete", meta: formatCost(usage.total_cost_usd) });
        break;
      }
      case "agent.message": {
        const message = (event.message ?? {}) as SdkMessage;
        if (message._type === "AssistantMessage" && Array.isArray(message.content)) {
          message.content.forEach((block, index) => {
            const blockKey = `${key}-${index}`;
            if (block._type === "TextBlock" && block.text?.trim()) items.push({ kind: "assistant", key: blockKey, text: block.text });
            else if (block._type === "ThinkingBlock" && block.thinking?.trim()) items.push({ kind: "thinking", key: blockKey, text: block.thinking });
            else if (block._type === "ToolUseBlock" && block.id && block.name) {
              const input = block.input ?? {};
              const call: ToolCall = { id: block.id, name: block.name, input, ...describeTool(block.name, input) };
              tools.set(block.id, call);
              items.push({ kind: "tool", key: blockKey, call });
            }
          });
        } else if (message._type === "UserMessage" && Array.isArray(message.content)) {
          for (const block of message.content) {
            if (block._type !== "ToolResultBlock" || !block.tool_use_id) continue;
            const call = tools.get(block.tool_use_id);
            if (!call) continue;
            call.result = resultText(block.content);
            call.isError = Boolean(block.is_error);
            if (call.name === `${MCP_PREFIX}ask_user` && !call.isError) {
              try {
                const parsed = JSON.parse(call.result) as { question?: string; options?: string[] };
                if (parsed.question) items.push({ kind: "question", key: `${key}-q-${call.id}`, question: parsed.question, options: parsed.options ?? [] });
              } catch { /* not JSON: shown as a plain tool result */ }
            }
          }
        } else if (message._type === "ResultMessage" && message.is_error) {
          // subtype can be "success" even when the CLI reports an error (for
          // example an invalid API key), so show the CLI's message instead.
          items.push({ kind: "status", key, tone: "error", text: "The run ended with an error", meta: short(message.result ?? message.subtype, 400) });
        }
        break;
      }
      default:
        break;
    }
  }
  return items;
}

export function isTurnFinished(events: RunEvent[]) {
  const last = [...events].reverse().find((event) => ["agent.succeeded", "agent.failed", "run.cancelled", "user.answer", "run.created"].includes(event.type));
  return Boolean(last && ["agent.succeeded", "agent.failed", "run.cancelled"].includes(last.type));
}
