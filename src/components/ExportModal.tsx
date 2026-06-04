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
 }).catch(() => {});
 };

 const handleDownload = () => {
 const blob = new Blob([text], { type: "text/plain" });
 const url = URL.createObjectURL(blob);
 const a = document.createElement("a");
 a.href = url;
 a.download = `mythos-export-${Date.now()}.md`;
 a.click();
 URL.revokeObjectURL(url);
 };

 return (
 <div
 className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
 onClick={onClose}
 >
 <div
 className="w-[90vw] max-w-3xl max-h-[80vh] bg-[var(--mythos-surface)] border border-[var(--mythos-border)] rounded-xl shadow-2xl flex flex-col"
 onClick={(e) => e.stopPropagation()}
 >
 <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--mythos-border)]">
 <h3 className="text-xs font-bold text-[var(--mythos-text)] uppercase tracking-wider">
 Export Conversation
 </h3>
 <div className="flex gap-2">
 <button
 onClick={handleCopy}
 className={`mythos-copy-btn ${copied ? "copied" : ""}`}
 >
 {copied ? " Copied" : "Copy"}
 </button>
 <button
 onClick={handleDownload}
 className="mythos-copy-btn"
 >
 Download .md
 </button>
 <button
 onClick={onClose}
 className="mythos-copy-btn"
 >
 Close
 </button>
 </div>
 </div>
 <pre className="flex-1 overflow-auto p-4 text-xs text-[var(--mythos-text2)] whitespace-pre-wrap font-mono leading-relaxed">
 {text}
 </pre>
 </div>
 </div>
 );
}
