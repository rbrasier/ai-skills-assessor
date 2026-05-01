interface Props {
  summary?: string | null;
}

export default function AiSummaryPanel({ summary }: Props) {
  return (
    <div className="summary-box">
      <div className="kicker">AI-generated summary</div>
      {summary ? (
        <div className="summary-text">{summary}</div>
      ) : (
        <div className="summary-placeholder">
          Summary will appear here once AI processing completes.
        </div>
      )}
    </div>
  );
}
