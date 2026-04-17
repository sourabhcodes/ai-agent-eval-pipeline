# 🚀 Deployment Quick Reference Card

## Copy & Paste Commands

### Render Deployment
```
1. Go to: https://render.com/deploy?repo=https://github.com/YOUR_USER/YOUR_REPO

2. Or manually:
   - Go to https://dashboard.render.com
   - Click "New" → "Blueprint"
   - Connect GitHub repo

3. Set env variables:
   POSTGRES_PASSWORD=your-strong-password
   OPENAI_API_KEY=your-api-key

4. Deploy → Wait 5-10 min
```

### Railway Deployment
```
1. Go to: https://railway.app/new

2. Select: "Deploy from GitHub repo"

3. Choose your repository

4. Set env variables:
   POSTGRES_PASSWORD=your-strong-password
   OPENAI_API_KEY=your-api-key

5. Deploy → Wait 3-5 min
```

---

## Test Your Deployment

```bash
# Set your API URL
API_URL="https://your-deployed-api.com"

# 1. Health check
curl $API_URL/health

# 2. Ingest conversation
curl -X POST "$API_URL/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "agent_id": "agent_v1",
    "turns": [
      {"role": "user", "content": "What is 2+2?"},
      {"role": "assistant", "content": "2+2 equals 4"}
    ]
  }'

# 3. Get suggestions (after 1-2 minutes)
curl "$API_URL/suggestions"
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| API not responding | Check database connection in logs |
| Workers not running | Verify Redis URL in env variables |
| High latency | Check CPU/memory in dashboard |
| Database error | Verify DATABASE_URL environment variable |
| No suggestions | Wait 1-2 min after first ingest |

---

## Key Documentation

| Document | Use When |
|----------|----------|
| DEPLOY_QUICK.md | Deploying for first time |
| DEPLOY.md | Need detailed troubleshooting |
| README.md | Understanding architecture |
| DOCKER_REFERENCE.md | Customizing containers |
| QUICK_START.md | Setting up locally |

---

## Environment Variables Needed

```env
DATABASE_URL=postgresql://...      # Auto-generated
REDIS_URL=redis://...              # Auto-generated
OPENAI_API_KEY=sk-...              # Get from OpenAI
POSTGRES_PASSWORD=your_password    # Create strong one
ENVIRONMENT=production
LOG_LEVEL=INFO
```

---

## Services Deployed

| Service | Purpose | Port |
|---------|---------|------|
| FastAPI | API server | 8000 (internal) |
| PostgreSQL | Database | 5432 (internal) |
| Redis | Cache/broker | 6379 (internal) |
| Celery Worker | Tasks | - |
| Celery Beat | Scheduling | - |

---

## Performance Targets

- **Ingest:** 1000+/minute
- **API latency:** ~10ms
- **Health check:** ~5ms
- **Evaluation time:** 3-5 seconds (async)
- **Monthly cost:** $45-58

---

## Monitoring Commands

```bash
# Check if API is healthy
curl -i https://your-api/health

# View logs in dashboard:
# Render: Dashboard → Service → Logs
# Railway: Dashboard → Service → Logs

# Test database
psql $DATABASE_URL -c "SELECT COUNT(*) FROM conversations;"

# Test Redis
redis-cli -u $REDIS_URL ping
```

---

## Post-Deployment Checklist

- [ ] API responding to `/health`
- [ ] Can ingest conversations via `/ingest`
- [ ] Workers processing tasks (check logs)
- [ ] Suggestions appearing after ~1-2 min
- [ ] Dashboard accessible locally
- [ ] Database has records
- [ ] No errors in logs
- [ ] All services green/healthy

---

## Support

- **Stuck?** Check DEPLOY.md#Common Issues
- **Need details?** See DOCKER_REFERENCE.md
- **Want to learn more?** Read README.md
- **Local testing?** Follow QUICK_START.md

---

**Save this card for quick reference during deployment!**

Last Updated: April 17, 2026
