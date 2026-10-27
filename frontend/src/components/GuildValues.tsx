/**
 * Valeurs de la guilde, mises en avant comme une devise gravée : plume d'or en haut à droite,
 * filets brodés, texte en italique de parchemin. Rien n'est affiché tant que le GM n'a rien écrit.
 */
export function GuildValues({ text, author }: { text: string; author?: string }) {
  const paragraphs = text
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);
  if (paragraphs.length === 0) return null;

  return (
    <figure className="relative mb-8 overflow-hidden rounded-md border border-gold-dark/50 bg-surface/80 px-6 py-6 sm:px-10 sm:py-8">
      <div className="rule-gold absolute inset-x-6 top-0 sm:inset-x-10" />
      <QuillIcon className="absolute top-4 right-4 size-7 text-gold sm:top-5 sm:right-5 sm:size-8" />
      <blockquote className="relative space-y-3 text-center font-sans text-lg italic leading-relaxed text-text sm:text-xl">
        {paragraphs.map((paragraph, index) => (
          <p key={index}>{paragraph}</p>
        ))}
      </blockquote>
      {author && (
        <figcaption className="mt-4 text-center font-display text-sm tracking-widest text-gold uppercase">
          {author}
        </figcaption>
      )}
      <div className="rule-gold absolute inset-x-6 bottom-0 sm:inset-x-10" />
    </figure>
  );
}

/** Plume d'écriture (tracé Lucide « feather »). */
function QuillIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M12.67 19a2 2 0 0 0 1.416-.588l6.154-6.172a6 6 0 0 0-8.49-8.49L5.586 9.914A2 2 0 0 0 5 11.328V18a1 1 0 0 0 1 1z" />
      <path d="M16 8 2 22" />
      <path d="M17.5 15H9" />
    </svg>
  );
}
