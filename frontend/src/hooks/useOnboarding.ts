import { useState, useCallback } from "react";

const STORAGE_KEY = "farewise-onboarding-done";

export function useOnboarding() {
  const [step, setStep] = useState(0);
  const [active, setActive] = useState(() => {
    return !localStorage.getItem(STORAGE_KEY);
  });

  const next = useCallback(() => {
    setStep((s) => s + 1);
  }, []);

  const skip = useCallback(() => {
    setActive(false);
    localStorage.setItem(STORAGE_KEY, "true");
  }, []);

  const finish = useCallback(() => {
    setActive(false);
    localStorage.setItem(STORAGE_KEY, "true");
  }, []);

  const reset = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setStep(0);
    setActive(true);
  }, []);

  return { step, active, next, skip, finish, reset };
}
