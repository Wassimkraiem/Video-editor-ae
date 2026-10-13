import { describe, expect, it } from "vitest";
import { buildChat, isTurnFinished, type RunEvent } from "./agent-events";

const events: RunEvent[] = [
  { id: "1", type: "run.created", status: "queued", brief: "Edit my clip", skill: "wassim-style" },
  { id: "2", type: "agent.message", message: { _type: "AssistantMessage", content: [
    { _type: "TextBlock", text: "Plan: transcribe, then build." },
    { _type: "ToolUseBlock", id: "t1", name: "Skill", input: { skill: "wassim-style" } },
    { _type: "ToolUseBlock", id: "t2", name: "mcp__video-editing__ask_user", input: { question: "Palette?", options: ["Blue", "Brand"] } },
  ] } },
  { id: "3", type: "agent.message", message: { _type: "UserMessage", content: [
    { _type: "ToolResultBlock", tool_use_id: "t1", content: "Launching skill", is_error: false },
    { _type: "ToolResultBlock", tool_use_id: "t2", content: JSON.stringify({ status: "needs_user", question: "Palette?", options: ["Blue", "Brand"] }), is_error: false },
  ] } },
  { id: "4", type: "agent.succeeded", usage: { total_cost_usd: 0.4213 } },
];

describe("buildChat", () => {
  it("renders the brief, text, tool calls with results, questions and cost", () => {
    const items = buildChat(events);
    expect(items.map((item) => item.kind)).toEqual(["user", "assistant", "tool", "tool", "question", "status"]);
    const skill = items[2];
    expect(skill.kind === "tool" && skill.call.label).toBe("Using skill");
    expect(skill.kind === "tool" && skill.call.result).toBe("Launching skill");
    const question = items[4];
    expect(question.kind === "question" && question.options).toEqual(["Blue", "Brand"]);
    const done = items[5];
    expect(done.kind === "status" && done.meta).toBe("$0.421");
  });

  it("knows when the agent finished its turn", () => {
    expect(isTurnFinished(events)).toBe(true);
    expect(isTurnFinished([...events, { id: "5", type: "user.answer", answer: "Blue" }])).toBe(false);
  });
});
