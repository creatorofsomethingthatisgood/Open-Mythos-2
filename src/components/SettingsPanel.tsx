import type { Settings } from "../types";
import { SYSTEM_PROMPTS } from "../types";

interface SettingsPanelProps {
  settings: Settings;
  onChange: (s: Settings) => void;
  onClear: () => void;
  onExport: () => void;
  onSave: () => void;
  statusText: string;
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="mb-3">
      <div className="flex justify-between text-xs mb-1">
        <span className="text-[var(--mythos-text2)]">{label}</span>
        <span className="text-[var(--mythos-accent2)] font-mono">{value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
      />
    </div>
  );
}

export function SettingsPanel({
  settings,
  onChange,
  onClear,
  onExport,
  onSave,
  statusText,
}: SettingsPanelProps) {
  const set = <K extends keyof Settings>(key: K, val: Settings[K]) =>
    onChange({ ...settings, [key]: val });

  return (
    <div className="h-full flex flex-col overflow-y-auto px-3 py-4">
      <h3 className="text-sm font-bold text-[var(--mythos-text)] mb-3 uppercase tracking-wider">
        Settings
      </h3>

      {/* System prompt selector */}
      <div className="mb-3">
        <label className="text-xs text-[var(--mythos-text2)] block mb-1">
          Prompt Template
        </label>
        <select
          className="w-full rounded-lg bg-[var(--mythos-surface2)] border border-[var(--mythos-border)] text-[var(--mythos-text)] text-sm px-2 py-1.5"
          value=""
          onChange={(e) => {
            if (!e.target.value) return;
            // Just indicate which prompt -- the actual text loads from backend
            set("systemPrompt", `[Loading ${e.target.value}...]`);
          }}
        >
          <option value="">Custom</option>
          {Object.entries(SYSTEM_PROMPTS).map(([name]) => (
            <option key={name} value={name}>
              {name.charAt(0).toUpperCase() + name.slice(1).replace("-", " ")}
            </option>
          ))}
        </select>
      </div>

      {/* System prompt textarea */}
      <div className="mb-3">
        <label className="text-xs text-[var(--mythos-text2)] block mb-1">
          System Prompt
        </label>
        <textarea
          className="w-full resize-y rounded-lg bg-[var(--mythos-surface2)] border border-[var(--mythos-border)] text-[var(--mythos-text)] text-xs px-2 py-2 font-mono"
          rows={5}
          value={settings.systemPrompt}
          onChange={(e) => set("systemPrompt", e.target.value)}
        />
      </div>

      {/* Sliders */}
      <Slider
        label="Temperature"
        value={settings.temperature}
        min={0}
        max={2}
        step={0.1}
        onChange={(v) => set("temperature", v)}
      />
      <Slider
        label="Top P"
        value={settings.topP}
        min={0}
        max={1}
        step={0.05}
        onChange={(v) => set("topP", v)}
      />
      <Slider
        label="Top K"
        value={settings.topK}
        min={0}
        max={100}
        step={1}
        onChange={(v) => set("topK", Math.round(v))}
      />
      <Slider
        label="Max Tokens"
        value={settings.maxTokens}
        min={256}
        max={4096}
        step={256}
        onChange={(v) => set("maxTokens", Math.round(v))}
      />
      <Slider
        label="Repeat Penalty"
        value={settings.repeatPenalty}
        min={1.0}
        max={2.0}
        step={0.1}
        onChange={(v) => set("repeatPenalty", v)}
      />

      {/* Toggles */}
      <div className="space-y-2 mt-2 mb-4">
        <label className="flex items-center gap-2 text-xs text-[var(--mythos-text2)] cursor-pointer">
          <input
            type="checkbox"
            checked={settings.useReflection}
            onChange={(e) => set("useReflection", e.target.checked)}
          />
          Self-Reflection (slower, higher quality)
        </label>
        <label className="flex items-center gap-2 text-xs text-[var(--mythos-text2)] cursor-pointer">
          <input
            type="checkbox"
            checked={settings.useRag}
            onChange={(e) => set("useRag", e.target.checked)}
          />
          RAG (Retrieval-Augmented Generation)
        </label>
      </div>

      {/* Status */}
      {statusText && (
        <div className="text-xs text-[var(--mythos-text2)] mb-3 px-1 py-1.5 rounded bg-[var(--mythos-surface2)] border border-[var(--mythos-border)]">
          {statusText}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2 mt-auto pt-3 border-t border-[var(--mythos-border)]">
        <button
          onClick={onClear}
          className="flex-1 text-xs py-2 rounded-lg bg-[var(--mythos-surface2)] border border-[var(--mythos-border)] text-[var(--mythos-text2)] hover:text-[var(--mythos-error)] hover:border-[var(--mythos-error)] transition-colors"
        >
          Clear
        </button>
        <button
          onClick={onSave}
          className="flex-1 text-xs py-2 rounded-lg bg-[var(--mythos-surface2)] border border-[var(--mythos-border)] text-[var(--mythos-text2)] hover:text-[var(--mythos-accent2)] hover:border-[var(--mythos-accent)] transition-colors"
        >
          Save
        </button>
        <button
          onClick={onExport}
          className="flex-1 text-xs py-2 rounded-lg bg-[var(--mythos-surface2)] border border-[var(--mythos-border)] text-[var(--mythos-text2)] hover:text-[var(--mythos-success)] hover:border-[var(--mythos-success)] transition-colors"
        >
          Export
        </button>
      </div>
    </div>
  );
}
