import { useState, useEffect } from "react";

interface ThinkingBlockProps {
 content: string;
}

function formatThinkingMarkdown(text: string): string {
 let html = text
 .replace(/&/g, "&amp;")
 .replace(/</g, "&lt;")
 .replace(/>/g, "&gt;")
 .replace(/"/g, "&quot;")
 .replace(/'/g, "&#39;");

 // Inline code
 html = html.replace(
 /`([^`]+)`/g,
 '<code class="mythos-inline-code">$1</code>'
 );
 // Bold
 html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
 // Italic
 html = html.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>");
 // Line breaks
 html = html.replace(/\n/g, "<br/>");

 return html;
}

export function ThinkingBlock({ content }: ThinkingBlockProps) {
 const [open, setOpen] = useState(false);
 const wordCount = content.split(/\s+/).filter(Boolean).length;

 return (
 <div className="mythos-thinking">
 <div
 className="mythos-thinking-toggle"
 onClick={() => setOpen(!open)}
 >
 <span
 className="mythos-arrow"
 style={{
 transform: open ? "rotate(90deg)" : "rotate(0)",
 transition: "transform 0.15s",
 }}
 >
 
 </span>
 <span className="mythos-thinking-icon">{GLYPHS[glyphIdx]}</span>
 <span className="mythos-thinking-label">Thinking</span>
 <span className="mythos-thinking-words">
 {wordCount} words
 </span>
 </div>
 {open && (
 <div className="mythos-thinking-body">
 <div
 className="mythos-thinking-content"
 dangerouslySetInnerHTML={{
 __html: formatThinkingMarkdown(content),
 }}
 />
 </div>
 )}
 </div>
 );
}
