# ⚡ AI-Powered Rural Microgrid Intelligence System
**Team: Data Mavericks | Leader: Shiva Chauhan**

Smart AI energy management for rural villages — solar forecasting, battery optimization, and fair power distribution for homes, clinics, schools, and water pumps.

---

## 🚀 Quick Start (Local Development)

```bash
# 1. Install Python dependencies
cd backend
pip install -r requirements.txt

# 2. Train models (creates .pkl files)
python scripts/train_models.py

# 3. Start backend API
uvicorn app.main:app --reload --port 8000

# 4. Open API docs
# http://localhost:8000/docs

# 5. Start frontend (new terminal)
cd frontend
npm install
npm run dev
# http://localhost:5173
```

---

## 📁 Project Structure

```
ai-microgrid/
├── backend/
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── scripts/train_models.py       # Run this first!
│   └── app/
│       ├── main.py                   # FastAPI app + startup
│       ├── config.py                 # Settings + env vars
│       ├── api/v1/
│       │   ├── forecast.py           # GET /forecast/demand, /solar
│       │   ├── optimize.py           # POST /optimize/allocate
│       │   ├── dashboard.py          # GET /dashboard/stats, WebSocket
│       │   └── alerts.py             # GET /alerts/
│       ├── models/
│       │   ├── demand_forecaster.py  # Unified XGBoost (1 model, all 13 consumers)
│       │   ├── solar_forecaster.py   # Solar XGBoost model
│       │   ├── energy_optimizer.py   # PuLP LP optimizer
│       │   └── saved_models/         # .pkl files saved here (gitignored)
│       ├── schemas/schemas.py        # Pydantic models
│       └── utils/data_generator.py  # Simulation data
├── frontend/
│   ├── src/App.jsx                   # Full React dashboard
│   ├── src/services/api.js           # API calls
│   ├── nginx.conf                    # Production proxy
│   └── Dockerfile
├── sagemaker/
│   ├── train.py                      # SageMaker training script
│   ├── inference.py                  # SageMaker endpoint handler
│   └── launch_training_job.py        # Launch training job from laptop
├── infra/aws/
│   └── deploy.sh                     # EC2 deploy script
├── docker-compose.yml
└── .env.example
```

---

## 🤖 ML Models

### Unified Demand Forecasting Model
- **1 XGBoost model** for all 13 consumers (clinic, school, pump, 10 houses)
- `house_id_encoded` as feature — model learns each consumer's pattern
- **20 features**: cyclic time encoding, lag values, rolling stats, peak flags
- Trained on 120 days × 13 consumers × 24h = ~37,440 rows

### Solar Forecasting Model
- XGBoost model predicting hourly solar generation
- Features: time of day, season, cloud cover, lag values

### Energy Optimizer
- **PuLP Linear Programming** (CBC solver)
- Priority order: 🏥 Clinic → 🏫 School → 💧 Pump → 🏠 Houses
- Maximizes weighted satisfaction, guarantees minimum supply to critical loads
- **Jain's Fairness Index** as equity metric

---

## 🌐 API Endpoints

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/health` | Health check |
| GET | `/docs` | Swagger UI |
| GET | `/api/v1/dashboard/stats` | Live stats |
| GET | `/api/v1/dashboard/24h-profile` | 24h energy chart data |
| GET | `/api/v1/dashboard/house-allocations` | Per-house allocation |
| WS  | `/api/v1/dashboard/ws/realtime` | Live WebSocket stream |
| GET | `/api/v1/forecast/demand` | All-house demand forecast |
| GET | `/api/v1/forecast/solar` | Solar generation forecast |
| GET | `/api/v1/forecast/metrics` | Model accuracy (MAE/RMSE/MAPE) |
| GET | `/api/v1/optimize/simulate` | Simulate optimization now |
| POST| `/api/v1/optimize/allocate` | Run LP optimization |
| GET | `/api/v1/alerts/` | Active system alerts |
| POST| `/api/v1/alerts/sms/test` | Send test SMS (Twilio) |

---

## 🐳 Docker Deployment

```bash
# Copy and configure
cp .env.example .env
# Edit .env with your values

# Build and start
docker-compose build
docker-compose up -d

# View logs
docker-compose logs -f backend

# Check health
curl http://localhost:8000/health
curl http://localhost:80
```

---

## ☁️ AWS Deployment

### Estimated Cost: ~₹660/month
| Service | Cost |
|---------|------|
| EC2 t3.small | ~₹600 |
| S3 ~1GB | ~₹20 |
| SageMaker 10min/week | ~₹40 |

### Steps
1. Create S3 bucket → upload models
2. Create IAM role for SageMaker
3. Launch EC2 (Ubuntu 24.04, t3.small)
4. SSH in → install Docker → clone repo
5. Configure `.env` with S3 bucket name
6. `docker-compose up -d`

See full step-by-step: [AWS Deployment Guide in transcript]

### SageMaker Training
```bash
# Edit sagemaker/launch_training_job.py with your ARN + bucket
python sagemaker/launch_training_job.py
# Takes ~10 min, outputs model.tar.gz to S3
```

---

## 🔧 Troubleshooting

```bash
# Models not loading?
cd backend
python scripts/train_models.py

# Check what models exist
ls -lh app/models/saved_models/

# Start server without training (uses statistical fallback)
uvicorn app.main:app --reload --port 8000

# Docker logs
docker-compose logs backend --tail=50

# Force retrain
python scripts/train_models.py --retrain

# More training data (better accuracy)
python scripts/train_models.py --days 365
```

---

## 📱 SMS Alerts (Twilio)

```bash
# Set in .env
TWILIO_ACCOUNT_SID=ACxxxxx
TWILIO_AUTH_TOKEN=xxxxx
TWILIO_FROM_NUMBER=+1xxxxxxxxxx

# Test
curl -X POST "http://localhost:8000/api/v1/alerts/sms/test?phone=+91XXXXXXXXXX"
```

Example SMS sent to village operator:
> बिजली कम है। क्लिनिक सुरक्षित है। घर 4-10 बंद हैं। Battery 25%.

---

## 👥 Team

**Data Mavericks**
- Leader: Shiva Chauhan
- Hackathon project: AI for Rural India
