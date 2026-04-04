from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    videos = db.relationship('VideoResource', backref='uploader', lazy=True)
    recipes = db.relationship('UserRecipe', backref='author', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class VideoResource(db.Model):
    __tablename__ = 'video_resources'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255))
    file_path = db.Column(db.String(255))
    processed_file_path = db.Column(db.String(255))
    thumbnail_path = db.Column(db.String(255))
    thumbnail_url = db.Column(db.String(255))
    original_url = db.Column(db.String(512), index=True) # For deduplication by URL
    file_hash = db.Column(db.String(64), index=True)     # For deduplication by content
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='pending') # pending, analyzing, completed, error
    duration_seconds = db.Column(db.Float)
    has_audio = db.Column(db.Boolean, default=False)
    processing_version = db.Column(db.Integer, default=1)
    
    steps = db.relationship('RecipeStep', backref='video', lazy=True, cascade="all, delete-orphan")
    recipe = db.relationship('UserRecipe', backref='source_video', uselist=False, lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'status': self.status,
            'upload_time': self.upload_time.isoformat() if self.upload_time else None,
            'processed_file_path': self.processed_file_path,
            'thumbnail_url': self.thumbnail_url,
            'duration_seconds': self.duration_seconds,
            'has_audio': self.has_audio,
            'steps': [step.to_dict() for step in self.steps]
        }

class RecipeStep(db.Model):
    __tablename__ = 'recipe_steps'
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(36), db.ForeignKey('video_resources.id'), nullable=False)
    step_number = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.Float)
    end_time = db.Column(db.Float)
    title = db.Column(db.String(100))
    description = db.Column(db.Text)
    video_url = db.Column(db.String(255))
    
    def to_dict(self):
        return {
            'id': self.id,
            'step_number': self.step_number,
            'start': self.start_time,
            'end': self.end_time,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'title': self.title,
            'description': self.description,
            'video_url': self.video_url
        }

class UserRecipe(db.Model):
    __tablename__ = 'user_recipes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    video_id = db.Column(db.String(36), db.ForeignKey('video_resources.id'), nullable=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        data = {
            'id': self.id,
            'user_id': self.user_id,
            'video_id': self.video_id,
            'title': self.title,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if self.source_video:
            data.update({
                'thumbnail_url': self.source_video.thumbnail_url,
                'duration_seconds': self.source_video.duration_seconds,
                'video_status': self.source_video.status,
                'has_audio': self.source_video.has_audio
            })
        else:
            data.update({
                'thumbnail_url': None,
                'duration_seconds': None,
                'video_status': None,
                'has_audio': None
            })
        return data
