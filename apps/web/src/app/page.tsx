"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AgentPanel, stylesFrom } from "../components/AgentPanel";
import { AuthPanel } from "../components/AuthPanel";
import { FilmIcon, LogoutIcon } from "../components/icons";
import { PreviewPanel, type PreviewSource } from "../components/PreviewPanel";
import { ProjectMemoryEditor } from "../components/ProjectMemoryEditor";
import { AssetLibrary, ProjectList } from "../components/Sidebar";
import { StoryboardPanel, type Storyboard } from "../components/StoryboardPanel";
import { TimelinePanel } from "../components/TimelinePanel";
import { Badge, Spinner } from "../components/ui";
import type { RunEvent } from "../lib/agent-events";
import { API_URL, api, refreshSession, setAccessToken, type Asset, type Health, type Output, type Project, type Render, type Run, type Skill, type TimelineVersion } from "../lib/api-client";
import { subscribeSSE } from "../lib/sse";

const TURN_END = new Set(["agent.succeeded", "agent.failed", "run.cancelled"]);

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
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [storyboard, setStoryboard] = useState<Storyboard>();
  const [preview, setPreview] = useState<PreviewSource>();
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
      setPreview({ url: newest.url, title: newest.name, subtitle: newest.path.split("/").slice(0, -1).join("/") });
    }
    latestOutput.current = newest?.path;
  }, []);

  const refreshProject = useCallback(async (projectId: string) => {
    await Promise.all([
      api.assets(projectId).then(setAssets).catch(() => setAssets([])),
      api.renders(projectId).then(setRenders).catch(() => setRenders([])),
      api.timeline(projectId).then((versions) => setTimeline(versions[versions.length - 1])).catch(() => setTimeline(undefined)),
      api.storyboard(projectId).then((board) => setStoryboard(board ?? undefined)).catch(() => setStoryboard(undefined)),
      refreshOutputs(projectId),
    ]);
  }, [refreshOutputs]);

  // Load everything for the selected project and follow its ingest events.
  useEffect(() => {
    if (session !== "signed-in" || !activeId) return;
    setPreview(undefined);
    latestOutput.current = undefined;
    setRun(undefined);
    setEvents([]);
    void refreshProject(activeId);
    void api.runs(activeId).then((runs) => setRun(runs[0])).catch(() => undefined);
    return subscribeSSE<RunEvent>(`${API_URL}/projects/${activeId}/events`, ({ data }) => {
      if (data.type.startsWith("ingest.")) void api.assets(activeId).then(setAssets).catch(() => undefined);
    });
  }, [session, activeId, refreshProject]);

  // Stream the current run's conversation.
  const runId = run?.id;
  useEffect(() => {
    if (!runId || !activeId) return;
    setEvents([]);
    return subscribeSSE<RunEvent>(`${API_URL}/runs/${runId}/events`, ({ id, data }) => {
      setEvents((current) => (current.some((event) => event.id === id) ? current : [...current, { ...data, id }]));
      if (data.type === "agent.message" || TURN_END.has(data.type)) void api.run(runId).then(setRun).catch(() => undefined);
      if (TURN_END.has(data.type)) void refreshProject(activeId).then(() => refreshOutputs(activeId, true));
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

  async function upload(files: File[]) {
    if (!activeId) return;
    for (const file of files) {
      const asset = await api.uploadAsset(activeId, file);
      setAssets((current) => [asset, ...current.filter((item) => item.id !== asset.id)]);
    }
  }

  async function previewAsset(asset: Asset) {
    const { url } = await api.assetUrl(asset.id);
    setPreview({ url, title: asset.filename, subtitle: "source" });
  }

  async function startRun(brief: string, skill: string | null) {
    if (!activeId) return;
    const next = await api.createRun(activeId, { brief, skill });
    setRun(next);
    if (next.status === "waiting_for_approval") void api.storyboard(activeId).then((board) => setStoryboard(board ?? undefined)).catch(() => undefined);
  }

  async function reply(text: string) {
    if (!run) return;
    const result = await api.answerRun(run.id, text);
    setRun({ ...run, status: result.status ?? run.status });
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

  const loadMemory = useCallback((projectId: string) => api.memory(projectId).then((memory) => memory.content), []);
  const saveMemory = useCallback(async (projectId: string, content: string) => { await api.saveMemory(projectId, content); }, []);

  if (session === "booting") return <main className="flex min-h-screen items-center justify-center text-slate-500"><Spinner /></main>;
  if (session === "signed-out") return <AuthPanel onAuthenticated={(token) => { setAccessToken(token); setSession("signed-in"); }} />;

  return (
    <main className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-10 border-b border-line bg-ink/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1680px] items-center gap-4 px-4 lg:px-6">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-white shadow-glow"><FilmIcon /></div>
            <span className="text-sm font-semibold text-white">Studio</span>
          </div>
          <span className="text-slate-600">/</span>
          <h1 className="min-w-0 truncate text-sm font-medium text-slate-200">{active?.name ?? "No project"}</h1>
          {active && <Badge>{active.workflow.replace(/-/g, " ")}</Badge>}
          <div className="ml-auto flex items-center gap-3">
            {health && <Badge tone={health.agent_key_configured ? "success" : "warning"}>{health.worker === "local" ? "Local worker" : "Queue worker"}{health.agent_key_configured ? "" : " · no API key"}</Badge>}
            {email && <span className="hidden text-xs text-slate-500 sm:inline">{email}</span>}
            <button onClick={() => void signOut()} className="rounded-lg p-2 text-slate-400 transition hover:bg-white/[0.06] hover:text-white" aria-label="Sign out"><LogoutIcon /></button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid w-full max-w-[1680px] flex-1 gap-4 p-4 lg:grid-cols-[260px_minmax(0,1fr)_400px] lg:p-6">
        <aside className="space-y-4">
          <ProjectList projects={projects} activeId={activeId} onSelect={setActiveId} onCreate={createProject} />
          <AssetLibrary assets={assets} onUpload={upload} onPreview={(asset) => void previewAsset(asset)} disabled={!activeId} />
        </aside>

        <section className="min-w-0 space-y-4">
          <PreviewPanel
            source={preview}
            outputs={outputs}
            renders={renders}
            onSelect={setPreview}
            canRender={Boolean(activeId)}
            onRender={() => { if (activeId) void api.createRender(activeId, "preview").then((render) => setRenders((current) => [render, ...current])); }}
          />
          <TimelinePanel version={timeline} />
          {storyboard && storyboard.scenes.length > 0 && <StoryboardPanel storyboard={storyboard} />}
          <ProjectMemoryEditor projectId={activeId} load={loadMemory} onSave={saveMemory} />
        </section>

        <aside className="min-w-0 lg:sticky lg:top-20 lg:h-[calc(100vh-6.5rem)]">
          <AgentPanel
            projectId={activeId}
            run={run}
            events={events}
            styles={styles}
            agentReady={health?.agent_key_configured ?? true}
            onStart={startRun}
            onReply={reply}
            onCancel={cancel}
            onNewRun={() => { setRun(undefined); setEvents([]); }}
          />
        </aside>
      </div>
    </main>
  );
}
