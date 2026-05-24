const QUICK_ACTIONS = [
  { label: "Explain", prompt: "Explain this code step by step:", icon: "📖" },
  { label: "Review", prompt: "Review this code for bugs, performance issues, and best practices:", icon: "🔍" },
  { label: "Optimize", prompt: "Optimize this code for performance and readability:", icon: "⚡" },
  { label: "Test", prompt: "Write comprehensive tests for:", icon: "🧪" },
  { label: "Document", prompt: "Add thorough documentation and docstrings to:", icon: "📝" },
  { label: "Refactor", prompt: "Refactor this code following clean code principles:", icon: "🔄" },
  { label: "Security", prompt: "Perform a security audit on:", icon: "🛡" },
  { label: "TypeScript", prompt: "Convert this to TypeScript with proper types:", icon: "🔷" },
];

interface QuickActionsProps {
  onAction: (prompt: string) => void;
}

export function QuickActions({ onAction }: QuickActionsProps) {
  return (
    <div className="flex items-center gap-1.5 overflow-x-auto py-1 px-2">
      {QUICK_ACTIONS.map((a) => (
        <button
          key={a.label}
          className="mythos-quick-action"
          onClick={() => onAction(a.prompt)}
          title={a.prompt}
        >
          <span>{a.icon}</span>
          <span>{a.label}</span>
        </button>
      ))}
    </div>
  );
}
