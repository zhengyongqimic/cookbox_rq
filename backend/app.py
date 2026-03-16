import sys
# Workaround for MediaPipe Chinese path issue: use C:\Trae_Temp for mediapipe package
sys.path.insert(0, r'C:\Trae_Temp')

import eventlet
import eventlet.tpool # Explicitly import tpool
# Monkey patch socket to make yt-dlp non-blocking (cooperative)
# Note: Some older versions of eventlet might not support dns=False, if so, we just patch all
# or patch specific modules. Let's try patching socket only explicitly if dns kwarg fails,
# but usually patching everything is default.
try:
    eventlet.monkey_patch(dns=False)
except TypeError:
    # Fallback for older eventlet versions
    eventlet.monkey_patch(socket=True, select=True)

import os
import time
import logging
import base64
import json
import re
import uuid
from datetime import datetime
import cv2
import mediapipe as mp
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
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from models import db, User, VideoResource, RecipeStep, UserRecipe

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'hyperkitchen-secret-key'
app.config['JWT_SECRET_KEY'] = 'hyperkitchen-jwt-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hyperkitchen.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
app.config['SLICES_FOLDER'] = os.path.join(os.getcwd(), 'slices')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max upload

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
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

# Global state for gesture control
gesture_state = {
    "last_gesture_time": 0,
    "cooldown": 1.0,  # seconds
    "current_gesture": None,
    "history": []
}

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

def convert_to_hls(input_path, output_dir):
    """Convert video to HLS format using ffmpeg"""
    try:
        os.makedirs(output_dir, exist_ok=True)
        output_playlist = os.path.join(output_dir, 'playlist.m3u8')
        
        cmd = [
            'ffmpeg', '-y', '-loglevel', 'error',
            '-i', input_path,
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '128k',
            '-f', 'hls',
            '-hls_time', '10',
            '-hls_list_size', '0',
            output_playlist
        ]
        
        eventlet.tpool.execute(
            lambda: subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        )
        return output_playlist
    except Exception as e:
        logger.error(f"Error converting to HLS: {e}")
        return None

