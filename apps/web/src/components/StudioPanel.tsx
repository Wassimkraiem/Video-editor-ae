"use client";

import { useEffect, useState } from "react";
import { api, type StudioState } from "../lib/api-client";
import { Button, Card, Empty, Spinner } from "./ui";
import { AlertIcon, LayersIcon } from "./icons";

/**
 * HyperFrames Studio, embedded: the full timeline editor for the project's
 * reel. Edits save straight into the composition files; Render picks them up.
 */
export type StudioRequest = { composition: string; nonce: number };

export function StudioPanel({ projectId, composition, onRender, rendering, request }: { projectId?: string; composition?: string | null; onRender: (composition?: string | null) => void; rendering: boolean; request?: StudioRequest }) {
  const [state, setState] = useState<StudioState>({ status: "closed" });
  const [frameKey, setFrameKey] = useState(0);

  // "Open in Studio" on a video switches Studio to that video's reel.
  useEffect(() => {
    if (request && projectId) void open(request.composition);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request?.nonce, projectId]);

  useEffect(() => {
    if (!projectId) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      const next = await api.studio(projectId).catch(() => ({ status: "closed" }) as StudioState);
      if (stopped) return;
      setState(next);
      if (next.status === "starting") timer = setTimeout(() => void poll(), 1500);
    };
    void poll();
    return () => { stopped = true; if (timer) clearTimeout(timer); };
  }, [projectId, frameKey]);

  async function open(reel?: string | null) {
    if (!projectId) return;
    setState(await api.openStudio(projectId, reel ?? composition ?? state.composition));
    setFrameKey((key) => key + 1);
  }

  const hasComposition = Boolean(composition);
  // Studio may still be showing another video's reel; only embed this one's.
  const ready = state.status === "ready" && state.url && (!composition || state.composition === composition);
  return (
    <Card
      className="flex h-[calc(100vh-10rem)] min-h-[620px] flex-col overflow-hidden"
      title={<span className="flex items-center gap-2"><LayersIcon className="text-accent-soft" /> Studio {state.composition && <span className="hidden truncate font-normal text-slate-500 md:inline">{state.composition}</span>}</span>}
      action={
        <div className="flex items-center gap-2">
          {ready && <a href={state.url ?? undefined} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center rounded-lg px-2.5 text-xs text-slate-300 hover:bg-white/[0.06]">Open in tab</a>}
          {ready && <Button size="sm" variant="secondary" onClick={() => void open()}>Reload</Button>}
          <Button size="sm" onClick={() => onRender(composition)} disabled={!hasComposition || rendering} title="Render the reel with your Studio edits">{rendering ? <><Spinner /> Rendering</> : "Render"}</Button>
        </div>
      }
    >
      {ready ? (
        <iframe key={frameKey} src={state.url ?? undefined} title="HyperFrames Studio" className="h-full w-full flex-1 border-0 bg-black" allow="autoplay; fullscreen; clipboard-read; clipboard-write" />
      ) : (
        <div className="flex flex-1 items-center justify-center">
          {!hasComposition ? (
            <Empty icon={<LayersIcon />} title="No reel to edit yet">Run an edit with the agent first. Studio opens the HyperFrames project it builds.</Empty>
          ) : state.status === "starting" ? (
            <div className="flex items-center gap-2 text-sm text-slate-400"><Spinner /> Starting Studio…</div>
          ) : (
            <div className="max-w-md text-center">
              {state.status === "failed" && <p className="mb-4 flex items-start gap-2 rounded-lg bg-red-500/10 px-3 py-2 text-left text-xs text-red-200"><AlertIcon className="mt-0.5 shrink-0" />{state.error}</p>}
              <p className="text-lg font-semibold text-white">Edit by hand in HyperFrames Studio</p>
              <p className="mt-2 text-sm text-slate-400">Fix caption text and timing, move or trim clips, tweak cards, then render. For bigger changes, select an element in Studio and ask the agent: it can see your selection.</p>
              <Button className="mt-5" onClick={() => void open()}>Open Studio</Button>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
