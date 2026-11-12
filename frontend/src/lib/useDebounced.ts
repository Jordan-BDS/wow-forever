import { useEffect, useState } from "react";

/** La valeur, une fois qu'elle n'a plus bougé pendant `delay` ms (saisie d'une recherche). */
export function useDebounced<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(id);
  }, [value, delay]);
  return debounced;
}
