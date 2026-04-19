interface ReviewPageProps {
  params: { token: string };
}

export default function SmeReviewPage({ params }: ReviewPageProps) {
  return (
    <main className="mx-auto max-w-5xl p-8">
      <h1 className="text-2xl font-semibold">SME review</h1>
      <p className="mt-2 text-slate-600">
        Token: <code className="rounded bg-slate-200 px-1 py-0.5">{params.token}</code>
      </p>
      <p className="mt-2 text-slate-500">
        Stub page — claim approval workflow is implemented in Phase 7 (SME Review Portal).
      </p>
    </main>
  );
}
