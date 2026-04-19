import { Mic } from "lucide-react";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center gap-6 p-8 text-center">
      <div className="flex items-center gap-3 text-indigo-600">
        <Mic className="h-8 w-8" aria-hidden="true" />
        <span className="text-sm font-semibold uppercase tracking-widest">
          AI Skills Assessor
        </span>
      </div>
      <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
        Voice-AI SFIA Skills Assessment Platform
      </h1>
      <p className="max-w-xl text-base text-slate-600">
        Phase 1 scaffold — the candidate dashboard, SME review portal, and live call experience
        will be built in subsequent phases.
      </p>
    </main>
  );
}
