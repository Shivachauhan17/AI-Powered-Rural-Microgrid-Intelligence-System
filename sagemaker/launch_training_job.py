#!/usr/bin/env python3
"""
Launch SageMaker Training Job — run this from your LOCAL machine.

Usage:
    pip install boto3 sagemaker
    python sagemaker/launch_training_job.py

What it does:
  1. Uploads sagemaker/train.py to S3
  2. Creates a SageMaker Training Job (ml.m5.large, ~10 minutes, ~₹8)
  3. SageMaker trains all 14 models
  4. Saves model artifacts to s3://YOUR_BUCKET/models/latest/
  5. EC2 server downloads and uses them
"""

import boto3
import sagemaker
from sagemaker.estimator import Estimator
from datetime import datetime
import json

# ── CONFIG — fill these in ─────────────────────────────────────────────────
BUCKET_NAME   = "microgrid-ai-yourname"        # your S3 bucket name
REGION        = "ap-south-1"                   # Mumbai region
ROLE_ARN      = "arn:aws:iam::XXXXXXXXXXXX:role/SageMakerRole"  # from Step 2
JOB_NAME      = f"microgrid-train-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
INSTANCE_TYPE = "ml.m5.large"                  # cheapest that works
# ──────────────────────────────────────────────────────────────────────────

session    = boto3.Session(region_name=REGION)
sm_session = sagemaker.Session(boto_session=session)
s3_client  = session.client("s3")

print(f"\n{'='*55}")
print(f"  AI Microgrid — Launching SageMaker Training Job")
print(f"  Job name: {JOB_NAME}")
print(f"  Instance: {INSTANCE_TYPE}")
print(f"  Bucket:   s3://{BUCKET_NAME}")
print(f"{'='*55}\n")

# Step 1: Upload training script to S3
print("[1/4] Uploading training script to S3...")
s3_client.upload_file(
    "sagemaker/train.py",
    BUCKET_NAME,
    "scripts/train.py"
)
print(f"  ✅ s3://{BUCKET_NAME}/scripts/train.py")

# Step 2: Create estimator
print("[2/4] Creating SageMaker Estimator...")
estimator = Estimator(
    # Use AWS pre-built XGBoost container — no Docker needed
    image_uri=sagemaker.image_uris.retrieve(
        framework="xgboost",
        region=REGION,
        version="1.7-1"
    ),
    entry_point="train.py",
    source_dir="sagemaker",
    role=ROLE_ARN,
    instance_count=1,
    instance_type=INSTANCE_TYPE,
    output_path=f"s3://{BUCKET_NAME}/models/",
    base_job_name="microgrid-train",
    sagemaker_session=sm_session,
    hyperparameters={
        "n_days":       "120",
        "n_estimators": "200",
        "max_depth":    "6",
        "learning_rate":"0.08",
    },
    # Keep logs for debugging
    enable_sagemaker_metrics=True,
    metric_definitions=[
        {"Name": "mae",  "Regex": r"\[sagemaker metric\] .* mae=(\S+)"},
        {"Name": "rmse", "Regex": r"\[sagemaker metric\] .* rmse=(\S+)"},
    ]
)
print("  ✅ Estimator configured")

# Step 3: Point to training data in S3 (CSV files from smart meters)
# For first run: we use synthetic data (no input_data needed)
# For production: uncomment below and point to your real meter CSVs
# training_input = f"s3://{BUCKET_NAME}/training-data/"

print("[3/4] Launching training job...")
print(f"  ⏳ This takes ~10 minutes. Instance: {INSTANCE_TYPE}")
print(f"  💰 Estimated cost: ~₹8-12 for this run")
print(f"  You can track progress at:")
print(f"  https://{REGION}.console.aws.amazon.com/sagemaker/home#/jobs")
print()

estimator.fit(
    # inputs={"training": training_input},  # uncomment for real data
    job_name=JOB_NAME,
    wait=True,   # blocks until done — set False to run in background
    logs="All"
)

# Step 4: Print model S3 location
model_s3_path = estimator.model_data
print(f"\n[4/4] Training complete!")
print(f"  ✅ Models saved to: {model_s3_path}")
print()

# Save job info to local file — EC2 deploy script reads this
job_info = {
    "job_name":        JOB_NAME,
    "model_s3_path":   model_s3_path,
    "instance_type":   INSTANCE_TYPE,
    "bucket":          BUCKET_NAME,
    "completed_at":    datetime.now().isoformat(),
}
with open("sagemaker/last_training_job.json", "w") as f:
    json.dump(job_info, f, indent=2)

print("  Job info saved to sagemaker/last_training_job.json")
print()
print("  Next step: Run the EC2 deploy script to pull new models:")
print("  bash infra/aws/deploy.sh")
print()
