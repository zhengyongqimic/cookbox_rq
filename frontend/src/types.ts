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
  step_number?: number;
  start: number;
  end: number;
  start_time?: number;
  end_time?: number;
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
  thumbnail_url?: string | null;
  duration_seconds?: number | null;
  video_status?: string | null;
  has_audio?: boolean | null;
}

export type GestureType = 'next' | 'prev' | 'toggle_pause' | 'overview' | 'resume_overview' | 'open_palm' | null;

export interface ProcessingStatus {
  file_id: string;
  status: 'analyzing' | 'slicing' | 'completed' | 'error';
  progress?: number;
  steps?: Step[];
  message?: string;
  video_url?: string | null;
  thumbnail_url?: string | null;
  duration_seconds?: number | null;
  has_audio?: boolean | null;
  original_url?: string | null;
}

export interface RecipeDetailPayload {
  file_id: string;
  status: string;
  steps: Step[];
  original_url?: string | null;
  video_url?: string | null;
  thumbnail_url?: string | null;
  duration_seconds?: number | null;
  has_audio?: boolean | null;
}

export type PlaybackState =
  | 'idle'
  | 'loading_source'
  | 'seeking_transition'
  | 'playing_step'
  | 'buffering_recovering'
  | 'step_end_holding'
  | 'manual_pause'
  | 'overview_mode'
  | 'error_recoverable';

export type PauseReason = 'gesture_pause' | 'step_complete' | 'manual_click' | null;

export type PlaybackCommandType = 'toggle' | 'pause' | 'resume' | 'replay_current';

export interface PlaybackCommand {
  type: PlaybackCommandType;
  token: number;
}

export interface GestureDetectedEvent {
  gesture: Exclude<GestureType, null>;
  confidence?: number;
  hold_ms?: number;
  mode?: PlaybackState | 'grid';
  event_id?: string;
  gesture_session_id?: string;
}
