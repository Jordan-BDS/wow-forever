/** Écu héraldique stylisé : un bouclier bleu nuit liseré d'or, une épée et une couronne. */
export function Emblem({ className = "size-10" }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 72" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="emblem-field" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#2b5bb0" />
          <stop offset="1" stopColor="#0d1a30" />
        </linearGradient>
      </defs>
      <path
        d="M32 4 L58 12 V36 C58 52 46 63 32 68 C18 63 6 52 6 36 V12 Z"
        fill="url(#emblem-field)"
        stroke="#d9b84a"
        strokeWidth="2.5"
        strokeLinejoin="round"
      />
      <path
        d="M32 9 L53 15.5 V36 C53 49 43 58.5 32 63 C21 58.5 11 49 11 36 V15.5 Z"
        fill="none"
        stroke="#a8862a"
        strokeWidth="1"
      />
      <path d="M32 20 V54" stroke="#efe6cf" strokeWidth="3" strokeLinecap="round" />
      <path d="M22 28 H42" stroke="#d9b84a" strokeWidth="3" strokeLinecap="round" />
      <path d="M28 56 H36" stroke="#d9b84a" strokeWidth="3" strokeLinecap="round" />
      <path d="M22 18 L26 13 L32 17 L38 13 L42 18 Z" fill="#d9b84a" />
    </svg>
  );
}
