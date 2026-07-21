# run_audit.py
# Audit runner script executing the dataset QA verification pipeline.

from pathlib import Path
from .dataset_audit import DatasetAuditor

def main():
    base_dir = Path(__file__).parent
    processed_dir = base_dir / "processed"
    
    # We want output reports and plots to be saved under the main project directories
    project_root = base_dir.parent
    
    print("Initializing SQL dataset verification audit...")
    auditor = DatasetAuditor(
        processed_dir=processed_dir,
        output_dir=project_root
    )
    
    print("\nRunning comprehensive QA audits and training baselines...")
    score = auditor.compile_audit_report()
    
    print(f"\nAudit completed successfully. Overall QA Score: {score}/100")

if __name__ == "__main__":
    main()
