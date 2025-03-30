import { memo, useCallback } from 'react';

import { useGallery } from './GalleryContext';
import { GalleryOverlay } from './GalleryOverlay';
import { ImageThumbnail } from './ImageThumbnail';
import './styles.css';

interface ImageGalleryProps {
  images: Array<{
    src: string;
    alt?: string;
    isMatching?: boolean;
  }>;
}

// Extracted list item component
const GalleryItem = memo(
  ({
    image,
    index,
    onItemClick,
  }: {
    image: { src: string; alt?: string; isMatching?: boolean };
    index: number;
    onItemClick: (index: number) => void;
  }) => {
    const handleClick = useCallback(() => {
      onItemClick(index);
    }, [index, onItemClick]);

    return (
      <ImageThumbnail
        src={image.src}
        alt={image.alt}
        onClick={handleClick}
        isMatching={image.isMatching}
      />
    );
  },
);

const ImageGallery = memo(({ images }: ImageGalleryProps) => {
  const { openGallery } = useGallery();

  const handleImageClick = useCallback(
    (index: number) => {
      openGallery(images, index);
    },
    [images, openGallery],
  );

  if (!images || images.length === 0) {
    return null;
  }

  return (
    <div className="image-gallery">
      {images.map((image, index) => (
        <GalleryItem
          key={`${image.src}-${index}`}
          image={image}
          index={index}
          onItemClick={handleImageClick}
        />
      ))}
    </div>
  );
});

export default ImageGallery;
export { GalleryProvider, useGallery } from './GalleryContext';
export { GalleryOverlay };
