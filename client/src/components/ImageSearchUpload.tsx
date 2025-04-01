import { useState, useRef, useCallback, memo } from 'react';

import { API_ROUTES } from '@/const';

interface ImageSearchUploadProps {
  onSearchResults: (results: any) => void;
  onError: (error: string) => void;
  onSearchStart: () => void;
}

export const ImageSearchUpload = memo(
  ({ onSearchResults, onError, onSearchStart }: ImageSearchUploadProps) => {
    const [dragActive, setDragActive] = useState(false);
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleDrag = useCallback((e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();

      if (e.type === 'dragenter' || e.type === 'dragover') {
        setDragActive(true);
      } else if (e.type === 'dragleave') {
        setDragActive(false);
      }
    }, []);

    const handleDrop = useCallback(
      (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);

        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
          const file = e.dataTransfer.files[0];
          if (file.type.startsWith('image/')) {
            setSelectedFile(file);
          } else {
            onError('Please upload an image file');
          }
        }
      },
      [onError],
    );

    const handleChange = useCallback(
      (e: React.ChangeEvent<HTMLInputElement>) => {
        e.preventDefault();

        if (e.target.files && e.target.files[0]) {
          const file = e.target.files[0];
          if (file.type.startsWith('image/')) {
            setSelectedFile(file);
          } else {
            onError('Please upload an image file');
          }
        }
      },
      [onError],
    );

    const handleSubmit = useCallback(
      async (e: React.FormEvent) => {
        e.preventDefault();

        if (!selectedFile) {
          onError('Please select an image to search with');
          return;
        }

        try {
          onSearchStart();

          const formData = new FormData();
          formData.append('file', selectedFile);

          const response = await fetch(API_ROUTES.SEARCH_BY_IMAGE, {
            method: 'POST',
            body: formData,
          });

          if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to search with image');
          }

          const data = await response.json();
          onSearchResults(data.results);
        } catch (error) {
          onError(error instanceof Error ? error.message : 'Error searching with image');
        }
      },
      [selectedFile, onSearchResults, onError, onSearchStart],
    );

    const openFileSelector = useCallback(() => {
      if (fileInputRef.current) {
        fileInputRef.current.click();
      }
    }, []);

    const clearSelectedFile = useCallback(() => {
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }, []);

    return (
      <div className="image-search-container">
        <form
          onSubmit={handleSubmit}
          onDragEnter={handleDrag}
          className={`image-drop-area ${dragActive ? 'active' : ''} ${selectedFile ? 'has-file' : ''}`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleChange}
            className="image-upload-input"
          />

          {!selectedFile ? (
            <div className="image-upload-placeholder">
              <div className="image-upload-icon">
                <span className="material-icons">image_search</span>
              </div>
              <div className="image-upload-text">
                <p>Drag and drop an image or</p>
                <button type="button" className="image-upload-button" onClick={openFileSelector}>
                  Browse files
                </button>
              </div>
            </div>
          ) : (
            <div className="selected-image-container">
              <div className="selected-image-preview">
                <img src={URL.createObjectURL(selectedFile)} alt="Selected" />
              </div>
              <div className="selected-image-info">
                <p>{selectedFile.name}</p>
                <button type="button" className="clear-image-button" onClick={clearSelectedFile}>
                  <span className="material-icons">close</span>
                </button>
              </div>
            </div>
          )}

          {selectedFile && (
            <button type="submit" className="image-search-button">
              <span className="material-icons">search</span>
              Search with this image
            </button>
          )}

          {dragActive && (
            <div
              className="drag-overlay"
              onDragEnter={handleDrag}
              onDragOver={handleDrag}
              onDragLeave={handleDrag}
              onDrop={handleDrop}
            />
          )}
        </form>
      </div>
    );
  },
);
