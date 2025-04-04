import { useEffect, useCallback, Dispatch, SetStateAction } from 'react';

import { useGallery } from './GalleryContext';

interface GalleryOverlayProps {
  onSearchSimilarResults?: (results: any) => void;
  onError?: (error: string) => void;
  onSwitchTab?: Dispatch<SetStateAction<string>>;
}

export const GalleryOverlay: React.FC<GalleryOverlayProps> = ({
  onSearchSimilarResults,
  onError,
  onSwitchTab,
}) => {
  const {
    isOpen,
    images,
    currentIndex,
    isSearchingSimilar,
    closeGallery,
    nextImage,
    prevImage,
    findSimilarImages,
  } = useGallery();

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!isOpen) {
        return;
      }

      switch (e.key) {
        case 'Escape':
          closeGallery();
          break;
        case 'ArrowRight':
          nextImage();
          break;
        case 'ArrowLeft':
          prevImage();
          break;
      }
    },
    [isOpen, closeGallery, nextImage, prevImage],
  );

  const handleFindSimilar = useCallback(() => {
    if (onSearchSimilarResults && onError) {
      findSimilarImages(onSearchSimilarResults, onError, onSwitchTab);
    }
  }, [findSimilarImages, onSearchSimilarResults, onError, onSwitchTab]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleKeyDown]);

  if (!isOpen || images.length === 0) {
    return null;
  }

  const currentImage = images[currentIndex];

  return (
    <div className="gallery-overlay">
      <div className="gallery-overlay-content">
        <button className="gallery-close" onClick={closeGallery}>
          <span className="material-icons">close</span>
        </button>

        {images.length > 1 && (
          <button className="gallery-prev" onClick={prevImage}>
            <span className="material-icons">chevron_left</span>
          </button>
        )}

        <div className="gallery-image-container">
          <img src={currentImage.src} alt={currentImage.alt || 'Gallery image'} />
        </div>

        {images.length > 1 && (
          <button className="gallery-next" onClick={nextImage}>
            <span className="material-icons">chevron_right</span>
          </button>
        )}

        {onSearchSimilarResults && onError && (
          <button
            className={`gallery-find-similar ${isSearchingSimilar ? 'loading' : ''}`}
            onClick={handleFindSimilar}
            disabled={isSearchingSimilar}
          >
            <span className="material-icons">
              {isSearchingSimilar ? 'hourglass_top' : 'image_search'}
            </span>
            {isSearchingSimilar ? 'Searching...' : 'Find Similar Images'}
          </button>
        )}

        <div className="gallery-counter">
          {currentIndex + 1} / {images.length}
        </div>
      </div>
    </div>
  );
};
