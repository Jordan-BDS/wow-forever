import { useEffect } from "react";

/** Domaine Wowhead à utiliser pour les infobulles. À passer sur le domaine Forever dès qu'il existe. */
export const WOWHEAD_DOMAIN = "classic";

export const QUALITY_COLOR: Record<number, string> = {
  0: "#9d9d9d",
  1: "#ffffff",
  2: "#1eff00",
  3: "#0070dd",
  4: "#a335ee",
  5: "#ff8000",
};

declare global {
  interface Window {
    $WowheadPower?: { refreshLinks: () => void };
  }
}

/** Demande au script Wowhead de (re)brancher les infobulles après un rendu. */
export function useWowheadTooltips(deps: unknown[]) {
  useEffect(() => {
    const id = window.setTimeout(() => window.$WowheadPower?.refreshLinks(), 50);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
