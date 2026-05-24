import { useState, useCallback, useRef, useEffect } from "react";

interface InputBarProps {
  onSend: (message: string) => void;
  disabled: boolean;
  onQuickAction?: (prompt: string) => void;
}

export function InputBar({ onSend, disabled, onQuickAction }: InputBarProps) {
  const [text, setText] = useState("");
  const [mono, setMono] = useState(false);
  const [rows, setRows] = useState(3);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
    setRows(3);
    // Refocus textarea
    setTimeout(() => textareaRef.current?.focus(), 50);
  }, [text, disabled, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey) {
        e.preventDefault();
        handleSend();
      }
      // Ctrl+N: new chat (let parent handle)
    },
    [handleSend]
  );

  // Auto-resize textarea
  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const maxH = 320;
    el.style.height = Math.min(el.scrollHeight, maxH) + "px";
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [text, adjustHeight]);

  const handlePaste = useCallback(
    (e: React.ClipboardEvent) => {
      const pasted = e.clipboardData.getData("text");
      // Auto-enable mono mode if pasting code
      if (
        pasted.includes("```") ||
        pasted.includes("function ") ||
        pasted.includes("class ") ||
        pasted.includes("def ") ||
        pasted.includes("import ") ||
        pasted.includes("from ") ||
        pasted.includes("const ") ||
        pasted.includes("return ")
      ) {
        setMono(true);
      }
    },
    []
  );

  const charCount = text.length;
  const lineCount = text.split("\n").length;

  return (
    <div className="border-t border-[var(--mythos-border)] bg-[var(--mythos-surface)]">
      {/* Input area */}
      <div className="flex items-end gap-2 px-3 py-2">
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder={
              mono
                ? "Paste or type code here..."
                : "Ask Mythos... (Shift+Enter for newline)"
            }
            disabled={disabled}
            rows={rows}
            className={`w-full resize-none rounded-lg bg-[var(--mythos-bg)] border border-[var(--mythos-border)] text-[var(--mythos-text)] placeholder:text-[var(--mythos-text3)] px-4 py-3 text-sm focus:outline-none focus:border-[var(--mythos-accent)] transition-colors ${
              mono ? "font-mono" : ""
            }`}
            style={{
              fontFamily: mono ? "var(--font-mono)" : "var(--font-sans)",
              fontSize: mono ? 13 : 14,
              minHeight: "48px",
              maxHeight: "320px",
            }}
            spellCheck={!mono}
          />
          {/* Tiny metadata bar */}
          <div className="absolute bottom-1 right-2 flex items-center gap-2 text-[10px] text-[var(--mythos-text3)] font-mono select-none">
            {lineCount > 1 && <span>{lineCount}L</span>}
            {charCount > 0 && <span>{charCount}c</span>}
          </div>
        </div>

        {/* Toggle buttons */}
        <div className="flex flex-col gap-1">
          <button
            onClick={() => setMono(!mono)}
            className={`px-2 py-1.5 rounded-md text-[10px] font-mono border transition-colors ${
              mono
                ? "bg-[var(--mythos-accent-dim)] text-[var(--mythos-accent2)] border-[var(--mythos-accent)]"
                : "bg-[var(--mythos-surface2)] text-[var(--mythos-text3)] border-[var(--mythos-border)]"
            }`}
            title="Toggle monospace input"
          >
            {"</>"}
          </button>
        </div>

        {/* Send button */}
        <button
          onClick={handleSend}
          disabled={disabled || !text.trim()}
          className="h-[44px] px-5 rounded-lg font-semibold text-sm bg-[var(--mythos-accent)] text-white hover:bg-[var(--mythos-accent2)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
            <path d="M1 1l14 7-14 7V9l10-2-10-2V1z" />
          </svg>
          Send
        </button>
      </div>
    </div>
  );
}
