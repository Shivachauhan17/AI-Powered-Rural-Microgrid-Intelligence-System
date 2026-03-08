#!/bin/bash
# ============================================================
#  AWS Deployment Script - AI Rural Microgrid System
#  Team: Data Mavericks | Shiva Chauhan
# ============================================================
set -euo pipefail

# ── CONFIG (edit these) ──────────────────────────────────────
AWS_REGION="ap-south-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
CLUSTER_NAME="microgrid-cluster"
SERVICE_NAME="microgrid-service"
BACKEND_REPO="microgrid-backend"
FRONTEND_REPO="microgrid-frontend"

echo "======================================================"
echo "  Deploying AI Microgrid System to AWS ECS"
echo "  Account: $AWS_ACCOUNT_ID  |  Region: $AWS_REGION"
echo "======================================================"

# Step 1: Authenticate Docker to ECR
echo ""
echo "► Step 1: Authenticating with ECR..."
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR_REGISTRY

# Step 2: Create ECR repos if they don't exist
echo "► Step 2: Ensuring ECR repositories exist..."
aws ecr describe-repositories --repository-names $BACKEND_REPO --region $AWS_REGION 2>/dev/null || \
  aws ecr create-repository --repository-name $BACKEND_REPO --region $AWS_REGION

aws ecr describe-repositories --repository-names $FRONTEND_REPO --region $AWS_REGION 2>/dev/null || \
  aws ecr create-repository --repository-name $FRONTEND_REPO --region $AWS_REGION

# Step 3: Build Docker images
echo "► Step 3: Building Docker images..."
docker build -t $BACKEND_REPO ./backend
docker build -t $FRONTEND_REPO ./frontend

# Step 4: Tag and push images
echo "► Step 4: Tagging and pushing images to ECR..."
TAG=$(git rev-parse --short HEAD 2>/dev/null || echo "latest")

docker tag $BACKEND_REPO:latest $ECR_REGISTRY/$BACKEND_REPO:$TAG
docker tag $BACKEND_REPO:latest $ECR_REGISTRY/$BACKEND_REPO:latest
docker push $ECR_REGISTRY/$BACKEND_REPO:$TAG
docker push $ECR_REGISTRY/$BACKEND_REPO:latest

docker tag $FRONTEND_REPO:latest $ECR_REGISTRY/$FRONTEND_REPO:$TAG
docker tag $FRONTEND_REPO:latest $ECR_REGISTRY/$FRONTEND_REPO:latest
docker push $ECR_REGISTRY/$FRONTEND_REPO:$TAG
docker push $ECR_REGISTRY/$FRONTEND_REPO:latest

echo "   ✅ Images pushed: $ECR_REGISTRY/$BACKEND_REPO:$TAG"
echo "   ✅ Images pushed: $ECR_REGISTRY/$FRONTEND_REPO:$TAG"

# Step 5: Update ECS task definition with new image
echo "► Step 5: Updating ECS task definition..."
sed -e "s/YOUR_ACCOUNT_ID/$AWS_ACCOUNT_ID/g" \
    infra/aws/ecs-task-definition.json > /tmp/task-def-updated.json

NEW_TASK_DEF=$(aws ecs register-task-definition \
  --cli-input-json file:///tmp/task-def-updated.json \
  --region $AWS_REGION \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text)

echo "   ✅ New task definition: $NEW_TASK_DEF"

# Step 6: Update ECS service
echo "► Step 6: Deploying to ECS service..."
aws ecs update-service \
  --cluster $CLUSTER_NAME \
  --service $SERVICE_NAME \
  --task-definition $NEW_TASK_DEF \
  --force-new-deployment \
  --region $AWS_REGION

echo "► Step 7: Waiting for deployment to stabilize (2-3 min)..."
aws ecs wait services-stable \
  --cluster $CLUSTER_NAME \
  --services $SERVICE_NAME \
  --region $AWS_REGION

echo ""
echo "======================================================"
echo "  ✅ DEPLOYMENT COMPLETE!"
echo "  Dashboard: Check your ALB DNS in AWS Console"
echo "  API Docs:  <ALB_DNS>/docs"
echo "  Health:    <ALB_DNS>/health"
echo "======================================================"
