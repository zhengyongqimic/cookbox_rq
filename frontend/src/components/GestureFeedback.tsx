import React, { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { GestureType } from '../types';
import { Hand, ArrowRight, ArrowLeft, LayoutGrid, PlayCircle } from 'lucide-react';

interface GestureFeedbackProps {
  gesture: GestureType;
  onClear: () => void;
}

const GestureFeedback: React.FC<GestureFeedbackProps> = ({ gesture, onClear }) => {
  useEffect(() => {
    if (gesture) {
      const timer = setTimeout(onClear, 2000);
      return () => clearTimeout(timer);
    }
  }, [gesture, onClear]);

  const getIcon = () => {
    switch (gesture) {
      case 'next': return <ArrowRight size={48} />;
      case 'prev': return <ArrowLeft size={48} />;
      case 'toggle_pause': return <Hand size={48} />; // Placeholder for Pause/Play toggle
      case 'overview': return <LayoutGrid size={48} />;
      case 'resume_overview': return <PlayCircle size={48} />;
      case 'open_palm': return <PlayCircle size={48} />; // Changed icon to PlayCircle for clarity
      default: return null;
    }
  };

  const getText = () => {
    switch (gesture) {
      case 'next': return 'Next Step';
      case 'prev': return 'Previous Step';
      case 'toggle_pause': return 'Pause/Resume';
      case 'overview': return 'Overview';
      case 'resume_overview': return 'Back to Step';
      case 'open_palm': return 'Back to Step'; // Changed text
      default: return '';
    }
  };

  return (
    <AnimatePresence>
      {gesture && (
        <motion.div
          initial={{ opacity: 0, scale: 0.5, y: 50 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.5, y: -50 }}
          transition={{ duration: 0.3, ease: "easeOut" }}
          className="fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 bg-black/80 text-[#FF6A00] p-8 rounded-2xl flex flex-col items-center justify-center gap-4 z-50 backdrop-blur-md border border-[#FF6A00]/30 shadow-2xl"
        >
          {getIcon()}
          <span className="text-xl font-bold text-white">{getText()}</span>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default GestureFeedback;
