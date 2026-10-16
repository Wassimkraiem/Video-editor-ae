"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AgentPanel, stylesFrom, type StartOptions } from "../components/AgentPanel";
import { AppSidebar, type View } from "../components/AppSidebar";
import { CreateFlow, type Step } from "../components/CreateFlow";
import { isResource } from "../components/ResourcePicker";
import { AuthPanel } from "../components/AuthPanel";
import { LibraryView } from "../components/LibraryView";
import { PreviewPanel, type PreviewSource } from "../components/PreviewPanel";
import { ProjectMemoryEditor } from "../components/ProjectMemoryEditor";
import { StoryboardPanel, type Storyboard } from "../components/StoryboardPanel";
import { StudioPanel, type StudioRequest } from "../components/StudioPanel";
import { StylesView } from "../components/StylesView";
import { TimelinePanel } from "../components/TimelinePanel";
import { Spinner } from "../components/ui";
import type { RunEvent } from "../lib/agent-events";
import { API_URL, api, refreshSession, setAccessToken, type Asset, type Health, type Output, type Project, type Render, type Run, type Skill, type TimelineVersion } from "../lib/api-client";
import { subscribeSSE } from "../lib/sse";

const TURN_END = new Set(["agent.succeeded", "agent.failed", "run.cancelled"]);
const TITLES: Record<View, { title: string; hint: string }> = {
  create: { title: "Create", hint: "Upload, approve the transcript, pick a style, edit" },
  library: { title: "Library", hint: "Every video of the project, from raw footage to finished edits" },
  styles: { title: "Styles", hint: "Your house styles, and new ones cloned from reference videos" },
};

