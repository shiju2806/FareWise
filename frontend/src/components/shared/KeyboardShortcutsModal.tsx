interface Props {
  open: boolean;
  onClose: () => void;
}

const shortcuts = [
  { key: "N", desc: "New trip" },
  { key: "T", desc: "My trips" },
  { key: "A", desc: "Analytics" },
  { key: "S", desc: "My stats" },
  { key: "?", desc: "Show shortcuts" },
  { key: "Esc", desc: "Close dialog" },
];

export function KeyboardShortcutsModal({ open, onClose }: Props) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="bg-card rounded-lg shadow-xl p-6 w-80"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-semibold mb-4">Keyboard Shortcuts</h3>
        <div className="space-y-2">
          {shortcuts.map((s) => (
            <div key={s.key} className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">{s.desc}</span>
              <kbd className="px-2 py-0.5 bg-muted rounded text-xs font-mono">
                {s.key}
              </kbd>
            </div>
          ))}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="mt-4 w-full text-center text-xs text-muted-foreground hover:text-foreground"
        >
          Close
        </button>
      </div>
    </div>
  );
}
