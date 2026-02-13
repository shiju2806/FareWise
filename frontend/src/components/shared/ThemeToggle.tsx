import { useTheme } from "@/contexts/ThemeContext";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  function cycle() {
    const next = theme === "light" ? "dark" : theme === "dark" ? "system" : "light";
    setTheme(next);
  }

  const icon = theme === "dark" ? "\u263E" : theme === "light" ? "\u2600" : "\u2699";
  const label = theme === "dark" ? "Dark" : theme === "light" ? "Light" : "System";

  return (
    <button
      type="button"
      onClick={cycle}
      className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
      aria-label={`Theme: ${label}. Click to change.`}
    >
      <span className="text-sm">{icon}</span>
      <span>{label}</span>
    </button>
  );
}
