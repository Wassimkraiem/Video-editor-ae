"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../lib/api-client";
import { Button, Input, Spinner } from "./ui";
import { FilmIcon } from "./icons";

export function AuthPanel({ onAuthenticated }: { onAuthenticated: (token: string) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = mode === "login" ? await api.login(email, password) : await api.register(email, password);
      onAuthenticated(result.access_token);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm animate-fade-in">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-white shadow-glow"><FilmIcon width={20} height={20} /></div>
          <div>
            <p className="text-sm font-semibold text-white">Studio</p>
            <p className="text-xs text-slate-400">AI video editing with your house styles</p>
          </div>
        </div>
        <form onSubmit={(event) => void submit(event)} className="rounded-2xl border border-line bg-panel/80 p-6 shadow-panel backdrop-blur">
          <h1 className="text-xl font-semibold tracking-tight text-white">{mode === "login" ? "Welcome back" : "Create your account"}</h1>
          <p className="mt-1 text-sm text-slate-400">{mode === "login" ? "Sign in to continue editing." : "Your media and provider keys stay on your server."}</p>
          <div className="mt-6 space-y-3">
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-slate-400">Email</span>
              <Input type="email" autoComplete="email" placeholder="you@example.com" value={email} onChange={(event) => setEmail(event.target.value)} required />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-slate-400">Password</span>
              <Input type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} placeholder="At least 8 characters" value={password} onChange={(event) => setPassword(event.target.value)} minLength={8} required />
            </label>
            {error && <p role="alert" className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-200">{error}</p>}
            <Button type="submit" className="w-full" disabled={busy || !email || password.length < 8}>
              {busy && <Spinner />}{mode === "login" ? "Sign in" : "Create account"}
            </Button>
          </div>
          <p className="mt-5 text-center text-xs text-slate-500">
            {mode === "login" ? "New here?" : "Already have an account?"}{" "}
            <button type="button" className="font-medium text-accent-soft hover:text-white" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>
              {mode === "login" ? "Create an account" : "Sign in"}
            </button>
          </p>
        </form>
      </div>
    </main>
  );
}
