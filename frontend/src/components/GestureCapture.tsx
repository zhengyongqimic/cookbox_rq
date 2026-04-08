import React, { useEffect, useRef, useState } from 'react';
import io, { Socket } from 'socket.io-client';
import type { GestureDetectedEvent, PlaybackState } from '../types';

interface GestureCaptureProps {
  enabled: boolean;
  mode: PlaybackState | 'grid';
  onGesture: (event: GestureDetectedEvent) => void;
}

const frameIntervalByMode: Record<PlaybackState | 'grid', number> = {
  idle: 140,
  loading_source: 180,
  seeking_transition: 220,
  playing_step: 120,
  buffering_recovering: 180,
  step_end_holding: 90,
  manual_pause: 110,
  overview_mode: 140,
  error_recoverable: 180,
  grid: 200,
};

const GestureCapture: React.FC<GestureCaptureProps> = ({ enabled, mode, onGesture }) => {
  const [webcamStream, setWebcamStream] = useState<MediaStream | null>(null);
  const webcamVideoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const socketRef = useRef<Socket | null>(null);
  const captureFrameRef = useRef<number | null>(null);
  const lastFrameSentAtRef = useRef<number>(0);
  const consumedEventIdsRef = useRef<string[]>([]);
  const consumedSessionIdsRef = useRef<string[]>([]);

  useEffect(() => {
    socketRef.current = io('/', { path: '/socket.io' });
    socketRef.current.on('gesture_detected', (data: GestureDetectedEvent) => {
      if (data.event_id) {
        if (consumedEventIdsRef.current.includes(data.event_id)) {
          return;
        }
        consumedEventIdsRef.current = [...consumedEventIdsRef.current.slice(-24), data.event_id];
      }
      if (data.gesture_session_id) {
        if (consumedSessionIdsRef.current.includes(data.gesture_session_id)) {
          return;
        }
        consumedSessionIdsRef.current = [...consumedSessionIdsRef.current.slice(-24), data.gesture_session_id];
      }
      onGesture(data);
    });
    return () => {
      socketRef.current?.disconnect();
      socketRef.current = null;
    };
  }, [onGesture]);

  useEffect(() => {
    if (webcamVideoRef.current && webcamStream) {
      webcamVideoRef.current.srcObject = webcamStream;
      webcamVideoRef.current.play().catch((error) => console.error('Webcam preview error', error));
    }
  }, [webcamStream]);

  useEffect(() => {
    if (!enabled) {
      if (captureFrameRef.current) {
        cancelAnimationFrame(captureFrameRef.current);
        captureFrameRef.current = null;
      }
      if (webcamStream) {
        webcamStream.getTracks().forEach((track) => track.stop());
        setWebcamStream(null);
      }
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      console.error('Browser API navigator.mediaDevices.getUserMedia not available');
      return;
    }

    let activeStream: MediaStream | null = null;
    const sourceVideo = document.createElement('video');
    sourceVideo.width = 320;
    sourceVideo.height = 240;
    sourceVideo.autoplay = true;
    sourceVideo.muted = true;
    sourceVideo.playsInline = true;

    navigator.mediaDevices.getUserMedia({ video: true })
      .then((stream) => {
        activeStream = stream;
        setWebcamStream(stream);
        sourceVideo.srcObject = stream;
        return sourceVideo.play();
      })
      .then(() => {
        const captureFrame = () => {
          if (!enabled || !activeStream || !socketRef.current || !canvasRef.current) {
            return;
          }
          const now = performance.now();
          const frameInterval = frameIntervalByMode[mode] ?? 120;
          if (now - lastFrameSentAtRef.current < frameInterval) {
            if (activeStream.getTracks().some((track) => track.readyState === 'live')) {
              captureFrameRef.current = requestAnimationFrame(captureFrame);
            }
            return;
          }
          const context = canvasRef.current.getContext('2d');
          if (context && sourceVideo.readyState >= 2) {
            canvasRef.current.width = 320;
            canvasRef.current.height = 240;
            context.drawImage(sourceVideo, 0, 0, canvasRef.current.width, canvasRef.current.height);
            lastFrameSentAtRef.current = now;
            socketRef.current.emit('video_frame', {
              image: canvasRef.current.toDataURL('image/jpeg', 0.5),
              mode,
            });
          }
          if (activeStream.getTracks().some((track) => track.readyState === 'live')) {
            captureFrameRef.current = requestAnimationFrame(captureFrame);
          }
        };
        captureFrameRef.current = requestAnimationFrame(captureFrame);
      })
      .catch((error) => {
        console.error('Error accessing webcam:', error);
      });

    return () => {
      if (captureFrameRef.current) {
        cancelAnimationFrame(captureFrameRef.current);
        captureFrameRef.current = null;
      }
      if (activeStream) {
        activeStream.getTracks().forEach((track) => track.stop());
      }
      setWebcamStream(null);
    };
  }, [enabled, mode]);

  if (!enabled) {
    return null;
  }

  return (
    <>
      {webcamStream && (
        <div className="fixed top-24 right-6 z-50 w-48 aspect-video bg-black/50 rounded-lg overflow-hidden border border-zinc-700 shadow-lg">
          <video
            ref={webcamVideoRef}
            className="w-full h-full object-cover"
            muted
            playsInline
            style={{ transform: 'scaleX(-1)' }}
          />
          <div className="absolute bottom-1 left-2 text-[10px] text-white/70">Gesture Cam</div>
          <div className="absolute top-1 left-2 text-[10px] text-emerald-300/90 uppercase tracking-wide">{mode.replace('_', ' ')}</div>
        </div>
      )}
      <canvas ref={canvasRef} className="hidden" />
    </>
  );
};

export default GestureCapture;
