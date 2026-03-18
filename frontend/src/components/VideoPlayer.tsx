import React, { useEffect, useRef, useState } from 'react';
import io, { Socket } from 'socket.io-client';
import { PlayCircle, PauseCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import type { Step, GestureType } from '../types';

interface VideoPlayerProps {
  currentStep: Step | null;
  onGesture: (gesture: GestureType) => void;
  originalSource?: string | null;
  togglePlayTrigger?: number; // Add a trigger prop to handle play/pause from parent
}

const VideoPlayer: React.FC<VideoPlayerProps> = ({ currentStep, onGesture, originalSource, togglePlayTrigger }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const socketRef = useRef<Socket | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [webcamStream, setWebcamStream] = useState<MediaStream | null>(null);
  const webcamVideoRef = useRef<HTMLVideoElement>(null);
  const [isVideoReady, setIsVideoReady] = useState(false);
  const [isCameraAllowed, setIsCameraAllowed] = useState(false); // Safety mechanism
  const [showPlayPauseFeedback, setShowPlayPauseFeedback] = useState(false); // Flashing feedback
  
  // Track if we are using the full video file (soft slicing)
  // Check if currentStep has the flag or if we are just checking properties
  // The backend might send HLS url, which is also a full video usually.
  const isSoftSlicing = currentStep?.video_url?.includes('/videos/') || currentStep?.video_url?.endsWith('.mp4') || false;

  // Reset video ready state when step changes
  useEffect(() => {
    setIsVideoReady(false);
    setIsCameraAllowed(false);
    
    // Safety timer: Enable camera after 3s even if video fails
    const timer = setTimeout(() => {
        console.log("Video load timeout, enabling camera anyway");
        setIsCameraAllowed(true);
    }, 3000);
    
    return () => clearTimeout(timer);
  }, [currentStep?.id]);

  useEffect(() => {
    // Initialize Socket.io
    socketRef.current = io('/', {
      path: '/socket.io',
    });

    socketRef.current.on('connect', () => {
      console.log('Connected to socket server');
    });

    socketRef.current.on('gesture_detected', (data: { gesture: GestureType }) => {
      console.log('Gesture detected:', data.gesture);
      onGesture(data.gesture);
    });

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
    };
  }, [onGesture]);

  // Handle play/pause trigger from parent
  useEffect(() => {
    if (togglePlayTrigger && videoRef.current) {
      // Show feedback animation
      setShowPlayPauseFeedback(true);
      setTimeout(() => setShowPlayPauseFeedback(false), 800);

      if (videoRef.current.paused) {
        videoRef.current.play().catch(() => {});
      } else {
        videoRef.current.pause();
      }
    }
  }, [togglePlayTrigger]);

  // Handle video source change and Seeking logic
  useEffect(() => {
    if (videoRef.current && currentStep?.video_url) {
      const newSrc = currentStep.video_url;
      
      const seekToStart = () => {
         if (videoRef.current) {
            if (isSoftSlicing && currentStep.start !== undefined) {
                videoRef.current.currentTime = currentStep.start;
            } else {
                videoRef.current.currentTime = 0;
            }
            videoRef.current.play()
              .then(() => setIsPlaying(true))
              .catch(e => console.log("Autoplay prevented:", e));
         }
      };
      
      // If src is different, load new source. Otherwise just seek.
      // This allows smooth transitions between steps using the same file.
      const currentSrcPath = videoRef.current.getAttribute('src'); // Get raw attribute
      // Note: videoRef.current.src returns absolute URL, so we compare carefully or just check filename
      
      if (!currentSrcPath || !currentSrcPath.endsWith(newSrc)) {
          console.log("Loading new video source:", newSrc);
          videoRef.current.src = newSrc;
          videoRef.current.load();
          videoRef.current.onloadedmetadata = () => {
              seekToStart();
          };
      } else {
          console.log("Same source, seeking to:", currentStep.start);
          seekToStart();
      }
    }
  }, [currentStep]); // Depend on full currentStep object to trigger on step change

  // Time update listener for Soft Slicing Loop
  const handleTimeUpdate = () => {
      if (videoRef.current && isSoftSlicing && currentStep?.end) {
          if (videoRef.current.currentTime >= currentStep.end) {
              console.log("Step ended, looping...");
              videoRef.current.pause();
              videoRef.current.currentTime = currentStep.start || 0;
              setIsPlaying(false);
              // Option: Auto-loop
              // videoRef.current.play();
          }
      }
  };

  useEffect(() => {
    if (webcamVideoRef.current && webcamStream) {
      webcamVideoRef.current.srcObject = webcamStream;
      webcamVideoRef.current.play().catch(e => console.error("Webcam play error", e));
    }
  }, [webcamStream]);

  // Frame capture loop for gesture recognition
  useEffect(() => {
    // Only start if camera is allowed (safety mechanism)
    if (!isCameraAllowed) {
        if (webcamStream) {
            // Cleanup if video became unready (e.g. switching)
            webcamStream.getTracks().forEach(track => track.stop());
            setWebcamStream(null);
        }
        return;
    }

    // Check if browser supports getUserMedia
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      console.error("Browser API navigator.mediaDevices.getUserMedia not available");
      return;
    }

    let stream: MediaStream | null = null;
    const videoElement = document.createElement('video');
    videoElement.width = 320;
    videoElement.height = 240;
    videoElement.autoplay = true;
    videoElement.muted = true; // Important to avoid feedback loop if mic is included

    // Start webcam
    navigator.mediaDevices.getUserMedia({ video: true })
      .then(s => {
        stream = s;
        setWebcamStream(s); // Save stream for preview
        videoElement.srcObject = stream;
        videoElement.play(); // Ensure video plays
        console.log("Webcam started");
        
        const captureFrame = () => {
          if (videoElement && canvasRef.current && socketRef.current && stream && isCameraAllowed) {
            const canvas = canvasRef.current;
            const context = canvas.getContext('2d');
    
            if (context && videoElement.readyState >= 2) { // HAVE_CURRENT_DATA or more
              canvas.width = 320; // Fixed width
              canvas.height = 240;
              context.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
              
              const imageData = canvas.toDataURL('image/jpeg', 0.5);
              socketRef.current.emit('video_frame', { image: imageData });
            }
          }
          if (stream.getTracks().some(track => track.readyState === 'live')) {
             requestAnimationFrame(captureFrame);
          }
        };
        requestAnimationFrame(captureFrame);
      })
      .catch(err => {
        console.error("Error accessing webcam:", err);
      });

    
    return () => {
      if (stream) {
        stream.getTracks().forEach(track => track.stop());
      }
    };
  }, [isCameraAllowed]);



  // Keyboard controls
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!currentStep) return;
      // Ignore if typing in an input
      if (document.activeElement instanceof HTMLInputElement || document.activeElement instanceof HTMLTextAreaElement) return;
      
      switch (e.code) {
        case 'Space':
          e.preventDefault();
          if (videoRef.current) {
            if (videoRef.current.paused) {
              videoRef.current.play().catch(() => {});
            } else {
              videoRef.current.pause();
            }
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

  const togglePlay = () => {
    if (videoRef.current) {
      if (videoRef.current.paused) {
        videoRef.current.play().catch(() => {});
      } else {
        videoRef.current.pause();
      }
    }
  };

  return (
    <div 
      className="relative w-full max-w-4xl aspect-video bg-black rounded-xl overflow-hidden shadow-2xl border border-zinc-800 cursor-pointer group"
      onClick={togglePlay}
    >
      {currentStep ? (
        <video
          // key={currentStep.id} // Removed key to prevent unmount/remount on step change
          ref={videoRef}
          className="w-full h-full object-contain"
          controls={false} // Custom controls or gesture only
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onTimeUpdate={handleTimeUpdate} // Attach time update handler
          loop={!isSoftSlicing} // Only loop natively if NOT soft slicing
          muted // Muted for autoplay policy, user can unmute
          playsInline
          onCanPlay={() => {
              setIsVideoReady(true);
              setIsCameraAllowed(true); // Video ready, enable camera immediately
          }}
          onError={() => {
              console.error("Video load error");
              setIsCameraAllowed(true); // Error, enable camera anyway
          }}
        />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-zinc-500">
          No video selected
        </div>
      )}
      
      {/* Webcam Preview */}
      {webcamStream && (
        <div className="absolute top-4 right-4 w-48 aspect-video bg-black/50 rounded-lg overflow-hidden border border-zinc-700 shadow-lg z-50">
          <video
            ref={webcamVideoRef}
            className="w-full h-full object-cover mirror" // mirror class for flip
            muted
            playsInline
            style={{ transform: 'scaleX(-1)' }} // CSS mirror
          />
          <div className="absolute bottom-1 left-2 text-[10px] text-white/70">Gesture Cam</div>
        </div>
      )}

      {/* Hidden canvas for frame capture */}
      <canvas ref={canvasRef} className="hidden" />
      
      {/* Overlay info */}
      <div className="absolute bottom-0 left-0 right-0 p-6 bg-gradient-to-t from-black/80 to-transparent">
        <div className="flex justify-between items-end">
          <div>
            <h2 className="text-2xl font-bold text-white mb-2">{currentStep?.title || "Ready"}</h2>
            <p className="text-zinc-300 text-lg mb-2">{currentStep?.description}</p>
            {currentStep?.highlight && (
              <div className="inline-block px-3 py-1 bg-orange-500 text-white text-sm font-bold rounded-full">
                {currentStep.highlight}
              </div>
            )}
          </div>
          
          {originalSource && (
            <a 
              href={originalSource} 
              target="_blank" 
              rel="noopener noreferrer"
              className="text-zinc-400 hover:text-orange-500 text-sm flex items-center gap-1 transition-colors bg-black/40 px-3 py-1 rounded-full border border-zinc-700 hover:border-orange-500/50"
              onClick={(e) => e.stopPropagation()}
            >
              Original Source ↗
            </a>
          )}
        </div>
      </div>

      {/* Play/Pause Indicator (Optional) */}
      {!isPlaying && currentStep && !showPlayPauseFeedback && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/20 pointer-events-none">
          <div className="bg-black/50 p-4 rounded-full backdrop-blur-sm">
             <PlayCircle size={48} className="text-white/80" />
          </div>
        </div>
      )}

      {/* Dynamic Flashing Play/Pause Feedback */}
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
