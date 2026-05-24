import { useEffect, useRef } from "react";
import type { Message } from "../types";

function formatContent(content: string): string {
  // Simple markdown-ish: code blocks, bold, italic
  let html = content
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Code blocks ```...```
  html = html.replace(
    /```(\w*)\n([\s\S]*?)```/g,
    '<pre class="mythos-codeblock"><code>$2</code></pre>'
  );
  // Inline code `...`
  html = html.replace(
    /`([^`]+)`/g,
    '<code class="mythos-inline-code">$1</code>'
  );
  // Bold **...**
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  // Italic *...*
  html = html.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>");
  // Line breaks
  html = html.replace(/\n/g, "<br/>");

  return html;
}

export function ChatMessage({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";

  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3 px-1`}
    >
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? "bg-[var(--mythos-user)] text-[var(--mythos-text)] rounded-br-md"
            : "bg-[var(--mythos-surface2)] text-[var(--mythos-text)] rounded-bl-md border border-[var(--mythos-border)]"
        }`}
      >
        <div className="flex items-center gap-2 mb-1">
          <span
            className={`text-xs font-semibold ${
              isUser ? "text-[var(--mythos-accent2)]" : "text-[var(--mythos-success)]"
            }`}
          >
            {isUser ? "You" : "Mythos"}
          </span>
        </div>
        <div
          className="prose-sm"
          dangerouslySetInnerHTML={{ __html: formatContent(msg.content) }}
        />
      </div>
    </div>
  );
}

export function ChatArea({
  messages,
  isTyping,
}: {
  messages: Message[];
  isTyping: boolean;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, isTyping]);

  return (
    <div className="flex-1 overflow-y-auto px-2 py-4">
      {messages.length === 0 && (
        <div className="flex flex-col items-center justify-center h-full text-center gap-4 opacity-60">
          <div className="text-5xl">&#127775;</div>
          <h2 className="text-2xl font-bold text-[var(--mythos-text)]">
            Mythos Local
          </h2>
          <p className="text-[var(--mythos-text2)] max-w-md">
            High-quality local language model. Type a message to start a
            conversation.
          </p>
        </div>
      )}
      {messages.map((m, i) => (
        <ChatMessage key={i} msg={m} />
      ))}
      {isTyping && (
        <div className="flex justify-start mb-3 px-1">
          <div className="bg-[var(--mythos-surface2)] border border-[var(--mythos-border)] rounded-2xl rounded-bl-md px-4 py-3">
            <div className="flex items-center gap-1">
              <span className="text-xs text-[var(--mythos-success)] font-semibold mr-2">
                Mythos
              </span>
              <span className="animate-pulse text-[var(--mythos-accent)]">
                &#9679;&#9679;&#9679;
              </span>
            </div>
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
