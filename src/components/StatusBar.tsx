import type { CodingMode } from "../types";
import { MODE_CONFIG } from "../types";

interface StatusBarProps {
  mode: CodingMode;
  messageCount: number;
  statusText: string;
  isTyping: boolean;
  fontSize: number;
}

export function StatusBar({
  mode,
  messageCount,
  statusText,
  isTyping,
  fontSize,
}: StatusBarProps) {
  const cfg = MODE_CONFIG[mode];
  return (
    <div className="mythos-statusbar">
      <span style={{ color: "var(--mythos-accent2)" }}>
        {cfg.icon} {cfg.label}
      </span>
      <span>│</span>
      <span>{messageCount} msgs</span>
      <span>│</span>
      <span>{fontSize}px</span>
      <span>│</span>
      {isTyping && (
        <>
          <span style={{ color: "var(--mythos-warning)" }}>● Generating</span>
          <span>│</span>
        </>
      )}
      {statusText && <span>{statusText}</span>}
      <span style={{ marginLeft: "auto" }}>Mythos 2.0</span>
    </div>
  );
}
