import sys
import traceback

print("Testing MediaPipe import...")
try:
    import mediapipe as mp
    print(f"MediaPipe version: {mp.__version__}")
except Exception as e:
    print("Error importing mediapipe:")
    traceback.print_exc()
    sys.exit(1)

print("Initializing Pose...")
try:
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        model_complexity=1
    )
    print("MediaPipe Pose initialized successfully!")
    
    # Test processing a dummy image
    import numpy as np
    import cv2
    print("Testing processing on dummy image...")
    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
    results = pose.process(dummy_img)
    print("Processing successful!")
    
except Exception as e:
    print("Error initializing or using Pose:")
    traceback.print_exc()
