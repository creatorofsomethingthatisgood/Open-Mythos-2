import { useEffect, useRef, useCallback } from "react";
import type { Message, Settings } from "../types";
import { CodeBlock } from "./CodeBlock";
import { ThinkingBlock } from "./ThinkingBlock";

interface ParsedBlock {
 type: "text" | "code" | "thinking";
 content: string;
 language?: string;
 fileName?: string;
}

function parseMessageContent(content: string): ParsedBlock[] {
 const blocks: ParsedBlock[] = [];
 let remaining = content;

 while (remaining.length > 0) {
 // Thinking blocks: HLSL... HLSR (Qwen2.5 alpha-bracket style)
 const thinkAlphaMatch = remaining.match(
 /^\u00ab\u00ab\u00ab\u00ab([\s\S]*?)\u00bb\u00bb\u00bb\u00bb\n?/
 );
 if (thinkAlphaMatch) {
 blocks.push({ type: "thinking", content: thinkAlphaMatch[1].trim() });
 remaining = remaining.slice(thinkAlphaMatch[0].length);
 continue;
 }

 // Thinking blocks: HLSL/ or HL9;
 const thinkXmlMatch = remaining.match(
 /^<(?:think|thinking)>([\s\S]*?)<\/(?:think|thinking)>\n?/
 );
 if (thinkXmlMatch) {
 blocks.push({ type: "thinking", content: thinkXmlMatch[1].trim() });
 remaining = remaining.slice(thinkXmlMatch[0].length);
 continue;
 }

 // Code blocks: ```lang\n...\n```
 const codeMatch = remaining.match(/^```(\w*)\n([\s\S]*?)```\n?/);
 if (codeMatch) {
 const lang = codeMatch[1] || "text";
 const code = codeMatch[2];
 const fileNameMatch = code.match(/^\/\/\s*(\S+\.\w+)\s*$/m) ||
 code.match(/^#\s*(\S+\.\w+)\s*$/m) ||
 code.match(/^<!--\s*(\S+\.\w+)\s*-->\s*$/m);
 blocks.push({
 type: "code",
 content: code,
 language: lang,
 fileName: fileNameMatch?.[1],
 });
 remaining = remaining.slice(codeMatch[0].length);
 continue;
 }

 // Find next code block or thinking block
 const nextCode = remaining.search(/```/);
 const nextThinkXml = remaining.search(/<(?:think|thinking)>/);
 const nextThinkAlpha = remaining.search(/\u00ab\u00ab\u00ab\u00ab/);
 let endIdx = remaining.length;
 if (nextCode !== -1) endIdx = Math.min(endIdx, nextCode);
 if (nextThinkXml !== -1) endIdx = Math.min(endIdx, nextThinkXml);
 if (nextThinkAlpha !== -1) endIdx = Math.min(endIdx, nextThinkAlpha);

 const text = remaining.slice(0, endIdx);
 if (text) {
 blocks.push({ type: "text", content: text });
 }
 remaining = remaining.slice(endIdx);
 }

 return blocks;
}

function formatInlineMarkdown(text: string): string {
 // Split text into segments: ASCII art blocks vs regular text.
 // ASCII art blocks are multi-line runs that contain visual structure
 // (box-drawing chars, pipe tables, repeated spacing for alignment).
 const ASCII_PATTERN =
 /((?:[]+|(?:\|.{1,60}\|[\s]*\n?){2,}|(?:[^\S\n]{2,}\S.*\n?){2,}))/g;

 // Process regular text segments through inline markdown
 const processText = (t: string): string => {
 let html = t
 .replace(/&/g, "&amp;")
 .replace(/</g, "&lt;")
 .replace(/>/g, "&gt;")
 .replace(/"/g, "&quot;")
 .replace(/'/g, "&#39;");

 html = html.replace(
 /`([^`]+)`/g,
 '<code class="mythos-inline-code">$1</code>'
 );
 html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
 html = html.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>");
 html = html.replace(/~~(.+?)~~/g, "<del>$1</del>");
 html = html.replace(/\n/g, "<br/>");
 return html;
 };

 // Process ASCII art blocks: escape HTML, preserve whitespace with <pre>
 const processAscii = (raw: string): string => {
 const escaped = raw
 .replace(/&/g, "&amp;")
 .replace(/</g, "&lt;")
 .replace(/>/g, "&gt;")
 .replace(/"/g, "&quot;")
 .replace(/'/g, "&#39;");
 return `<pre class="mythos-ascii-block">${escaped}</pre>`;
 };

 let result = "";
 let lastIdx = 0;
 let match: RegExpExecArray | null;

 // Reset regex state
 const regex = new RegExp(ASCII_PATTERN.source, ASCII_PATTERN.flags);

 while ((match = regex.exec(text)) !== null) {
 // Text before this match
 if (match.index > lastIdx) {
 result += processText(text.slice(lastIdx, match.index));
 }
 result += processAscii(match[1]);
 lastIdx = match.index + match[0].length;
 }

 // Remaining text after last match
 if (lastIdx < text.length) {
 result += processText(text.slice(lastIdx));
 }

 return result || processText(text);
}

function ChatMessage({
 msg,
 settings,
 onCopy,
}: {
 msg: Message;
 settings: Settings;
 onCopy: (text: string) => void;
}) {
 const isUser = msg.role === "user";
 const blocks = parseMessageContent(msg.content);

 // If the message has a reasoning field from the API, prepend it as a thinking block
 const allBlocks: ParsedBlock[] = msg.reasoning
 ? [{ type: "thinking", content: msg.reasoning }, ...blocks]
 : blocks;

 return (
 <div
 className={`py-3 px-4 ${
 isUser ? "mythos-msg-user" : "mythos-msg-assistant"
 }`}
 >
 {/* Role label */}
 <div className="flex items-center gap-2 mb-2">
 <span
 className={`text-[10px] font-bold uppercase tracking-widest ${
 isUser
 ? "text-[var(--mythos-accent2)]"
 : "text-[var(--mythos-success)]"
 }`}
 >
 {isUser ? "You" : "Mythos"}
 </span>
 {msg.timestamp && (
 <span className="text-[10px] text-[var(--mythos-text3)]">
 {new Date(msg.timestamp).toLocaleTimeString([], {
 hour: "2-digit",
 minute: "2-digit",
 })}
 </span>
 )}
 {!isUser && (
 <button
 className="ml-auto text-[var(--mythos-text3)] hover:text-[var(--mythos-text)] transition-colors"
 onClick={() => onCopy(msg.content)}
 title="Copy message"
 style={{ fontSize: 11 }}
 >
 Copy
 </button>
 )}
 </div>

 {/* Content blocks */}
 <div className="text-sm leading-relaxed">
 {allBlocks.map((block, i) => {
 if (block.type === "code") {
 return (
 <CodeBlock
 key={i}
 language={block.language || "text"}
 code={block.content}
 fileName={block.fileName}
 showLineNumbers={settings.showLineNumbers}
 lineWrap={settings.lineWrap}
 fontSize={settings.fontSize}
 />
 );
 }
 if (block.type === "thinking") {
 return <ThinkingBlock key={i} content={block.content} />;
 }
 return (
 <div
 key={i}
 className="text-[var(--mythos-text)]"
 dangerouslySetInnerHTML={{
 __html: formatInlineMarkdown(block.content),
 }}
 />
 );
 })}
 </div>
 </div>
 );
}

export function ChatArea({
 messages,
 isTyping,
 settings,
}: {
 messages: Message[];
 isTyping: boolean;
 settings: Settings;
}) {
 const bottomRef = useRef<HTMLDivElement>(null);
 const handleCopyMessage = useCallback(
 (text: string) => {
 navigator.clipboard.writeText(text).catch(() => {});
 },
 []
 );

 useEffect(() => {
 bottomRef.current?.scrollIntoView({ behavior: "smooth" });
 }, [messages.length, isTyping]);

 return (
 <div className="flex-1 overflow-y-auto" style={{ background: "var(--mythos-bg)" }}>
 {messages.length === 0 && (
 <div className="flex flex-col items-center justify-center h-full text-center gap-6 px-8">
 <div className="text-6xl opacity-80"></div>
 <div>
 <h2 className="text-2xl font-bold text-[var(--mythos-text)] mb-2">
 Mythos Coding Interface
 </h2>
 <p className="text-[var(--mythos-text2)] max-w-lg text-sm leading-relaxed">
 Local AI coding assistant. Paste code, ask questions, request
 reviews, or use the quick actions below. Everything runs on your
 machine.
 </p>
 </div>
 <div className="flex flex-wrap justify-center gap-2 max-w-md">
 {[
 "Write a Python web scraper",
 "Explain this error",
 "Review my API design",
 "Generate unit tests",
 ].map((hint) => (
 <span
 key={hint}
 className="text-xs px-3 py-1.5 rounded-full border border-[var(--mythos-border)] text-[var(--mythos-text2)] bg-[var(--mythos-surface)]"
 >
 {hint}
 </span>
 ))}
 </div>
 <div className="flex items-center gap-3 text-[10px] text-[var(--mythos-text3)]">
 <span>
 <span className="mythos-kbd">Enter</span> send
 </span>
 <span>
 <span className="mythos-kbd">Shift+Enter</span> newline
 </span>
 <span>
 <span className="mythos-kbd">Ctrl+N</span> new chat
 </span>
 </div>
 </div>
 )}
 {messages.map((m, i) => (
 <ChatMessage
 key={i}
 msg={{ ...m, timestamp: m.timestamp || Date.now() }}
 settings={settings}
 onCopy={handleCopyMessage}
 />
 ))}
 {isTyping && (
 <div className="py-3 px-4 mythos-msg-assistant">
 <div className="flex items-center gap-2 mb-2">
 <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--mythos-success)]">
 Mythos
 </span>
 </div>
 <div className="flex items-center gap-1.5">
 <span className="mythos-typing-dot" />
 <span className="mythos-typing-dot" />
 <span className="mythos-typing-dot" />
 </div>
 </div>
 )}
 <div ref={bottomRef} />
 </div>
 );
}
