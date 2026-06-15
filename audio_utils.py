import os
import subprocess
import imageio_ffmpeg

def get_ffmpeg_path():
    """
    Get the path to the ffmpeg executable.
    imageio-ffmpeg handles downloading the binary for the platform if it is not present.
    """
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        raise RuntimeError(f"Failed to locate ffmpeg executable via imageio-ffmpeg: {e}")

def extract_audio(video_path: str, output_audio_path: str, bitrate: int = 32) -> bool:
    """
    Extracts the audio track from a video file and encodes it as a low-bitrate mono MP3.
    Using low bitrate (e.g. 32kbps) and mono channels minimizes the file size,
    allowing longer videos to fit in single API requests.
    
    Args:
        video_path: Path to the source video file.
        output_audio_path: Path where the extracted MP3 file should be saved.
        bitrate: Audio bitrate in kbps (default 32, which is excellent for speech).
        
    Returns:
        True if extraction was successful, False otherwise.
    """
    try:
        ffmpeg_exe = get_ffmpeg_path()
    except Exception as e:
        print(f"Error finding ffmpeg: {e}")
        return False
        
    cmd = [
        ffmpeg_exe,
        "-y",                    # Overwrite output file if it exists
        "-i", video_path,        # Input video
        "-vn",                   # Disable video recording
        "-acodec", "libmp3lame", # Use MP3 encoder
        "-ac", "1",              # Convert to mono (1 audio channel)
        "-ar", "16000",          # Set sample rate to 16kHz (optimal for speech recognition)
        "-b:a", f"{bitrate}k",   # Set bitrate (lower bitrate = smaller file size)
        output_audio_path
    ]
    
    try:
        # Run ffmpeg with stdout and stderr piped to capture errors silently
        result = subprocess.run(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True, 
            check=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n[FFmpeg Error] Command failed for {os.path.basename(video_path)}:\n{e.stderr}")
        return False
    except Exception as e:
        print(f"\n[Error] Unexpected error during audio extraction: {e}")
        return False

def split_audio(audio_path: str, segment_time_secs: int = 1800, max_size_mb: float = 24.0) -> list[str]:
    """
    Checks if an audio file exceeds the size threshold. If it does, splits it into
    multiple sequential chunks of specified segment duration.
    
    Args:
        audio_path: Path to the audio file.
        segment_time_secs: Time length of each segment in seconds (default 1800s = 30 minutes).
        max_size_mb: Threshold size in MB. If file is under this, it is not split.
        
    Returns:
        A list of paths to the audio chunks (or the original file if no splitting was needed).
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    if file_size_mb <= max_size_mb:
        return [audio_path]
        
    print(f"Audio file size ({file_size_mb:.2f} MB) exceeds limit ({max_size_mb} MB). Splitting into {segment_time_secs // 60}-minute segments...")
    
    try:
        ffmpeg_exe = get_ffmpeg_path()
    except Exception as e:
        print(f"Error finding ffmpeg for splitting: {e}")
        return [audio_path]
        
    dir_name = os.path.dirname(audio_path)
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    output_pattern = os.path.join(dir_name, f"{base_name}_chunk_%03d.mp3")
    
    # Use ffmpeg's segment muxer to split the file without re-encoding (-c copy is fast and lossless)
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", audio_path,
        "-f", "segment",
        "-segment_time", str(segment_time_secs),
        "-c", "copy",
        output_pattern
    ]
    
    try:
        subprocess.run(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True, 
            check=True
        )
        
        # Discover all chunk files generated
        chunks = []
        i = 0
        while True:
            chunk_path = os.path.join(dir_name, f"{base_name}_chunk_{i:03d}.mp3")
            if os.path.exists(chunk_path):
                chunks.append(chunk_path)
                i += 1
            else:
                break
                
        if not chunks:
            print("Warning: ffmpeg segment command ran but no chunks were found. Falling back to full file.")
            return [audio_path]
            
        print(f"Successfully split audio into {len(chunks)} chunks.")
        return chunks
        
    except subprocess.CalledProcessError as e:
        print(f"\n[FFmpeg Error] Splitting failed:\n{e.stderr}")
        return [audio_path]
    except Exception as e:
        print(f"\n[Error] Unexpected error during audio splitting: {e}")
        return [audio_path]
