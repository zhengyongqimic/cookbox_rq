import eventlet
import eventlet.tpool # Explicitly import tpool
# Monkey patch socket to make yt-dlp non-blocking (cooperative)
try:
    eventlet.monkey_patch(dns=False)
except TypeError:
    # Fallback for older eventlet versions
    eventlet.monkey_patch(socket=True, select=True)

import os
import sys
TRAe_MEDIAPIPE_PATH = r'C:\Trae_Temp'
if os.path.isdir(TRAe_MEDIAPIPE_PATH) and TRAe_MEDIAPIPE_PATH not in sys.path:
    # Prefer the temp path when it is complete, but fall back if import fails.
    sys.path.insert(0, TRAe_MEDIAPIPE_PATH)

import time
import logging
import base64
import json
import re
import uuid
from datetime import datetime
import cv2
try:
    import mediapipe as mp
except ModuleNotFoundError:
    if TRAe_MEDIAPIPE_PATH in sys.path:
        sys.path.remove(TRAe_MEDIAPIPE_PATH)
    try:
        import mediapipe as mp
    except ModuleNotFoundError:
        mp = None
import numpy as np
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from volcenginesdkarkruntime import Ark
import subprocess
import yt_dlp
import ffmpeg
import mimetypes
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from sqlalchemy import text
from models import db, User, VideoResource, RecipeStep, UserRecipe

# Register MIME types for MP4
mimetypes.add_type('video/mp4', '.mp4')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..'))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
DB_PATH = os.path.join(INSTANCE_DIR, 'hyperkitchen.db')

app = Flask(__name__, instance_path=INSTANCE_DIR)
app.config['SECRET_KEY'] = 'hyperkitchen-secret-key'
app.config['JWT_SECRET_KEY'] = 'hyperkitchen-jwt-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{DB_PATH.replace(os.sep, '/')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
app.config['THUMBNAIL_FOLDER'] = os.path.join(BASE_DIR, 'thumbnails')
app.config['SLICES_FOLDER'] = os.path.join(BASE_DIR, 'slices')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max upload
app.config['FRONTEND_DIST_FOLDER'] = os.path.join(PROJECT_ROOT, 'frontend', 'dist')

# Ensure directories exist
os.makedirs(INSTANCE_DIR, exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['THUMBNAIL_FOLDER'], exist_ok=True)
os.makedirs(app.config['SLICES_FOLDER'], exist_ok=True)

# Enable CORS
CORS(app)

# Initialize Extensions
db.init_app(app)
migrate = Migrate(app, db)
jwt = JWTManager(app)

# Initialize SocketIO
# Increase ping_timeout and ping_interval to prevent disconnection during long processing
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='eventlet',
    ping_timeout=120, # Wait 120s for ping response (default 5)
    ping_interval=25  # Send ping every 25s (default 25)
)

# Initialize MediaPipe Solutions
if mp is not None:
    mp_hands = mp.solutions.hands
    try:
        hands = mp_hands.Hands(
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5
        )
        logger.info("MediaPipe Hands initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize MediaPipe: {e}")
        hands = None
else:
    logger.warning("MediaPipe not available. Gesture recognition will be disabled.")
    mp_hands = None
    hands = None

# Global state for gesture control
gesture_state = {
    "history": [],
    "lifecycles": {},
    "event_counter": 0,
}

GESTURE_MODE_DEFAULT = 'playing_step'

GESTURE_RULES = {
    'playing_step': {
        'next': {'window_ms': 450, 'min_hits': 2, 'cooldown_ms': 550, 'release_hits': 2},
        'prev': {'window_ms': 450, 'min_hits': 2, 'cooldown_ms': 550, 'release_hits': 2},
        'open_palm': {'window_ms': 600, 'min_hits': 3, 'cooldown_ms': 900, 'release_hits': 3},
        'overview': {'window_ms': 700, 'min_hits': 3, 'cooldown_ms': 1200, 'release_hits': 4},
    },
    'step_end_holding': {
        'next': {'window_ms': 350, 'min_hits': 2, 'cooldown_ms': 400, 'release_hits': 2},
        'prev': {'window_ms': 350, 'min_hits': 2, 'cooldown_ms': 400, 'release_hits': 2},
        'open_palm': {'window_ms': 450, 'min_hits': 2, 'cooldown_ms': 700, 'release_hits': 3},
        'overview': {'window_ms': 650, 'min_hits': 3, 'cooldown_ms': 1200, 'release_hits': 4},
    },
    'manual_pause': {
        'next': {'window_ms': 450, 'min_hits': 2, 'cooldown_ms': 500, 'release_hits': 2},
        'prev': {'window_ms': 450, 'min_hits': 2, 'cooldown_ms': 500, 'release_hits': 2},
        'open_palm': {'window_ms': 450, 'min_hits': 2, 'cooldown_ms': 700, 'release_hits': 3},
        'overview': {'window_ms': 650, 'min_hits': 3, 'cooldown_ms': 1200, 'release_hits': 4},
    },
    'overview_mode': {
        'open_palm': {'window_ms': 450, 'min_hits': 2, 'cooldown_ms': 800, 'release_hits': 3},
        'overview': {'window_ms': 750, 'min_hits': 3, 'cooldown_ms': 1400, 'release_hits': 4},
        'next': {'window_ms': 500, 'min_hits': 2, 'cooldown_ms': 650, 'release_hits': 2},
        'prev': {'window_ms': 500, 'min_hits': 2, 'cooldown_ms': 650, 'release_hits': 2},
    },
}

