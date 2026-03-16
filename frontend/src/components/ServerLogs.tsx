import React, { useEffect, useState, useRef } from 'react';
import { Terminal, X, Minimize2, Maximize2 } from 'lucide-react';
import io from 'socket.io-client';

interface LogEntry {
  time: string;
  message: string;
  level: 'info' | 'warning' | 'error';
}

const ServerLogs: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Initial fetch of logs
    fetch('/api/logs')
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          setLogs(data);
        }
      })
      .catch(err => console.error("Failed to fetch logs", err));

    // Connect to the same host but via proxy (or direct if needed)
    // Using path /socket.io which is proxied in vite.config.ts
    const socket = io('/', { 
      path: '/socket.io',
      reconnectionAttempts: 5,
      timeout: 10000,
    });
    
    socket.on('connect', () => {
      console.log("Socket connected for logs");
      setIsConnected(true);
    });

    socket.on('disconnect', () => {
      console.log("Socket disconnected");
      setIsConnected(false);
    });

    socket.on('connect_error', (err) => {
      console.error("Socket connection error:", err);
      setIsConnected(false);
    });
    
    socket.on('server_log', (log: LogEntry) => {
      setLogs(prev => [...prev, log].slice(-100)); // Keep last 100 logs
      if (!isOpen) setIsOpen(true); // Auto open on new log
    });

    return () => {
      socket.disconnect();
    };
  }, []);

  useEffect(() => {
    if (isOpen && !isMinimized) {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, isOpen, isMinimized]);

  if (!isOpen) {
    return (
      <button 
        onClick={() => setIsOpen(true)}
        className={`fixed bottom-4 left-4 p-2 rounded-full border transition-all z-50 shadow-lg ${
          isConnected ? 'bg-black/80 text-green-400 border-green-900 hover:bg-black' : 'bg-red-900/80 text-white border-red-700 hover:bg-red-900'
        }`}
        title="Show Server Logs"
      >
        <Terminal size={20} />
        {!isConnected && <span className="absolute -top-1 -right-1 w-3 h-3 bg-red-500 rounded-full animate-pulse" />}
      </button>
    );
  }

  if (isMinimized) {
    return (
      <div className="fixed bottom-4 left-4 w-64 bg-black/90 border border-zinc-800 rounded-t-lg z-50 font-mono text-xs shadow-xl">
        <div className="flex justify-between items-center p-2 bg-zinc-900 border-b border-zinc-800 rounded-t-lg cursor-pointer" onClick={() => setIsMinimized(false)}>
          <span className="text-zinc-400 flex items-center gap-2">
            <Terminal size={14} className={isConnected ? "text-green-500" : "text-red-500"} /> 
            Server Logs {isConnected ? "" : "(Offline)"}
          </span>
          <div className="flex gap-2">
            <button onClick={(e) => { e.stopPropagation(); setIsMinimized(false); }} className="text-zinc-500 hover:text-white"><Maximize2 size={14} /></button>
            <button onClick={(e) => { e.stopPropagation(); setIsOpen(false); }} className="text-zinc-500 hover:text-white"><X size={14} /></button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed bottom-4 left-4 w-96 h-64 bg-black/90 border border-zinc-800 rounded-lg z-50 font-mono text-xs shadow-xl flex flex-col">
      <div className="flex justify-between items-center p-2 bg-zinc-900 border-b border-zinc-800 rounded-t-lg">
        <span className="text-zinc-400 flex items-center gap-2">
            <Terminal size={14} className={isConnected ? "text-green-500" : "text-red-500"} /> 
            Server Logs {isConnected ? "" : "(Offline)"}
        </span>
        <div className="flex gap-2">
          <button onClick={() => setIsMinimized(true)} className="text-zinc-500 hover:text-white"><Minimize2 size={14} /></button>
          <button onClick={() => setIsOpen(false)} className="text-zinc-500 hover:text-white"><X size={14} /></button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {logs.length === 0 ? (
          <div className="text-zinc-600 italic">No logs yet...</div>
        ) : (
          logs.map((log, i) => (
            <div key={i} className={`break-words ${
              log.level === 'error' ? 'text-red-400' : 
              log.level === 'warning' ? 'text-yellow-400' : 'text-zinc-300'
            }`}>
              <span className="text-zinc-600">[{log.time}]</span> {log.message}
            </div>
          ))
        )}
        <div ref={logsEndRef} />
      </div>
    </div>
  );
};

export default ServerLogs;