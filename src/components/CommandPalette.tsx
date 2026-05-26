import { useState, useEffect, useRef, useCallback } from "react";
import type { SlashCommand } from "../types";
import { matchCommands, SLASH_COMMANDS } from "../types";

interface CommandPaletteProps {
  input: string;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  onSelect: (command: SlashCommand) => void;
  onClose: () => void;
}

export function CommandPalette({
  input,
  inputRef,
  onSelect,
  onClose,
}: CommandPaletteProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [showHelp, setShowHelp] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const matches = matchCommands(input);

  // Check if input is exactly "/help" (no args needed)
  const isHelpRequest =
    input.trim() === "/help" || input.trim() === "/help ";

  useEffect(() => {
    setSelectedIndex(0);
  }, [input]);

  useEffect(() => {
    if (isHelpRequest) setShowHelp(true);
  }, [isHelpRequest]);

  // Scroll selected item into view
  useEffect(() => {
    const el = listRef.current?.children[selectedIndex] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (showHelp) {
        if (e.key === "Escape") {
          e.preventDefault();
          setShowHelp(false);
          onClose();
        }
        return;
      }

      if (matches.length === 0) return;

      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setSelectedIndex((i) => (i + 1) % matches.length);
          break;
        case "ArrowUp":
          e.preventDefault();
          setSelectedIndex((i) => (i - 1 + matches.length) % matches.length);
          break;
        case "Tab":
        case "Enter":
          e.preventDefault();
          if (matches[selectedIndex]) {
            onSelect(matches[selectedIndex]);
          }
          break;
        case "Escape":
          e.preventDefault();
          onClose();
          break;
      }
    },
    [matches, selectedIndex, onSelect, onClose, showHelp]
  );

  // Attach keyboard listener to input
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    const handler = (e: KeyboardEvent) => handleKeyDown(e as any);
    el.addEventListener("keydown", handler as any, true);
    return () => el.removeEventListener("keydown", handler as any, true);
  }, [inputRef, handleKeyDown]);

  // Don't render palette if not typing a command or if help modal is shown
  if (showHelp) {
    return (
      <div className="mythos-help-overlay" onClick={() => { setShowHelp(false); onClose(); }}>
        <div className="mythos-help-modal" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-bold text-[var(--mythos-text)]">
              Mythos Commands
            </h2>
            <button
              className="mythos-help-close"
              onClick={() => { setShowHelp(false); onClose(); }}
            >
              Esc
            </button>
          </div>
          <div className="mythos-help-grid">
            {(() => {
              const categories = [
                { label: "Chat & Session", cmds: SLASH_COMMANDS.filter((c) =>
                  ["help","clear","save","load","export","markdown","copy","dump","search","history","compact","redo","edit","rename","auto-title","summary","cost","tokens"].includes(c.name)) },
                { label: "Mode & Persona", cmds: SLASH_COMMANDS.filter((c) =>
                  ["mode","persona","system"].includes(c.name)) },
                { label: "Generation", cmds: SLASH_COMMANDS.filter((c) =>
                  ["temp","topp","topk","reppen","maxtokens"].includes(c.name)) },
                { label: "Toggles", cmds: SLASH_COMMANDS.filter((c) =>
                  ["think","reflect","rag"].includes(c.name)) },
                { label: "Info", cmds: SLASH_COMMANDS.filter((c) =>
                  ["config","version","sysinfo"].includes(c.name)) },
              ];
              return categories.map((cat) => (
                <div key={cat.label} className="mythos-help-category">
                  <h3 className="text-[10px] font-bold text-[var(--mythos-accent2)] uppercase tracking-wider mb-2">
                    {cat.label}
                  </h3>
                  {cat.cmds.map((cmd) => (
                    <div key={cmd.name} className="mythos-help-row">
                      <code className="mythos-help-cmd">/{cmd.name}</code>
                      {cmd.aliases?.map((a) => (
                        <code key={a} className="mythos-help-alias">/{a}</code>
                      ))}
                      <span className="mythos-help-desc">{cmd.description}</span>
                    </div>
                  ))}
                </div>
              ));
            })()}
          </div>
        </div>
      </div>
    );
  }

  if (!input.startsWith("/") || matches.length === 0) return null;

  return (
    <div className="mythos-command-palette">
      <div ref={listRef} className="mythos-command-list">
        {matches.map((cmd, i) => (
          <div
            key={cmd.name}
            className={`mythos-command-item ${i === selectedIndex ? "selected" : ""}`}
            onMouseEnter={() => setSelectedIndex(i)}
            onMouseDown={(e) => {
              e.preventDefault();
              onSelect(cmd);
            }}
          >
            <span className="mythos-command-name">
              /{cmd.name}
              {cmd.aliases?.map((a) => (
                <span key={a} className="mythos-command-alias"> /{a}</span>
              ))}
            </span>
            {cmd.args && (
              <span className="mythos-command-args">{cmd.args}</span>
            )}
            <span className="mythos-command-desc">{cmd.description}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
