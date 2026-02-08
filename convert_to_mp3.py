#!/usr/bin/env python3
"""
Convert WAV files to MP3 and trim beginning/ending silence conservatively.
"""

import subprocess
import json
import re
from pathlib import Path

def detect_silence(wav_path, noise_db=-40, min_duration=0.3):
    """
    Detect silence in audio file.
    Returns (start_trim, end_trim) in seconds to trim from beginning and end.
    """
    # Use ffmpeg silencedetect to find silence
    cmd = [
        'ffmpeg', '-i', wav_path,
        '-af', f'silencedetect=noise={noise_db}dB:d={min_duration}',
        '-f', 'null', '-'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stderr
    
    # Parse silence periods
    silence_starts = []
    silence_ends = []
    
    for line in output.split('\n'):
        if 'silence_start:' in line:
            match = re.search(r'silence_start:\s*([\d.]+)', line)
            if match:
                silence_starts.append(float(match.group(1)))
        elif 'silence_end:' in line:
            match = re.search(r'silence_end:\s*([\d.]+)', line)
            if match:
                silence_ends.append(float(match.group(1)))
    
    return silence_starts, silence_ends

def get_audio_duration(wav_path):
    """Get audio duration in seconds"""
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        wav_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())

def convert_to_mp3_trimmed(wav_path, mp3_path, start_trim=0, end_trim=0):
    """
    Convert WAV to MP3 with optional trimming.
    start_trim: seconds to trim from beginning
    end_trim: seconds to trim from end
    """
    duration = get_audio_duration(wav_path)
    
    # Calculate actual duration after trimming
    actual_duration = duration - start_trim - end_trim
    
    if actual_duration <= 0.5:
        # If trimming would leave very little audio, don't trim
        start_trim = 0
        end_trim = 0
        actual_duration = duration
    
    cmd = [
        'ffmpeg', '-y', '-i', wav_path,
        '-ss', str(start_trim),
        '-t', str(actual_duration),
        '-codec:a', 'libmp3lame',
        '-q:a', '2',  # High quality VBR (~190kbps)
        mp3_path
    ]
    
    subprocess.run(cmd, capture_output=True)
    return start_trim, end_trim, actual_duration

def main():
    input_dir = Path("output_sections")
    output_dir = Path("output_sections_mp3")
    output_dir.mkdir(exist_ok=True)
    
    # Load sections data
    with open(input_dir / "sections_summary.json", 'r', encoding='utf-8') as f:
        sections = json.load(f)
    
    print("=" * 60)
    print("Converting WAV to MP3 with silence trimming")
    print("=" * 60)
    
    new_sections = []
    
    for section in sections:
        section_num = section['section']
        wav_path = input_dir / section['audio']
        mp3_filename = f"section_{section_num:03d}.mp3"
        mp3_path = output_dir / mp3_filename
        
        print(f"\nProcessing Section {section_num}:")
        
        # Detect silence
        silence_starts, silence_ends = detect_silence(str(wav_path))
        duration = get_audio_duration(str(wav_path))
        
        # Determine trim amounts (conservative)
        start_trim = 0
        end_trim = 0
        
        # Trim from beginning if silence at start
        if silence_starts and len(silence_ends) > 0:
            # If silence starts at 0, trim it
            if silence_starts[0] <= 0.1:  # Silence starts near beginning
                start_trim = silence_ends[0]
                # Be conservative - leave some padding
                start_trim = max(0, start_trim - 0.1)
        
        # Trim from end if silence at end
        if silence_starts and len(silence_starts) > len(silence_ends):
            # Silence extends to end
            end_trim = duration - silence_starts[-1]
            # Be conservative - leave some padding
            end_trim = max(0, end_trim - 0.1)
        elif silence_ends and silence_ends[-1] < duration - 0.1:
            # Check if there's silence at the end
            if len(silence_starts) == len(silence_ends):
                # Last silence period ends before the audio ends
                # Check if the gap is significant
                pass  # No trailing silence to trim
        
        # Conservative limits: don't trim more than 30% of audio
        max_trim = duration * 0.3
        start_trim = min(start_trim, max_trim)
        end_trim = min(end_trim, max_trim)
        
        print(f"  Original duration: {duration:.2f}s")
        print(f"  Detected silence periods: {len(silence_starts)}")
        print(f"  Trimming: start={start_trim:.2f}s, end={end_trim:.2f}s")
        
        # Convert and trim
        actual_start, actual_end, new_duration = convert_to_mp3_trimmed(
            str(wav_path), str(mp3_path), start_trim, end_trim
        )
        
        print(f"  New duration: {new_duration:.2f}s")
        print(f"  Saved: {mp3_path}")
        
        # Copy image to new directory
        img_src = input_dir / section['image']
        img_dst = output_dir / section['image']
        if not img_dst.exists():
            import shutil
            shutil.copy(str(img_src), str(img_dst))
        
        new_sections.append({
            'section': section_num,
            'start_time': section['start_time'],
            'end_time': section['end_time'],
            'duration': new_duration,
            'image': section['image'],
            'audio': mp3_filename,
            'trim_start': actual_start,
            'trim_end': actual_end,
            'original_duration': duration
        })
    
    # Write updated summary
    summary_path = output_dir / "sections_summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(new_sections, f, indent=2, ensure_ascii=False)
    
    # Copy and update HTML player
    with open(input_dir / "index.html", 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Update HTML to use MP3
    html_content = html_content.replace('.wav"', '.mp3"')
    html_content = html_content.replace('type="audio/wav"', 'type="audio/mpeg"')
    
    html_path = output_dir / "index.html"
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print("\n" + "=" * 60)
    print("Done!")
    print(f"MP3 files saved to: {output_dir}")
    print(f"Updated HTML player: {html_path}")
    print("=" * 60)

if __name__ == "__main__":
    main()
