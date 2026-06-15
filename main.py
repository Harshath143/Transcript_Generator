import os
import re
import sys
import argparse
from dotenv import load_dotenv
from transcription_utils import transcribe_video_with_cache
from pdf_generator import generate_pdf

def natural_sort_key(s: str):
    """
    Key function for natural sorting (e.g. 'Session 2' comes before 'Session 10').
    Splits string into numeric and non-numeric parts for comparison.
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def find_video_files(folder_path: str) -> list[str]:
    """
    Scans the folder for video files and returns a list of sorted absolute paths.
    """
    video_extensions = {
        '.mp4', '.mov', '.mkv', '.avi', '.webm', 
        '.flv', '.wmv', '.m4v', '.mpg', '.mpeg', '.3gp'
    }
    
    video_files = []
    for entry in os.scandir(folder_path):
        if entry.is_file():
            ext = os.path.splitext(entry.name)[1].lower()
            if ext in video_extensions:
                video_files.append(entry.name)
                
    # Sort naturally
    video_files.sort(key=natural_sort_key)
    return [os.path.join(folder_path, name) for name in video_files]

def setup_env():
    """
    Loads variables from .env and verifies API key is configured.
    """
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    
    # If the user hasn't set the key, or the key is still the default template string
    if not api_key or "your_api_key" in api_key:
        print("\n" + "=" * 60)
        print("                 GROQ API KEY CONFIGURATION")
        print("=" * 60)
        print("An active Groq API Key is required to run transcriptions.")
        print("Please create a file named '.env' in this directory and add your key:")
        print("GROQ_API_KEY=gsk_xxxxxxx...")
        print("\nYou can get a free/paid API key from: https://console.groq.com/")
        print("=" * 60 + "\n")
        
        # Ask the user if they want to paste it now to write it to .env
        input_key = input("Paste your Groq API Key now (or press Enter to exit): ").strip()
        if input_key:
            with open(".env", "w") as f:
                f.write(f"GROQ_API_KEY={input_key}\n")
            print(" -> API Key saved to '.env' file successfully!")
            os.environ["GROQ_API_KEY"] = input_key
            api_key = input_key
        else:
            print("Error: No Groq API Key found. Exiting.")
            sys.exit(1)
            
    return api_key

def main():
    # Parse CLI Arguments
    parser = argparse.ArgumentParser(description="Transcribe folder of videos into a structured PDF book.")
    parser.add_argument(
        "folder_path", 
        nargs="?", 
        help="Path to the folder containing video files."
    )
    parser.add_argument(
        "--output", 
        "-o", 
        help="Custom output path for the PDF file. (Defaults to <folder_path>/<folder_name>.pdf)"
    )
    parser.add_argument(
        "--bitrate", 
        type=int, 
        default=None, 
        help="Audio extraction bitrate in kbps. Defaults to value in .env or 32."
    )
    
    args = parser.parse_args()
    
    # Setup and get Groq API key
    api_key = setup_env()
    
    # Get target folder
    folder_path = args.folder_path
    if not folder_path:
        print("\n--- Video to PDF Book Transcriber ---")
        folder_path = input("Enter the absolute path to your video folder: ").strip()
        
    # Standardize path
    folder_path = os.path.abspath(folder_path.replace('"', '').replace("'", ""))
    
    if not os.path.exists(folder_path):
        print(f"Error: Folder path does not exist: {folder_path}")
        sys.exit(1)
    if not os.path.isdir(folder_path):
        print(f"Error: The specified path is not a directory: {folder_path}")
        sys.exit(1)
        
    # Book title is the folder name
    book_title = os.path.basename(folder_path)
    if not book_title:
        # Fallback if path ends with slashes and basename is empty
        book_title = os.path.basename(os.path.dirname(folder_path))
    if not book_title:
        book_title = "Transcript Book"
        
    # Get output PDF path
    output_pdf = args.output
    if not output_pdf:
        output_pdf = os.path.join(folder_path, f"{book_title}.pdf")
        
    # Locate videos
    print(f"\nScanning folder: {folder_path}...")
    video_paths = find_video_files(folder_path)
    
    if not video_paths:
        print("No video files found in the specified folder.")
        print("Supported formats: .mp4, .mov, .mkv, .avi, .webm, .flv, .wmv, .m4v, .mpg")
        sys.exit(0)
        
    print(f"Found {len(video_paths)} video files in natural sequence.")
    
    # Initialize cache directory
    cache_dir = os.path.join(folder_path, ".transcripts_cache")
    os.makedirs(cache_dir, exist_ok=True)
    
    # Configurations
    bitrate = args.bitrate
    if bitrate is None:
        bitrate_str = os.getenv("AUDIO_BITRATE", "32")
        bitrate = int(bitrate_str) if bitrate_str.isdigit() else 32
        
    prompt = os.getenv("TRANSCRIPTION_PROMPT", None)
    
    # Process transcripts
    chapters = []
    print("\nStarting video processing and transcription...")
    print("-" * 60)
    
    for i, video_path in enumerate(video_paths):
        video_filename = os.path.basename(video_path)
        print(f"[{i+1}/{len(video_paths)}] Processing {video_filename}...")
        try:
            transcript = transcribe_video_with_cache(
                video_path=video_path,
                cache_dir=cache_dir,
                api_key=api_key,
                bitrate=bitrate,
                prompt=prompt
            )
            chapters.append((video_filename, transcript))
            print("    Done!")
        except Exception as e:
            print(f"\n[ERROR] Failed to process {video_filename}: {e}\n")
            # Ask user if we should continue or stop
            choice = input("Do you want to continue processing remaining videos? (y/n): ").strip().lower()
            if choice != 'y':
                print("Process aborted by user.")
                sys.exit(1)
                
    if not chapters:
        print("\nNo chapters were successfully transcribed. PDF generation skipped.")
        sys.exit(1)
        
    print("-" * 60)
    print("All transcriptions completed successfully.")
    
    # Compile PDF
    try:
        generate_pdf(book_title, chapters, output_pdf)
        print(f"\nSuccess! Your book has been compiled to:\n{output_pdf}\n")
    except Exception as e:
        print(f"\n[ERROR] PDF compilation failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
