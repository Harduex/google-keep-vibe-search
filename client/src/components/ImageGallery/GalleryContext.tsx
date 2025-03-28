import React, { createContext, useContext, useState, useCallback, useMemo, ReactNode } from 'react';

interface GalleryImage {
  src: string;
  alt?: string;
}

interface GalleryState {
  isOpen: boolean;
  images: GalleryImage[];
  currentIndex: number;
}

interface GalleryActions {
  openGallery: (images: GalleryImage[], startIndex?: number) => void;
  closeGallery: () => void;
  nextImage: () => void;
  prevImage: () => void;
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

  return useMemo(
    () => ({
      isOpen,
      images,
      currentIndex,
      openGallery,
      closeGallery,
      nextImage,
      prevImage,
    }),
    [isOpen, images, currentIndex, openGallery, closeGallery, nextImage, prevImage],
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
