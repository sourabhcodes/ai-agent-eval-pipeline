# Docker & Orchestration Files Reference

## 📦 Docker Files

### Dockerfile (FastAPI Application)
**Purpose:** Production-ready FastAPI application container

**Features:**
- Python 3.11 slim base image (optimize for size)
- System dependencies: gcc, postgresql-client, curl
- Gunicorn + Uvicorn for production ASGI
- 4 worker processes for concurrent requests
- Health check endpoint monitoring
- Non-root user (appuser) for security
- Max requests: 1000 (worker recycling)
- Timeout: 60 seconds

**Build:**
```bash
docker build -f Dockerfile -t eval-pipeline-api:latest .
```

**Run:**
```bash
docker run -p 8000:8000 \
  -e DATABASE_URL="postgresql://..." \
  -e REDIS_URL="redis://..." \
  eval-pipeline-api:latest
```

**Health Check:**
Automatic health checks every 30 seconds via `GET /health`

---

### worker.dockerfile (Celery Worker)
**Purpose:** Background task processing for evaluations

**Features:**
- Same base image as API (consistency)
- Celery worker configuration
- 4 worker concurrency (processes)
- Dual queue support: evaluation + analysis
- Max tasks per child: 1000 (prevents memory leaks)
- Hard time limit: 1800 seconds (30 min)
- Soft time limit: 1500 seconds (graceful shutdown)
- Health check via Celery ping

**Build:**
```bash
docker build -f worker.dockerfile -t eval-pipeline-worker:latest .
```

**Run:**
```bash
docker run \
  -e DATABASE_URL="postgresql://..." \
  -e REDIS_URL="redis://..." \
  eval-pipeline-worker:latest
```

**Scaling:**
```bash
# Run multiple workers
for i in {1..10}; do
  docker run -d --name worker_$i \
    -e DATABASE_URL="postgresql://..." \
    -e REDIS_URL="redis://..." \
    eval-pipeline-worker:latest
done
```

---

## 🎯 Orchestration Configurations

### render.yaml (Render.com)
**Purpose:** One-click deployment to Render.com PaaS platform

**Services Defined:**
1. **eval-pipeline-postgres** (Database)
   - Type: PostgreSQL 15
   - Plan: Starter ($15/mo)
   - Persistent volume: postgres_data
   - Health checks enabled

2. **eval-pipeline-redis** (Cache/Broker)
   - Type: Redis 7
   - Plan: Starter ($15/mo)
   - Persistent volume: redis_data

3. **eval-pipeline-api** (Web Service)
   - Type: Docker
   - Dockerfile: ./Dockerfile
   - Plan: Starter ($7/mo)
   - Workers: 4 (uvicorn)
   - Port: 8000 (exposed)
   - Health checks enabled
   - Auto-deploy on Git push

4. **eval-pipeline-worker** (Background Task 1)
   - Type: Background Service
   - Dockerfile: ./worker.dockerfile
   - Concurrency: 4
   - Queue: evaluation, analysis

5. **eval-pipeline-beat** (Background Task 2)
   - Type: Background Service
   - Dockerfile: ./worker.dockerfile
   - Purpose: Schedule periodic analyses

**Deployment:**
```bash
# Connect GitHub repo to Render
# Click "Blueprint" → Select repo → "Deploy"
# Configure variables: POSTGRES_PASSWORD, OPENAI_API_KEY
# Services auto-provision in ~5-10 minutes
```

**Environment Variables:**
- `DATABASE_URL`: Auto-generated from PostgreSQL service
- `REDIS_URL`: Auto-generated from Redis service
- `OPENAI_API_KEY`: User-provided (for LLM-as-Judge)
- `ENVIRONMENT`: production
- `LOG_LEVEL`: INFO

---

### railway.json (Railway.app)
**Purpose:** One-click deployment to Railway.app PaaS platform

**Services Defined:**
1. **postgres** (Database)
   - Image: postgres:15-alpine
   - Database: eval_pipeline
   - Persistent volume
   - Health checks

2. **redis** (Cache/Broker)
   - Image: redis:7-alpine
   - Persistent volume
   - Health checks

3. **api** (FastAPI Service)
   - Build: ./Dockerfile
   - Port: 8000 (HTTP)
   - Health checks
   - Depends on: postgres, redis
   - Always restart

4. **worker** (Celery Worker)
   - Build: ./worker.dockerfile
   - Scale: 2 instances (configurable)
   - Depends on: postgres, redis

5. **beat** (Celery Beat Scheduler)
   - Build: ./worker.dockerfile
   - Scale: 1 instance
   - Depends on: postgres, redis

**Deployment:**
```bash
# Push code to GitHub
git push origin main

# Railway auto-detects railway.json
# Or manually import on Railway Dashboard:
# 1. Create project
# 2. Connect GitHub repo
# 3. Railway builds and deploys automatically
```

**Environment Variables:**
```
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
OPENAI_API_KEY=your_api_key
ENVIRONMENT=production
PYTHONUNBUFFERED=1
```

---

## 🔄 Service Dependencies

### Startup Order
```
1. PostgreSQL (database must be ready first)
2. Redis (message broker)
3. FastAPI (API service)
4. Celery Worker (depends on Redis for task queue)
5. Celery Beat (depends on Postgres for scheduling)
```

### Health Check Flow
```
API Health: GET /health
  ├─ Check PostgreSQL connection
  ├─ Check Redis connection
  └─ Return 200 if both OK

Worker Health: celery inspect ping
  ├─ Check Redis connectivity
  └─ Return pong if responsive

Beat Health: Process running
  └─ Verify task scheduling
```

