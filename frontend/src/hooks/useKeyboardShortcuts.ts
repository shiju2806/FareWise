import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

export function useKeyboardShortcuts(
  onToggleHelp: () => void
) {
  const navigate = useNavigate();

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      // Skip if user is typing in an input/textarea
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      switch (e.key) {
        case "n":
          navigate("/trips/new");
          break;
        case "t":
          navigate("/trips");
          break;
        case "a":
          navigate("/analytics");
          break;
        case "s":
          navigate("/my-stats");
          break;
        case "?":
          onToggleHelp();
          break;
        case "Escape":
          onToggleHelp();
          break;
      }
    }

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [navigate, onToggleHelp]);
}
