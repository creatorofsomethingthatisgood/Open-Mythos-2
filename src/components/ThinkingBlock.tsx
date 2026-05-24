import { useState } from "react";

interface ThinkingBlockProps {
  content: string;
}

export function ThinkingBlock({ content }: ThinkingBlockProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mythos-thinking">
      <div
        className="mythos-thinking-toggle"
        onClick={() => setOpen(!open)}
      >
        <span style={{ transform: open ? "rotate(90deg)" : "rotate(0)", transition: "transform 0.15s", display: "inline-block" }}>
          ▶
        </span>
        <span>Thinking</span>
        <span style={{ color: "var(--mythos-text3)", fontSize: 11 }}>
          ({content.split(/\s+/).length} words)
        </span>
      </div>
      {open && <div className="mythos-thinking-body">{content}</div>}
    </div>
  );
}
