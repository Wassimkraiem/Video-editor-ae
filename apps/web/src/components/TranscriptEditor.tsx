"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api, mediaUrl, type Asset, type TranscriptWord } from "../lib/api-client";
import { Badge, Button, Card, Empty, Spinner } from "./ui";
import { AlertIcon, CheckIcon, FileIcon } from "./icons";

const LANGUAGES = [
  { value: "tn", label: "Tunisian (Darija · Français · English)" },
  { value: "ar", label: "Arabic only" },
  { value: "fr", label: "French" },
  { value: "en", label: "English" },
  { value: "auto", label: "Auto-detect" },
];

// Display lines: break at pauses, keep them short enough to scan.
const PAUSE_MS = 450;
const MAX_WORDS = 9;
const MAX_CHARS = 56;

function stamp(ms: number) {
  const seconds = Math.floor(ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function transcriptLines(words: TranscriptWord[]): TranscriptWord[][] {
  const lines: TranscriptWord[][] = [];
  let line: TranscriptWord[] = [];
  let chars = 0;
  words.forEach((word, index) => {
    const previous = words[index - 1];
    const pause = previous ? word.start_ms - previous.end_ms : 0;
    const breakHere = line.length > 0 && (pause >= PAUSE_MS || line.length >= MAX_WORDS || chars + word.text.length > MAX_CHARS || (previous && previous.segment !== word.segment && line.length >= 3));
    if (breakHere) {
      lines.push(line);
      line = [];
      chars = 0;
    }
    line.push(word);
    chars += word.text.length + 1;
  });
  if (line.length) lines.push(line);
  return lines;
}

/**
 * Review, fix and approve a clip's transcript. Captions use the approved
 * words exactly, so a wrong word fixed here is fixed in every edit.
 */
export function TranscriptEditor({ assets, assetId, onChanged, onApproved }: { assets: Asset[]; assetId?: string; onChanged: () => void; onApproved?: () => void }) {
  const asset = assets.find((item) => item.id === assetId);
  const [words, setWords] = useState<TranscriptWord[]>([]);
  const [saved, setSaved] = useState("");
  const [language, setLanguage] = useState("tn");
  const [vocabulary, setVocabulary] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string>();
  const [now, setNow] = useState(0);
  const [state, setState] = useState<"idle" | "loading" | "saving" | "error">("idle");
  const [showOptions, setShowOptions] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const status = asset?.transcript_status ?? null;
  const busy = status === "transcribing" || status === "cleaning";

  useEffect(() => {
    if (!assetId) return;
    let cancelled = false;
    setState("loading");
    void api.assetUrl(assetId).then(({ url }) => { if (!cancelled) setVideoUrl(url); }).catch(() => undefined);
    api.transcript(assetId)
      .then((result) => {
        if (cancelled) return;
        setWords(result.words);
        setSaved(JSON.stringify(result.words));
        setLanguage(result.language && LANGUAGES.some((item) => item.value === result.language) ? result.language : "tn");
        setReviewed(result.reviewed);
        setState("idle");
      })
      .catch(() => { if (!cancelled) setState("error"); });
    return () => { cancelled = true; };
    // Reload when transcription finishes for this clip.
  }, [assetId, status]);

  const lines = useMemo(() => transcriptLines(words), [words]);
  const dirty = JSON.stringify(words) !== saved;

  function edit(id: string, text: string) {
    setWords((current) => current.map((word) => (word.id === id ? { ...word, text } : word)));
  }

  function seek(ms: number) {
    if (!video.current) return;
    video.current.currentTime = ms / 1000;
    void video.current.play().catch(() => undefined);
  }

  async function approve() {
    if (!assetId) return;
    setState("saving");
    try {
      const result = await api.saveTranscript(assetId, words, language);
      setWords(result.words);
      setSaved(JSON.stringify(result.words));
      setReviewed(true);
      setState("idle");
      onChanged();
      onApproved?.();
    } catch {
      setState("error");
    }
  }

  async function retranscribe() {
    if (!assetId) return;
    await api.transcribe(assetId, language, vocabulary);
    onChanged();
  }

  if (!asset) return <Card><Empty icon={<FileIcon />} title="No clip selected">Upload a clip first.</Empty></Card>;

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,300px)_minmax(0,1fr)]">
      <div className="space-y-3 lg:sticky lg:top-4 lg:self-start">
        <div className="overflow-hidden rounded-2xl bg-black ring-1 ring-line">
          {videoUrl ? <video ref={video} src={mediaUrl(videoUrl)} controls playsInline onTimeUpdate={(event) => setNow(event.currentTarget.currentTime * 1000)} className="mx-auto max-h-[62vh] w-full bg-black object-contain" /> : <div className="flex aspect-[9/16] items-center justify-center text-slate-600"><Spinner /></div>}
        </div>
        <p className="text-xs leading-relaxed text-slate-500">Click a word to hear it and type to fix it; clear a word to delete it. Timing stays attached to each word, so captions stay in sync.</p>
      </div>

      <Card
        className="min-w-0"
        title={
          <span className="flex items-center gap-2">
            <FileIcon className="text-accent-soft" /> {asset.filename}
            {busy ? <Badge tone="info"><Spinner className="h-2.5 w-2.5 border" /> {status === "cleaning" ? "cleaning up" : "transcribing"}</Badge> : reviewed && !dirty ? <Badge tone="success"><CheckIcon width={10} height={10} /> approved</Badge> : status === "ready" ? <Badge tone="warning">check the words</Badge> : null}
          </span>
        }
        action={
          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" onClick={() => setShowOptions((open) => !open)}>Language & re-transcribe</Button>
            <Button size="sm" onClick={() => void approve()} disabled={busy || words.length === 0 || state === "saving" || (reviewed && !dirty && !onApproved)}>
              {state === "saving" && <Spinner />}{reviewed && !dirty ? (onApproved ? "Continue" : "Approved") : dirty ? "Save & approve" : "Approve transcript"}
            </Button>
          </div>
        }
      >
        {showOptions && (
          <div className="flex flex-wrap items-center gap-2 border-b border-line bg-white/[0.02] px-4 py-3">
            <select value={language} onChange={(event) => setLanguage(event.target.value)} className="h-8 rounded-md border border-line bg-black/30 px-2 text-xs text-slate-200 outline-none" aria-label="Language">
              {LANGUAGES.map((item) => <option key={item.value} value={item.value} className="bg-panel">{item.label}</option>)}
            </select>
            <input value={vocabulary} onChange={(event) => setVocabulary(event.target.value)} placeholder="Spell these your way: Kachabiti, Notion…" className="h-8 min-w-[220px] flex-1 rounded-md border border-line bg-black/30 px-2 text-xs text-slate-200 outline-none placeholder:text-slate-500 focus:border-accent/50" />
            <Button size="sm" variant="secondary" onClick={() => void retranscribe()} disabled={busy}>Re-transcribe</Button>
          </div>
        )}
        <div className="px-4 py-4">
          {busy ? (
            <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-400"><Spinner /> {status === "cleaning" ? "Putting French and English words back in Latin script…" : "Transcribing with Whisper large-v3 on your machine…"}</div>
          ) : status === "failed" ? (
            <p className="flex items-start gap-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-200"><AlertIcon className="mt-0.5 shrink-0" />Transcription failed. Open "Language & re-transcribe" and try again.</p>
          ) : words.length === 0 ? (
            <Empty icon={<FileIcon />} title={state === "loading" ? "Loading…" : "No transcript yet"}>{state === "loading" ? "" : "Open \"Language & re-transcribe\" to transcribe this clip."}</Empty>
          ) : (
            <ol className="space-y-1">
              {lines.map((line) => {
                const active = now >= line[0].start_ms && now < line[line.length - 1].end_ms;
                return (
                  <li key={line[0].id} className={`flex items-baseline gap-3 rounded-lg px-2 py-1 transition ${active ? "bg-accent/[0.08]" : ""}`}>
                    <button onClick={() => seek(line[0].start_ms)} className="w-10 shrink-0 rounded px-1 py-0.5 text-right font-mono text-[11px] tabular-nums text-slate-500 hover:bg-accent/20 hover:text-white">{stamp(line[0].start_ms)}</button>
                    <p dir="auto" className="min-w-0 flex-1 break-words text-[16px] leading-8 text-slate-200">
                      {line.map((word) => {
                        const playing = now >= word.start_ms && now < word.end_ms;
                        return (
                          <span
                            key={word.id}
                            contentEditable
                            suppressContentEditableWarning
                            spellCheck={false}
                            onFocus={() => seek(word.start_ms)}
                            onBlur={(event) => edit(word.id, event.currentTarget.textContent ?? "")}
                            onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); event.currentTarget.blur(); } }}
                            title={`${stamp(word.start_ms)} · ${(word.start_ms / 1000).toFixed(2)}–${(word.end_ms / 1000).toFixed(2)}s`}
                            className={`mx-[1px] rounded px-1 outline-none transition focus:bg-accent/25 focus:ring-1 focus:ring-accent ${playing ? "bg-accent/40 text-white" : "hover:bg-white/[0.06]"}`}
                          >
                            {word.text}
                          </span>
                        );
                      })}
                    </p>
                  </li>
                );
              })}
            </ol>
          )}
          {state === "error" && <p className="mt-3 text-xs text-red-300">Could not save. Try again.</p>}
        </div>
      </Card>
    </div>
  );
}
