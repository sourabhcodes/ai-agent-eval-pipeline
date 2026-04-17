# Deployment Quick Start

Choose your deployment platform and follow the steps below.

## 🎯 Quick Decision

### Choose Render if:
- ✅ You want the simplest setup (Blueprint auto-detects render.yaml)
- ✅ You prefer automatic health checks and restarts
- ✅ You want native PostgreSQL and Redis services
- ✅ Budget: ~$58/month for starter tier

### Choose Railway if:
- ✅ You want lower costs (~$45/month)
- ✅ You prefer Docker-based flexibility
- ✅ You want better service scaling controls
- ✅ You like the Railway CLI interface

---

## 🚀 Deploy in 5 Minutes

### **For Render:**

```bash
# 1. Push code to GitHub
git push origin main

# 2. Go to https://dashboard.render.com
# 3. Click "New" → "Blueprint"
# 4. Select your repository
# 5. Set environment variables:
#    - POSTGRES_PASSWORD: (generate strong password)
#    - OPENAI_API_KEY: (your key from OpenAI)
# 6. Click "Deploy"
# 7. Wait ~5-10 minutes for services to provision

# 8. Test (get URL from dashboard)
curl https://eval-pipeline-api.onrender.com/health
```

### **For Railway:**

```bash
# 1. Push code to GitHub
git push origin main

# 2. Go to https://railway.app
# 3. Click "New Project" → "Deploy from GitHub repo"
# 4. Select your repository
# 5. Railway auto-detects railway.json
# 6. Set environment variables:
#    - POSTGRES_PASSWORD: (generate strong password)
#    - OPENAI_API_KEY: (your key from OpenAI)
# 7. Click "Deploy"
# 8. Wait ~3-5 minutes for services to provision

# 9. Test (get URL from dashboard)
curl https://your-railway-app.up.railway.app/health
```

---

## 📋 File Overview

| File | Platform | Purpose |
|------|----------|---------|
| `Dockerfile` | Both | FastAPI production image |
| `worker.dockerfile` | Both | Celery worker image |
| `render.yaml` | Render | One-click deployment config |
| `railway.json` | Railway | One-click deployment config |

---

## 🔧 What Gets Deployed

### Services
1. **PostgreSQL Database** - Stores conversations, evaluations, feedback
2. **Redis Cache** - Message broker for Celery tasks
3. **FastAPI API** - Ingestion & suggestion endpoints (port 8000)
4. **Celery Worker** - Processes evaluations asynchronously
5. **Celery Beat** - Schedules hourly/daily analyses

### Network
- All services communicate privately (same VPC)
- Only API exposed publicly (HTTPS)
- Database and Redis internal-only access

---

## 📊 Architecture Deployed

```
Public Internet
    ↓
HTTPS Load Balancer
    ↓
FastAPI (port 8000)
    ├─→ PostgreSQL (internal)
    ├─→ Redis (internal)
    └─→ Celery Worker → PostgreSQL, Redis
```

---

## ✅ Verify Deployment

Once deployed, test these endpoints:

```bash
API_URL="https://your-deployed-url.com"  # Get from dashboard

# 1. Health check
curl $API_URL/health

# 2. Ingest a conversation
curl -X POST "$API_URL/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "agent_id": "agent_v1",
    "turns": [
      {"role": "user", "content": "Hello"},
      {"role": "assistant", "content": "Hi there!"}
    ]
  }'

# 3. Get suggestions (wait 1-2 minutes for evaluation)
curl "$API_URL/suggestions?min_confidence=0.7&limit=5"

# 4. View conversation
# Replace CONV_ID with the id from step 2
curl "$API_URL/conversation/CONV_ID"
```

---

## 🐛 If Something Goes Wrong

### Service won't start
1. Check logs in platform dashboard
2. Verify DATABASE_URL environment variable
3. Ensure PostgreSQL is healthy
4. Check for typos in config files

### Celery tasks not running
1. Check Redis connection: `redis-cli -u $REDIS_URL ping`
2. Check worker logs: look for connection errors
3. Restart worker service in dashboard

### High latency
1. Check CPU/Memory usage in dashboard
2. Increase resource tier if needed
3. Check database query performance

### Database connection error
1. Verify DATABASE_URL is set correctly
2. Check PostgreSQL service is running
3. Ensure API can reach database (same network)

---

## 💰 Expected Costs

### First Month
- PostgreSQL setup: $0 (usually free trial)
- Redis setup: $0 (usually free trial)
- Compute services: $5-10/month (partial month)
- **Total: $5-20**

### Ongoing Monthly
**Render:**
- PostgreSQL: $15
- Redis: $15
- FastAPI: $7
- Worker (2x): $14
- Beat: $7
- **Total: $58**

**Railway:**
- PostgreSQL: $15
- Redis: $10
- FastAPI: $5
- Workers (2x): $10
- Beat: $5
- **Total: $45**

---

## 📈 Scaling After Deployment

### Add More Workers (Render)
1. Go to dashboard → eval-pipeline-worker service
2. Click "Settings" → "Instances"
3. Increase count (e.g., 2 → 5)
4. Service auto-scales

### Add More Workers (Railway)
1. Go to dashboard → worker service
2. Adjust CPU/Memory allocation
3. Or run: `railway scale worker=5`

### Upgrade Database
1. Go to database service
2. Change plan to "Pro" or higher
3. Automatic upgrade (minimal downtime)

---

## 🎓 Learning Resources

- **Render Docs:** https://render.com/docs
- **Railway Docs:** https://docs.railway.app
- **FastAPI:** https://fastapi.tiangolo.com
- **Celery:** https://docs.celeryproject.io
- **Docker:** https://docs.docker.com

---

## 📞 Support

### Common Issues
See [DEPLOY.md](DEPLOY.md) for:
- Detailed troubleshooting guide
- Monitoring setup
- Performance tuning
- Security best practices

### Docker Reference
See [DOCKER_REFERENCE.md](DOCKER_REFERENCE.md) for:
- Dockerfile details
- Image customization
- Build optimizations
- Local testing

### Full Documentation
See [README.md](README.md) for:
- Project overview
- Architecture
- Scaling strategy
- Flywheel effect

---

## 🎉 Success!

Once deployed:
1. ✅ API is live at `https://your-url/`
2. ✅ Dashboard available (run: `streamlit run dashboard.py`)
3. ✅ Workers processing evaluations
4. ✅ Suggestions generated hourly
5. ✅ System ready to handle 1000+/min conversations

**Next steps:**
- [ ] Configure custom domain
- [ ] Set up monitoring/alerts
- [ ] Run test scenarios to verify
- [ ] Load test with realistic data
- [ ] Scale up for production

---

**Ready to deploy? Start with your chosen platform above! 🚀**

Last Updated: April 17, 2026