def normalize_gesture_mode(mode):
    if mode in GESTURE_RULES:
        return mode
    if mode == 'buffering_recovering':
        return 'manual_pause'
    if mode == 'seeking_transition':
        return 'playing_step'
    return GESTURE_MODE_DEFAULT

def get_gesture_lifecycle(mode, gesture):
    key = f"{mode}:{gesture}"
    if key not in gesture_state['lifecycles']:
        gesture_state['lifecycles'][key] = {
            'status': 'idle',
            'release_count': 0,
            'session_id': None,
            'last_confirmed_at': 0,
        }
    return gesture_state['lifecycles'][key]

def register_gesture_candidate(gesture, mode, current_time):
    history = gesture_state['history']
    history.append({'gesture': gesture, 'mode': mode, 'ts': current_time})
    max_window_seconds = 1.5
    gesture_state['history'] = [entry for entry in history if current_time - entry['ts'] <= max_window_seconds]

def reset_gesture_lifecycle(gesture, mode):
    lifecycle = get_gesture_lifecycle(mode, gesture)
    lifecycle['status'] = 'idle'
    lifecycle['release_count'] = 0
    lifecycle['session_id'] = None
    gesture_state['history'] = [
        entry for entry in gesture_state['history']
        if not (entry['gesture'] == gesture and entry['mode'] == mode)
    ]

def note_gesture_release(gesture, mode):
    rules = GESTURE_RULES.get(mode, GESTURE_RULES[GESTURE_MODE_DEFAULT]).get(gesture)
    if not rules:
        return

    lifecycle = get_gesture_lifecycle(mode, gesture)
    if lifecycle['status'] == 'idle':
        return

    lifecycle['release_count'] += 1
    if lifecycle['release_count'] >= rules.get('release_hits', 2):
        reset_gesture_lifecycle(gesture, mode)

def confirm_gesture(gesture, mode, current_time):
    rules = GESTURE_RULES.get(mode, GESTURE_RULES[GESTURE_MODE_DEFAULT]).get(gesture)
    if not rules:
        return None

    lifecycle = get_gesture_lifecycle(mode, gesture)
    if lifecycle['status'] == 'confirmed_locked':
        return None

    last_trigger_at = lifecycle.get('last_confirmed_at', 0)
    cooldown_seconds = rules['cooldown_ms'] / 1000
    if current_time - last_trigger_at < cooldown_seconds:
        return None

    window_seconds = rules['window_ms'] / 1000
    candidates = [
        entry for entry in gesture_state['history']
        if entry['gesture'] == gesture and entry['mode'] == mode and current_time - entry['ts'] <= window_seconds
    ]
    if len(candidates) < rules['min_hits']:
        return None

    hold_ms = int((candidates[-1]['ts'] - candidates[0]['ts']) * 1000) if len(candidates) > 1 else 0
    confidence = min(0.99, len(candidates) / max(rules['min_hits'], 1))
    if lifecycle['session_id'] is None:
        lifecycle['session_id'] = uuid.uuid4().hex
    lifecycle['status'] = 'confirmed_locked'
    lifecycle['release_count'] = 0
    lifecycle['last_confirmed_at'] = current_time
    gesture_state['event_counter'] += 1
    return {
        'gesture': gesture,
        'confidence': round(confidence, 2),
        'hold_ms': hold_ms,
        'mode': mode,
        'event_id': f"gesture-{gesture_state['event_counter']}",
        'gesture_session_id': lifecycle['session_id'],
    }

def observe_gesture(gesture, mode, current_time):
    supported_gestures = GESTURE_RULES.get(mode, GESTURE_RULES[GESTURE_MODE_DEFAULT]).keys()
    for candidate_gesture in supported_gestures:
        lifecycle = get_gesture_lifecycle(mode, candidate_gesture)
        if candidate_gesture == gesture:
            lifecycle['release_count'] = 0
            if lifecycle['status'] == 'idle':
                lifecycle['status'] = 'arming'
                lifecycle['session_id'] = uuid.uuid4().hex
            register_gesture_candidate(candidate_gesture, mode, current_time)
            confirmed_gesture = confirm_gesture(candidate_gesture, mode, current_time)
            if confirmed_gesture:
                return confirmed_gesture
        else:
            note_gesture_release(candidate_gesture, mode)
    return None

# Video processing status
processing_status = {}

# In-memory logs buffer
system_logs = []

