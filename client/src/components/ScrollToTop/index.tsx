import { useState, useEffect, memo, useCallback } from 'react';
import './styles.css';

interface ScrollToTopProps {
  threshold?: number; // Distance from top to show button (in pixels)
  smooth?: boolean; // Whether to use smooth scrolling
}

export const ScrollToTop = memo(({ threshold = 300, smooth = true }: ScrollToTopProps) => {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsVisible(window.scrollY > threshold);
    };

    window.addEventListener('scroll', handleScroll);

    handleScroll();

    // Clean up
    return () => {
      window.removeEventListener('scroll', handleScroll);
    };
  }, [threshold]);

  const scrollToTop = useCallback(() => {
    window.scrollTo({
      top: 0,
      behavior: smooth ? 'smooth' : 'auto',
    });
  }, [smooth]);

  if (!isVisible) {
    return null;
  }

  return (
    <div className="scroll-to-top" role="button" aria-label="Scroll to top">
      <button onClick={scrollToTop} title="Scroll to top">
        <span className="material-icons">arrow_upward</span>
      </button>
    </div>
  );
});
