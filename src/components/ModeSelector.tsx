import { MODE_CONFIG, type CodingMode } from "../types";

interface ModeSelectorProps {
  mode: CodingMode;
  onChange: (mode: CodingMode) => void;
}

export function ModeSelector({ mode, onChange }: ModeSelectorProps) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto py-1 px-1">
      {(Object.entries(MODE_CONFIG) as [CodingMode, typeof MODE_CONFIG[CodingMode]][]).map(
        ([key, cfg]) => (
          <button
            key={key}
            className={`mythos-mode-tab ${mode === key ? "active" : ""}`}
            onClick={() => onChange(key)}
            title={`Switch to ${cfg.label} mode`}
          >
            <span>{cfg.icon}</span>
            <span>{cfg.label}</span>
          </button>
        )
      )}
    </div>
  );
}
