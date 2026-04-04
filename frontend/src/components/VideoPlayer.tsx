import React, { useEffect, useRef, useState } from 'react';
import { PauseCircle, PlayCircle, Volume2, VolumeX } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import type { GestureType, Step } from '../types';

interface VideoPlayerProps {
  currentStep: Step | null;
  onGesture: (gesture: GestureType) => void;
  originalSource?: string | null;
  togglePlayTrigger?: number;
  isMuted: boolean;
  onMutedChange: (muted: boolean) => void;
  hasAudio?: boolean | null;
}

const VideoPlayer: React.FC<VideoPlayerProps> = ({
  currentStep,
  onGesture,
  originalSource,
  togglePlayTrigger,
  isMuted,
  onMutedChange,
  hasAudio,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const lastSourceRef = useRef<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [showPlayPauseFeedback, setShowPlayPauseFeedback] = useState(false);
  const isSoftSlicing = currentStep?.video_url?.includes('/videos/') || currentStep?.video_url?.endsWith('.mp4') || false;

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.muted = isMuted;
    }
  }, [isMuted]);

  useEffect(() => {
    if (!currentStep?.video_url || !videoRef.current) {
      return;
    }

    const video = videoRef.current;
    const nextSource = currentStep.video_url;
    const seekToStep = () => {
      const nextTime = isSoftSlicing ? currentStep.start ?? 0 : 0;
      video.currentTime = nextTime;
      video.play()
        .then(() => setIsPlaying(true))
        .catch((error) => console.log('Autoplay prevented:', error));
    };

    if (lastSourceRef.current !== nextSource) {
      lastSourceRef.current = nextSource;
      video.src = nextSource;
      const handleLoadedMetadata = () => {
        seekToStep();
        video.removeEventListener('loadedmetadata', handleLoadedMetadata);
      };
      video.addEventListener('loadedmetadata', handleLoadedMetadata);
      video.load();
      return () => video.removeEventListener('loadedmetadata', handleLoadedMetadata);
    }

    if (video.readyState >= 1) {
      seekToStep();
    } else {
      const handleCanPlay = () => {
        seekToStep();
        video.removeEventListener('canplay', handleCanPlay);
      };
      video.addEventListener('canplay', handleCanPlay);
      return () => video.removeEventListener('canplay', handleCanPlay);
    }
  }, [currentStep, isSoftSlicing]);

  useEffect(() => {
    if (!togglePlayTrigger || !videoRef.current) {
      return;
    }

    setShowPlayPauseFeedback(true);
    window.setTimeout(() => setShowPlayPauseFeedback(false), 800);
    if (videoRef.current.paused) {
      videoRef.current.play().catch(() => {});
    } else {
      videoRef.current.pause();
    }
  }, [togglePlayTrigger]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!currentStep) return;
      if (document.activeElement instanceof HTMLInputElement || document.activeElement instanceof HTMLTextAreaElement) return;

      switch (e.code) {
        case 'Space':
          e.preventDefault();
          if (videoRef.current?.paused) {
            videoRef.current.play().catch(() => {});
          } else {
            videoRef.current?.pause();
          }
          break;
        case 'ArrowLeft':
          e.preventDefault();
          onGesture('prev');
          break;
        case 'ArrowRight':
          e.preventDefault();
          onGesture('next');
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [currentStep, onGesture]);

  const handleTimeUpdate = () => {
    if (videoRef.current && isSoftSlicing && currentStep?.end !== undefined) {
      if (videoRef.current.currentTime >= currentStep.end) {
        videoRef.current.pause();
        videoRef.current.currentTime = currentStep.start || 0;
        setIsPlaying(false);
      }
    }
  };

  const togglePlay = () => {
    if (!videoRef.current) {
      return;
    }

    if (videoRef.current.paused) {
      videoRef.current.play().catch(() => {});
    } else {
      videoRef.current.pause();
    }
  };

  return (
    <div className="relative w-full max-w-4xl aspect-video bg-black rounded-xl overflow-hidden shadow-2xl border border-zinc-800 cursor-pointer group" onClick={togglePlay}>
      {currentStep ? (
        <video
          ref={videoRef}
          className="w-full h-full object-contain"
          controls={false}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onTimeUpdate={handleTimeUpdate}
          loop={!isSoftSlicing}
          muted={isMuted}
          playsInline
        />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-zinc-500">
          No video selected
        </div>
      )}

      <div className="absolute bottom-0 left-0 right-0 p-6 bg-gradient-to-t from-black/80 to-transparent">
        <div className="flex justify-between items-end gap-4">
          <div>
            <h2 className="text-2xl font-bold text-white mb-2">{currentStep?.title || 'Ready'}</h2>
            <p className="text-zinc-300 text-lg mb-2">{currentStep?.description}</p>
            {currentStep?.highlight && (
              <div className="inline-block px-3 py-1 bg-orange-500 text-white text-sm font-bold rounded-full">
                {currentStep.highlight}
              </div>
            )}
            {hasAudio === false && (
              <p className="mt-3 text-sm text-amber-300">This video does not contain an audio track.</p>
            )}
          </div>

          <div className="flex items-center gap-2">
            {hasAudio !== false && (
              <button
                type="button"
                className="text-zinc-200 hover:text-orange-500 transition-colors bg-black/50 px-3 py-2 rounded-full border border-zinc-700"
                onClick={(e) => {
                  e.stopPropagation();
                  onMutedChange(!isMuted);
                }}
                title={isMuted ? 'Enable sound' : 'Mute'}
              >
                {isMuted ? <VolumeX size={18} /> : <Volume2 size={18} />}
              </button>
            )}
            {originalSource && (
              <a
                href={originalSource}
                target="_blank"
                rel="noopener noreferrer"
                className="text-zinc-400 hover:text-orange-500 text-sm flex items-center gap-1 transition-colors bg-black/40 px-3 py-2 rounded-full border border-zinc-700 hover:border-orange-500/50"
                onClick={(e) => e.stopPropagation()}
              >
                Original Source
              </a>
            )}
          </div>
        </div>
      </div>

      {!isPlaying && currentStep && !showPlayPauseFeedback && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/20 pointer-events-none">
          <div className="bg-black/50 p-4 rounded-full backdrop-blur-sm">
            <PlayCircle size={48} className="text-white/80" />
          </div>
        </div>
      )}

      <AnimatePresence>
        {showPlayPauseFeedback && (
          <motion.div
            initial={{ opacity: 0, scale: 0.5 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 1.5 }}
            transition={{ duration: 0.3 }}
            className="absolute inset-0 flex items-center justify-center pointer-events-none z-40"
          >
            <div className="bg-black/60 p-6 rounded-full backdrop-blur-md text-white shadow-2xl">
              {isPlaying ? <PauseCircle size={64} /> : <PlayCircle size={64} />}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default VideoPlayer;
