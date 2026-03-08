# ⚡ AI-Powered Rural Microgrid Intelligence System

> **Team Data Mavericks** · Shiva Chauhan  
> Hackathon Prototype → Production-Ready System

## What This System Does

This system solves the **rural energy crisis** by intelligently managing solar microgrids:

| Problem | Our Solution |
|---------|-------------|
| Unpredictable solar energy | XGBoost weather-aware solar forecast |
| Blackouts from demand spikes | Next-day hourly demand forecasting per house |
| Unfair energy distribution | LP optimization with Jain's Fairness Index |
| Critical infra going dark | Priority allocation (Clinic > School > Pump > Houses) |
| Operator has no visibility | Real-time React dashboard with WebSocket |
| Rural operators miss alerts | SMS notifications via Twilio |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    AWS Infrastructure                    │
│                                                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────────────────┐ │
│  │  Route53  │──▶│   ALB    │──▶│    ECS Fargate       │ │
│  └──────────┘   └──────────┘   │  ┌────────────────┐  │ │
│                                │  │  React Frontend │  │ │
│  ┌──────────┐                  │  │  (Nginx:80)     │  │ │
│  │ IoT Core │──MQTT──────────▶ │  ├────────────────┤  │ │
│  └──────────┘                  │  │ FastAPI Backend │  │ │
│                                │  │  (Uvicorn:8000) │  │ │
│  ┌──────────┐                  │  └────────────────┘  │ │
│  │    S3    │◀───model data ───│                      │ │
│  └──────────┘                  └──────────────────────┘ │
│                                                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────────────────┐ │
│  │ElastiCache│  │ CloudWatch│  │   Secrets Manager    │ │
│  │  Redis   │  │  Logs     │  │  (API keys, tokens)  │ │
│  └──────────┘   └──────────┘   └──────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## Quick Start (Local)

### Prerequisites
- Docker + Docker Compose
- Python 3.11+ (for local backend dev)
- Node.js 20+ (for local frontend dev)

### Run with Docker (Recommended)

```bash
# Clone the repo
git clone https://github.com/Shivachauhan17/AI-Powered-Rural-Microgrid-Intelligence-System.git
cd AI-Powered-Rural-Microgrid-Intelligence-System

# Copy env file and configure
cp .env.example .env

# Build and run everything
docker compose up --build

# Open in browser
# Dashboard:  http://localhost:80
# API Docs:   http://localhost:8000/docs
# Health:     http://localhost:8000/health
```

### Run Backend Locally (Dev)

```bash
cd backend
pip install -r requirements.txt

# ── STEP 1: Train and save models (run ONCE) ──────────────────────────────
python scripts/train_models.py
# Output: saves 14 .joblib files to app/models/saved_models/
# Takes ~60-90 seconds. After this, server starts in under 5 seconds.

# ── STEP 2: Start the API server ──────────────────────────────────────────
uvicorn app.main:app --reload --port 8000
# On startup: loads models from disk (not re-trains)

# Visit: http://localhost:8000/docs
```

### Run Frontend Locally (Dev)

```bash
cd frontend
npm install
npm run dev

# Visit: http://localhost:5173
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/forecast/demand` | All-house demand forecast (24h) |
| GET | `/api/v1/forecast/demand/{house_id}` | Single house demand forecast |
| GET | `/api/v1/forecast/solar` | Solar generation forecast |
| GET | `/api/v1/forecast/metrics` | Model accuracy (MAE, RMSE, MAPE) |
| POST | `/api/v1/optimize/allocate` | Run LP energy optimization |
| GET | `/api/v1/optimize/simulate` | Simulate optimization (current conditions) |
| GET | `/api/v1/dashboard/stats` | Live system statistics |
| GET | `/api/v1/dashboard/24h-profile` | Full 24h energy profile |
| GET | `/api/v1/dashboard/house-allocations` | Per-house allocation status |
| WS | `/api/v1/dashboard/ws/realtime` | WebSocket live feed (5s interval) |
| GET | `/api/v1/alerts/` | Active system alerts |
| POST | `/api/v1/alerts/sms/test` | Send test SMS via Twilio |

---

## AWS Deployment (Step by Step)

### Step 1: Prerequisites

```bash
# Install AWS CLI
curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"
sudo installer -pkg AWSCLIV2.pkg -target /

# Configure AWS credentials
aws configure
# Enter: AWS Access Key ID, Secret, Region (ap-south-1), Output (json)
```

### Step 2: Create AWS Infrastructure

```bash
# Create ECS Cluster
aws ecs create-cluster --cluster-name microgrid-cluster --region ap-south-1

# Create CloudWatch log groups
aws logs create-log-group --log-group-name /ecs/microgrid-backend --region ap-south-1
aws logs create-log-group --log-group-name /ecs/microgrid-frontend --region ap-south-1

# Create Secrets Manager entries
aws secretsmanager create-secret \
  --name microgrid/secret-key \
  --secret-string "$(openssl rand -hex 32)" \
  --region ap-south-1
```

### Step 3: Create Application Load Balancer

```bash
# In AWS Console:
# 1. Go to EC2 → Load Balancers → Create Load Balancer
# 2. Choose "Application Load Balancer"
# 3. Add listeners: HTTP:80 and HTTPS:443
# 4. Create Target Group for ECS service
# 5. Note the ALB DNS name
```

### Step 4: Deploy

```bash
# Make deploy script executable
chmod +x infra/aws/deploy.sh

# Run deployment (builds, pushes to ECR, deploys to ECS)
./infra/aws/deploy.sh
```

### Step 5: Verify

```bash
# Get ALB DNS name
aws elbv2 describe-load-balancers --names microgrid-alb --query 'LoadBalancers[0].DNSName' --output text

# Visit: http://<ALB_DNS_NAME>
```

---

## Environment Variables

```bash
# Backend (.env)
SECRET_KEY=your-secret-key-here
DEBUG=false
SOLAR_CAPACITY_KW=30.0
BATTERY_CAPACITY_KWH=50.0
TOTAL_HOUSES=10

# AWS
AWS_REGION=ap-south-1
AWS_S3_BUCKET=microgrid-data

# Twilio SMS (optional)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_FROM_NUMBER=+1234567890

# Redis
REDIS_URL=redis://localhost:6379/0
```

---

## System Metrics

| Metric | Value |
|--------|-------|
| Demand Forecast MAE | ~0.08 kW |
| Forecast Accuracy | ~94% |
| Fairness Index (Jain's) | 0.88–0.95 |
| Optimization solve time | < 100ms |
| API response time | < 200ms |
| Blackout reduction | 30–50% |

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| ML Forecasting | XGBoost, scikit-learn, numpy |
| Optimization | PuLP (CBC solver), OR-Tools |
| Backend | Python 3.11, FastAPI, uvicorn |
| Messaging | MQTT (aiomqtt), WebSocket |
| Frontend | React 18, Recharts, Vite |
| Caching | Redis |
| Monitoring | Prometheus, CloudWatch |
| Containers | Docker, AWS ECS Fargate |
| Load Balancing | AWS ALB |
| Secrets | AWS Secrets Manager |
| Storage | AWS S3 |
| IoT | AWS IoT Core (ESP32 integration) |
| SMS | Twilio |

---

## Team

**Data Mavericks**  
Team Leader: Shiva Chauhan
