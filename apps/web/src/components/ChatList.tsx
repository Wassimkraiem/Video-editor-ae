"use client";

import type { Run } from "../lib/api-client";
import { Button, Card, Empty, StatusBadge } from "./ui";
import { PlusIcon, SparkIcon } from "./icons";

export function timeAgo(value?: string | null) {
  if (!value) return "";
  const seconds = Math.max(0, (Date.now() - new Date(value).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h ago`;
  return new Date(value).toLocaleDateString();
}

/** Every agent conversation in the project, newest first. */
export function ChatList({ runs, activeId, onSelect, onNew }: { runs: Run[]; activeId?: string; onSelect: (run: Run) => void; onNew: () => void }) {
  return (
    <Card title="Chats" action={<Button size="sm" variant="ghost" onClick={onNew} aria-label="New chat"><PlusIcon /></Button>}>
      <ul className="scroll-quiet max-h-[340px] space-y-0.5 overflow-auto p-2">
        {runs.length === 0 && <Empty icon={<SparkIcon />} title="No chats yet">Describe an edit in the agent panel to start one.</Empty>}
        {runs.map((run) => (
          <li key={run.id}>
            <button onClick={() => onSelect(run)} className={`w-full rounded-lg px-2.5 py-2 text-left transition ${activeId === run.id ? "bg-accent/15 ring-1 ring-inset ring-accent/30" : "hover:bg-white/[0.04]"}`}>
              <span className="line-clamp-2 text-xs text-slate-200" dir="auto">{run.brief}</span>
              <span className="mt-1 flex items-center gap-2 text-[11px] text-slate-500">
                <StatusBadge status={run.status} />
                {run.skill && <span className="truncate">{run.skill}</span>}
                <span className="ml-auto shrink-0">{timeAgo(run.created_at)}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