def update_db_status(file_id, status):
    with app.app_context():
        video = VideoResource.query.get(file_id)
        if video:
            video.status = status
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
            "filename": video.filename # Expose filename for MP4 fallback
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
            "steps": [step.to_dict() for step in existing_video.steps]
        })

    # Check if currently processing
    pending_video = VideoResource.query.filter_by(original_url=video_url).filter(VideoResource.status.in_(['pending', 'analyzing', 'slicing'])).first()
    if pending_video:
         return jsonify({
            "message": "Video is already being processed",
            "file_id": pending_video.id,
            "status": pending_video.status
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
            
        processing_status[file_id]["progress"] = 50
        socketio.emit('processing_update', {"file_id": file_id, "status": "slicing", "progress": 50, "message": "Transcoding to HLS..."})
        
        # 3. HLS Transcoding (replacing soft slicing with HLS)
        hls_dir = os.path.join(app.config['SLICES_FOLDER'], file_id, 'hls')
        hls_playlist = convert_to_hls(video_path, hls_dir)
        
        hls_url = None
        if hls_playlist:
            hls_url = f"/slices/{file_id}/hls/playlist.m3u8"
            add_log(f"HLS transcoding completed: {hls_url}")
        else:
            add_log("HLS transcoding failed, falling back to MP4", "warning")

        # Update steps with HLS URL or MP4 URL
        full_video_url = hls_url if hls_url else f"/videos/{os.path.basename(video_path)}"
        add_log(f"Processing completed. Using video URL: {full_video_url}")
        
        for step in steps:
            step['video_url'] = full_video_url
            step['is_full_video'] = True
            step['is_hls'] = bool(hls_url)

        # Save steps to DB
        save_steps_to_db(file_id, steps)
        update_db_status(file_id, "completed")

        processing_status[file_id] = {"status": "completed", "steps": steps, "original_url": video_url}
        socketio.emit('processing_update', {"file_id": file_id, "status": "completed", "steps": steps, "progress": 100, "original_url": video_url})
        
    except Exception as e:
        add_log(f"Error processing video URL: {e}", "error")
        update_db_status(file_id, "error")
        socketio.emit('processing_update', {"file_id": file_id, "status": "error", "message": str(e)})

@app.route('/api/upload', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({"error": "No video file provided"}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file:
        filename = secure_filename(file.filename)
        file_id = str(uuid.uuid4())
        extension = os.path.splitext(filename)[1]
        saved_filename = f"{file_id}{extension}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], saved_filename)
        file.save(file_path)
        
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
        socketio.emit('processing_update', {"file_id": file_id, "status": "slicing", "progress": 50})
        
        # 2. Slice video using ffmpeg
        slices_dir = os.path.join(app.config['SLICES_FOLDER'], file_id)
        os.makedirs(slices_dir, exist_ok=True)
        
        for step in steps:
            start_time = step['start']
            duration = step['end'] - step['start']
            output_filename = f"step_{step['id']}.mp4"
            output_path = os.path.join(slices_dir, output_filename)
            
            # Use ffmpeg to slice
            # ffmpeg -i input.mp4 -ss start -t duration -c copy output.mp4
            # Re-encoding to ensure compatibility and consistent formatting
            cmd = [
                'ffmpeg', '-y', '-loglevel', 'error',
                '-ss', str(start_time),
                '-t', str(duration),
                '-i', file_path,
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
                '-c:a', 'aac', '-b:a', '128k',
                '-vf', 'scale=-2:720', # Resize to 720p height, keep aspect ratio
                output_path
            ]
            
            # Check if ffmpeg is installed
            try:
                # Wrap subprocess.run in tpool to prevent blocking
                eventlet.tpool.execute(
                    lambda: subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                )
                step['video_url'] = f"/slices/{file_id}/{output_filename}"
            except subprocess.CalledProcessError as e:
                logger.error(f"Error slicing video for step {step['id']}: {e}")
                step['video_url'] = None # Handle error gracefully
            except FileNotFoundError:
                 logger.error("ffmpeg not found. Please install ffmpeg.")
                 # For prototype without ffmpeg, return original video with timestamps?
                 # Or just fail gracefully
                 step['video_url'] = None

        processing_status[file_id] = {"status": "completed", "steps": steps}
        socketio.emit('processing_update', {"file_id": file_id, "status": "completed", "steps": steps})
        logger.info(f"Processing completed for video {file_id}")

    except Exception as e:
        logger.error(f"Error processing video: {e}")
        processing_status[file_id] = {"status": "error", "message": str(e)}
        socketio.emit('processing_update', {"file_id": file_id, "status": "error", "message": str(e)})

@app.route('/videos/<filename>')
def serve_video(filename):
    """Serve the original full video file"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/slices/<file_id>/<filename>')
def serve_slice(file_id, filename):
    return send_from_directory(os.path.join(app.config['SLICES_FOLDER'], file_id), filename)

@app.route('/slices/<file_id>/hls/<filename>')
def serve_hls(file_id, filename):
    response = send_from_directory(os.path.join(app.config['SLICES_FOLDER'], file_id, 'hls'), filename)
    # Explicitly set MIME types to ensure browser compatibility
    if filename.endswith('.m3u8'):
        response.headers['Content-Type'] = 'application/vnd.apple.mpegurl'
    elif filename.endswith('.ts'):
        response.headers['Content-Type'] = 'video/MP2T'
    return response


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

        # Process frame
        gesture = detect_gesture(frame)
        
        if gesture:
            emit('gesture_detected', {'gesture': gesture})
            
    except Exception as e:
        logger.error(f"Error handling video frame: {e}")

def detect_gesture(frame):
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
    if current_time - gesture_state['last_gesture_time'] < gesture_state['cooldown']:
        return None

    if hands is None:
        return None

    # Convert to RGB
    image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    detected_gesture = None

    # Check Hands
    hand_results = hands.process(image_rgb)
    
    if not hand_results.multi_hand_landmarks:
        return None
        
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

    if detected_gesture:
        gesture_state['last_gesture_time'] = current_time
        logger.info(f"Gesture detected: {detected_gesture}")
        return detected_gesture
        
    return None

@app.route('/api/recipes', methods=['GET', 'POST'])
@jwt_required()
def handle_recipes():
    user_id = get_jwt_identity()
    if request.method == 'GET':
        recipes = UserRecipe.query.filter_by(user_id=user_id).all()
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

if __name__ == '__main__':
    # Create DB tables if not exist
    with app.app_context():
        db.create_all()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
