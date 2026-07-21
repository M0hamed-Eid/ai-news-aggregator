'use client';

// Per-source branded icon (frontend/public/sources/{key}.png) — restores
// web/apps/catalog/templatetags/source_display.py's "source_artwork" filter,
// which the old Django cards always rendered but the Z.ai-authored SPA
// never carried over (ArticleCard/VideoCard only ever showed a text
// Badge). Source.key strings match these filenames 1:1 (no lookup dict
// needed, same as the original filter): any source not in the curated set
// (e.g. a user-submitted custom source) 404s on its own file and falls
// back to _default.png via onError, mirroring that filter's own fallback.
interface SourceIconProps {
  sourceKey: string;
  className?: string;
}

export default function SourceIcon({ sourceKey, className = 'h-4 w-4' }: SourceIconProps) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- small local
    // asset swap set, not worth a next/image config for this.
    <img
      src={`/sources/${sourceKey}.png`}
      alt=""
      className={`shrink-0 rounded-sm object-contain ${className}`}
      onError={(e) => {
        if (!e.currentTarget.src.endsWith('_default.png')) {
          e.currentTarget.src = '/sources/_default.png';
        }
      }}
    />
  );
}
