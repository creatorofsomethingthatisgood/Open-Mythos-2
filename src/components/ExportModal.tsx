import { useState } from "react";

interface ExportModalProps {
  text: string;
  onClose: () => void;
}

export function ExportModal({ text, onClose }: ExportModalProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-[90vw] max-w-2xl max-h-[80vh] bg-[var(--mythos-surface)] border border-[var(--mythos-border)] rounded-2xl shadow-2xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--mythos-border)]">
          <h3 className="text-sm font-bold text-[var(--mythos-text)]">
            Exported Conversation
          </h3>
          <div className="flex gap-2">
            <button
              onClick={handleCopy}
              className="text-xs px-3 py-1.5 rounded-lg bg-[var(--mythos-accent)] text-white hover:bg-[var(--mythos-accent2)] transition-colors"
            >
              {copied ? "Copied!" : "Copy"}
            </button>
            <button
              onClick={onClose}
              className="text-xs px-3 py-1.5 rounded-lg bg-[var(--mythos-surface2)] text-[var(--mythos-text2)] hover:text-[var(--mythos-text)] transition-colors"
            >
              Close
            </button>
          </div>
        </div>
        <pre className="flex-1 overflow-auto p-5 text-xs text-[var(--mythos-text2)] whitespace-pre-wrap font-mono">
          {text}
        </pre>
      </div>
    </div>
  );
}
