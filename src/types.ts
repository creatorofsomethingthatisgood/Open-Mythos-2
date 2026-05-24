export interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: number;
  codeBlocks?: CodeBlock[];
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