def add_log(message, level='info'):
    """Add log to in-memory buffer and emit to clients"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_entry = {'time': timestamp, 'message': message, 'level': level}
    system_logs.append(log_entry)
    # Keep only last 100 logs
    if len(system_logs) > 100:
        system_logs.pop(0)
    
    # Emit to all connected clients
    socketio.emit('server_log', log_entry)
    
    # Also log to standard python logger
    if level == 'error':
        logger.error(message)
    elif level == 'warning':
        logger.warning(message)
    else:
        logger.info(message)

def ensure_runtime_schema():
    """Add lightweight columns needed by the prototype without requiring a migration step."""
    expected_columns = {
        'processed_file_path': 'TEXT',
        'thumbnail_path': 'TEXT',
        'thumbnail_url': 'TEXT',
        'duration_seconds': 'REAL',
        'has_audio': 'BOOLEAN DEFAULT 0',
        'processing_version': 'INTEGER DEFAULT 1'
    }
    with db.engine.begin() as connection:
        result = connection.execute(text("PRAGMA table_info(video_resources)"))
        existing_columns = {row[1] for row in result.fetchall()}
        for column_name, column_type in expected_columns.items():
            if column_name not in existing_columns:
                connection.execute(text(f"ALTER TABLE video_resources ADD COLUMN {column_name} {column_type}"))

def probe_video_metadata(input_path):
    """Return duration and audio presence for a video file."""
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_streams', '-show_format',
            '-of', 'json', input_path
        ]
        result = eventlet.tpool.execute(
            lambda: subprocess.run(cmd, check=True, capture_output=True, text=True)
        )
        payload = json.loads(result.stdout or '{}')
        streams = payload.get('streams', [])
        format_info = payload.get('format', {})
        duration = None
        if format_info.get('duration'):
            duration = float(format_info['duration'])
        elif streams:
            durations = [float(stream['duration']) for stream in streams if stream.get('duration')]
            if durations:
                duration = max(durations)
        has_audio = any(stream.get('codec_type') == 'audio' for stream in streams)
        return {
            'duration_seconds': duration,
            'has_audio': has_audio
        }
    except Exception as e:
        logger.warning(f"Failed to probe video metadata for {input_path}: {e}")
        return {
            'duration_seconds': None,
            'has_audio': False
        }

def generate_thumbnail(input_path, output_path):
    """Generate a JPEG thumbnail from the first meaningful frame."""
    try:
        cmd = [
            'ffmpeg', '-y', '-loglevel', 'error',
            '-ss', '1',
            '-i', input_path,
            '-frames:v', '1',
            '-q:v', '2',
            output_path
        ]
        eventlet.tpool.execute(
            lambda: subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        )
        if os.path.exists(output_path):
            return True
    except Exception:
        pass

    try:
        fallback_cmd = [
            'ffmpeg', '-y', '-loglevel', 'error',
            '-ss', '0',
            '-i', input_path,
            '-frames:v', '1',
            '-q:v', '2',
            output_path
        ]
        eventlet.tpool.execute(
            lambda: subprocess.run(fallback_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        )
        return os.path.exists(output_path)
    except Exception as e:
        logger.warning(f"Failed to generate thumbnail for {input_path}: {e}")
        return False

def backfill_existing_video_assets():
    with app.app_context():
        videos = VideoResource.query.filter(VideoResource.status == 'completed').all()
        for video in videos:
            source_path = video.processed_file_path
            inferred_processed_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{video.id}_processed.mp4")
            if not source_path:
                if os.path.exists(inferred_processed_path):
                    source_path = inferred_processed_path
                elif video.file_path and os.path.exists(video.file_path):
                    source_path = video.file_path
                elif video.filename:
                    candidate = os.path.join(app.config['UPLOAD_FOLDER'], video.filename)
                    if os.path.exists(candidate):
                        source_path = candidate
            if not source_path or not os.path.exists(source_path):
                continue

            updates = {}
            if os.path.basename(source_path).endswith('_processed.mp4'):
                updates['processed_file_path'] = source_path
            elif os.path.exists(inferred_processed_path):
                updates['processed_file_path'] = inferred_processed_path

            if not video.duration_seconds or video.has_audio is None or video.has_audio is False:
                metadata = probe_video_metadata(source_path)
                if not video.duration_seconds:
                    updates['duration_seconds'] = metadata['duration_seconds']
                if video.has_audio is None or video.has_audio is False:
                    updates['has_audio'] = metadata['has_audio']

            thumbnail_filename = f"{video.id}.jpg"
            thumbnail_path = os.path.join(app.config['THUMBNAIL_FOLDER'], thumbnail_filename)
            if not video.thumbnail_url:
                if os.path.exists(thumbnail_path) or generate_thumbnail(source_path, thumbnail_path):
                    updates['thumbnail_path'] = thumbnail_path
                    updates['thumbnail_url'] = f"/thumbnails/{thumbnail_filename}"

            if updates:
                for key, value in updates.items():
                    setattr(video, key, value)
        db.session.commit()

def standardize_video(input_path, output_path):
    """
    Convert video to standardized MP4 with fixed GOP for fast seeking (Soft Slicing).
    GOP=30 (approx 1s at 30fps) for precise seeking.
    """
    try:
        cmd = [
            'ffmpeg', '-y', '-loglevel', 'error',
            '-i', input_path,
            '-c:v', 'libx264', '-preset', 'veryfast', 
            '-g', '30', '-sc_threshold', '0', # Force keyframes every ~1s
            '-c:a', 'aac', '-b:a', '128k',
            output_path
        ]
        
        eventlet.tpool.execute(
            lambda: subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        )
        return True
    except Exception as e:
        logger.error(f"Error standardizing video: {e}")
        return False

def update_db_status(file_id, status):
    with app.app_context():
        video = VideoResource.query.get(file_id)
        if video:
            video.status = status
            db.session.commit()

def update_video_assets(file_id, **kwargs):
    with app.app_context():
        video = VideoResource.query.get(file_id)
        if not video:
            return
        for key, value in kwargs.items():
            if hasattr(video, key):
                setattr(video, key, value)
        db.session.commit()

def save_steps_to_db(file_id, steps):
    with app.app_context():
        # Clear existing steps if any
        RecipeStep.query.filter_by(video_id=file_id).delete()
        
        for step_data in steps:
            step = RecipeStep(
                video_id=file_id,
                step_number=step_data['id'],
                start_time=step_data['start'],
                end_time=step_data['end'],
                title=step_data['title'],
                description=step_data['description'],
                video_url=step_data.get('video_url')
            )
            db.session.add(step)
        db.session.commit()

def get_ark_client():
    # Set API Key directly for prototype convenience as requested
    api_key = "74f103d8-7502-4dc6-9976-6587f382e19f" 
    if not api_key:
        logger.warning("ARK_API_KEY not found")
        return None
    return Ark(api_key=api_key)

def download_video(url, output_folder, file_id=None):
    """
    Download video using yt-dlp with progress hook
    """
    def progress_hook(d):
        if d['status'] == 'downloading':
            try:
                # Calculate progress percentage
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes') or 0
                if total > 0:
                    percent = (downloaded / total) * 100
                    # Map download progress (0-100) to overall progress (5-30)
                    overall_progress = 5 + (percent * 0.25)
                    
                    # Send update to frontend
                    if file_id:
                        socketio.emit('processing_update', {
                            "file_id": file_id, 
                            "status": "analyzing", 
                            "progress": int(overall_progress),
                            "message": f"Downloading: {percent:.1f}%"
                        })
                        # Yield control to keep connection alive
                        eventlet.sleep(0)
            except Exception:
                pass 

    try:
        ydl_opts = {
            # Limit resolution to 720p to save bandwidth and memory
            'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]',
            'outtmpl': os.path.join(output_folder, '%(id)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'progress_hooks': [progress_hook], # Add progress hook
            # Add headers for Bilibili
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://www.bilibili.com/',
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            video_id = info_dict.get("id", None)
            video_ext = info_dict.get("ext", None)
            video_title = info_dict.get("title", None)
            
            if video_id and video_ext:
                filename = f"{video_id}.{video_ext}"
                return os.path.join(output_folder, filename), video_title
                
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        # Re-raise the exception so the caller knows the specific error
        raise e
    
    return None, None

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

# === Auth Endpoints ===
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 400

    hashed_password = generate_password_hash(password)
    new_user = User(username=username, password_hash=hashed_password)
    db.session.add(new_user)
    db.session.commit()

    return jsonify({"message": "User registered successfully"}), 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()

    if user and check_password_hash(user.password_hash, password):
        # Identity can be anything JSON serializable (e.g. user ID)
        access_token = create_access_token(identity=str(user.id))
        return jsonify(access_token=access_token, user=user.to_dict()), 200

    return jsonify({"error": "Invalid credentials"}), 401


@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Get recent logs"""
    return jsonify(system_logs)

