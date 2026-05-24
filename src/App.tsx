import { useState, useCallback } from "react";
import { ChatArea } from "./components/ChatArea";
import { InputBar } from "./components/InputBar";
import { SettingsPanel } from "./components/SettingsPanel";
import { ExportModal } from "./components/ExportModal";
import { sendChat, clearChat, exportChat, saveChat } from "./api";
import type { Message, Settings } from "./types";
import { DEFAULT_SETTINGS } from "./types";

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [isTyping, setIsTyping] = useState(false);
  const [statusText, setStatusText] = useState("");
  const [exportText, setExportText] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const handleSend = useCallback(
    async (message: string) => {
      const userMsg: Message = { role: "user", content: message };
      const newHistory = [...messages, userMsg];
      setMessages(newHistory);
      setIsTyping(true);
      setStatusText("Generating...");

      try {
        const result = await sendChat(message, newHistory, settings);
        setMessages(result.history);
        setStatusText(result.status);
      } catch (err: any) {
        // If API is unavailable, show a helpful offline message
        const assistantMsg: Message = {
          role: "assistant",
          content:
            err?.message?.includes("Failed to fetch") ||
            err?.message?.includes("NetworkError")
              ? "**Mythos backend not connected.**\n\nTo use this web UI, start the local Mythos server:\n\n```bash\npython main.py --mode web\n```\n\nOr configure a remote backend URL in settings."
              : `Error: ${err?.message || "Unknown error"}`,
        };
        setMessages([...newHistory, assistantMsg]);
        setStatusText("Error connecting to backend");
      } finally {
        setIsTyping(false);
      }
    },
    [messages, settings]
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
      // Offline fallback: format locally
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
      // Offline fallback: download as file
      const text = messages
        .map((m) => `${m.role}: ${m.content}`)
        .join("\n\n");
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

  return (
    <div className="flex h-screen bg-[var(--mythos-bg)] overflow-hidden">
      {/* Sidebar */}
      <aside
        className={`${
          sidebarOpen ? "w-72" : "w-0"
        } flex-shrink-0 bg-[var(--mythos-surface)] border-r border-[var(--mythos-border)] transition-all duration-200 overflow-hidden`}
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

      {/* Main chat area */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="flex items-center gap-3 px-4 py-3 bg-[var(--mythos-surface)] border-b border-[var(--mythos-border)]">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="text-[var(--mythos-text2)] hover:text-[var(--mythos-text)] transition-colors"
            title="Toggle sidebar"
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 20 20"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            >
              <line x1="3" y1="5" x2="17" y2="5" />
              <line x1="3" y1="10" x2="17" y2="10" />
              <line x1="3" y1="15" x2="17" y2="15" />
            </svg>
          </button>
          <div className="flex items-center gap-2">
            <span className="text-lg">&#127775;</span>
            <h1 className="text-base font-bold text-[var(--mythos-text)]">
              Mythos Local
            </h1>
          </div>
          <span className="text-xs text-[var(--mythos-text2)] ml-auto">
            {messages.length > 0
              ? `${messages.filter((m) => m.role === "user").length} messages`
              : ""}
          </span>
        </header>

        {/* Chat */}
        <ChatArea messages={messages} isTyping={isTyping} />

        {/* Input */}
        <InputBar onSend={handleSend} disabled={isTyping} />
      </main>

      {/* Export modal */}
      {exportText !== null && (
        <ExportModal text={exportText} onClose={() => setExportText(null)} />
      )}
    </div>
  );
}
