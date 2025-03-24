import { memo, useCallback } from 'react';
import { useGallery } from './GalleryContext';
import { ImageThumbnail } from './ImageThumbnail';
import { GalleryOverlay } from './GalleryOverlay';
import './styles.css';

interface ImageGalleryProps {
  images: Array<{
    src: string;
    alt?: string;
  }>;
}

const ImageGallery = memo(({ images }: ImageGalleryProps) => {
  const { openGallery } = useGallery();

  const handleImageClick = useCallback(
    (index: number) => {
      openGallery(images, index);
    },
    [images, openGallery]
  );

  if (!images || images.length === 0) {
    return null;
  }

  return (
    <div className="image-gallery">
      {images.map((image, index) => (
        <ImageThumbnail
          key={`${image.src}-${index}`}
          src={image.src}
          alt={image.alt}
          onClick={() => handleImageClick(index)}
        />
      ))}
    </div>
  );
});

ImageGallery.displayName = 'ImageGallery';

export default ImageGallery;
export { GalleryProvider, useGallery } from './GalleryContext';
export { GalleryOverlay };