@app.route('/api/status/<file_id>', methods=['GET'])
def get_status(file_id):
    """Get processing status for a specific file"""
    # Check in-memory status first
    status = processing_status.get(file_id)
    if status:
        return jsonify(status)
    
    # Check DB if not in memory (e.g. after restart)
    video = VideoResource.query.get(file_id)
    if video:
        return jsonify({
            "status": video.status,
            "steps": [step.to_dict() for step in video.steps],
            "original_url": video.original_url,
            "file_id": video.id,
            "video_url": f"/videos/{os.path.basename(video.processed_file_path)}" if video.processed_file_path else (f"/videos/{video.filename}" if video.filename else None),
            "thumbnail_url": video.thumbnail_url,
            "duration_seconds": video.duration_seconds,
            "has_audio": video.has_audio
        })

    return jsonify({"error": "File ID not found"}), 404

@app.route('/api/analyze-link', methods=['POST'])
@jwt_required(optional=True)
def analyze_link():
    data = request.json
    video_url = data.get('url')
    user_id = get_jwt_identity()
    
    if not video_url:
        return jsonify({"error": "No URL provided"}), 400

    # Deduplication: Check if URL already exists and completed
    existing_video = VideoResource.query.filter_by(original_url=video_url, status='completed').first()
    if existing_video:
        return jsonify({
            "message": "Video already processed",
            "file_id": existing_video.id,
            "status": existing_video.status,
            "steps": [step.to_dict() for step in existing_video.steps],
            "thumbnail_url": existing_video.thumbnail_url,
            "has_audio": existing_video.has_audio,
            "duration_seconds": existing_video.duration_seconds
        })

    # Check if currently processing
    pending_video = VideoResource.query.filter_by(original_url=video_url).filter(VideoResource.status.in_(['pending', 'analyzing', 'slicing'])).first()
    if pending_video:
         return jsonify({
            "message": "Video is already being processed",
            "file_id": pending_video.id,
            "status": pending_video.status,
            "thumbnail_url": pending_video.thumbnail_url
        })

    file_id = str(uuid.uuid4())
    
    # Create DB record
    new_video = VideoResource(
        id=file_id,
        user_id=user_id,
        original_url=video_url,
        filename=f"{file_id}.mp4", # Placeholder, will update after download
        status='pending'
    )
    db.session.add(new_video)
    db.session.commit()
    
    # Start background processing
    socketio.start_background_task(process_video_url, video_url, file_id)

    return jsonify({
        "message": "Video link received, processing started",
        "file_id": file_id
    })

