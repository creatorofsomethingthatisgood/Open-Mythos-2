import type { Message, Settings } from "./types";

const API_BASE = "/api";

export async function sendChat(
 message: string,
 history: Message[],
 settings: Settings
): Promise<{ history: Message[]; status: string; reasoning?: string }> {
 const res = await fetch(`${API_BASE}/chat`, {
 method: "POST",
 headers: { "Content-Type": "application/json" },
 body: JSON.stringify({
 message,
 history,
 system_prompt: settings.systemPrompt,
 temperature: settings.temperature,
 top_p: settings.topP,
 top_k: settings.topK,
 max_tokens: settings.maxTokens,
 repeat_penalty: settings.repeatPenalty,
 use_reflection: settings.useReflection,
 use_rag: settings.useRag,
 use_thinking: settings.useThinking,
 }),
 });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `Server error ${res.status}`);
  }

  return res.json();
}

export async function fetchPrompt(name: string): Promise<string> {
  const res = await fetch(`${API_BASE}/prompt?name=${encodeURIComponent(name)}`);
  if (!res.ok) throw new Error("Failed to load prompt");
  return res.text();
}

export async function clearChat(): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/clear`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to clear");
  return res.json();
}

export async function exportChat(
  history: Message[]
): Promise<string> {
  const res = await fetch(`${API_BASE}/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ history }),
  });
  if (!res.ok) throw new Error("Failed to export");
  return res.text();
}

export async function saveChat(
  history: Message[]
): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ history }),
  });
  if (!res.ok) throw new Error("Failed to save");
  return res.json();
}

export async function uploadRagDocument(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/rag-upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error("Failed to upload");
  return res.text();
}
