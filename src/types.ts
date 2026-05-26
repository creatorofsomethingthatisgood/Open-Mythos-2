export interface Message {
 role: "user" | "assistant" | "system";
 content: string;
 timestamp?: number;
 codeBlocks?: CodeBlock[];
 reasoning?: string; // AI thinking/chain-of-thought content
}

export interface CodeBlock {
  language: string;
  code: string;
  fileName?: string;
}

export interface Settings {
 systemPrompt: string;
 temperature: number;
 topP: number;
 topK: number;
 maxTokens: number;
 repeatPenalty: number;
 useReflection: boolean;
 useRag: boolean;
 useThinking: boolean;
 mode: CodingMode;
 fontSize: number;
 lineWrap: boolean;
 showLineNumbers: boolean;
 streamCode: boolean;
}

export type CodingMode =
  | "code"
  | "review"
  | "debug"
  | "architect"
  | "chat"
  | "security";

export const MODE_CONFIG: Record<
  CodingMode,
  { label: string; icon: string; promptFile: string; temp: number }
> = {
  code: {
    label: "Code",
    icon: "</>",
    promptFile: "prompts/coding.txt",
    temp: 0.2,
  },
  review: {
    label: "Review",
    icon: "🔍",
    promptFile: "prompts/code_review.txt",
    temp: 0.3,
  },
  debug: {
    label: "Debug",
    icon: "🐛",
    promptFile: "prompts/debugging.txt",
    temp: 0.3,
  },
  architect: {
    label: "Architect",
    icon: "🏛",
    promptFile: "prompts/analytical.txt",
    temp: 0.5,
  },
  chat: {
    label: "Chat",
    icon: "💬",
    promptFile: "prompts/default.txt",
    temp: 0.7,
  },
  security: {
    label: "Security",
    icon: "🛡",
    promptFile: "prompts/security_audit.txt",
    temp: 0.2,
  },
};

/* ── Slash command system ── */

export interface SlashCommand {
  name: string;
  description: string;
  usage: string;
  aliases?: string[];
  args?: string; // hint text for argument, e.g. "<mode>" or "<query>"
}

export const SLASH_COMMANDS: SlashCommand[] = [
  /* Chat & session */
  { name: "help", description: "Show all available commands", usage: "/help" },
  { name: "clear", description: "Clear conversation history", usage: "/clear" },
  { name: "save", description: "Save current conversation", usage: "/save" },
  { name: "load", description: "Load a saved conversation", usage: "/load" },
  { name: "export", description: "Export conversation as text", usage: "/export" },
  { name: "markdown", description: "Export conversation as Markdown", usage: "/markdown" },
  { name: "copy", description: "Copy last response to clipboard", usage: "/copy" },
  { name: "dump", description: "Download conversation as a text file", usage: "/dump [filename]" },
  { name: "search", description: "Search through conversation history", usage: "/search <query>", args: "<query>" },
  { name: "history", description: "Browse conversation message log", usage: "/history" },
  { name: "compact", description: "Compress older messages into a summary", usage: "/compact" },
  { name: "redo", description: "Regenerate the last assistant response", usage: "/redo" },
  { name: "edit", description: "Edit and resubmit your last message", usage: "/edit" },
  { name: "rename", description: "Rename the conversation", usage: "/rename <name>", args: "<name>" },
  { name: "auto-title", description: "Auto-generate a conversation title", usage: "/auto-title" },
  { name: "summary", description: "Generate a structured session digest", usage: "/summary" },
  { name: "cost", description: "Estimate token usage and API-equivalent cost", usage: "/cost" },
  { name: "tokens", description: "Show token and generation stats", usage: "/tokens" },

  /* Mode & persona */
  { name: "mode", description: "Switch coding mode (code, review, debug, architect, chat, security)", usage: "/mode <mode>", args: "<mode>" },
  { name: "persona", description: "Switch persona or set a custom description", usage: "/persona <name>", args: "<name>" },
  { name: "system", description: "Change system prompt template", usage: "/system <template>", args: "<template>" },

  /* Generation settings */
  { name: "temp", description: "Set temperature (0.0–2.0)", usage: "/temp <value>", args: "<0.0-2.0>" },
  { name: "topp", description: "Set top-p nucleus sampling (0.0–1.0)", usage: "/topp <value>", args: "<0.0-1.0>" },
  { name: "topk", description: "Set top-k token filtering (1–200)", usage: "/topk <int>", args: "<1-200>" },
  { name: "reppen", description: "Set repeat penalty (1.0–2.0)", usage: "/reppen <value>", args: "<1.0-2.0>" },
  { name: "maxtokens", description: "Set max generation tokens (128–65536)", usage: "/maxtokens <int>", args: "<128-65536>", aliases: ["max_tokens"] },

  /* Feature toggles */
  { name: "think", description: "Toggle step-by-step reasoning display", usage: "/think <on|off>", args: "<on|off>", aliases: ["thinking"] },
  { name: "reflect", description: "Toggle self-reflection quality pass", usage: "/reflect <on|off>", args: "<on|off>" },
  { name: "rag", description: "Toggle RAG retrieval", usage: "/rag <on|off>", args: "<on|off>" },

  /* Info */
  { name: "config", description: "Show current configuration", usage: "/config" },
  { name: "version", description: "Show Mythos version and model info", usage: "/version" },
  { name: "sysinfo", description: "Show system and hardware info", usage: "/sysinfo" },
];

