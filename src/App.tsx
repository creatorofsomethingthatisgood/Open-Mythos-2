import { useState, useCallback, useEffect } from "react";
import { ChatArea } from "./components/ChatArea";
import { InputBar } from "./components/InputBar";
import { SettingsPanel } from "./components/SettingsPanel";
import { ExportModal } from "./components/ExportModal";
import { ModeSelector } from "./components/ModeSelector";
import { StatusBar } from "./components/StatusBar";
import { QuickActions } from "./components/QuickActions";
import { sendChat, clearChat, exportChat, saveChat, fetchPrompt } from "./api";
import type { Message, Settings, CodingMode } from "./types";
import { DEFAULT_SETTINGS, MODE_CONFIG } from "./types";

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [isTyping, setIsTyping] = useState(false);
  const [statusText, setStatusText] = useState("");
  const [exportText, setExportText] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showQuickActions, setShowQuickActions] = useState(true);

  // Load system prompt when mode changes
  const handleModeChange = useCallback(
    async (mode: CodingMode) => {
      const cfg = MODE_CONFIG[mode];
      setSettings((s) => ({
        ...s,
        mode,
        temperature: cfg.temp,
      }));
      // Try to load the prompt file from backend
      try {
        const promptText = await fetchPrompt(cfg.promptFile);
        setSettings((s) => ({ ...s, systemPrompt: promptText }));
      } catch {
        // Backend not available — keep existing prompt
      }
    },
    []
  );

  const handleSend = useCallback(
    async (message: string) => {
      const userMsg: Message = {
        role: "user",
        content: message,
        timestamp: Date.now(),
      };
      const newHistory = [...messages, userMsg];
      setMessages(newHistory);
      setIsTyping(true);
      setStatusText("Generating...");

      try {
        const result = await sendChat(message, newHistory, settings);
        setMessages(
          result.history.map((m) => ({
            ...m,
            timestamp: m.timestamp || Date.now(),
          }))
        );
        setStatusText(result.status);
      } catch (err: any) {
        const assistantMsg: Message = {
          role: "assistant",
          content:
            err?.message?.includes("Failed to fetch") ||
            err?.message?.includes("NetworkError")
              ? "**Mythos backend not connected.**\n\nTo use this web UI, start the local Mythos server:\n\n```bash\npython main.py --mode web\n```\n\nOr configure a remote backend URL in settings."
              : `Error: ${err?.message || "Unknown error"}`,
          timestamp: Date.now(),
        };
        setMessages([...newHistory, assistantMsg]);
        setStatusText("Error connecting to backend");
      } finally {
        setIsTyping(false);
      }
    },
    [messages, settings]
  );

  const handleQuickAction = useCallback(
    (prompt: string) => {
      handleSend(prompt);
    },
    [handleSend]
  );

  const handleClear = useCallback(async () => {
    try {
      const result = await clearChat();
      setStatusText(result.status);
    } catch {
      // Offline fallback
    }
    setMessages([]);
    setStatusText("Conversation cleared");
  }, []);

  const handleExport = useCallback(async () => {
    try {
      const text = await exportChat(messages);
      setExportText(text);
    } catch {
      const text = messages
        .map((m) => `${m.role === "user" ? "You" : "Mythos"}: ${m.content}`)
        .join("\n\n---\n\n");
      setExportText(text || "No messages to export");
    }
  }, [messages]);

  const handleSave = useCallback(async () => {
    try {
      const result = await saveChat(messages);
      setStatusText(result.status);
    } catch {
      const text = messages.map((m) => `${m.role}: ${m.content}`).join("\n\n");
      const blob = new Blob([text], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `mythos-conversation-${Date.now()}.txt`;
      a.click();
      URL.revokeObjectURL(url);
      setStatusText("Conversation saved (offline)");
    }
  }, [messages]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ctrl+N: new chat
      if (e.ctrlKey && e.key === "n") {
        e.preventDefault();
        handleClear();
      }
      // Ctrl+B: toggle sidebar
      if (e.ctrlKey && e.key === "b") {
        e.preventDefault();
        setSidebarOpen((o) => !o);
      }
      // Ctrl+L: clear chat
      if (e.ctrlKey && e.key === "l") {
        e.preventDefault();
        handleClear();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [handleClear]);

  const userMsgCount = messages.filter((m) => m.role === "user").length;

  return (
    <div className="flex h-screen bg-[var(--mythos-bg)] overflow-hidden">
      {/* Sidebar — slide over on toggle */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside
        className={`${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        } fixed left-0 top-0 bottom-0 z-50 w-72 flex-shrink-0 bg-[var(--mythos-surface)] border-r border-[var(--mythos-border)] transition-transform duration-200 overflow-hidden`}
      >
        <SettingsPanel
          settings={settings}
          onChange={setSettings}
          onClear={handleClear}
          onExport={handleExport}
          onSave={handleSave}
          statusText={statusText}
        />
      </aside>

      {/* Main area */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Header bar with mode tabs */}
        <header className="flex items-center gap-2 px-3 py-1.5 bg-[var(--mythos-surface)] border-b border-[var(--mythos-border)]">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="text-[var(--mythos-text2)] hover:text-[var(--mythos-text)] transition-colors p-1"
            title="Toggle sidebar (Ctrl+B)"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            >
              <line x1="2" y1="4" x2="14" y2="4" />
              <line x1="2" y1="8" x2="14" y2="8" />
              <line x1="2" y1="12" x2="14" y2="12" />
            </svg>
          </button>

          <div className="w-px h-5 bg-[var(--mythos-border)]" />

          {/* Mode tabs */}
          <ModeSelector mode={settings.mode} onChange={handleModeChange} />

          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => setShowQuickActions(!showQuickActions)}
              className={`text-[11px] px-2 py-1 rounded transition-colors ${
                showQuickActions
                  ? "text-[var(--mythos-accent2)] bg-[var(--mythos-accent-dim)]"
                  : "text-[var(--mythos-text3)] hover:text-[var(--mythos-text2)]"
              }`}
              title="Toggle quick actions"
            >
              Actions
            </button>
            {userMsgCount > 0 && (
              <span className="text-[11px] text-[var(--mythos-text3)] font-mono">
                {userMsgCount}
              </span>
            )}
          </div>
        </header>

        {/* Quick actions bar */}
        {showQuickActions && messages.length === 0 && (
          <div className="border-b border-[var(--mythos-border)] bg-[var(--mythos-surface)]">
            <QuickActions onAction={handleQuickAction} />
          </div>
        )}

        {/* Chat area */}
        <ChatArea messages={messages} isTyping={isTyping} settings={settings} />

        {/* Input area */}
        <InputBar
          onSend={handleSend}
          disabled={isTyping}
          onQuickAction={handleQuickAction}
        />

        {/* Status bar */}
        <StatusBar
          mode={settings.mode}
          messageCount={messages.length}
          statusText={statusText}
          isTyping={isTyping}
          fontSize={settings.fontSize}
        />
      </main>

      {/* Export modal */}
      {exportText !== null && (
        <ExportModal text={exportText} onClose={() => setExportText(null)} />
      )}
    </div>
  );
}