def process_video_url(video_url, file_id):
    add_log(f"Starting processing for video URL {file_id}")
    update_db_status(file_id, "analyzing")
    
    processing_status[file_id] = {"status": "analyzing", "progress": 0}
    socketio.emit('processing_update', {"file_id": file_id, "status": "analyzing", "progress": 5})
    
    try:
        # 1. Download Video
        add_log(f"Downloading video from {video_url}")
        
        try:
            # Pass file_id to download_video to enable progress reporting
            video_path, video_title = download_video(video_url, app.config['UPLOAD_FOLDER'], file_id)
            
            if not video_path:
                raise Exception("Failed to download video: No file path returned")
                
            # Update filename in DB
            with app.app_context():
                video = VideoResource.query.get(file_id)
                if video:
                    video.filename = os.path.basename(video_path)
                    video.file_path = video_path
                    db.session.commit()

        except Exception as dl_error:
            # Check for common Bilibili/yt-dlp errors
            err_msg = str(dl_error)
            if "HTTP Error 403" in err_msg:
                 raise Exception("Download failed (403 Forbidden). This usually means Bilibili blocked the request. Try a different link or check server IP.")
            elif "ffmpeg" in err_msg.lower():
                 raise Exception("Download failed: FFmpeg not found or failed to merge video/audio.")
            else:
                 raise Exception(f"Download failed: {err_msg}")
            
        add_log(f"Video downloaded to {video_path}")
        socketio.emit('processing_update', {"file_id": file_id, "status": "analyzing", "progress": 30})
        
        # 2. Analyze with AI
        client = get_ark_client()
        steps = []
        
        # Determine the correct video URL to use for steps (MP4 Soft Slicing)
        processed_filename = f"{file_id}_processed.mp4"
        processed_path = os.path.join(app.config['UPLOAD_FOLDER'], processed_filename)
        thumbnail_filename = f"{file_id}.jpg"
        thumbnail_path = os.path.join(app.config['THUMBNAIL_FOLDER'], thumbnail_filename)
        thumbnail_url = None
        
        # We need to standardize it anyway for smooth playback
        add_log("Standardizing video for playback...")
        if standardize_video(video_path, processed_path):
             full_video_url = f"/videos/{processed_filename}"
             media_probe_path = processed_path
        else:
             full_video_url = f"/videos/{os.path.basename(video_path)}"
             media_probe_path = video_path

        metadata = probe_video_metadata(media_probe_path)
        if generate_thumbnail(media_probe_path, thumbnail_path):
            thumbnail_url = f"/thumbnails/{thumbnail_filename}"
        update_video_assets(
            file_id,
            file_path=video_path,
            processed_file_path=processed_path if os.path.exists(processed_path) else None,
            thumbnail_path=thumbnail_path if thumbnail_url else None,
            thumbnail_url=thumbnail_url,
            duration_seconds=metadata['duration_seconds'],
            has_audio=metadata['has_audio'],
            processing_version=2
        )
        
        if client:
            try:
                # Read video file and encode to base64
                # Check size limit (50MB soft limit for some APIs, but let's try)
                file_size = os.path.getsize(video_path)
                if file_size > 50 * 1024 * 1024:
                    add_log("Video larger than 50MB, compressing for AI analysis...", "warning")
                    socketio.emit('processing_update', {"file_id": file_id, "status": "analyzing", "progress": 35, "message": "Compressing video for AI..."})
                    
                    # Compress video to lower resolution/bitrate for AI analysis
                    compressed_path = os.path.join(app.config['UPLOAD_FOLDER'], f"compressed_{os.path.basename(video_path)}")
                    compress_cmd = [
                        'ffmpeg', '-y', '-loglevel', 'error',
                        '-i', video_path,
                        '-vf', 'scale=-2:480', # Scale to 480p
                        '-c:v', 'libx264', '-crf', '28', '-preset', 'veryfast', # High compression
                        '-an', # Remove audio to save space
                        compressed_path
                    ]
                    
                    try:
                        # Run compression in tpool
                        eventlet.tpool.execute(
                            lambda: subprocess.run(compress_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                        )
                        # Use compressed video for AI analysis
                        analysis_video_path = compressed_path
                        add_log(f"Video compressed. Original: {file_size/1024/1024:.1f}MB, Compressed: {os.path.getsize(compressed_path)/1024/1024:.1f}MB")
                    except Exception as compress_error:
                        add_log(f"Compression failed: {compress_error}. Using original video.", "warning")
                        analysis_video_path = video_path
                else:
                    analysis_video_path = video_path
                    socketio.emit('processing_update', {"file_id": file_id, "status": "analyzing", "progress": 35, "message": "Uploading to AI..."})
                    
                with open(analysis_video_path, 'rb') as f:
                    video_bytes = f.read()
                    
                base64_video = base64.b64encode(video_bytes).decode('utf-8')
                
                # User-provided prompt
                prompt = """
根据这个视频，列出制作这道菜的详细步骤。请严格按照以下格式回答：
总步骤数：N（根据实际情况填写具体数字）
步骤1: [开始时间-结束时间] [步骤标题] 详细描述
步骤2: [开始时间-结束时间] [步骤标题] 详细描述
...
步骤N: [开始时间-结束时间] [步骤标题] 详细描述

提供一个示例，例如：
总步骤数：8
步骤1: [21-57] [处理大虾] 剪掉虾须、前面的虾腔、虾头内沙包，虾身剪开去掉虾线
...
步骤8: [249-257] [出锅装盘] 关火，将做好的白菜炖大虾出锅装盘
请先给出总步骤数，然后按序号分行列出每个步骤。每个步骤必须包含：时间戳[开始时间-结束时间]、步骤标题[标题内容]、详细描述。请确保标题简洁明了，能准确反映该步骤的主要操作。步骤数量应根据视频内容的实际操作流程来确定，不要固定为某个特定数字。
"""
                
                add_log("Calling AI with video content...")
                socketio.emit('processing_update', {"file_id": file_id, "status": "analyzing", "progress": 40, "message": "AI Analyzing..."})
                
                # Use tpool to run the blocking AI call in a separate thread
                completion = eventlet.tpool.execute(
                    lambda: client.chat.completions.create(
                        model="ep-20260310222613-z2g79", # Using the provided endpoint ID
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "video_url",
                                        "video_url": {
                                            "url": f"data:video/mp4;base64,{base64_video}",
                                            "fps": 1, 
                                        }
                                    },
                                    {
                                        "type": "text",
                                        "text": prompt
                                    }
                                ]
                            }
                        ],
                        timeout=300
                    )
                )
                
                result_text = completion.choices[0].message.content
                add_log(f"AI Response content: {result_text}") 
                add_log(f"AI Response received (length: {len(result_text)})")
                
                # Parse the response using regex
                step_pattern = r'步骤(\d+):\s*\[\s*(\d+)\s*-\s*(\d+)\s*\]\s*\[(.*?)\]\s*(.*?)(?=步骤|$)'
                
                matches = re.finditer(step_pattern, result_text, re.DOTALL)
                
                for match in matches:
                    step_id = int(match.group(1))
                    start = int(match.group(2))
                    end = int(match.group(3))
                    title = match.group(4).strip()
                    description = match.group(5).strip()
                    
                    steps.append({
                        "id": step_id,
                        "start": start,
                        "end": end,
                        "title": title,
                        "description": description,
                        "highlight": title 
                    })
                
                add_log(f"Parsed {len(steps)} steps from AI response")
                    
            except Exception as ai_error:
                add_log(f"AI Analysis failed: {ai_error}", "error")
                socketio.emit('processing_update', {"file_id": file_id, "status": "analyzing", "progress": 45, "message": f"AI Error: {str(ai_error)}. Using fallback."})
                steps = [] # Clear to trigger fallback
        
        # Fallback if AI fails or returns empty
        if not steps:
            add_log("Using fallback steps")
            steps = [
                {"id": 1, "start": 0, "end": 10, "title": "Preparation", "description": f"Prepare ingredients for {video_title or 'the dish'}.", "highlight": "Ingredients"},
                {"id": 2, "start": 10, "end": 30, "title": "Cooking Process", "description": "Main cooking steps.", "highlight": "Heat & Cook"},
                {"id": 3, "start": 30, "end": 45, "title": "Finishing Touches", "description": "Seasoning and plating.", "highlight": "Serve"}
            ]
            
        processing_status[file_id]["progress"] = 90
        socketio.emit('processing_update', {"file_id": file_id, "status": "slicing", "progress": 90, "message": "Finalizing..."})
        
        # Update steps with Full Video URL
        add_log(f"Processing completed. Using video URL: {full_video_url}")
        
        for step in steps:
            step['video_url'] = full_video_url
            step['is_full_video'] = True
            step['is_hls'] = False

        # Save steps to DB
        save_steps_to_db(file_id, steps)
        update_db_status(file_id, "completed")

        processing_status[file_id] = {
            "status": "completed",
            "steps": steps,
            "original_url": video_url,
            "file_id": file_id,
            "video_url": full_video_url,
            "thumbnail_url": thumbnail_url,
            "duration_seconds": metadata['duration_seconds'],
            "has_audio": metadata['has_audio']
        }
        socketio.emit('processing_update', {
            "file_id": file_id,
            "status": "completed",
            "steps": steps,
            "progress": 100,
            "original_url": video_url,
            "video_url": full_video_url,
            "thumbnail_url": thumbnail_url,
            "duration_seconds": metadata['duration_seconds'],
            "has_audio": metadata['has_audio']
        })
        
    except Exception as e:
        add_log(f"Error processing video URL: {e}", "error")
        update_db_status(file_id, "error")
        socketio.emit('processing_update', {"file_id": file_id, "status": "error", "message": str(e)})

