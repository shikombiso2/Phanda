import { useEffect, useState } from "react";

/** Returns `value`, but only after it's stopped changing for `delayMs` --
 * used on the search box so every keystroke doesn't fire its own request. */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
