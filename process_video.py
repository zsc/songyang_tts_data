#!/usr/bin/env python3
"""
Process video composed of still images:
1. Detect consecutive still image sections using ffmpeg scene detection
   - Only considers UPPER HALF of screen (ignores buttons in lower half)
2. Chop into sections
3. Extract (still image, accompanying audio wav) pairs
"""

import subprocess
import os
import json
import re
from pathlib import Path

def detect_scenes_upper_half(video_path, threshold=0.02):
    """
    Use ffmpeg's scene detection on upper half only to find scene changes.
    This ignores buttons/animations in the lower half of the screen.
    threshold: scene change threshold (0.0-1.0), lower = more sensitive
    """
    print("Analyzing video for scene changes (upper half only)...")
    
    # First get video dimensions
    cmd = [
        'ffprobe', '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height',
        '-of', 'csv=s=x:p=0',
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    width, height = map(int, result.stdout.strip().split('x'))
    print(f"Video dimensions: {width}x{height}")
    print(f"Analyzing upper half: {width}x{height//2}")
    
    # Use ffmpeg to crop to upper half and detect scene changes
    # crop=width:height:start_x:start_y -> crop to upper half
    crop_filter = f"crop={width}:{height//2}:0:0"
    cmd = [
        'ffmpeg', '-i', video_path,
        '-vf', f'{crop_filter},select=gt(scene\\,{threshold}),showinfo',
        '-f', 'null', '-'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stderr
    
    # Parse scene change timestamps
    scene_times = [0.0]  # Start at 0
    
    for line in output.split('\n'):
        if 'pts_time:' in line:
            match = re.search(r'pts_time:\s*([\d.]+)', line)
            if match:
                time_sec = float(match.group(1))
                scene_times.append(time_sec)
    
    # Get video duration
    duration_cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path
    ]
    duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
    duration = float(duration_result.stdout.strip())
    scene_times.append(duration)
    
    # Create segments, filtering very short ones
    segments = []
    for i in range(len(scene_times) - 1):
        start = scene_times[i]
        end = scene_times[i + 1]
        if end - start >= 0.5:  # At least 0.5 seconds
            segments.append((start, end))
    
    return segments, (width, height)

def extract_still_image(video_path, time_sec, output_path):
    """Extract a single frame at given time"""
    cmd = [
        'ffmpeg', '-y', '-i', video_path,
        '-ss', str(time_sec),
        '-vframes', '1',
        '-q:v', '2',
        output_path
    ]
    subprocess.run(cmd, capture_output=True)
    print(f"  Image: {output_path}")

def extract_audio_segment(video_path, start_sec, end_sec, output_path):
    """Extract audio segment for given time range"""
    duration = end_sec - start_sec
    cmd = [
        'ffmpeg', '-y', '-i', video_path,
        '-ss', str(start_sec),
        '-t', str(duration),
        '-vn',  # No video
        '-acodec', 'pcm_s16le',  # PCM 16-bit
        '-ar', '48000',  # 48kHz
        '-ac', '2',  # Stereo
        output_path
    ]
    subprocess.run(cmd, capture_output=True)
    print(f"  Audio: {output_path}")

def main():
    video_path = "吴语上丽片-松阳话 [BV1icCyYAEr5].mp4"
    output_dir = Path("output_sections")
    output_dir.mkdir(exist_ok=True)
    
    print("=" * 60)
    print("Step 1: Detecting scene changes (upper half only)...")
    print("=" * 60)
    
    # Detect scene changes with lower threshold (more sensitive)
    segments, (width, height) = detect_scenes_upper_half(video_path, threshold=0.02)
    
    print(f"\nFound {len(segments)} sections:")
    for i, (start, end) in enumerate(segments):
        print(f"  Section {i+1}: {start:.2f}s - {end:.2f}s (duration: {end-start:.2f}s)")
    
    print("\n" + "=" * 60)
    print("Step 2: Extracting images and audio...")
    print("=" * 60)
    
    results = []
    
    for i, (start, end) in enumerate(segments):
        section_num = i + 1
        
        # Extract still image from middle of segment
        img_time = start + 0.3
        img_path = output_dir / f"section_{section_num:03d}.jpg"
        audio_path = output_dir / f"section_{section_num:03d}.wav"
        
        print(f"\nSection {section_num} ({start:.1f}s - {end:.1f}s):")
        extract_still_image(video_path, img_time, str(img_path))
        extract_audio_segment(video_path, start, end, str(audio_path))
        
        results.append({
            'section': section_num,
            'start_time': start,
            'end_time': end,
            'duration': end - start,
            'image': str(img_path.name),
            'audio': str(audio_path.name)
        })
    
    # Write summary JSON
    summary_path = output_dir / "sections_summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 60)
    print("Done!")
    print(f"Summary: {summary_path}")
    print("=" * 60)

if __name__ == "__main__":
    main()
