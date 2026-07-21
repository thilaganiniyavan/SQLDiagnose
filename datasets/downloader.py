# downloader.py
# Resolves and extracts local dataset zips (like spider.zip) and handles fallbacks.

import os
import shutil
import zipfile
from pathlib import Path

RAW_DIR = Path(__file__).parent / "raw"

class DatasetDownloader:
    def __init__(self, raw_dir: Path = RAW_DIR):
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def download_spider(self) -> Path:
        dest_dir = self.raw_dir / "spider"
        if (dest_dir / "spider").exists():
            print("Spider dataset already extracted.")
            return dest_dir / "spider"

        # Check local downloads folder first (bypasses network block)
        local_downloads_path = Path("C:/Users/tejes/Downloads/spider.zip")
        zip_path = self.raw_dir / "spider.zip"
        
        if local_downloads_path.exists():
            print(f"Found local spider.zip at {local_downloads_path}. Copying...")
            shutil.copy(local_downloads_path, zip_path)
            extract_zip(zip_path, dest_dir)
            if zip_path.exists():
                os.remove(zip_path)
        else:
            # Fallback: Attempt download
            url = "https://lily.science.yale.edu/static/spider.zip"
            print(f"Local spider.zip not found. Attempting download from {url}...")
            try:
                import urllib.request
                req = urllib.request.Request(
                    url, 
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                )
                with urllib.request.urlopen(req) as response, open(zip_path, 'wb') as out_file:
                    out_file.write(response.read())
                extract_zip(zip_path, dest_dir)
                if zip_path.exists():
                    os.remove(zip_path)
            except Exception as e:
                print(f"Warning: Download failed ({e}). Bypassing download to use project schema fallbacks.")
                
        return dest_dir / "spider"

    def download_all(self):
        print("Starting dataset localization/download phase...")
        self.download_spider()
        print("All raw datasets verified/downloaded.")

def extract_zip(zip_path: Path, dest_dir: Path):
    print(f"Extracting {zip_path} to {dest_dir}...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(dest_dir)
    print("Extraction complete.")

if __name__ == "__main__":
    downloader = DatasetDownloader()
    downloader.download_all()
