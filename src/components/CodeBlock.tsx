import { useState, useCallback, useMemo } from "react";
import hljs from "highlight.js";

interface CodeBlockProps {
 language: string;
 code: string;
 fileName?: string;
 showLineNumbers: boolean;
 lineWrap: boolean;
 fontSize: number;
}

export function CodeBlock({
 language,
 code,
 fileName,
 showLineNumbers,
 lineWrap,
 fontSize,
}: CodeBlockProps) {
 const [copied, setCopied] = useState(false);

 const handleCopy = useCallback(() => {
 navigator.clipboard.writeText(code).then(() => {
 setCopied(true);
 setTimeout(() => setCopied(false), 2000);
 }).catch(() => {});
 }, [code]);

 const langLabel = language || "text";
 const langIcon = getLangIcon(langLabel);

 const highlightedHtml = useMemo(() => {
 try {
 const result = hljs.highlight(code, { language: langLabel });
 return result.value;
 } catch {
 return code;
 }
 }, [code, langLabel]);

 const lines = code.split("\n");
 const lineNums = showLineNumbers ? (
 <div
 className="absolute left-0 top-0 bottom-0 w-[44px] flex flex-col items-end pr-3 pt-4 select-none overflow-hidden"
 style={{
 color: "var(--mythos-line-number)",
 fontFamily: "var(--font-mono)",
 fontSize: fontSize,
 lineHeight: 1.6,
 }}
 >
 {lines.map((_, i) => (
 <span key={i}>{i + 1}</span>
 ))}
 </div>
 ) : null;

 return (
 <div className="mythos-code-container">
 <div className="mythos-code-header">
 <div className="mythos-code-lang">
 <span>{langIcon}</span>
 <span>{langLabel}</span>
 {fileName && (
 <span className="mythos-code-filename">{fileName}</span>
 )}
 </div>
 <button
 className={`mythos-copy-btn ${copied ? "copied" : ""}`}
 onClick={handleCopy}
 >
 {copied ? " Copied" : "Copy"}
 </button>
 </div>
 <div
 className={`mythos-code-body ${showLineNumbers ? "linenums" : ""} ${
 lineWrap ? "mythos-line-wrap" : ""
 }`}
 style={{ position: "relative" }}
 >
 {lineNums}
 <pre style={{ fontSize }}>
 <code ref={codeRef} className={`language-${langLabel}`}>
 {code}
 </code>
 </pre>
 </div>
 </div>
 );
}

function getLangIcon(lang: string): string {
 const icons: Record<string, string> = {
 python: "",
 py: "",
 javascript: "",
 js: "",
 typescript: "",
 ts: "",
 tsx: "",
 jsx: "",
 rust: "",
 rs: "",
 go: "",
 java: "",
 cpp: "",
 c: "",
 html: "",
 css: "",
 scss: "",
 sql: "",
 bash: "",
 sh: "",
 shell: "",
 yaml: "",
 yml: "",
 json: "",
 toml: "",
 dockerfile: "",
 docker: "",
 diff: "",
 markdown: "",
 md: "",
 plaintext: "",
 text: "",
 };
 return icons[lang.toLowerCase()] || "";
}
