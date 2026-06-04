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
import { DEFAULT_SETTINGS, MODE_CONFIG, SLASH_COMMANDS } from "./types";

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
 // Backend not available -- keep existing prompt
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

 const handleCommand = useCallback(
 (name: string, args: string) => {
 // Helper: add a system message visible in chat
 const sysMsg = (content: string) => {
 const msg: Message = { role: "assistant", content, timestamp: Date.now() };
 setMessages((prev) => [...prev, msg]);
 };

 switch (name) {
 /* Chat & session */
 case "help":
 // The CommandPalette component handles /help visually
 sysMsg("**Commands available --** type `/` in the input bar to browse all commands with autocomplete, or see the list:\n\n" +
 SLASH_COMMANDS.map(c => `\`/${c.name}\` -- ${c.description}`).join("\n"));
 break;
 case "clear":
 handleClear();
 break;
 case "save":
 handleSave();
 break;
 case "load":
 sysMsg("**Load conversation:** Use the Settings panel (Ctrl+B) to load a saved conversation, or drag a .txt/.json file into the chat.");
 break;
 case "export":
 handleExport();
 break;
 case "markdown": {
 const md = messages
 .map((m) => m.role === "user" ? `## You\n\n${m.content}` : `## Mythos\n\n${m.content}`)
 .join("\n\n---\n\n");
 const blob = new Blob([md || "# Empty conversation"], { type: "text/markdown" });
 const url = URL.createObjectURL(blob);
 const a = document.createElement("a");
 a.href = url;
 a.download = `mythos-${Date.now()}.md`;
 a.click();
 URL.revokeObjectURL(url);
 setStatusText("Exported as Markdown");
 break;
 }
 case "copy": {
 const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
 if (lastAssistant) {
 navigator.clipboard.writeText(lastAssistant.content).then(() => {
 setStatusText("Last response copied to clipboard");
 }).catch(() => {
 setStatusText("Failed to copy to clipboard");
 });
 } else {
 setStatusText("No assistant response to copy");
 }
 break;
 }
 case "dump": {
 const filename = args?.trim() || `mythos-dump-${Date.now()}.txt`;
 const text = messages.map((m) => `${m.role === "user" ? "You" : "Mythos"}: ${m.content}`).join("\n\n");
 const blob = new Blob([text || "Empty"], { type: "text/plain" });
 const url = URL.createObjectURL(blob);
 const a = document.createElement("a");
 a.href = url;
 a.download = filename;
 a.click();
 URL.revokeObjectURL(url);
 setStatusText(`Dumped to ${filename}`);
 break;
 }
 case "search": {
 const query = args?.trim().toLowerCase();
 if (!query) { setStatusText("Usage: /search <query>"); break; }
 const results = messages.filter((m) => m.content.toLowerCase().includes(query));
 if (results.length === 0) {
 sysMsg(`No messages matching \`${query}\`.`);
 } else {
 sysMsg(`**${results.length} result${results.length > 1 ? "s" : ""}** for \`${query}\`:\n\n` +
 results.map((m, i) => `${i + 1}. **${m.role}**: ${m.content.slice(0, 120)}${m.content.length > 120 ? "..." : ""}`).join("\n"));
 }
 break;
 }
 case "history": {
 if (messages.length === 0) { sysMsg("No messages in this session."); break; }
 sysMsg("**Message history:**\n\n" +
 messages.map((m, i) => `${i + 1}. **${m.role === "user" ? "You" : "Mythos"}** -- ${m.content.slice(0, 80)}${m.content.length > 80 ? "..." : ""}`).join("\n"));
 break;
 }
 case "compact": {
 if (messages.length < 4) { setStatusText("Not enough messages to compact"); break; }
 const half = Math.floor(messages.length / 2);
 const older = messages.slice(0, half);
 const summary = older.map((m) => `${m.role}: ${m.content.slice(0, 60)}`).join("; ");
 const compacted: Message = {
 role: "assistant",
 content: `**[Compact]** Earlier conversation summarized: ${summary}`,
 timestamp: Date.now(),
 };
 setMessages([compacted, ...messages.slice(half)]);
 setStatusText(`Compacted ${half} older messages`);
 break;
 }
 case "redo": {
 // Remove last assistant message and re-send last user message
 const lastUserIdx = messages.map((m, i) => m.role === "user" ? i : -1).filter((i) => i >= 0).pop();
 if (lastUserIdx === undefined) { setStatusText("No user message to redo"); break; }
 const lastUser = messages[lastUserIdx!];
 const trimmed = messages.slice(0, lastUserIdx!);
 setMessages(trimmed);
 // Re-send after state updates
 setTimeout(() => handleSend(lastUser.content), 50);
 break;
 }
 case "edit": {
 const lastUserMsg = [...messages].reverse().find((m) => m.role === "user");
 if (lastUserMsg) {
 sysMsg(`**Edit your last message:**\n\n\`\`\`\n${lastUserMsg.content}\n\`\`\`\n\nCopy it, edit, and resubmit.`);
 } else {
 setStatusText("No user message to edit");
 }
 break;
 }
 case "rename":
 setStatusText(args ? `Conversation renamed to "${args}"` : "Usage: /rename <name>");
 break;
 case "auto-title":
 if (messages.length === 0) { setStatusText("No messages to generate title from"); break; }
 const firstMsg = messages.find((m) => m.role === "user");
 const title = firstMsg ? firstMsg.content.slice(0, 50) : "New Conversation";
 setStatusText(`Title: "${title}${firstMsg && firstMsg.content.length > 50 ? "..." : ""}"`);
 break;
 case "summary":
 if (messages.length === 0) { sysMsg("No messages to summarize."); break; }
 sysMsg("**Session summary:**\n\n" +
 `- Messages: ${messages.length}\n` +
 `- User messages: ${messages.filter((m) => m.role === "user").length}\n` +
 `- Assistant messages: ${messages.filter((m) => m.role === "assistant").length}\n` +
 `- Total chars: ${messages.reduce((s, m) => s + m.content.length, 0).toLocaleString()}\n`);
 break;
 case "cost":
 case "tokens": {
 const totalChars = messages.reduce((s, m) => s + m.content.length, 0);
 const estTokens = Math.round(totalChars / 4);
 const userMsgs = messages.filter((m) => m.role === "user").length;
 const asstMsgs = messages.filter((m) => m.role === "assistant").length;
 sysMsg(`**Token estimate:**\n\n| Metric | Value |\n|---|---|\n| User messages | ${userMsgs} |\n| Assistant messages | ${asstMsgs} |\n| Total characters | ${totalChars.toLocaleString()} |\n| Estimated tokens | ~${estTokens.toLocaleString()} |\n| Est. cost (GPT-4 equiv.) | ~$${(estTokens * 0.00003).toFixed(4)} |`);
 break;
 }

 /* Mode & persona */
 case "mode": {
 const modeArg = args?.trim().toLowerCase();
 const validModes = Object.keys(MODE_CONFIG) as CodingMode[];
 if (!modeArg || !validModes.includes(modeArg as CodingMode)) {
 sysMsg("**Available modes:**\n\n" + validModes.map((m) => `- \`${m}\``).join("\n"));
 } else {
 handleModeChange(modeArg as CodingMode);
 }
 break;
 }
 case "persona":
 setStatusText(args ? `Persona set to "${args}"` : "Usage: /persona <name or description>");
 break;
 case "system": {
 const template = args?.trim().toLowerCase();
 if (!template) {
 sysMsg("**Available system prompt templates:**\n\ndefault, coding, creative, roleplay, debugging, analytical, code_review, security_audit, security_fix\n\nUsage: `/system <template>`");
 } else {
 fetchPrompt(`${template}.txt`)
 .then((p) => {
 setSettings((s) => ({ ...s, systemPrompt: p }));
 setStatusText(`System prompt: ${template}`);
 })
 .catch(() => setStatusText(`Template "${template}" not found`));
 }
 break;
 }

 /* Generation settings */
 case "temp": {
 const val = parseFloat(args);
 if (isNaN(val) || val < 0 || val > 2) { setStatusText("Usage: /temp <0.0-2.0>"); break; }
 setSettings((s) => ({ ...s, temperature: val }));
 setStatusText(`Temperature set to ${val}`);
 break;
 }
 case "topp": {
 const val = parseFloat(args);
 if (isNaN(val) || val < 0 || val > 1) { setStatusText("Usage: /topp <0.0-1.0>"); break; }
 setSettings((s) => ({ ...s, topP: val }));
 setStatusText(`Top-p set to ${val}`);
 break;
 }
 case "topk": {
 const val = parseInt(args);
 if (isNaN(val) || val < 1 || val > 200) { setStatusText("Usage: /topk <1-200>"); break; }
 setSettings((s) => ({ ...s, topK: val }));
 setStatusText(`Top-k set to ${val}`);
 break;
 }
 case "reppen": {
 const val = parseFloat(args);
 if (isNaN(val) || val < 1 || val > 2) { setStatusText("Usage: /reppen <1.0-2.0>"); break; }
 setSettings((s) => ({ ...s, repeatPenalty: val }));
 setStatusText(`Repeat penalty set to ${val}`);
 break;
 }
 case "maxtokens":
 case "max_tokens": {
 const val = parseInt(args);
 if (isNaN(val) || val < 128 || val > 65536) { setStatusText("Usage: /maxtokens <128-65536>"); break; }
 setSettings((s) => ({ ...s, maxTokens: val }));
 setStatusText(`Max tokens set to ${val}`);
 break;
 }

 /* Feature toggles */
 case "think":
 case "thinking": {
 const on = args?.trim().toLowerCase();
 if (on === "on") { setSettings((s) => ({ ...s, useThinking: true })); setStatusText("Thinking enabled"); }
 else if (on === "off") { setSettings((s) => ({ ...s, useThinking: false })); setStatusText("Thinking disabled"); }
 else setStatusText(`Thinking is currently ${settings.useThinking ? "on" : "off"}. Use /think <on|off>`);
 break;
 }
 case "reflect": {
 const on = args?.trim().toLowerCase();
 if (on === "on") { setSettings((s) => ({ ...s, useReflection: true })); setStatusText("Reflection enabled"); }
 else if (on === "off") { setSettings((s) => ({ ...s, useReflection: false })); setStatusText("Reflection disabled"); }
 else setStatusText(`Reflection is currently ${settings.useReflection ? "on" : "off"}. Use /reflect <on|off>`);
 break;
 }
 case "rag": {
 const on = args?.trim().toLowerCase();
 if (on === "on") { setSettings((s) => ({ ...s, useRag: true })); setStatusText("RAG enabled"); }
 else if (on === "off") { setSettings((s) => ({ ...s, useRag: false })); setStatusText("RAG disabled"); }
 else setStatusText(`RAG is currently ${settings.useRag ? "on" : "off"}. Use /rag <on|off>`);
 break;
 }

 /* Info */
 case "config":
 sysMsg("**Current configuration:**\n\n" +
 `| Setting | Value |\n|---|---|\n` +
 `| Mode | ${settings.mode} |\n` +
 `| Temperature | ${settings.temperature} |\n` +
 `| Top-p | ${settings.topP} |\n` +
 `| Top-k | ${settings.topK} |\n` +
 `| Repeat penalty | ${settings.repeatPenalty} |\n` +
 `| Max tokens | ${settings.maxTokens} |\n` +
 `| Thinking | ${settings.useThinking ? "on" : "off"} |\n` +
 `| Reflection | ${settings.useReflection ? "on" : "off"} |\n` +
 `| RAG | ${settings.useRag ? "on" : "off"} |\n`);
 break;
 case "version":
 sysMsg("**Mythos** -- Open-Mythos-2\n\nLocal AI coding assistant with GGUF inference.");
 break;
 case "sysinfo":
 sysMsg("**System info:**\n\n" +
 `| | |\n|---|---|\n` +
 `| Platform | ${navigator.platform} |\n` +
 `| Cores | ${navigator.hardwareConcurrency || "?"} |\n` +
 `| Memory | ${((navigator as any).deviceMemory ?? "?")} GB |\n` +
 `| Language | ${navigator.language} |\n` +
 `| Screen | ${screen.width}x${screen.height} |\n` +
 `| UA | ${navigator.userAgent.slice(0, 80)}... |`);
 break;

 default:
 setStatusText(`Unknown command: /${name}. Type /help for available commands.`);
 }
 },
 [messages, settings, handleClear, handleExport, handleSave, handleModeChange, handleSend]
 );



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
 {/* Sidebar -- slide over on toggle */}
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
 onCommand={handleCommand}
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
