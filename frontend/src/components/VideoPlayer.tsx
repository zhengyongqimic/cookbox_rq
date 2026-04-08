import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, LoaderCircle, PauseCircle, PlayCircle, Volume2, VolumeX } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import type { PauseReason, PlaybackCommand, PlaybackState, Step } from '../types';

interface VideoPlayerProps {
  currentStep: Step | null;
  originalSource?: string | null;
  playbackCommand?: PlaybackCommand | null;
  isMuted: boolean;
  onMutedChange: (muted: boolean) => void;
  hasAudio?: boolean | null;
  playbackState: PlaybackState;
  onPlaybackStateChange: (state: PlaybackState) => void;
  pauseReason: PauseReason;
  onPauseReasonChange: (reason: PauseReason) => void;
}

const STALL_DETECTION_MS = 1500;
const MAX_RECOVERY_ATTEMPTS = 3;

const statusCopy: Record<PlaybackState, string> = {
  idle: 'Ready',
  loading_source: 'Loading step...',
  seeking_transition: 'Jumping to step...',
  playing_step: 'Playing',
  buffering_recovering: 'Recovering playback...',
  step_end_holding: 'Step complete. Point for next or open palm to replay.',
  manual_pause: 'Paused. Open palm to continue.',
  overview_mode: 'Overview mode',
  error_recoverable: 'Playback needs attention.',
};

const pauseReasonCopy: Record<Exclude<PauseReason, null>, { label: string; className: string }> = {
  gesture_pause: {
    label: 'Gesture Paused',
    className: 'border-orange-500/40 bg-orange-500/10 text-orange-200',
  },
  step_complete: {
    label: 'Step Complete',
    className: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200',
  },
  manual_click: {
    label: 'Paused',
    className: 'border-zinc-500/40 bg-zinc-700/30 text-zinc-100',
  },
};

const formatSeconds = (value: number) => {
  const safe = Math.max(0, Math.floor(value));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
};

