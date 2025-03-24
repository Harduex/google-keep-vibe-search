import { memo } from 'react';

interface ImageThumbnailProps {
  src: string;
  alt?: string;
  onClick: () => void;
}

export const ImageThumbnail = memo(({ src, alt, onClick }: ImageThumbnailProps) => {
  return (
    <div className="gallery-thumbnail" onClick={onClick}>
      <img src={src} alt={alt || 'Image thumbnail'} />
    </div>
  );
});

ImageThumbnail.displayName = 'ImageThumbnail';
