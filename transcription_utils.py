import os
import json
import time
from groq import Groq
from audio_utils import extract_audio, split_audio

def transcribe_audio_file(audio_path: str, api_key: str, prompt: str = None) -> str:
    """
    Directly transcribes a single audio file using Groq's Whisper-large-v3 API.
    
    Args:
        audio_path: Path to the audio file (must be < 25MB).
        api_key: The Groq API key.
        prompt: Optional prompt to guide the style/punctuation of transcription.
        
    Returns:
        The transcribed text.
    """
    if not api_key:
        raise ValueError("Groq API Key is not set or empty. Please check your configuration.")
        
    client = Groq(api_key=api_key)
    
    # We must pass a tuple of (filename, file_body) to the file argument
    filename = os.path.basename(audio_path)
    
    with open(audio_path, "rb") as f:
        file_data = f.read()
        
    params = {
        "file": (filename, file_data),
        "model": "whisper-large-v3",
        "response_format": "json"
    }
    if prompt:
        params["prompt"] = prompt
        
    # Attempt with simple retry mechanism for rate limits or transient issues
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.audio.transcriptions.create(**params)
            return response.text
        except Exception as e:
            # Check for Rate Limit (HTTP 429) or other errors
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5
                print(f"\nAPI Error: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise e

def transcribe_video_with_cache(
    video_path: str, 
    cache_dir: str, 
    api_key: str, 
    bitrate: int = 32,
    prompt: str = None
) -> str:
    """
    Manages transcription workflow for a video file with caching:
    1. Checks if a cached transcript already exists. If yes, returns it.
    2. Extracts audio from the video.
    3. Splits audio if it exceeds 24MB.
    4. Transcribes all chunks and merges them.
    5. Caches the result and cleans up temporary audio files.
    
    Args:
        video_path: Path to the source video.
        cache_dir: Directory where transcripts are cached.
        api_key: The Groq API key.
        bitrate: Audio bitrate for extraction.
        prompt: Optional transcription prompt.
        
    Returns:
        The full transcript text.
    """
    video_filename = os.path.basename(video_path)
    cache_filename = f"{video_filename}.json"
    cache_path = os.path.join(cache_dir, cache_filename)
    
    # Check cache
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                cached_text = data.get("text", "")
                if cached_text:
                    print(f" -> Found cached transcript for: {video_filename}")
                    return cached_text
        except Exception as e:
            print(f"Warning: Failed to read cache file {cache_path}. Re-transcribing... ({e})")
            
    # Process transcript
    print(f" -> Processing: {video_filename}")
    
    # Temporary audio path
    temp_dir = os.path.join(cache_dir, "temp_audio")
    os.makedirs(temp_dir, exist_ok=True)
    temp_audio_path = os.path.join(temp_dir, f"{os.path.splitext(video_filename)[0]}.mp3")
    
    # 1. Extract audio
    print(f"    Extracting audio track...")
    success = extract_audio(video_path, temp_audio_path, bitrate=bitrate)
    if not success:
        raise RuntimeError(f"Failed to extract audio from video: {video_path}")
        
    try:
        # 2. Split audio into chunks if necessary
        audio_chunks = split_audio(temp_audio_path, segment_time_secs=1800, max_size_mb=24.0)
        
        # 3. Transcribe chunks
        transcript_parts = []
        for index, chunk_path in enumerate(audio_chunks):
            if len(audio_chunks) > 1:
                print(f"    Transcribing chunk {index + 1}/{len(audio_chunks)}...")
            else:
                print(f"    Transcribing audio...")
                
            chunk_text = transcribe_audio_file(chunk_path, api_key, prompt=prompt)
            if chunk_text.strip():
                transcript_parts.append(chunk_text.strip())
                
        full_transcript = "\n\n".join(transcript_parts)
        
        # 4. Save to cache
        cache_data = {
            "video_name": video_filename,
            "video_size_bytes": os.path.getsize(video_path),
            "transcribed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "text": full_transcript
        }
        
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
        return full_transcript
        
    finally:
        # Clean up temporary audio files
        if os.path.exists(temp_audio_path):
            try:
                os.remove(temp_audio_path)
            except Exception as e:
                print(f"Warning: Could not remove temporary file {temp_audio_path}: {e}")
                
        # Clean up chunks if any were generated
        if 'audio_chunks' in locals() and len(audio_chunks) > 1:
            for chunk_path in audio_chunks:
                if chunk_path != temp_audio_path and os.path.exists(chunk_path):
                    try:
                        os.remove(chunk_path)
                    except Exception as e:
                        print(f"Warning: Could not remove temporary chunk file {chunk_path}: {e}")
                        
        # Attempt to clean up empty temp directory
        if os.path.exists(temp_dir) and not os.listdir(temp_dir):
            try:
                os.rmdir(temp_dir)
            except Exception:
                pass
