/** Pied de page : signature Butschi Digital Systems, discrète, sous le contenu. */
export function Footer() {
  return (
    <footer className="mx-auto flex w-full max-w-6xl items-center justify-center gap-1.5 px-4 py-6 text-xs text-muted">
      <span>
        made with <span className="text-gold">♥</span> by
      </span>
      <a
        href="https://butschi-digital-systems.ch"
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center opacity-80 transition-opacity hover:opacity-100"
        aria-label="Butschi Digital Systems"
        title="Butschi Digital Systems"
      >
        <img src="/bds-shield.png" alt="Butschi Digital Systems" className="size-5" />
      </a>
    </footer>
  );
}
