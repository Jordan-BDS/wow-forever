/**
 * Valeurs de la guilde, mises en avant comme une devise gravée : plume d'or en haut à droite,
 * filets brodés, texte en italique de parchemin aligné à gauche. Une ligne vide sépare les strophes,
 * les retours à la ligne à l'intérieur d'une strophe sont conservés (vers d'un poème).
 * Rien n'est affiché tant que le GM n'a rien écrit.
 */
export function GuildValues({ text, author }: { text: string; author?: string }) {
  const stanzas = text
    .split(/\n\s*\n/)
    .map((stanza) =>
      stanza
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .join("\n"),
    )
    .filter(Boolean);
  if (stanzas.length === 0) return null;

  return (
    <figure className="relative flex h-full flex-col justify-center overflow-hidden rounded-md border border-gold-dark/50 bg-surface/80 px-6 py-6 sm:px-10 sm:py-8">
      <div className="rule-gold absolute inset-x-6 top-0 sm:inset-x-10" />
      <QuillIcon className="absolute top-4 right-4 size-7 text-gold sm:top-5 sm:right-5 sm:size-8" />
      {/* Bloc centré à la largeur du vers le plus long, texte aligné à gauche à l'intérieur. */}
      <div className="relative mx-auto w-fit max-w-full pr-8 sm:pr-0">
        <blockquote className="space-y-4 text-left font-sans text-lg italic leading-relaxed whitespace-pre-line text-text">
          {stanzas.map((stanza, index) => (
            <p key={index}>{stanza}</p>
          ))}
        </blockquote>
        {author && (
          <figcaption className="mt-5 text-right font-display text-sm tracking-widest text-gold uppercase">
            {author}
          </figcaption>
        )}
      </div>
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
