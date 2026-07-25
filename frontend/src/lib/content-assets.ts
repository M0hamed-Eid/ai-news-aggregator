import type { SyntheticEvent } from 'react';
import type { ContentItem, SourceKey } from '@/lib/types';

export const DEFAULT_SOURCE_IMAGE_SRC = '/sources/_default.png';

export function getSourceImageSrc(source: SourceKey | string): string {
  return `/sources/${source}.png`;
}

export function getContentImageSrc(item: ContentItem): string {
  if (item.type === 'video') {
    return item.thumbnailUrl || getSourceImageSrc(item.source);
  }

  return item.imageUrl || getSourceImageSrc(item.source);
}

export function fallbackContentImage(event: SyntheticEvent<HTMLImageElement>, source: SourceKey | string) {
  const image = event.currentTarget;
  const sourceImageSrc = getSourceImageSrc(source);

  if (image.src.endsWith(DEFAULT_SOURCE_IMAGE_SRC)) return;

  if (!image.src.endsWith(sourceImageSrc)) {
    image.src = sourceImageSrc;
    return;
  }

  image.src = DEFAULT_SOURCE_IMAGE_SRC;
}
