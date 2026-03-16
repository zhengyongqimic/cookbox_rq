import React, { useEffect, useRef, useState } from 'react';
import io, { Socket } from 'socket.io-client';
import Hls from 'hls.js';
import { PlayCircle } from 'lucide-react';
import type { Step, GestureType } from '../types';

interface VideoPlayerProps {
  currentStep: Step | null;
  onGesture: (gesture: GestureType) => void;
  originalSource?: string | null;
  filename?: string | null; // Filename for MP4 fallback
}

const VideoPlayer: React.FC<VideoPlayerProps> = ({ currentStep, onGesture, originalSource, filename }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const socketRef = useRef<Socket | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const lastUrlRef = useRef<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [webcamStream, setWebcamStream] = useState<MediaStream | null>(null);
  const webcamVideoRef = useRef<HTMLVideoElement>(null);
  
  // Track if we are using the full video file (soft slicing)
  // Check if currentStep has the flag or if we are just checking properties
  // The backend might send HLS url, which is also a full video usually.
  const isSoftSlicing = currentStep?.video_url?.includes('/videos/') || currentStep?.video_url?.endsWith('.m3u8') || false;

  useEffect(() => {
    // Initialize Socket.io
    socketRef.current = io({
      path: '/socket.io',
      transports: ['websocket'],
    });

    socketRef.current.on('connect', () => {
      console.log('Connected to socket server');
    });

    socketRef.current.on('gesture_detected', (data: { gesture: GestureType }) => {
      console.log('Gesture detected:', data.gesture);
      onGesture(data.gesture);
      
      // Handle local pause/play based on gesture if needed, but App.tsx handles logic
      if (data.gesture === 'open_palm' && videoRef.current) {
        if (videoRef.current.paused) {
          videoRef.current.play().catch(() => {});
        } else {
          videoRef.current.pause();
        }
      }
    });

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
      if (hlsRef.current) {
          hlsRef.current.destroy();
      }
    };
  }, [onGesture]);

  // Handle video source change and Seeking logic
  useEffect(() => {
    if (videoRef.current && currentStep?.video_url) {
      const newSrc = currentStep.video_url;
      
      // Only reload src if it changed to avoid flickering when switching steps on same video
      if (newSrc !== lastUrlRef.current) {
          lastUrlRef.current = newSrc;
          
          if (hlsRef.current) {
              hlsRef.current.destroy();
              hlsRef.current = null;
          }

          if (newSrc.endsWith('.m3u8')) {
              if (Hls.isSupported()) {
                  const hls = new Hls({
                      debug: true, // Enable debug logs to troubleshoot black screen
                  });
                  hls.loadSource(newSrc);
                  hls.attachMedia(videoRef.current);
                  hlsRef.current = hls;
                  hls.on(Hls.Events.MANIFEST_PARSED, () => {
                      // Only play if we are ready or just loaded
                      videoRef.current?.play().catch(() => {});
                  });
                  
                  hls.on(Hls.Events.ERROR, (event, data) => {
                      console.error("HLS Error:", data);
                      if (data.fatal) {
                          switch (data.type) {
                              case Hls.ErrorTypes.NETWORK_ERROR:
                                  console.log("fatal network error encountered, try to recover");
                                  hls.startLoad();
                                  break;
                              case Hls.ErrorTypes.MEDIA_ERROR:
                                  console.log("fatal media error encountered, try to recover");
                                  hls.recoverMediaError();
                                  break;
                              default:
                                  console.log("cannot recover, destroy hls");
                                  hls.destroy();
                                  // Fallback to MP4 if HLS fails fatally
                                  if (filename) {
                                      console.log("Falling back to MP4:", filename);
                                      videoRef.current!.src = `/videos/${filename}`;
                                      videoRef.current!.load();
                                      videoRef.current!.play().catch(() => {});
                                  }
                                  break;
                          }
                      }
                  });
              } else if (videoRef.current.canPlayType('application/vnd.apple.mpegurl')) {
                  videoRef.current.src = newSrc;
              }
          } else {
              videoRef.current.src = newSrc;
              videoRef.current.load();
          }
      }

      // Seeking Logic
      const seekToStart = () => {
         if (videoRef.current) {
            if (isSoftSlicing && currentStep.start !== undefined) {
                videoRef.current.currentTime = currentStep.start;
                console.log(`Soft Slice: Seeked to ${currentStep.start}s`);
            } else {
                videoRef.current.currentTime = 0;
            }
            videoRef.current.play().catch(e => console.log("Autoplay prevented:", e));
            setIsPlaying(true);
         }
      };

      // If HLS, we might need to wait for manifest parsed or media attached
      // But usually setting currentTime works if metadata is loaded.
      // We can use a small timeout or check readyState, but for now direct seek is usually fine if we just loaded or are already loaded.
      
      // If src didn't change, we can seek immediately.
      // If src changed, we might need to wait for loadedmetadata.
      
      if (videoRef.current.readyState >= 1) {
          seekToStart();
      } else {
          videoRef.current.onloadedmetadata = () => {
              seekToStart();
              // Remove listener to avoid seeking on subsequent metadata loads if any
              if (videoRef.current) videoRef.current.onloadedmetadata = null;
          };
      }
    }
  }, [currentStep, isSoftSlicing]);

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
          if (videoElement && canvasRef.current && socketRef.current && stream) {
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
          requestAnimationFrame(captureFrame);
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
  }, []);



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
          ref={videoRef}
          className="w-full h-full object-contain"
          controls={false} // Custom controls or gesture only
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onTimeUpdate={handleTimeUpdate} // Attach time update handler
          loop={!isSoftSlicing} // Only loop natively if NOT soft slicing
          muted // Muted for autoplay policy, user can unmute
          playsInline
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
      {!isPlaying && currentStep && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/20 pointer-events-none">
          <div className="bg-black/50 p-4 rounded-full backdrop-blur-sm">
             <PlayCircle size={48} className="text-white/80" />
          </div>
        </div>
      )}
    </div>
  );
};

export default VideoPlayer;