export default function StudioPage() {
  const [session, setSession] = useState<"booting" | "signed-out" | "signed-in">("booting");
  const [email, setEmail] = useState("");
  const [health, setHealth] = useState<Health>();
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeId, setActiveId] = useState<string>();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [outputs, setOutputs] = useState<Output[]>([]);
  const [renders, setRenders] = useState<Render[]>([]);
  const [timeline, setTimeline] = useState<TimelineVersion>();
  const [run, setRun] = useState<Run>();
  const [runs, setRuns] = useState<Run[]>([]);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [storyboard, setStoryboard] = useState<Storyboard>();
  const [preview, setPreview] = useState<PreviewSource>();
  const [view, setView] = useState<View>("create");
  const [step, setStep] = useState<Step>(1);
  const [clipId, setClipId] = useState<string>();
  const [studioRequest, setStudioRequest] = useState<StudioRequest>();
  const [stage, setStage] = useState<"preview" | "studio">("preview");
  const latestOutput = useRef<string | undefined>(undefined);

  const active = useMemo(() => projects.find((project) => project.id === activeId), [projects, activeId]);
  const styles = useMemo(() => stylesFrom(skills), [skills]);

  // Restore the session from the httpOnly refresh cookie on reload.
  useEffect(() => {
    void refreshSession().then((token) => setSession(token ? "signed-in" : "signed-out"));
  }, []);

  useEffect(() => {
    if (session !== "signed-in") return;
    void api.me().then((user) => setEmail(user.email)).catch(() => undefined);
    void api.health().then(setHealth).catch(() => undefined);
    void api.skills().then(setSkills).catch(() => setSkills([]));
    void api.projects().then((items) => { setProjects(items); setActiveId((current) => current ?? items[0]?.id); }).catch(() => setProjects([]));
  }, [session]);

  const refreshOutputs = useCallback(async (projectId: string, autoplay = false) => {
    const items = await api.outputs(projectId).catch(() => [] as Output[]);
    setOutputs(items);
    const newest = items[0];
    if (newest && (autoplay || !latestOutput.current) && newest.path !== latestOutput.current) {
      setPreview({ url: newest.url, title: newest.title || newest.name, subtitle: newest.skill ?? undefined, composition: newest.composition, skill: newest.skill });
    }
    latestOutput.current = newest?.path;
  }, []);

  const refreshProject = useCallback(async (projectId: string) => {
    await Promise.all([
      api.assets(projectId).then(setAssets).catch(() => setAssets([])),
      api.renders(projectId).then(setRenders).catch(() => setRenders([])),
      // Style edits live in a HyperFrames composition; fall back to timeline.json cuts.
      Promise.all([api.compositionTimeline(projectId).catch(() => null), api.timeline(projectId).catch(() => [] as TimelineVersion[])])
        .then(([composition, versions]) => setTimeline(composition ?? versions[versions.length - 1])),
      api.storyboard(projectId).then((board) => setStoryboard(board ?? undefined)).catch(() => setStoryboard(undefined)),
      refreshOutputs(projectId),
    ]);
  }, [refreshOutputs]);

  // Load everything for the selected project and follow its upload events.
  useEffect(() => {
    if (session !== "signed-in" || !activeId) return;
    setPreview(undefined);
    setClipId(undefined);
    setStep(1);
    latestOutput.current = undefined;
    setRun(undefined);
    setEvents([]);
    void refreshProject(activeId);
    void api.runs(activeId).then((items) => { setRuns(items); setRun(items[0]); }).catch(() => setRuns([]));
    return subscribeSSE<RunEvent>(`${API_URL}/projects/${activeId}/events`, ({ data }) => {
      if (/^(ingest|transcribe)\./.test(data.type) || data.type === "asset.uploaded" || data.type === "transcript.edited") void api.assets(activeId).then(setAssets).catch(() => undefined);
    });
  }, [session, activeId, refreshProject]);

  // Stream the selected chat.
  const runId = run?.id;
  useEffect(() => {
    if (!runId || !activeId) return;
    setEvents([]);
    return subscribeSSE<RunEvent>(`${API_URL}/runs/${runId}/events`, ({ id, data }) => {
      setEvents((current) => (current.some((event) => event.id === id) ? current : [...current, { ...data, id }]));
      if (data.type === "agent.message" || TURN_END.has(data.type)) void api.run(runId).then(setRun).catch(() => undefined);
      if (TURN_END.has(data.type)) {
        void refreshProject(activeId).then(() => refreshOutputs(activeId, true));
        void api.runs(activeId).then(setRuns).catch(() => undefined);
      }
    });
  }, [runId, activeId, refreshProject, refreshOutputs]);

  // Poll while a render is in flight.
  const rendering = renders.some((render) => render.status === "queued" || render.status === "running");
  useEffect(() => {
    if (!rendering || !activeId) return;
    const timer = setInterval(() => {
      void api.renders(activeId).then((items) => {
        setRenders(items);
        if (!items.some((render) => render.status === "queued" || render.status === "running")) void refreshOutputs(activeId, true);
      });
    }, 2000);
    return () => clearInterval(timer);
  }, [rendering, activeId, refreshOutputs]);

  async function createProject(name: string, workflow: string) {
    const project = await api.createProject({ name, workflow });
    setProjects((current) => [project, ...current]);
    setActiveId(project.id);
  }

  async function upload(files: File[]): Promise<Asset[]> {
    if (!activeId) return [];
    const uploaded: Asset[] = [];
    for (const file of files) {
      const asset = await api.uploadAsset(activeId, file);
      uploaded.push(asset);
      setAssets((current) => [asset, ...current.filter((item) => item.id !== asset.id)]);
    }
    return uploaded;
  }

  async function uploadResources(files: File[]): Promise<Asset[]> {
    if (!activeId) return [];
    const uploaded = await Promise.all(files.map((file) => api.uploadAsset(activeId, file, "resource")));
    setAssets((current) => [...uploaded, ...current.filter((item) => !uploaded.some((added) => added.id === item.id))]);
    return uploaded;
  }

  async function previewAsset(asset: Asset) {
    const { url } = await api.assetUrl(asset.id);
    setPreview({ url, title: asset.filename, subtitle: "source" });
    setStage("preview");
  }

  async function startRun(brief: string, skill: string | null, options: StartOptions) {
    if (!activeId) return;
    const next = await api.createRun(activeId, { brief, skill, mode: options.mode, asset_id: options.assetId ?? null, quick: options.quick, resources: options.resources ?? [] });
    setRun(next);
    setRuns((current) => [next, ...current]);
    if (next.status === "waiting_for_approval") void api.storyboard(activeId).then((board) => setStoryboard(board ?? undefined)).catch(() => undefined);
  }

  async function reply(text: string, resources: string[] = []) {
    if (!run) return;
    const result = await api.answerRun(run.id, text, resources);
    const updated = { ...run, status: result.status ?? run.status };
    setRun(updated);
    setRuns((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    if (activeId) void api.storyboard(activeId).then((board) => setStoryboard(board ?? undefined)).catch(() => undefined);
  }

  async function cancel() {
    if (run) setRun(await api.cancelRun(run.id));
  }

  async function signOut() {
    await api.logout().catch(() => undefined);
    setAccessToken(null);
    setSession("signed-out");
    setProjects([]);
    setActiveId(undefined);
  }

  const refreshSkills = useCallback(() => { void api.skills().then(setSkills).catch(() => undefined); }, []);
  const loadMemory = useCallback((projectId: string) => api.memory(projectId).then((memory) => memory.content), []);
  const saveMemory = useCallback(async (projectId: string, content: string) => { await api.saveMemory(projectId, content); }, []);
  const startRender = (composition?: string | null) => { if (activeId) void api.createRender(activeId, "preview", composition).then((item) => setRenders((current) => [item, ...current])); };
  const openInStudio = (composition: string) => {
    setStudioRequest({ composition, nonce: Date.now() });
    setStage("studio");
    setStep(4);
    setView("create");
  };
  const playOutput = (output: Output) => {
    setPreview({ url: output.url, title: output.title || output.name, subtitle: output.skill ?? undefined, composition: output.composition, skill: output.skill });
    setStage("preview");
    setStep(4);
    setView("create");
  };
  const newChat = () => { setRun(undefined); setEvents([]); };
  const refreshAssets = () => { if (activeId) void api.assets(activeId).then(setAssets).catch(() => undefined); };
  const openRun = (item: Run) => {
    setRun(item);
    if (item.asset_id) setClipId(item.asset_id);
    setStep(4);
    setView("create");
  };
  const reviewCount = assets.filter((asset) => !isResource(asset) && asset.transcript_status === "ready" && !asset.transcript_reviewed).length;

  if (session === "booting") return <main className="flex min-h-screen items-center justify-center text-slate-500"><Spinner /></main>;
  if (session === "signed-out") return <AuthPanel onAuthenticated={(token) => { setAccessToken(token); setSession("signed-in"); }} />;

  return (
    <main className="flex min-h-screen">
      <AppSidebar
        view={view}
        onView={setView}
        projects={projects}
        activeId={activeId}
        onSelectProject={setActiveId}
        onCreateProject={createProject}
        reviewCount={reviewCount}
        health={health}
        email={email}
        onSignOut={() => void signOut()}
      />

      <div className="min-w-0 flex-1">
        <header className="flex items-end justify-between gap-4 px-6 pb-2 pt-5">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-white">{TITLES[view].title}</h1>
            <p className="mt-0.5 truncate text-sm text-slate-500">{active ? <><span className="text-slate-300">{active.name}</span> · </> : null}{TITLES[view].hint}</p>
          </div>
          {view === "create" && step === 4 && (
            <div className="flex shrink-0 items-center gap-1 rounded-xl bg-white/[0.04] p-1">
              {(["preview", "studio"] as const).map((item) => (
                <button key={item} onClick={() => setStage(item)} className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${stage === item ? "bg-accent text-white shadow-glow" : "text-slate-400 hover:text-white"}`}>
                  {item === "preview" ? "Preview & timeline" : "Studio (hand edit)"}
                </button>
              ))}
            </div>
          )}
        </header>

        <div className="px-6 pb-6 pt-3">

          {view === "library" && (
            <LibraryView
              assets={assets.filter((asset) => !isResource(asset))}
              runs={runs}
              outputs={outputs}
              onUpload={upload}
              onPlayAsset={(asset) => { setClipId(asset.id); setStep(asset.transcript_reviewed ? 3 : 2); setView("create"); }}
              onPlayOutput={playOutput}
              onOpenRun={openRun}
              onOpenInStudio={(output) => { if (output.composition) openInStudio(output.composition); }}
            />
          )}

          {view === "styles" && <StylesView skills={skills} onSkillsChanged={refreshSkills} />}

          {view === "create" && (
            <CreateFlow
              step={step}
              onStep={setStep}
              clipId={clipId}
              onClip={setClipId}
              assets={assets}
              skills={skills}
              run={run}
              runs={runs}
              events={events}
              agentReady={health?.agent_key_configured ?? true}
              onUpload={upload}
              onUploadResources={uploadResources}
              onRefreshAssets={refreshAssets}
              onStart={startRun}
              onReply={reply}
              onCancel={cancel}
              onSelectRun={setRun}
              result={stage === "studio" ? (
                <StudioPanel projectId={activeId} hasComposition={Boolean(timeline?.source)} onRender={startRender} rendering={rendering} request={studioRequest} />
              ) : (
                <>
                  <PreviewPanel source={preview} outputs={outputs} renders={renders} onSelect={setPreview} canRender={Boolean(activeId)} onRender={() => startRender(preview?.composition)} onOpenInStudio={openInStudio} />
                  <TimelinePanel version={timeline} onEdit={timeline?.source ? () => setStage("studio") : undefined} />
                  {storyboard && storyboard.scenes.length > 0 && <StoryboardPanel storyboard={storyboard} />}
                  <ProjectMemoryEditor projectId={activeId} load={loadMemory} onSave={saveMemory} />
                </>
              )}
            />
          )}
        </div>
      </div>
    </main>
  );
}
