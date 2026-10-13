"use client";

export type StoryboardScene = {
  id: string;
  title: string;
  start_ms: number;
  end_ms: number;
  assets: string[];
  template: string;
};

export type Storyboard = {
  project_id: string;
  brief: string;
  scenes: StoryboardScene[];
  status: "awaiting_approval" | "approved" | "revision_requested";
};

type StoryboardPanelProps = {
  storyboard: Storyboard;
  onDecision: (decision: "Approve" | "Revise") => void;
};

export function StoryboardPanel({ storyboard, onDecision }: StoryboardPanelProps) {
  return (
    <section aria-label="Storyboard" data-status={storyboard.status}>
      <header>
        <p>Storyboard</p>
        <span>{storyboard.status.replace("_", " ")}</span>
      </header>
      <p>{storyboard.brief}</p>
      <ol>
        {storyboard.scenes.map((scene) => (
          <li key={scene.id}>
            <strong>{scene.title}</strong>
            <span>
              {scene.start_ms}–{scene.end_ms} ms · {scene.template || "custom"}
            </span>
            {scene.assets.length > 0 && <small>{scene.assets.join(", ")}</small>}
          </li>
        ))}
      </ol>
      {storyboard.status === "awaiting_approval" && (
        <div>
          <button type="button" onClick={() => onDecision("Approve")}>Approve and continue</button>
          <button type="button" onClick={() => onDecision("Revise")}>Request changes</button>
        </div>
      )}
    </section>
  );
}
