// Types mirroring the backend API (backend/api, vision/engine.py payloads).

export interface ScoreInfo {
  sector: number;
  multiplier: number;
  score: number;
  ring: string;
  label: string;
}

export interface Alternative extends ScoreInfo {
  probability: number;
}

export interface DartDetection {
  dart_id: string;
  timestamp: number;
  impact: { x_mm: number; y_mm: number; r_mm: number; theta_deg: number; x_norm: number; y_norm: number };
  covariance_mm2: number[][];
  sigma_mm: number;
  score: ScoreInfo;
  alternatives: Alternative[];
  score_probability: number;
  confidence: { detection: number; impact: number; score: number; overall: number };
  uncertain: boolean;
  cameras_used: string[];
  cameras_rejected: Record<string, string>;
  per_camera: Record<string, CandidateInfo & { line_residual_mm: number; line_sigma_mm: number; tip_weight: number }>;
  axis: number[] | null;
  tilt_deg: number | null;
  consistency: number;
}

export interface CandidateInfo {
  camera_id: string;
  tip_px: number[];
  tail_px: number[];
  line_rms_px: number;
  length_px: number;
  width_px: number;
  tip_visible: boolean;
  confidence: number;
  pixel_count: number;
  factors: Record<string, number>;
}

export interface CameraHealth {
  camera_id: string;
  kind: string;
  state: string;
  connected: boolean;
  fps: number;
  target_fps: number;
  frames_total: number;
  frames_corrupted: number;
  reconnects: number;
  last_error: string | null;
  last_frame_age_ms: number | null;
  frame_interval_jitter_ms: number;
  width: number;
  height: number;
  brightness: number;
  contrast: number;
  saturated_fraction: number;
  dark_fraction: number;
  sharpness: number;
  low_fps: boolean;
  controls: Record<string, number | string>;
}

export interface CameraConfig {
  id: string;
  name: string;
  enabled: boolean;
  source: { type: string; device?: number | string | null; url?: string | null; path?: string | null; api: string; fourcc?: string | null };
  width: number;
  height: number;
  fps: number;
  auto_exposure: boolean;
  exposure: number | null;
  gain: number | null;
  white_balance: number | null;
  rotate_180: boolean;
  mount: { azimuth_deg: number | null; description: string };
}

export interface CameraInfo {
  id: string;
  name: string;
  enabled: boolean;
  synthetic: boolean;
  config: CameraConfig;
  health: CameraHealth | null;
  calibration: {
    intrinsics: boolean;
    intrinsics_rms_px: number | null;
    pose: boolean;
    grade: string | null;
    calibrated_at: string | null;
    method: string | null;
    intrinsics_source: string | null;
  };
}

export interface Player {
  id: string;
  name: string;
  nickname: string | null;
  color: string;
  avatar: string | null;
  archived: boolean;
  created_at: string | null;
}

export interface GameDart {
  sector: number;
  multiplier: number;
  score: number;
  label: string;
  dart_id: string;
}

export interface Turn {
  player_index: number;
  darts: GameDart[];
  bust: boolean;
  finished: boolean;
  points: number;
  note: string;
}

export interface PendingDetection {
  id: string;
  label: string;
  score: number;
  x_mm: number;
  y_mm: number;
  confidence: number;
  uncertain: boolean;
  status: string;
  alternatives: Alternative[];
  score_probability: number | null;
  cameras_used: string[];
  sigma_mm: number | null;
  created_at: string | null;
}

export interface GameState {
  id: string;
  mode: string;
  mode_name: string;
  status: string;
  settings: Record<string, any>;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  players: (Player & { position: number })[];
  state: {
    current_player: number;
    leg: number;
    set: number;
    legs_won: number[];
    sets_won: number[];
    turns: Turn[];
    leg_history: { leg: number; set: number; winner: number; turns: Turn[] }[];
    player_data: Record<string, any>[];
    winner: number | null;
    finished: boolean;
    awaiting_takeout: boolean;
    message: string;
  };
  player_summaries: Record<string, any>[];
  checkout_hint: string[] | null;
  pending: PendingDetection[];
  winner: Player | null;
}

export interface GameSummary {
  id: string;
  mode: string;
  status: string;
  settings: Record<string, any>;
  players: Player[];
  created_at: string | null;
  finished_at: string | null;
  winner: Player | null;
}

export interface GameMode {
  id: string;
  name: string;
  description: string;
  darts_per_turn: number;
  settings: Record<string, SettingSchema>;
}

export interface SettingSchema {
  type: "integer" | "enum" | "boolean";
  default: any;
  values?: string[];
  presets?: number[];
  min?: number;
  max?: number;
  help?: string;
}

export interface BoardInfo {
  radii_mm: Record<string, number>;
  board_radius_mm: number;
  sector_order: number[];
  sector_angle_deg: number;
  wire_width_mm: number;
}

export interface EngineStatus {
  state: string;
  paused: boolean;
  darts_on_board: { dart_id: string; impact_mm: number[]; label: string; detected_at: number; cameras: string[]; manual: boolean }[];
  cameras: Record<string, { calibrated: boolean; has_reference: boolean; has_empty_reference: boolean; motion_fraction: number; candidates: number; validation: any }>;
  stats: Record<string, any>;
  last_detection: DartDetection | null;
}

export interface WsMessage {
  seq: number;
  channel: string;
  type: string;
  ts: number;
  data: any;
}
