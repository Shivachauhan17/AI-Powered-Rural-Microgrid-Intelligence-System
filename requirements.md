# AI-Powered Rural Microgrid Intelligence System
Team: Data Mavericks  
Team Leader: Shiva Chauhan  

---

## 1. Problem Statement

Rural solar microgrids face operational inefficiencies due to:

- Unpredictable solar energy generation
- Variable household electricity demand
- Inefficient battery usage
- Lack of intelligent energy allocation
- No fairness-based distribution mechanism

These issues lead to blackouts, energy wastage, reduced battery lifespan, and economic loss.

The goal is to build an AI-powered intelligent energy planning and allocation system.

---

## 2. Objectives

- Predict next-day hourly electricity demand per household.
- Predict solar energy generation.
- Optimize battery charge-discharge cycles.
- Allocate energy fairly with priority constraints.
- Reduce blackout duration.
- Improve overall system efficiency.

---

## 3. Scope of the System

The system will:

- Operate for small rural microgrids (5–50 households).
- Support critical infrastructure prioritization (clinic, school, irrigation).
- Work in low-bandwidth environments.
- Provide operator dashboard and SMS alerts.

---

## 4. Functional Requirements

### 4.1 Data Collection
- Collect smart meter data (energy usage per household).
- Collect weather data (temperature, irradiance).
- Collect solar inverter generation data.

### 4.2 Forecasting
- Predict next-day hourly demand per household.
- Predict next-day solar energy generation.
- Estimate uncertainty bounds in predictions.

### 4.3 Optimization & Allocation
- Ensure minimum guaranteed energy per household.
- Prioritize critical infrastructure.
- Optimize battery utilization.
- Reduce unmet demand.
- Enable load scheduling.

### 4.4 Control & Communication
- Send allocation schedule to control system.
- Generate SMS alerts in local languages.
- Provide operator dashboard.

---

## 5. Non-Functional Requirements

### Performance
- Forecast generation within 5 minutes.
- Allocation computation within 2 minutes.
- Support up to 100 households.

### Reliability
- 99% uptime for backend services.
- Edge processing fallback for internet outages.

### Scalability
- Cloud-ready and horizontally scalable.
- Modular microservice architecture.

### Security
- Encrypted MQTT communication.
- Role-based access control for dashboard.

### Fairness
- Minimum energy guarantee for all households.
- Fairness index monitoring.

---

## 6. Constraints

- Limited internet connectivity in rural areas.
- Low-cost hardware requirement.
- Budget-sensitive deployment.
- Data availability may initially be limited.

---

## 7. Assumptions

- Smart meters are installed in each household.
- Solar inverter provides real-time generation data.
- Basic operator training available.

---

## 8. Success Metrics

- Reduction in blackout duration (%).
- Reduction in unmet demand (%).
- Improvement in battery lifespan.
- Forecast MAE and RMSE.
- Fairness index score.
