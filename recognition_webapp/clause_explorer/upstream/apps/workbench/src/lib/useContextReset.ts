import { useEffect, useRef } from "react";

/** Reset drafts on an actual context change, not when Activity resumes effects. */
export function useContextReset(key: string, reset: () => void): void {
  const previous = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (previous.current === key) return;
    previous.current = key;
    reset();
  }, [key]);
}
