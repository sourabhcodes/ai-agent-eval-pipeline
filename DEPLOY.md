# Deployment Guide: Render & Railway

## 🚀 Option 1: Deploy to Render

### Prerequisites
- Render account (https://render.com)
- GitHub repository with this code pushed
- OpenAI API key

### Step-by-Step Deployment

#### 1. Connect GitHub Repository
```
1. Go to Render Dashboard: https://dashboard.render.com
2. Click "New" → "Blueprint"
3. Authorize GitHub access
4. Select your repository
5. Click "Connect"
```

#### 2. Configure Environment Variables
```
1. In Render Dashboard, go to Environment
2. Add these variables:
   - POSTGRES_PASSWORD: (generate strong password)
   - OPENAI_API_KEY: (your OpenAI API key)
   - BRANCH: main (or your branch)
   - REPO_URL: (your GitHub repo URL)
```

#### 3. Deploy
```
1. Click "Deploy Blueprint"
2. Wait for services to provision (~5-10 minutes)
   - PostgreSQL database created
   - Redis cache initialized
   - FastAPI service deployed (may take 2-3 min)
   - Celery worker started
   - Celery Beat scheduler started
```

#### 4. Verify Deployment
```bash
# Get your API URL from Render Dashboard
API_URL="https://eval-pipeline-api.onrender.com"

# Test health endpoint
curl $API_URL/health

# Test ingestion
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

# Check suggestions (after a few minutes)
curl "$API_URL/suggestions?min_confidence=0.7&limit=5"
```

#### 5. Access Dashboard
```
1. From Render Dashboard, find your Streamlit service
2. Or run locally: streamlit run dashboard.py
3. Configure to connect to remote database:
   export DATABASE_URL="postgresql://..."
   streamlit run dashboard.py
```

### Render Service Types
- **Web Service**: FastAPI (port 8000)
- **Background Service**: Celery Worker & Beat
- **PostgreSQL Service**: Database
- **Redis Service**: Message Broker

### Render Pricing Estimate
- PostgreSQL: $15/month (starter)
- Redis: $15/month (starter)
- FastAPI Web: $7/month (starter - always on)
- Celery Worker (2x): $14/month ($7 each)
- Celery Beat: $7/month
- **Total: ~$58/month** (for starter tier)

### Render Advanced Features
- Auto-deploy on Git push (enabled in render.yaml)
- Health checks configured (30s intervals)
- Automatic restarts on failure
- Environment variable management
- Service dependencies configured

---

## 🚂 Option 2: Deploy to Railway

### Prerequisites
- Railway account (https://railway.app)
- GitHub repository with this code
- OpenAI API key

### Step-by-Step Deployment

#### 1. Create Railway Project
```
1. Go to Railway Dashboard: https://railway.app
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Authorize GitHub and select your repository
```

#### 2. Add Services Using railway.json

**Option A: Automatic (Recommended)**
```
1. Railway will auto-detect railway.json
2. Click "Deploy"
3. Services will be provisioned automatically
```

**Option B: Manual**
```
1. Create New Service
2. Select "Database" → PostgreSQL
   - Name: postgres
   - Database: eval_pipeline
3. Create New Service
   - Select "Add Service" → "Redis"
   - Name: redis
4. Create New Service
   - Select "Deploy from GitHub"
   - Name: api
   - Dockerfile: ./Dockerfile
5. Create New Service
   - Select "Deploy from GitHub"
   - Name: worker
   - Dockerfile: ./worker.dockerfile
6. Create New Service
   - Select "Deploy from GitHub"
   - Name: beat
   - Dockerfile: ./worker.dockerfile
```

#### 3. Configure Environment Variables
```
1. In each service, go to "Variables"
2. Add:
   - DATABASE_URL: ${{Postgres.DATABASE_URL}}
   - REDIS_URL: ${{Redis.REDIS_URL}}
   - OPENAI_API_KEY: (your API key)
   - ENVIRONMENT: production
   - LOG_LEVEL: INFO
```

#### 4. Deploy
```
1. Click "Deploy"
2. Monitor deployment logs:
   - API service should start on port 8000
   - Worker services should connect to Redis
   - Beat scheduler should start
3. Wait for all services to be healthy (~3-5 minutes)
```

#### 5. Verify Deployment
```bash
# Get your API URL from Railway Dashboard
API_URL="https://your-railway-app.up.railway.app"

# Test health
curl $API_URL/health

# Create test conversation
curl -X POST "$API_URL/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "agent_id": "agent_v1",
    "title": "Test",
    "turns": [
      {"role": "user", "content": "Test query"},
      {"role": "assistant", "content": "Test response"}
    ]
  }'

# Get suggestions
curl "$API_URL/suggestions"
```

### Railway Service Configuration
- **API Service**: Runs Gunicorn + Uvicorn (FastAPI)
- **Worker Services**: 2 instances of Celery worker
- **Beat Service**: 1 instance of Celery Beat
- **PostgreSQL**: Managed database
- **Redis**: Managed cache

### Railway Pricing Estimate
- PostgreSQL: $15/month (5GB)
- Redis: $10/month (1GB)
- FastAPI Web: $5/month (512MB)
- Worker (2x): $10/month ($5 each)
- Beat: $5/month
- **Total: ~$45/month**

### Railway Advanced Features
- Auto-deploy on Git push
- Service scaling (adjust resource allocation)
- Environment variables per service
- Public/private networking
- Log streaming and monitoring
- Backup and restore capabilities

---

## 📋 Deployment Comparison

| Feature | Render | Railway |
|---------|--------|---------|
| **Setup Time** | ~10 min | ~10 min |
| **Monthly Cost** | $58 | $45 |
| **Auto-deploy** | ✅ Yes | ✅ Yes |
| **Scaling** | Manual | ✅ Easy |
| **Health Checks** | ✅ Built-in | ✅ Built-in |
| **Log Streaming** | ✅ Yes | ✅ Yes |
| **CLI Available** | ✅ Yes | ✅ Yes |
| **Custom Domain** | ✅ Yes | ✅ Yes |
| **Support** | Good | Excellent |

---

## 🔧 Common Deployment Issues

### PostgreSQL Connection Error
**Problem:** `could not connect to server`

**Solution:**
1. Verify DATABASE_URL environment variable
2. Check PostgreSQL service is healthy in dashboard
3. Ensure API/Worker can reach database (same VPC)
4. Try: `psql $DATABASE_URL -c "SELECT 1"`

### Redis Connection Error
**Problem:** `Connection refused` on Redis port

**Solution:**
1. Verify REDIS_URL environment variable
2. Check Redis service is running
3. Ensure worker can reach Redis (same network)
4. Try: `redis-cli -u $REDIS_URL ping`

### Celery Tasks Not Running
**Problem:** Tasks queued but not executed

**Solution:**
1. Check worker service is running: `celery -A app.celery inspect active`
2. Check Redis connection: `redis-cli PING`
3. Check logs for errors
4. Restart worker service

### FastAPI Service Timeout
**Problem:** HTTP 504 Gateway Timeout

**Solution:**
1. Check service logs for errors
2. Ensure database can handle connections
3. Increase timeout in Gunicorn config
4. Scale up resources in dashboard

### High Memory Usage
**Problem:** Service killed due to memory limit

**Solution:**
1. Reduce Celery concurrency: `-c 2` (instead of 4)
2. Limit max tasks per worker: `--max-tasks-per-child 500`
3. Upgrade service tier in dashboard
4. Check for memory leaks in code

---

## 📊 Monitoring & Debugging

### Render Monitoring
```
1. Dashboard → Service → Logs
2. View real-time logs for each service
3. Monitor CPU/Memory usage
4. Check deployment history
```

### Railway Monitoring
```
1. Dashboard → Service → Logs
2. View logs with search/filter
3. Monitor Metrics tab (CPU, Memory, Disk)
4. Check Deployments for rollback options
```

### Remote Database Debugging
```bash
# Connect to remote PostgreSQL
psql $DATABASE_URL

# Query evaluations
SELECT id, conversation_id, evaluator_type, score FROM evaluations LIMIT 10;

# Check conversations
SELECT id, user_id, agent_id, created_at FROM conversations LIMIT 10;

# Monitor Redis
redis-cli -u $REDIS_URL
> KEYS *
> GET celery-task-meta-*
```

### Celery Monitoring
```bash
# Check active tasks
celery -A app.celery inspect active

# Check queue length
celery -A app.celery inspect active_queues

# Monitor in real-time
celery -A app.celery events

# Check worker status
celery -A app.celery inspect ping
```

---

## 🔐 Security Best Practices

### Environment Variables
- ✅ Store API keys in secure environment variables
- ✅ Don't commit .env files to Git
- ✅ Use strong PostgreSQL passwords
- ✅ Rotate credentials regularly

### Network Security
- ✅ Use HTTPS for all API endpoints (automatic on Render/Railway)
- ✅ Limit database access to application servers only
- ✅ Use private networking between services
- ✅ Enable PostgreSQL SSL connections

### Application Security
- ✅ Enable CORS only for trusted domains
- ✅ Add rate limiting to /ingest endpoint
- ✅ Validate all input data
- ✅ Use Pydantic schemas for validation

### Database Security
- ✅ Regular backups enabled (check dashboard)
- ✅ Restrict database user permissions
- ✅ Use parameterized queries (SQLAlchemy does this)
- ✅ Monitor for unusual access patterns

---

## 📈 Scaling Strategy

### Vertical Scaling (Single Tier)
- Increase CPU/Memory in dashboard
- Suitable for: Development, testing

### Horizontal Scaling (Multiple Workers)
```
1. In railway.json or render.yaml: Set scale: 2 (or higher)
2. Workers will load-balance automatically
3. Each worker handles 4 concurrent Celery tasks
4. Max throughput: N_workers × 4 × 15 evals/sec
```

### Example: Scaling to 1000+ conv/sec
```
- 4x FastAPI instances (load balanced)
- 10x Celery workers (2 per instance)
- PostgreSQL: Premium tier (50+ connections)
- Redis: Cluster mode (10GB+)
```

---

## 🎯 Performance Tuning

### FastAPI Optimization
```python
# In main.py (already configured)
- Workers: 4 per instance
- Max requests: 1000 (recycle workers)
- Timeout: 60 seconds
```

### Celery Optimization
```bash
# In worker.dockerfile (already configured)
- Concurrency: 4
- Time limit: 1800 seconds (30 min)
- Soft limit: 1500 seconds
- Max tasks: 1000 per child
```

### Database Optimization
```sql
-- Create indexes (auto-created in models.py)
CREATE INDEX idx_user_id_created_at ON conversations(user_id, created_at);
CREATE INDEX idx_conversation_evaluator ON evaluations(conversation_id, evaluator_type);
```

---

## 🚀 Post-Deployment Checklist

- [ ] Verify all services are healthy in dashboard
- [ ] Test /health endpoint
- [ ] Send test conversation via /ingest
- [ ] Check suggestions appear after 1-2 minutes
- [ ] Access dashboard (Streamlit)
- [ ] Monitor logs for errors
- [ ] Set up alerts for service failures
- [ ] Configure custom domain (optional)
- [ ] Enable HTTPS (automatic)
- [ ] Test database backups
- [ ] Document deployment configuration
- [ ] Set up CI/CD pipeline (GitHub Actions)

---

## 📚 Useful Commands

### Render CLI
```bash
# Install Render CLI
npm install -g @render-sh/render-cli

# Deploy blueprint
render deploy

# Check service logs
render logs <service-name>

# Scale service
render scale <service-name> <num-instances>
```

### Railway CLI
```bash
# Install Railway CLI
curl -fsSL cli.railway.app | sh

# Login
railway login

# View logs
railway logs --service api

# Scale services
railway scale api=2 worker=3

# Redeploy
railway redeploy --service api
```

---

## 💡 Next Steps

1. **Choose Platform:** Render or Railway
2. **Prepare Repository:** Push code to GitHub
3. **Deploy:** Follow platform-specific steps above
4. **Test:** Verify all endpoints working
5. **Monitor:** Set up alerts and logging
6. **Scale:** Adjust resources as needed
7. **Backup:** Configure database backups
8. **Monitor:** Use dashboard and logs

---

**Last Updated:** April 17, 2026
