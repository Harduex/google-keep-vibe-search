import { memo } from 'react';

interface ImageThumbnailProps {
  src: string;
  alt?: string;
  onClick: () => void;
  isMatching?: boolean;
}

export const ImageThumbnail = memo(({ src, alt, onClick, isMatching }: ImageThumbnailProps) => {
  return (
    <div className={`gallery-thumbnail ${isMatching ? 'matching-image' : ''}`} onClick={onClick}>
      <img src={src} alt={alt || 'Image thumbnail'} />
    </div>
  );
});