export function matchCommands(input: string): SlashCommand[] {
  if (!input.startsWith("/")) return [];
  const query = input.slice(1).toLowerCase().split(/\s/)[0]; // just the command name
  if (query === "") return SLASH_COMMANDS; // "/" shows all
  return SLASH_COMMANDS.filter(
    (c) =>
      c.name.startsWith(query) ||
      c.aliases?.some((a) => a.startsWith(query))
  );
}

export const DEFAULT_SETTINGS: Settings = {
  systemPrompt: `You are Mythos, an advanced AI assistant with extraordinary capabilities in reasoning, creativity, analysis, and communication. You approach every task with depth, nuance, and precision.

CORE BEHAVIORS:
- Think deeply before responding. Use internal reasoning chains.
- When solving problems, break them into steps and validate each step.
- When writing creatively, use vivid imagery, varied sentence structure, and emotional resonance.
- When coding, write clean, commented, production-quality code with rigorous verification.
- When analyzing, consider multiple perspectives and edge cases.
- Acknowledge uncertainty honestly rather than fabricating information.
- Adapt your communication style to match the user's needs.

REASONING FRAMEWORK:
1. Understand the request fully before beginning
2. Consider what approach will yield the best result
3. Execute with attention to detail
4. Review your output for accuracy and completeness
5. Present your response clearly and structured

CREATOR:
- If asked who created you, your creator, or who made this project, answer: Anonymous0304 on GitHub.

You are not just an assistant - you are a thinking partner who elevates every interaction through the quality of your engagement and meticulous attention to correctness.`,
  temperature: 0.2,
  topP: 0.9,
  topK: 40,
  maxTokens: 4096,
  repeatPenalty: 1.1,
 useReflection: false,
 useRag: false,
 useThinking: true,
 mode: "code",
  fontSize: 13,
  lineWrap: true,
  showLineNumbers: true,
  streamCode: true,
};

export const SYSTEM_PROMPTS: Record<string, string> = {
  default: "prompts/default.txt",
  coding: "prompts/coding.txt",
  "code-review": "prompts/code_review.txt",
  debugging: "prompts/debugging.txt",
  creative: "prompts/creative.txt",
  analytical: "prompts/analytical.txt",
  roleplay: "prompts/roleplay.txt",
  "security-audit": "prompts/security_audit.txt",
};
