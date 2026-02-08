#!/usr/bin/env python3
"""
Trim silence from MP3 files in-place with aggressive trailing silence detection.
"""

import subprocess
import re
from pathlib import Path
import json

def detect_silence_full(mp3_path, noise_db=-40, min_duration=0.2):
    """
    Detect all silence periods in MP3.
    Returns list of (start, end) tuples for silence periods.
    """
    cmd = [
        'ffmpeg', '-i', mp3_path,
        '-af', f'silencedetect=noise={noise_db}dB:d={min_duration}',
        '-f', 'null', '-'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stderr
    
    silences = []
    current_start = None
    
    for line in output.split('\n'):
        if 'silence_start:' in line:
            match = re.search(r'silence_start:\s*([\d.]+)', line)
            if match:
                current_start = float(match.group(1))
        elif 'silence_end:' in line:
            match = re.search(r'silence_end:\s*([\d.]+)', line)
            if match and current_start is not None:
                silence_end = float(match.group(1))
                silences.append((current_start, silence_end))
                current_start = None
    
    # If there's a silence_start without silence_end, it goes to end of file
    if current_start is not None:
        silences.append((current_start, None))  # None means goes to end
    
    return silences

def get_audio_duration(mp3_path):
    """Get audio duration in seconds"""
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        mp3_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())

def trim_silence_inplace(mp3_path):
    """
    Trim leading and trailing silence from MP3 file in-place.
    Returns (trim_start, trim_end, original_duration, new_duration)
    """
    duration = get_audio_duration(mp3_path)
    silences = detect_silence_full(str(mp3_path))
    
    if not silences:
        return 0, 0, duration, duration
    
    # Determine trim amounts
    trim_start = 0
    trim_end = 0
    
    # Check for leading silence (silence that starts at or very near 0)
    first_silence = silences[0]
    if first_silence[0] <= 0.1:  # Silence starts near beginning
        trim_start = first_silence[1] if first_silence[1] else 0
        # Be conservative: leave 0.05s padding
        trim_start = max(0, trim_start - 0.05)
    
    # Check for trailing silence (silence that extends to end)
    last_silence = silences[-1]
    if last_silence[1] is None:  # Silence goes to end of file
        trim_end = duration - last_silence[0]
        # Be conservative: leave 0.1s padding at end
        trim_end = max(0, trim_end - 0.1)
    elif last_silence[1] >= duration - 0.1:  # Silence ends very near end
        trim_end = duration - last_silence[0]
        trim_end = max(0, trim_end - 0.1)
    
    # Conservative limits: don't trim more than 40% from either end
    max_trim_start = duration * 0.4
    max_trim_end = duration * 0.4
    trim_start = min(trim_start, max_trim_start)
    trim_end = min(trim_end, max_trim_end)
    
    new_duration = duration - trim_start - trim_end
    
    if new_duration < 0.5:
        # Too much would be trimmed, keep original
        return 0, 0, duration, duration
    
    if trim_start > 0.1 or trim_end > 0.1:
        # Need to trim - use ffmpeg to create temp file then replace
        temp_path = str(mp3_path) + ".tmp.mp3"
        
        cmd = [
            'ffmpeg', '-y', '-i', str(mp3_path),
            '-ss', str(trim_start),
            '-t', str(new_duration),
            '-codec:a', 'libmp3lame',
            '-q:a', '2',
            temp_path
        ]
        
        result = subprocess.run(cmd, capture_output=True)
        
        if result.returncode == 0:
            # Replace original with trimmed version
            import os
            os.replace(temp_path, mp3_path)
            return trim_start, trim_end, duration, new_duration
        else:
            print(f"    Error trimming {mp3_path}: {result.stderr}")
            if Path(temp_path).exists():
                Path(temp_path).unlink()
            return 0, 0, duration, duration
    
    return 0, 0, duration, duration

def main():
    mp3_dir = Path("output_sections_mp3")
    
    # Load sections data
    with open(mp3_dir / "sections_summary.json", 'r', encoding='utf-8') as f:
        sections = json.load(f)
    
    print("=" * 70)
    print("Trimming silence from MP3 files in-place")
    print("=" * 70)
    
    updated_sections = []
    
    for section in sections:
        section_num = section['section']
        mp3_path = mp3_dir / section['audio']
        
        print(f"\nSection {section_num}: {section['audio']}")
        print(f"  Current duration: {section['duration']:.2f}s")
        
        # Detect silences for reporting
        silences = detect_silence_full(str(mp3_path))
        duration = get_audio_duration(str(mp3_path))
        
        if silences:
            print(f"  Silence periods detected: {len(silences)}")
            for i, (s, e) in enumerate(silences):
                if e is None:
                    print(f"    [{i+1}] {s:.2f}s -> END (trailing silence: {duration - s:.2f}s)")
                else:
                    print(f"    [{i+1}] {s:.2f}s -> {e:.2f}s (duration: {e - s:.2f}s)")
        
        # Trim in-place
        trim_start, trim_end, orig_dur, new_dur = trim_silence_inplace(mp3_path)
        
        if trim_start > 0 or trim_end > 0:
            print(f"  ✓ Trimmed: start={trim_start:.2f}s, end={trim_end:.2f}s")
            print(f"  ✓ New duration: {new_dur:.2f}s")
            
            # Update cumulative trim info
            section['trim_start'] = section.get('trim_start', 0) + trim_start
            section['trim_end'] = section.get('trim_end', 0) + trim_end
            section['duration'] = new_dur
        else:
            print(f"  - No significant silence to trim")
        
        updated_sections.append(section)
    
    # Save updated summary
    with open(mp3_dir / "sections_summary.json", 'w', encoding='utf-8') as f:
        json.dump(updated_sections, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 70)
    print("Done! All MP3 files trimmed in-place.")
    print("=" * 70)
    
    # Show total savings
    total_original = sum(s['original_duration'] for s in updated_sections)
    total_new = sum(s['duration'] for s in updated_sections)
    print(f"\nTotal duration: {total_original:.1f}s -> {total_new:.1f}s (saved {total_original - total_new:.1f}s)")

if __name__ == "__main__":
    main()
