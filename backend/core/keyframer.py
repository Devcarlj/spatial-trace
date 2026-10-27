import cv2
import numpy as np
import os

def compute_diff(prev_frame, curr_frame):
    # Compute frame-diff on downscaled grayscale
    diff = cv2.absdiff(prev_frame, curr_frame)
    score = np.sum(diff)
    return score, diff

def get_region_diff_bbox(pre_motion_frame, post_settle_frame):
    """
    Compares pre-motion and post-settle frames to get a changed-area bbox.
    """
    gray1 = cv2.cvtColor(pre_motion_frame, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(post_settle_frame, cv2.COLOR_BGR2GRAY)
    
    # Gaussian blur to reduce noise
    gray1 = cv2.GaussianBlur(gray1, (21, 21), 0)
    gray2 = cv2.GaussianBlur(gray2, (21, 21), 0)
    
    diff = cv2.absdiff(gray1, gray2)
    _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
    thresh = cv2.dilate(thresh, None, iterations=2)
    
    contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return None
        
    # Find the largest contour which represents the biggest change
    largest_contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest_contour) < 500: # Ignore tiny changes
        return None
        
    x, y, w, h = cv2.boundingRect(largest_contour)
    return [x, y, w, h] # diff_bbox

def process_video(video_path, clip_id):
    os.makedirs(f"data/frames/{clip_id}", exist_ok=True)
    
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    
    # Target 2-4 FPS
    frame_skip = int(fps // 3) 
    
    prev_gray_small = None
    pre_motion_full_frame = None
    
    motion_spike = False
    calm_frames = 0
    calm_threshold = 3 * 2 # ~2 seconds at 3 FPS
    
    frame_count = 0
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
            
        if frame_count % frame_skip == 0:
            # Downscaled copy for diffing
            small_frame = cv2.resize(frame, (640, 360))
            gray_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
            
            if prev_gray_small is not None:
                diff_score, _ = compute_diff(prev_gray_small, gray_small)
                
                # Settle detection logic
                if diff_score > 500000: # Arbitrary spike threshold, needs tuning per clip[cite: 1]
                    if not motion_spike:
                        # Capture the frame right before motion started
                        pre_motion_full_frame = prev_full_frame 
                    motion_spike = True
                    calm_frames = 0
                elif motion_spike and diff_score < 100000:
                    calm_frames += 1
                    
                if motion_spike and calm_frames >= calm_threshold:
                    timestamp = frame_count / fps
                    print(f"Settled keyframe detected at {timestamp:.2f}s")
                    
                    if pre_motion_full_frame is not None:
                        bbox = get_region_diff_bbox(pre_motion_full_frame, frame)
                        
                        if bbox:
                            # Save full-res keyframe and crop[cite: 1]
                            x, y, w, h = bbox
                            crop = frame[y:y+h, x:x+w]
                            
                            frame_path = f"data/frames/{clip_id}/frame_{frame_count}.jpg"
                            crop_path = f"data/frames/{clip_id}/crop_{frame_count}.jpg"
                            
                            cv2.imwrite(frame_path, frame)
                            cv2.imwrite(crop_path, crop)
                            
                            print(f"Saved region diff crop. Bbox: {bbox}")
                            # TODO for Days 2-3: Send to VLM and index to SQLite
                            
                    motion_spike = False 
                    calm_frames = 0
            
            prev_gray_small = gray_small
            prev_full_frame = frame.copy()
            
        frame_count += 1

    cap.release()

if __name__ == "__main__":
    # Example usage once you record your clips
    # process_video("data/clips/desk_scripted.mp4", "clip_desk_01")
    pass