@app.route('/api/upload', methods=['POST'])
@jwt_required(optional=True)
def upload_video():
    if 'video' not in request.files:
        return jsonify({"error": "No video file provided"}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file:
        user_id = get_jwt_identity()
        filename = secure_filename(file.filename)
        file_id = str(uuid.uuid4())
        extension = os.path.splitext(filename)[1]
        saved_filename = f"{file_id}{extension}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], saved_filename)
        file.save(file_path)

        new_video = VideoResource(
            id=file_id,
            user_id=user_id,
            filename=saved_filename,
            original_filename=filename,
            file_path=file_path,
            status='pending'
        )
        db.session.add(new_video)
        db.session.commit()
        
        # Start processing in background
        # socketio.start_background_task(process_video, file_path, file_id)
        
        # Respond immediately, then client should listen to socket updates
        # But for prototype simplicity, let's just trigger processing and hope socket connects in time
        # Or even better, just return success and let client wait for socket event
        
        socketio.start_background_task(process_video, file_path, file_id)

        return jsonify({
            "message": "Video uploaded successfully, processing started",
            "file_id": file_id,
            "filename": filename
        })

def process_video(file_path, file_id):
    """
    Process the video:
    1. Extract audio/visual features (simulated/simplified here)
    2. Call AI to get steps and timestamps
    3. Slice video based on timestamps
    """
    logger.info(f"Starting processing for video {file_id}")
    update_db_status(file_id, "analyzing")
    
    # Wait a bit to ensure client has received the upload response and subscribed to socket events
    time.sleep(1)
    
    processing_status[file_id] = {"status": "analyzing", "progress": 0}
    socketio.emit('processing_update', {"file_id": file_id, "status": "analyzing", "progress": 10})
    
    try:
        # 1. Analyze video with AI (Mocking the AI call for prototype if no key, or implementing real call)
        client = get_ark_client()
        steps = []
        
        if client:
            # TODO: Implement actual AI analysis with frame extraction
            # For now, we'll use a mock response or a simplified prompt if we had the frames
            pass
        
        # Fallback/Mock steps for prototype demonstration if AI fails or no key
        if not steps:
            logger.info("Using mock steps for demonstration")
            # Simulate processing time
            time.sleep(2)
            steps = [
                {"id": 1, "start": 0, "end": 5, "title": "准备食材", "description": "将大虾洗净，去除虾线，白菜切段备用。", "highlight": "大虾500g, 白菜300g"},
                {"id": 2, "start": 5, "end": 10, "title": "炒制虾油", "description": "热锅凉油，放入虾头煸炒出红油。", "highlight": "油温160℃, 中火"},
                {"id": 3, "start": 10, "end": 15, "title": "放入大虾", "description": "放入大虾翻炒至变色。", "highlight": "大火翻炒"},
                {"id": 4, "start": 15, "end": 20, "title": "加入白菜", "description": "加入白菜帮，继续翻炒均匀。", "highlight": "白菜帮先下"},
                {"id": 5, "start": 20, "end": 25, "title": "炖煮", "description": "加入适量清水，盖盖炖煮5分钟。", "highlight": "清水500ml, 5分钟"},
                {"id": 6, "start": 25, "end": 30, "title": "调味出锅", "description": "加入盐、胡椒粉调味，收汁出锅。", "highlight": "盐3g, 胡椒粉1g"}
            ]
            
        processing_status[file_id]["progress"] = 50
        socketio.emit('processing_update', {"file_id": file_id, "status": "slicing", "progress": 50, "message": "Standardizing video..."})
        
        # 2. Standardize Video (Soft Slicing preparation)
        processed_filename = f"{file_id}_processed.mp4"
        processed_path = os.path.join(app.config['UPLOAD_FOLDER'], processed_filename)
        thumbnail_filename = f"{file_id}.jpg"
        thumbnail_path = os.path.join(app.config['THUMBNAIL_FOLDER'], thumbnail_filename)
        
        # In process_video (upload), file_path is the uploaded file
        if standardize_video(file_path, processed_path):
             full_video_url = f"/videos/{processed_filename}"
             media_probe_path = processed_path
        else:
             full_video_url = f"/videos/{os.path.basename(file_path)}"
             media_probe_path = file_path

        metadata = probe_video_metadata(media_probe_path)
        thumbnail_url = None
        if generate_thumbnail(media_probe_path, thumbnail_path):
            thumbnail_url = f"/thumbnails/{thumbnail_filename}"

        update_video_assets(
            file_id,
            file_path=file_path,
            processed_file_path=processed_path if os.path.exists(processed_path) else None,
            thumbnail_path=thumbnail_path if thumbnail_url else None,
            thumbnail_url=thumbnail_url,
            duration_seconds=metadata['duration_seconds'],
            has_audio=metadata['has_audio'],
            processing_version=2
        )
        
        for step in steps:
            step['video_url'] = full_video_url
            step['is_full_video'] = True
            step['is_hls'] = False
            
        save_steps_to_db(file_id, steps)
        update_db_status(file_id, "completed")
        processing_status[file_id] = {
            "status": "completed",
            "steps": steps,
            "file_id": file_id,
            "video_url": full_video_url,
            "thumbnail_url": thumbnail_url,
            "duration_seconds": metadata['duration_seconds'],
            "has_audio": metadata['has_audio']
        }
        socketio.emit('processing_update', {
            "file_id": file_id,
            "status": "completed",
            "steps": steps,
            "video_url": full_video_url,
            "thumbnail_url": thumbnail_url,
            "duration_seconds": metadata['duration_seconds'],
            "has_audio": metadata['has_audio']
        })
        logger.info(f"Processing completed for video {file_id}")

    except Exception as e:
        logger.error(f"Error processing video: {e}")
        update_db_status(file_id, "error")
        processing_status[file_id] = {"status": "error", "message": str(e)}
        socketio.emit('processing_update', {"file_id": file_id, "status": "error", "message": str(e)})

@app.route('/videos/<filename>')
def serve_video(filename):
    """Serve the original full video file"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/thumbnails/<filename>')
def serve_thumbnail(filename):
    return send_from_directory(app.config['THUMBNAIL_FOLDER'], filename)

@app.route('/slices/<file_id>/<filename>')
def serve_slice(file_id, filename):
    return send_from_directory(os.path.join(app.config['SLICES_FOLDER'], file_id), filename)

@app.route('/slices/<file_id>/hls/<filename>')
def serve_hls(file_id, filename):
    return send_from_directory(os.path.join(app.config['SLICES_FOLDER'], file_id, 'hls'), filename)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    """
    Serve the built frontend so the project can be previewed without Vite.
    API, video, and socket routes declared above still take precedence.
    """
    dist_dir = app.config['FRONTEND_DIST_FOLDER']
    if not os.path.isdir(dist_dir):
        return jsonify({"error": "Frontend build not found", "path": dist_dir}), 404

    requested_path = os.path.join(dist_dir, path)
    if path and os.path.exists(requested_path) and os.path.isfile(requested_path):
        return send_from_directory(dist_dir, path)

    return send_from_directory(dist_dir, 'index.html')


# Gesture Recognition Socket Namespace
@socketio.on('video_frame')
def handle_video_frame(data):
    """
    Receive video frame from client, process with MediaPipe, and return gesture event if detected.
    """
    try:
        # Decode base64 frame
        if 'image' not in data:
            return
            
        image_data = base64.b64decode(data['image'].split(',')[1])
        nparr = np.frombuffer(image_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            return

        mode = normalize_gesture_mode(data.get('mode'))
        # Process frame
        gesture_event = detect_gesture(frame, mode)
        
        if gesture_event:
            emit('gesture_detected', gesture_event)
            
    except Exception as e:
        logger.error(f"Error handling video frame: {e}")

def detect_gesture(frame, mode=GESTURE_MODE_DEFAULT):
    """
    Detect gestures using MediaPipe Hands.
    Gestures:
    - Point Left (Next Step): Index finger pointing left (x decreases)
    - Point Right (Prev Step): Index finger pointing right (x increases)
    - Open Palm (Resume from Overview): All fingers extended
    - Both Hands Up (Overview): Two hands above shoulder level
    - Closed Fist (Pause/Resume): All fingers folded
    """
    global gesture_state
    
    current_time = time.time()

    if hands is None:
        return None

    # Convert to RGB
    image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    detected_gesture = None

    # Check Hands
    hand_results = hands.process(image_rgb)
    
    if not hand_results.multi_hand_landmarks:
        return observe_gesture(None, mode, current_time)
        
    multi_landmarks = hand_results.multi_hand_landmarks
    num_hands = len(multi_landmarks)
    
    def is_finger_extended(landmarks, tip_idx, pip_idx):
        wrist = landmarks[0]
        tip = landmarks[tip_idx]
        pip = landmarks[pip_idx]
        dist_tip = (tip.x - wrist.x)**2 + (tip.y - wrist.y)**2
        dist_pip = (pip.x - wrist.x)**2 + (pip.y - wrist.y)**2
        return dist_tip > dist_pip

    # Overview: Both Hands Up
    hands_up_count = 0
    for hand_landmarks in multi_landmarks:
        wrist = hand_landmarks.landmark[0]
        if wrist.y < 0.4:
            hands_up_count += 1
            
    if hands_up_count >= 2:
        detected_gesture = "overview"
    
    elif num_hands > 0:
        hand_landmarks = multi_landmarks[0].landmark
        
        thumb_open = is_finger_extended(hand_landmarks, 4, 2)
        index_open = is_finger_extended(hand_landmarks, 8, 6)
        middle_open = is_finger_extended(hand_landmarks, 12, 10)
        ring_open = is_finger_extended(hand_landmarks, 16, 14)
        pinky_open = is_finger_extended(hand_landmarks, 20, 18)
        
        open_fingers_count = sum([thumb_open, index_open, middle_open, ring_open, pinky_open])
        
        # Open Palm (Resume from Overview OR Toggle Pause)
        if open_fingers_count >= 5:
            detected_gesture = "open_palm"
            
        # Pointing (Index Open)
        elif index_open and (open_fingers_count <= 2):
            wrist = hand_landmarks[0]
            index_tip = hand_landmarks[8]
            dx = index_tip.x - wrist.x
            dy = index_tip.y - wrist.y
            
            # Horizontal pointing
            if abs(dx) > abs(dy):
                # Pointing Logic (Independent of which hand is used):
                # If pointing to User's Right (Image Left, dx < 0) -> Next
                # If pointing to User's Left (Image Right, dx > 0) -> Prev
                
                # User Feedback: "Left hand points Right -> Next", "Right hand points Left -> Prev"
                # User wants: "Point Right -> Next", "Point Left -> Prev" (User's perspective)
                
                # Image Coordinates (Mirrored):
                # User points Right -> Image Hand points Left (dx < 0)
                # User points Left -> Image Hand points Right (dx > 0)
                
                # Requested Logic:
                # "Point Right (User perspective) -> Next" => dx < -0.1
                # "Point Left (User perspective) -> Prev" => dx > 0.1
                
                if dx < -0.1: # Pointing Right (User perspective) -> Next
                    detected_gesture = "next"
                elif dx > 0.1: # Pointing Left (User perspective) -> Prev
                    detected_gesture = "prev"

    confirmed_gesture = observe_gesture(detected_gesture, mode, current_time)
    if confirmed_gesture:
        logger.info(
            "Gesture detected: %s (%s) session=%s",
            confirmed_gesture['gesture'],
            mode,
            confirmed_gesture['gesture_session_id'],
        )
        return confirmed_gesture

    return None

@app.route('/api/recipes', methods=['GET', 'POST'])
@jwt_required()
def handle_recipes():
    user_id = get_jwt_identity()
    if request.method == 'GET':
        recipes = UserRecipe.query.filter_by(user_id=user_id).order_by(UserRecipe.created_at.desc()).all()
        return jsonify([recipe.to_dict() for recipe in recipes])
    
    if request.method == 'POST':
        data = request.json
        new_recipe = UserRecipe(
            user_id=user_id,
            title=data.get('title'),
            description=data.get('description'),
            video_id=data.get('video_id') # Optional link to a processed video
        )
        db.session.add(new_recipe)
        db.session.commit()
        return jsonify(new_recipe.to_dict()), 201

@app.route('/api/recipes/<int:recipe_id>', methods=['GET', 'PUT', 'DELETE'])
@jwt_required()
def handle_recipe_detail(recipe_id):
    user_id = get_jwt_identity()
    recipe = UserRecipe.query.filter_by(id=recipe_id, user_id=user_id).first()
    
    if not recipe:
        return jsonify({"error": "Recipe not found"}), 404
        
    if request.method == 'GET':
        return jsonify(recipe.to_dict())
        
    if request.method == 'PUT':
        data = request.json
        recipe.title = data.get('title', recipe.title)
        recipe.description = data.get('description', recipe.description)
        db.session.commit()
        return jsonify(recipe.to_dict())
        
    if request.method == 'DELETE':
        db.session.delete(recipe)
        db.session.commit()
        return jsonify({"message": "Recipe deleted"})

with app.app_context():
    db.create_all()
    ensure_runtime_schema()
    backfill_existing_video_assets()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
