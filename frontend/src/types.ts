export interface User {
  id: number;
  username: string;
}

export interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

export interface Step {
  id: number;
  start: number;
  end: number;
  title: string;
  description: string;
  highlight?: string;
  video_url?: string | null;
  is_full_video?: boolean;
  is_hls?: boolean;
}

export interface Recipe {
  id: number;
  user_id: number;
  video_id: string;
  title: string;
  description: string;
  created_at: string;
}

export type GestureType = 'next' | 'prev' | 'toggle_pause' | 'overview' | 'resume_overview' | 'open_palm' | null;

export interface ProcessingStatus {
  file_id: string;
  status: 'analyzing' | 'slicing' | 'completed' | 'error';
  progress?: number;
  steps?: Step[];
  message?: string;
}
