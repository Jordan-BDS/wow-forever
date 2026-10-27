import { QUALITY_COLOR, WOWHEAD_DOMAIN, WOWHEAD_URL } from "@/lib/wowhead";

export function WowheadLink({
  kind,
  id,
  quality,
  className,
  children,
}: {
  kind: "item" | "spell";
  id: number;
  quality?: number;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <a
      href={`${WOWHEAD_URL}/${kind}=${id}`}
      data-wowhead={`${kind}=${id}&domain=${WOWHEAD_DOMAIN}`}
      data-wh-icon-added="true"
      target="_blank"
      rel="noreferrer"
      className={className}
      style={quality != null ? { color: QUALITY_COLOR[quality] } : undefined}
    >
      {children}
    </a>
  );
}
