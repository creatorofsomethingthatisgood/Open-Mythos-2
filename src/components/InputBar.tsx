import { useState, useCallback } from "react";

interface InputBarProps {
  onSend: (message: string) => void;
  disabled: boolean;
}

export function InputBar({ onSend, disabled }: InputBarProps) {
  const [text, setText] = useState("");

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  }, [text, disabled, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  return (
    <div className="flex items-end gap-2 px-2 pb-2">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Type your message here..."
        disabled={disabled}
        rows={2}
        className="flex-1 resize-none rounded-xl bg-[var(--mythos-surface2)] border border-[var(--mythos-border)] text-[var(--mythos-text)] placeholder:text-[var(--mythos-text2)] px-4 py-3 text-sm focus:outline-none focus:border-[var(--mythos-accent)] transition-colors"
      />
      <button
        onClick={handleSend}
        disabled={disabled || !text.trim()}
        className="h-[52px] px-5 rounded-xl font-semibold text-sm bg-[var(--mythos-accent)] text-white hover:bg-[var(--mythos-accent2)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        Send
      </button>
    </div>
  );
}