const VideoPlayer: React.FC<VideoPlayerProps> = ({
  currentStep,
  originalSource,
  playbackCommand,
  isMuted,
  onMutedChange,
  hasAudio,
  playbackState,
  onPlaybackStateChange,
  pauseReason,
  onPauseReasonChange,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const lastSourceRef = useRef<string | null>(null);
  const lastProgressRef = useRef<{ time: number; at: number }>({ time: 0, at: Date.now() });
  const recoveryAttemptsRef = useRef(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [showPlayPauseFeedback, setShowPlayPauseFeedback] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string>(statusCopy.idle);
  const [lastCommandToken, setLastCommandToken] = useState(0);
  const [currentPlaybackTime, setCurrentPlaybackTime] = useState(0);
  const isSoftSlicing = currentStep?.video_url?.includes('/videos/') || currentStep?.video_url?.endsWith('.mp4') || false;
  const stepStart = currentStep?.start ?? 0;
  const stepEnd = currentStep?.end ?? currentPlaybackTime;
  const stepDuration = Math.max(0.1, stepEnd - stepStart);
  const stepElapsed = Math.min(Math.max(currentPlaybackTime - stepStart, 0), stepDuration);
  const stepProgressPercent = Math.max(0, Math.min(100, (stepElapsed / stepDuration) * 100));

  const shouldWatchForStall = useMemo(
    () => playbackState === 'playing_step' || playbackState === 'buffering_recovering' || playbackState === 'seeking_transition',
    [playbackState]
  );

  useEffect(() => {
    setStatusMessage(statusCopy[playbackState]);
  }, [playbackState]);

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.muted = isMuted;
    }
  }, [isMuted]);

  useEffect(() => {
    if (!currentStep) {
      setCurrentPlaybackTime(0);
      return;
    }
    setCurrentPlaybackTime(currentStep.start ?? 0);
  }, [currentStep]);

  useEffect(() => {
    if (!currentStep?.video_url || !videoRef.current) {
      return;
    }

    const video = videoRef.current;
    const nextSource = currentStep.video_url;

    const seekToStep = async () => {
      try {
        onPlaybackStateChange('seeking_transition');
        const nextTime = isSoftSlicing ? currentStep.start ?? 0 : 0;
        video.currentTime = nextTime;
        await video.play();
        recoveryAttemptsRef.current = 0;
        lastProgressRef.current = { time: video.currentTime, at: Date.now() };
        setCurrentPlaybackTime(video.currentTime);
        onPauseReasonChange(null);
        onPlaybackStateChange('playing_step');
        setIsPlaying(true);
      } catch (error) {
        console.log('Playback seek/play failed:', error);
        onPlaybackStateChange('manual_pause');
      }
    };

    if (lastSourceRef.current !== nextSource) {
      lastSourceRef.current = nextSource;
      onPlaybackStateChange('loading_source');
      video.src = nextSource;
      const handleLoadedMetadata = () => {
        void seekToStep();
        video.removeEventListener('loadedmetadata', handleLoadedMetadata);
      };
      video.addEventListener('loadedmetadata', handleLoadedMetadata);
      video.load();
      return () => video.removeEventListener('loadedmetadata', handleLoadedMetadata);
    }

    if (video.readyState >= 1) {
      void seekToStep();
    } else {
      const handleCanPlay = () => {
        void seekToStep();
        video.removeEventListener('canplay', handleCanPlay);
      };
      video.addEventListener('canplay', handleCanPlay);
      return () => video.removeEventListener('canplay', handleCanPlay);
    }
  }, [currentStep, isSoftSlicing, onPlaybackStateChange]);

  useEffect(() => {
    if (!playbackCommand || playbackCommand.token === lastCommandToken || !videoRef.current || !currentStep) {
      return;
    }

    setLastCommandToken(playbackCommand.token);
    setShowPlayPauseFeedback(true);
    window.setTimeout(() => setShowPlayPauseFeedback(false), 800);

    const video = videoRef.current;
    const runCommand = async () => {
      try {
        if (playbackCommand.type === 'replay_current') {
          video.currentTime = currentStep.start ?? 0;
          await video.play();
          setCurrentPlaybackTime(video.currentTime);
          onPauseReasonChange(null);
          onPlaybackStateChange('playing_step');
          return;
        }

        if (playbackCommand.type === 'resume') {
          await video.play();
          onPauseReasonChange(null);
          onPlaybackStateChange('playing_step');
          return;
        }

        if (playbackCommand.type === 'pause') {
          video.pause();
          onPlaybackStateChange('manual_pause');
          return;
        }

        if (video.paused) {
          await video.play();
          onPlaybackStateChange('playing_step');
        } else {
          video.pause();
          onPlaybackStateChange('manual_pause');
        }
      } catch (error) {
        console.log('Playback command failed:', error);
        onPlaybackStateChange('error_recoverable');
      }
    };

    void runCommand();
  }, [currentStep, lastCommandToken, onPlaybackStateChange, playbackCommand]);

  useEffect(() => {
    if (!shouldWatchForStall || !videoRef.current) {
      return;
    }

    const interval = window.setInterval(() => {
      const video = videoRef.current;
      if (!video || video.paused || playbackState === 'step_end_holding' || playbackState === 'manual_pause') {
        return;
      }

      const now = Date.now();
      if (Math.abs(video.currentTime - lastProgressRef.current.time) > 0.05) {
        lastProgressRef.current = { time: video.currentTime, at: now };
        return;
      }

      if (now - lastProgressRef.current.at < STALL_DETECTION_MS) {
        return;
      }

      if (recoveryAttemptsRef.current >= MAX_RECOVERY_ATTEMPTS) {
        onPlaybackStateChange('error_recoverable');
        setStatusMessage('Playback stalled. Tap to retry or change step.');
        return;
      }

      recoveryAttemptsRef.current += 1;
      onPlaybackStateChange('buffering_recovering');
      setStatusMessage(`Recovering playback (${recoveryAttemptsRef.current}/${MAX_RECOVERY_ATTEMPTS})...`);

      const recover = async () => {
        if (!videoRef.current || !currentStep) {
          return;
        }
        const safeEnd = currentStep.end ?? videoRef.current.currentTime + 1;
        const targetTime = Math.max(Math.min(videoRef.current.currentTime, safeEnd - 0.1), currentStep.start ?? 0);
        try {
          videoRef.current.load();
          const handleCanPlay = async () => {
            try {
              videoRef.current?.removeEventListener('canplay', handleCanPlay);
              if (videoRef.current) {
                videoRef.current.currentTime = targetTime;
                await videoRef.current.play();
                lastProgressRef.current = { time: videoRef.current.currentTime, at: Date.now() };
                setCurrentPlaybackTime(videoRef.current.currentTime);
                onPauseReasonChange(null);
                onPlaybackStateChange('playing_step');
              }
            } catch (error) {
              console.log('Playback recovery failed:', error);
              onPlaybackStateChange('error_recoverable');
            }
          };
          videoRef.current.addEventListener('canplay', handleCanPlay);
        } catch (error) {
          console.log('Playback recovery failed:', error);
          onPlaybackStateChange('error_recoverable');
        }
      };

      void recover();
    }, 500);

    return () => window.clearInterval(interval);
  }, [currentStep, onPlaybackStateChange, playbackState, shouldWatchForStall]);

  const handleTimeUpdate = () => {
    if (!videoRef.current) {
      return;
    }

    lastProgressRef.current = { time: videoRef.current.currentTime, at: Date.now() };
    setCurrentPlaybackTime(videoRef.current.currentTime);

    if (isSoftSlicing && currentStep?.end !== undefined && videoRef.current.currentTime >= currentStep.end) {
      videoRef.current.pause();
      videoRef.current.currentTime = currentStep.start || 0;
      setIsPlaying(false);
      setCurrentPlaybackTime(currentStep.end);
      onPauseReasonChange('step_complete');
      onPlaybackStateChange('step_end_holding');
      setStatusMessage(statusCopy.step_end_holding);
    }
  };

  const togglePlay = () => {
    if (!videoRef.current || !currentStep) {
      return;
    }

    setShowPlayPauseFeedback(true);
    window.setTimeout(() => setShowPlayPauseFeedback(false), 800);

    if (playbackState === 'step_end_holding') {
      videoRef.current.currentTime = currentStep.start ?? 0;
      videoRef.current.play().catch(() => {});
      setCurrentPlaybackTime(videoRef.current.currentTime);
      onPauseReasonChange(null);
      onPlaybackStateChange('playing_step');
      return;
    }

    if (videoRef.current.paused) {
      videoRef.current.play().catch(() => {});
      onPauseReasonChange(null);
      onPlaybackStateChange('playing_step');
    } else {
      videoRef.current.pause();
      onPauseReasonChange('manual_click');
      onPlaybackStateChange('manual_pause');
    }
  };

  return (
    <div className="relative w-full max-w-4xl aspect-video bg-black rounded-xl overflow-hidden shadow-2xl border border-zinc-800 cursor-pointer group" onClick={togglePlay}>
      {currentStep ? (
        <video
          ref={videoRef}
          className="w-full h-full object-contain"
          controls={false}
          onPlay={() => {
            setIsPlaying(true);
            setCurrentPlaybackTime(videoRef.current?.currentTime ?? currentPlaybackTime);
            if (playbackState !== 'buffering_recovering') {
              onPlaybackStateChange('playing_step');
            }
          }}
          onPause={() => {
            setIsPlaying(false);
            if (playbackState === 'playing_step') {
              onPlaybackStateChange('manual_pause');
            }
          }}
          onWaiting={() => {
            if (playbackState === 'playing_step') {
              onPlaybackStateChange('buffering_recovering');
            }
          }}
          onStalled={() => onPlaybackStateChange('buffering_recovering')}
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

      <div className="absolute left-4 top-4 z-30 flex items-center gap-2 rounded-full border border-zinc-700 bg-black/60 px-3 py-2 text-xs text-zinc-100 backdrop-blur-sm">
        {playbackState === 'buffering_recovering' ? <LoaderCircle size={14} className="animate-spin text-orange-400" /> : playbackState === 'error_recoverable' ? <AlertCircle size={14} className="text-red-400" /> : <div className="h-2 w-2 rounded-full bg-emerald-400" />}
        <span>{statusMessage}</span>
      </div>

      <div className="absolute bottom-0 left-0 right-0 p-6 bg-gradient-to-t from-black/80 to-transparent">
        <div className="mb-4 space-y-2">
          <div className="flex items-center justify-between gap-3 text-xs uppercase tracking-[0.18em] text-zinc-400">
            <span>{currentStep ? `Step ${currentStep.step_number ?? ''}`.trim() : 'Step'}</span>
            <span>{formatSeconds(stepElapsed)} / {formatSeconds(stepDuration)}</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full border border-zinc-700/80 bg-zinc-900/80">
            <motion.div
              className={`h-full rounded-full ${
                playbackState === 'step_end_holding'
                  ? 'bg-emerald-400 shadow-[0_0_16px_rgba(52,211,153,0.45)]'
                  : 'bg-[#FF6A00] shadow-[0_0_14px_rgba(255,106,0,0.45)]'
              }`}
              animate={{ width: `${stepProgressPercent}%` }}
              transition={{ duration: playbackState === 'playing_step' ? 0.2 : 0.35, ease: 'easeOut' }}
            />
          </div>
          <div className="flex items-center justify-between gap-3">
            <div className="text-xs text-zinc-500">
              {playbackState === 'step_end_holding'
                ? 'This step has finished playing.'
                : playbackState === 'manual_pause' && pauseReason === 'gesture_pause'
                  ? 'Paused by gesture command.'
                  : playbackState === 'manual_pause'
                    ? 'Playback is paused.'
                    : playbackState === 'buffering_recovering'
                      ? 'Re-syncing playback stream.'
                      : 'Following the current cooking step.'}
            </div>
            {pauseReason && (
              <div className={`rounded-full border px-3 py-1 text-xs font-semibold ${pauseReasonCopy[pauseReason].className}`}>
                {pauseReasonCopy[pauseReason].label}
              </div>
            )}
          </div>
        </div>

        <div className="flex justify-between items-end gap-4">
          <div>
            <h2 className="text-2xl font-bold text-white mb-2">{currentStep?.title || 'Ready'}</h2>
            <p className="text-zinc-300 text-lg mb-2">{currentStep?.description}</p>
            {currentStep?.highlight && (
              <div className="inline-block px-3 py-1 bg-orange-500 text-white text-sm font-bold rounded-full">
                {currentStep.highlight}
              </div>
            )}
            {playbackState === 'step_end_holding' && (
              <p className="mt-3 text-sm text-emerald-300">Point right for next, point left to go back, or open palm to replay.</p>
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
