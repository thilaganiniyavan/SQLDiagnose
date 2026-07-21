# builder_run.py
# The primary entrypoint to execute the dataset downloader and processor pipeline.

import os
from pathlib import Path
from .downloader import DatasetDownloader
from .data_processor import SQLDataProcessor

def main():
    base_dir = Path(__file__).parent
    raw_dir = base_dir / "raw"
    output_dir = base_dir / "processed"
    
    # 1. Download datasets
    print("=== Step 1: Downloading Raw Datasets ===")
    downloader = DatasetDownloader(raw_dir)
    downloader.download_all()
    
    # 2. Process, mutate, validate, and build splits
    print("\n=== Step 2: Processing and Building Unified Datasets ===")
    processor = SQLDataProcessor(
        raw_dir=raw_dir,
        output_dir=output_dir,
        seed=42
    )
    # We build the dataset with 1500 samples per class to maintain class balance
    splits = processor.process_and_build(target_samples_per_class=1500)
    
    print("\n=== Step 3: Pipeline Execution Completed ===")
    print(f"Train dataset size: {len(splits['train'])} samples")
    print(f"Validation dataset size: {len(splits['validation'])} samples")
    print(f"Test dataset size: {len(splits['test'])} samples")

if __name__ == "__main__":
    main()
