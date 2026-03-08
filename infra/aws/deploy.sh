#!/bin/bash
# ============================================================
#  AI Microgrid — EC2 Deploy Script
#  Run this on your EC2 instance to:
#  1. Pull latest code
#  2. Download new models from S3
#  3. Rebuild and restart containers
# ============================================================

set -e

BUCKET="microgrid-ai-yourname"     # change to your bucket name
REGION="ap-south-1"
APP_DIR="$HOME/ai-microgrid"
MODEL_DIR="$APP_DIR/backend/app/models/saved_models"

echo ""
echo "================================================"
echo "  AI Microgrid — Deploying to EC2"
echo "  $(date)"
echo "================================================"

echo ""
echo "[1/5] Checking code..."
cd $APP_DIR
echo "  Done"

echo ""
echo "[2/5] Downloading ML models from S3..."
mkdir -p $MODEL_DIR

aws s3 sync \
    s3://$BUCKET/models/latest/ \
    $MODEL_DIR/ \
    --region $REGION \
    --exclude "*" \
    --include "*.joblib" \
    --include "*.json"

if aws s3 ls s3://$BUCKET/models/latest/model.tar.gz 2>/dev/null; then
    aws s3 cp s3://$BUCKET/models/latest/model.tar.gz $MODEL_DIR/
    cd $MODEL_DIR && tar -xzf model.tar.gz && rm model.tar.gz
    cd $APP_DIR
fi

MODEL_COUNT=$(ls $MODEL_DIR/*.joblib 2>/dev/null | wc -l)
echo "  $MODEL_COUNT model files ready"

echo ""
echo "[3/5] Checking .env..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp $APP_DIR/.env.example $APP_DIR/.env
fi
if ! grep -q "MODEL_S3_BUCKET" $APP_DIR/.env; then
    echo "MODEL_S3_BUCKET=$BUCKET" >> $APP_DIR/.env
    echo "MODEL_S3_PREFIX=models/latest/" >> $APP_DIR/.env
fi

echo ""
echo "[4/5] Building Docker containers..."
cd $APP_DIR
docker-compose build

echo ""
echo "[5/5] Restarting services..."
docker-compose down
docker-compose up -d
sleep 15

PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "YOUR_IP")
BACKEND=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health || echo "000")
FRONTEND=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:80 || echo "000")

echo ""
echo "================================================"
echo "  DEPLOYMENT COMPLETE — $(date)"
echo "================================================"
echo "  Dashboard:  http://$PUBLIC_IP"
echo "  API Docs:   http://$PUBLIC_IP:8000/docs"
echo "  Backend:    $BACKEND | Frontend: $FRONTEND"
echo "  Models:     $MODEL_COUNT files"
echo "================================================"
