import type { Settings } from "../types";
import { SYSTEM_PROMPTS, MODE_CONFIG, type CodingMode } from "../types";

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
        <span className="text-[var(--mythos-accent2)] font-mono text-[11px]">
          {value}
        </span>
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

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-xs text-[var(--mythos-text2)] cursor-pointer py-1">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
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
      {/* Mode quick-switch */}
      <h3 className="text-[10px] font-bold text-[var(--mythos-text3)] mb-2 uppercase tracking-widest">
        Mode
      </h3>
      <div className="grid grid-cols-2 gap-1 mb-4">
        {(Object.entries(MODE_CONFIG) as [CodingMode, typeof MODE_CONFIG[CodingMode]][]).map(
          ([key, cfg]) => (
            <button
              key={key}
              onClick={() => {
                set("mode", key);
                set("temperature", cfg.temp);
              }}
              className={`flex items-center gap-1.5 px-2 py-1.5 rounded-md text-[11px] font-medium transition-colors ${
                settings.mode === key
                  ? "bg-[var(--mythos-accent-dim)] text-[var(--mythos-accent2)] border border-[var(--mythos-accent)]"
                  : "bg-[var(--mythos-surface2)] text-[var(--mythos-text2)] border border-transparent hover:border-[var(--mythos-border)]"
              }`}
            >
              <span>{cfg.icon}</span>
              <span>{cfg.label}</span>
            </button>
          )
        )}
      </div>

      {/* Generation params */}
      <h3 className="text-[10px] font-bold text-[var(--mythos-text3)] mb-2 uppercase tracking-widest">
        Generation
      </h3>
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
        max={8192}
        step={256}
        onChange={(v) => set("maxTokens", Math.round(v))}
      />
      <Slider
        label="Repeat Penalty"
        value={settings.repeatPenalty}
        min={1.0}
        max={2.0}
        step={0.05}
        onChange={(v) => set("repeatPenalty", v)}
      />

      {/* Code display */}
      <h3 className="text-[10px] font-bold text-[var(--mythos-text3)] mb-2 mt-4 uppercase tracking-widest">
        Code Display
      </h3>
      <Slider
        label="Font Size"
        value={settings.fontSize}
        min={11}
        max={18}
        step={1}
        onChange={(v) => set("fontSize", Math.round(v))}
      />
      <Toggle
        label="Line Numbers"
        checked={settings.showLineNumbers}
        onChange={(v) => set("showLineNumbers", v)}
      />
      <Toggle
        label="Line Wrap"
        checked={settings.lineWrap}
        onChange={(v) => set("lineWrap", v)}
      />

      {/* Features */}
      <h3 className="text-[10px] font-bold text-[var(--mythos-text3)] mb-2 mt-4 uppercase tracking-widest">
        Features
      </h3>
      <Toggle
        label="Self-Reflection (slower, higher quality)"
        checked={settings.useReflection}
        onChange={(v) => set("useReflection", v)}
      />
      <Toggle
        label="Thinking Mode (show step-by-step reasoning)"
        checked={settings.useThinking}
        onChange={(v) => set("useThinking", v)}
      />
      <Toggle
        label="RAG (Retrieval-Augmented Generation)"
        checked={settings.useRag}
        onChange={(v) => set("useRag", v)}
      />

      {/* System prompt */}
      <h3 className="text-[10px] font-bold text-[var(--mythos-text3)] mb-2 mt-4 uppercase tracking-widest">
        System Prompt
      </h3>
      <select
        className="w-full rounded-lg bg-[var(--mythos-surface2)] border border-[var(--mythos-border)] text-[var(--mythos-text)] text-xs px-2 py-1.5 mb-2"
        value=""
        onChange={(e) => {
          if (!e.target.value) return;
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
      <textarea
        className="w-full resize-y rounded-lg bg-[var(--mythos-surface2)] border border-[var(--mythos-border)] text-[var(--mythos-text)] text-[11px] px-2 py-2 font-mono mb-3"
        rows={4}
        value={settings.systemPrompt}
        onChange={(e) => set("systemPrompt", e.target.value)}
      />

      {/* Status */}
      {statusText && (
        <div className="text-[11px] text-[var(--mythos-text2)] mb-3 px-2 py-1.5 rounded-md bg-[var(--mythos-surface2)] border border-[var(--mythos-border)] font-mono">
          {statusText}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2 mt-auto pt-3 border-t border-[var(--mythos-border)]">
        <button
          onClick={onClear}
          className="flex-1 text-[11px] py-2 rounded-lg bg-[var(--mythos-surface2)] border border-[var(--mythos-border)] text-[var(--mythos-text2)] hover:text-[var(--mythos-error)] hover:border-[var(--mythos-error)] transition-colors"
        >
          Clear
        </button>
        <button
          onClick={onSave}
          className="flex-1 text-[11px] py-2 rounded-lg bg-[var(--mythos-surface2)] border border-[var(--mythos-border)] text-[var(--mythos-text2)] hover:text-[var(--mythos-accent2)] hover:border-[var(--mythos-accent)] transition-colors"
        >
          Save
        </button>
        <button
          onClick={onExport}
          className="flex-1 text-[11px] py-2 rounded-lg bg-[var(--mythos-surface2)] border border-[var(--mythos-border)] text-[var(--mythos-text2)] hover:text-[var(--mythos-success)] hover:border-[var(--mythos-success)] transition-colors"
        >
          Export
        </button>
      </div>
    </div>
  );
}
