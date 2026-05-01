interface Turn {
  speaker: string;
  text: string;
  timestamp?: string | number;
}

interface Props {
  transcriptJson?: { turns?: Turn[] } | null;
}

function fmtTime(t: string | number | undefined): string {
  if (t === undefined || t === null) return "";
  if (typeof t === "string") return t;
  const secs = Math.floor(t);
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function TranscriptPanel({ transcriptJson }: Props) {
  const turns = transcriptJson?.turns ?? [];

  return (
    <div className="transcript-section">
      <div className="st-head">
        <b>Transcript</b>
        <span style={{ fontSize: 11.5, color: "var(--ink-4)" }}>{turns.length} turns</span>
      </div>
      {turns.length === 0 ? (
        <div style={{ padding: "16px 18px", fontSize: 13, color: "var(--ink-4)", fontStyle: "italic" }}>
          No transcript available.
        </div>
      ) : (
        <div className="transcript-body">
          {turns.map((turn, i) => {
            const isBot = turn.speaker?.toLowerCase().includes("bot") ||
              turn.speaker?.toLowerCase().includes("ai") ||
              turn.speaker?.toLowerCase().includes("assistant");
            return (
              <div key={i} className={`utt ${isBot ? "bot" : "cand"}`}>
                <div className="utt-time">{fmtTime(turn.timestamp)}</div>
                <div>
                  <div className="utt-who">{turn.speaker ?? (isBot ? "AI" : "Candidate")}</div>
                  <div className="utt-text">{turn.text}</div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
