import { useOnboarding } from "@/hooks/useOnboarding";

const STEPS = [
  {
    title: "Welcome to FareWise!",
    body: "Find the best travel deals while staying compliant with company policies.",
  },
  {
    title: "Create a Trip",
    body: "Click 'New Trip' to describe your travel needs in natural language or fill in the form.",
  },
  {
    title: "Smart Search",
    body: "Use the What-If slider to balance cost vs convenience. FareWise finds the optimal options.",
  },
  {
    title: "Track & Save",
    body: "Set up Price Watches, earn badges, and see how you rank on the leaderboard!",
  },
];

export function OnboardingTour() {
  const { step, active, next, skip, finish } = useOnboarding();

  if (!active || step >= STEPS.length) return null;

  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-card rounded-xl shadow-2xl p-6 max-w-sm w-full mx-4">
        {/* Step indicator */}
        <div className="flex gap-1.5 mb-4">
          {STEPS.map((_, i) => (
            <div
              key={i}
              className={`h-1 flex-1 rounded-full ${
                i <= step ? "bg-primary" : "bg-muted"
              }`}
            />
          ))}
        </div>

        <h3 className="text-lg font-bold mb-2">{current.title}</h3>
        <p className="text-sm text-muted-foreground mb-4">{current.body}</p>

        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={skip}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Skip tour
          </button>
          <button
            type="button"
            onClick={isLast ? finish : next}
            className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded-md hover:opacity-90"
          >
            {isLast ? "Get Started" : "Next"}
          </button>
        </div>
      </div>
    </div>
  );
}
