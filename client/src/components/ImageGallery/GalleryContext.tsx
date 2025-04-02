import React, { createContext, useContext, useState, useCallback, useMemo, ReactNode } from 'react';

import { API_ROUTES } from '@/const';

interface GalleryImage {
  src: string;
  alt?: string;
  isMatching?: boolean;
}

interface GalleryState {
  isOpen: boolean;
  images: GalleryImage[];
  currentIndex: number;
  isSearchingSimilar: boolean;
}

interface GalleryActions {
  openGallery: (images: GalleryImage[], startIndex?: number) => void;
  closeGallery: () => void;
  nextImage: () => void;
  prevImage: () => void;
  findSimilarImages: (
    onResults: (results: any) => void,
    onError: (error: string) => void,
    onSwitchTab?: (tab: string) => void,
  ) => void;
}

export interface GalleryContextData extends GalleryState, GalleryActions {}

const GalleryContext = createContext<GalleryContextData | undefined>(undefined);

interface GalleryProviderProps {
  children: ReactNode;
}

function useCreateGallery(): GalleryContextData {
  const [isOpen, setIsOpen] = useState(false);
  const [images, setImages] = useState<GalleryImage[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isSearchingSimilar, setIsSearchingSimilar] = useState(false);

  const openGallery = useCallback((newImages: GalleryImage[], startIndex = 0) => {
    setImages(newImages);
    setCurrentIndex(startIndex);
    setIsOpen(true);
  }, []);

  const closeGallery = useCallback(() => {
    setIsOpen(false);
  }, []);

  const nextImage = useCallback(() => {
    if (images.length > 1) {
      setCurrentIndex((prevIndex) => (prevIndex + 1) % images.length);
    }
  }, [images.length]);

  const prevImage = useCallback(() => {
    if (images.length > 1) {
      setCurrentIndex((prevIndex) => (prevIndex - 1 + images.length) % images.length);
    }
  }, [images.length]);

  const findSimilarImages = useCallback(
    async (
      onResults: (results: any) => void,
      onError: (error: string) => void,
      onSwitchTab?: (tab: string) => void,
    ) => {
      if (!isOpen || images.length === 0) {
        return;
      }

      const currentImage = images[currentIndex];
      if (!currentImage || !currentImage.src) {
        return;
      }

      try {
        setIsSearchingSimilar(true);

        // Get the current image from the gallery
        const imageUrl = currentImage.src;

        // Fetch the image data from the URL
        const imageResponse = await fetch(imageUrl);
        if (!imageResponse.ok) {
          throw new Error('Failed to fetch image data');
        }

        // Get image as blob
        const imageBlob = await imageResponse.blob();

        // Create a FormData object and append the image blob
        const formData = new FormData();
        formData.append('file', imageBlob, 'gallery_image.jpg');

        // Send the image to the existing search API endpoint
        const searchResponse = await fetch(API_ROUTES.SEARCH_BY_IMAGE, {
          method: 'POST',
          body: formData,
        });

        if (!searchResponse.ok) {
          const errorData = await searchResponse.json();
          throw new Error(errorData.detail || 'Failed to find similar images');
        }

        const data = await searchResponse.json();

        // Switch to search tab if the handler is provided
        if (onSwitchTab) {
          onSwitchTab('search');
        }

        onResults(data.results);

        // Close the gallery after finding similar images
        closeGallery();
      } catch (error) {
        onError(error instanceof Error ? error.message : 'Error finding similar images');
      } finally {
        setIsSearchingSimilar(false);
      }
    },
    [isOpen, images, currentIndex, closeGallery],
  );

  return useMemo(
    () => ({
      isOpen,
      images,
      currentIndex,
      isSearchingSimilar,
      openGallery,
      closeGallery,
      nextImage,
      prevImage,
      findSimilarImages,
    }),
    [
      isOpen,
      images,
      currentIndex,
      isSearchingSimilar,
      openGallery,
      closeGallery,
      nextImage,
      prevImage,
      findSimilarImages,
    ],
  );
}

export const GalleryProvider: React.FC<GalleryProviderProps> = ({ children }) => {
  const gallery = useCreateGallery();

  return <GalleryContext.Provider value={gallery}>{children}</GalleryContext.Provider>;
};

export function useGallery(): GalleryContextData {
  const context = useContext(GalleryContext);

  if (!context) {
    throw new Error('useGallery must be used within a GalleryProvider');
  }

  return context;
}