---

## 📊 Resource Allocation

### Render Starter Tier
- **FastAPI API**: 512MB RAM, 0.5 CPU
- **Celery Worker**: 512MB RAM, 0.5 CPU (per instance)
- **Celery Beat**: 512MB RAM, 0.5 CPU
- **PostgreSQL**: 1GB disk, 512MB RAM
- **Redis**: 1GB disk, 512MB RAM

### Railway Starter Tier
- **API Service**: 512MB RAM
- **Worker Service**: 512MB RAM (per instance)
- **Beat Service**: 512MB RAM
- **PostgreSQL**: 5GB disk
- **Redis**: 1GB disk

### Estimated Monthly Costs
| Platform | PostgreSQL | Redis | API | 2x Workers | Beat | Total |
|----------|-----------|-------|-----|-----------|------|-------|
| **Render** | $15 | $15 | $7 | $14 | $7 | **$58** |
| **Railway** | $15 | $10 | $5 | $10 | $5 | **$45** |

---

## 🚀 Local Development vs Production

### Local (docker-compose.yml)
```yaml
- FastAPI: uvicorn (development server, auto-reload)
- Celery: single worker, verbosity level debug
- Workers: 1-2 for testing
```

### Production (Dockerfile + render.yaml)
```yaml
- FastAPI: Gunicorn + Uvicorn (ASGI server, multiple workers)
- Celery: optimized worker pool, production settings
- Workers: 2-10 depending on load
- Health checks: enabled and monitored
- Auto-restart: on failure
- Auto-deploy: on Git push
```

---

## 🔧 Customization Guide

### Scaling Workers
**Render:**
```yaml
# In render.yaml, under worker service:
scale: 5  # 5 worker instances
```

**Railway:**
```json
"worker": {
  "scale": 5
}
```

### Changing Concurrency
**In worker.dockerfile:**
```dockerfile
# Current: 4 concurrent tasks per worker
CMD ["celery", "-A", "app.celery", "worker", \
     "--concurrency=4", ...]

# Change to 8 for more throughput (higher memory)
# Or 2 for lower resource usage
```

### Adjusting Worker Tasks
**In worker.dockerfile:**
```dockerfile
# Max tasks before recycling worker
"--max-tasks-per-child=1000"  # Current
"--max-tasks-per-child=500"   # More aggressive recycling
"--max-tasks-per-child=5000"  # Less recycling
```

---

## 🐛 Debugging Deployments

### View Logs
**Render:**
```
Dashboard → Service → Logs → View real-time logs
```

**Railway:**
```
Dashboard → Service → Logs → Search and filter
```

### Check Health
```bash
# Test API health
curl https://eval-pipeline-api.onrender.com/health

# Check worker status
celery -A app.celery inspect ping

# Monitor active tasks
celery -A app.celery inspect active
```

### Database Connection
```bash
# Test PostgreSQL connection
psql $DATABASE_URL -c "SELECT 1"

# Query data
SELECT COUNT(*) FROM conversations;
SELECT COUNT(*) FROM evaluations;
```

### Redis Connection
```bash
# Test Redis connection
redis-cli -u $REDIS_URL ping

# Check queued tasks
redis-cli -u $REDIS_URL LLEN celery
```

---

## 📈 Monitoring & Alerts

### Render Monitoring
- CPU usage
- Memory usage
- Disk usage
- Request count
- Error rate
- Response time

**Set Alerts:**
1. Go to Service → Settings → Notifications
2. Add email/Slack for failures
3. Set thresholds

### Railway Monitoring
- CPU usage
- Memory usage
- Disk usage
- Network I/O
- Deployment history

**Set Alerts:**
1. Go to Project Settings → Alerts
2. Configure webhook or email
3. Set alert conditions

---

## 🔐 Security Considerations

### Docker Image Security
- ✅ Non-root user (appuser)
- ✅ Minimal base image (python:3.11-slim)
- ✅ Removed build dependencies
- ✅ No secrets in image

### Secrets Management
- ✅ Environment variables for secrets
- ✅ Never commit .env files
- ✅ Use platform-provided secret managers
- ✅ Rotate credentials regularly

### Network Security
- ✅ HTTPS enforced (automatic on Render/Railway)
- ✅ Services in private VPC
- ✅ Database restricted to app access
- ✅ Redis only accessible internally

---

## 📚 File Reference

### Docker-related Files
```
├── Dockerfile              # FastAPI production image
├── worker.dockerfile       # Celery worker image
└── .dockerignore          # Exclude unnecessary files from build
```

### Orchestration Files
```
├── render.yaml            # Render.com deployment config
├── railway.json           # Railway.app deployment config
└── docker-compose.yml     # Local development (included in root)
```

### Configuration Files
```
├── requirements.txt       # Python dependencies
├── .env.example          # Environment template
└── app/celery.py         # Celery configuration
```

---

## ✅ Deployment Checklist

Before deploying to production:

- [ ] Update requirements.txt with all dependencies
- [ ] Set strong passwords for PostgreSQL
- [ ] Generate OpenAI API key
- [ ] Review environment variables
- [ ] Test locally with docker-compose
- [ ] Push code to GitHub
- [ ] Connect platform (Render/Railway)
- [ ] Configure environment variables
- [ ] Deploy services
- [ ] Verify all services are healthy
- [ ] Test API endpoints
- [ ] Check logs for errors
- [ ] Monitor for 24 hours
- [ ] Set up alerts
- [ ] Document configuration

---

**Last Updated:** April 17, 2026
