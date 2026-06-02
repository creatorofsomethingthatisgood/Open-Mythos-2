import { useState, useEffect } from "react";
import type { CodingMode } from "../types";
import { MODE_CONFIG } from "../types";

interface StatusBarProps {
  mode: CodingMode;
  messageCount: number;
  statusText: string;
  isTyping: boolean;
  fontSize: number;
  modelName?: string;
  tokenCount?: number;
  contextPct?: number;
}

const SPINNER_GLYPHS = [
  "\u2736", "\u2737", "\u2738", "\u2739", "\u273A",
  "\u274B", "\u274A", "\u2747", "\u2748", "\u2749",
  "\u2726", "\u2727", "\u22C6", "\u2042", "\u2734",
  "\u2735", "\u2731", "\u2732", "\u2733", "\u2743",
  "\u2744", "\u2745", "\u2746", "\u2605",
];

export function StatusBar({
  mode,
  messageCount,
  statusText,
  isTyping,
  fontSize,
  modelName,
  tokenCount,
  contextPct,
}: StatusBarProps) {
  const cfg = MODE_CONFIG[mode];
  const [glyphIdx, setGlyphIdx] = useState(0);

  useEffect(() => {
    if (!isTyping) return;
    const id = setInterval(() => setGlyphIdx((i) => (i + 1) % SPINNER_GLYPHS.length), 120);
    return () => clearInterval(id);
  }, [isTyping]);

  const ctxPct = contextPct ?? Math.min(messageCount * 2, 100);
  const ctxColor = ctxPct > 80 ? "var(--mythos-accent2)" : ctxPct > 50 ? "yellow" : "green";
  const barLen = 8;
  const filled = Math.round(ctxPct / 100 * barLen);
  const ctxBar = "\u2588".repeat(filled) + "\u2591".repeat(barLen - filled);

  return (
    <div className="mythos-statusbar">
      <span style={{ color: "var(--mythos-accent2)" }}>
        {cfg.icon} {cfg.label}
      </span>
      <span>|</span>
      {modelName && (
        <>
          <span style={{ color: "var(--mythos-accent-light)" }}>{modelName}</span>
          <span>|</span>
        </>
      )}
      <span>{messageCount} msgs</span>
      <span>|</span>
      {tokenCount !== undefined && (
        <>
          <span style={{ color: "var(--mythos-accent-light)" }}>{tokenCount.toLocaleString()} tok</span>
          <span>|</span>
        </>
      )}
      <span style={{ color: ctxColor }}>{ctxBar}</span>
      <span style={{ fontSize: "0.85em" }}>{ctxPct}%</span>
      <span>|</span>
      <span>{fontSize}px</span>
      <span>|</span>
      {isTyping && (
        <>
          <span style={{ color: "var(--mythos-accent2)" }}>{SPINNER_GLYPHS[glyphIdx]} Generating</span>
          <span>|</span>
        </>
      )}
      {statusText && <span>{statusText}</span>}
      <span style={{ marginLeft: "auto" }}>Mythos 2.0</span>
    </div>
  );
}
