from app import app, db, RecipeStep, VideoResource
import os

def fix_database_paths():
    with app.app_context():
        # Get all steps
        steps = RecipeStep.query.all()
        updated_count = 0
        
        for step in steps:
            # Check if video_url points to a slice or HLS or needs update
            # We want ALL steps to point to /videos/xxx
            
            # Find the parent video resource
            video = VideoResource.query.get(step.video_id)
            if video:
                # Construct new path: 
                # 1. Try processed file: {file_id}_processed.mp4
                processed_filename = f"{video.id}_processed.mp4"
                processed_path = os.path.join(app.config['UPLOAD_FOLDER'], processed_filename)
                
                new_url = ""
                if os.path.exists(processed_path):
                    new_url = f"/videos/{processed_filename}"
                else:
                    # 2. Fallback to original filename (which should be in uploads folder)
                    # video.filename might be just the name, or relative path
                    # We assume it's in UPLOAD_FOLDER
                    new_url = f"/videos/{video.filename}"
                
                if step.video_url != new_url:
                    print(f"Updating Step {step.id} (Video {video.id}): {step.video_url} -> {new_url}")
                    step.video_url = new_url
                    updated_count += 1
        
        if updated_count > 0:
            db.session.commit()
            print(f"Successfully updated {updated_count} steps.")
        else:
            print("No steps needed updating.")

if __name__ == "__main__":
    fix_database_paths()
