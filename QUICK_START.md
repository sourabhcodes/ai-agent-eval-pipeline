# Quick Reference & Testing Guide

## Project Structure

```
assignment/
├── app/
│   ├── __init__.py              # Package init, exports Celery app
│   ├── main.py                  # FastAPI application with /ingest, /suggestions endpoints
│   ├── models.py                # SQLAlchemy ORM + Pydantic schemas
│   ├── evaluators.py            # Strategy Pattern evaluators (3 types)
│   ├── self_updater.py          # Self-updating mechanism & tiebreaker logic
│   └── celery.py                # Celery configuration & Beat schedule
├── dashboard.py                 # Streamlit dashboard
├── test_scenarios.py            # Test scenarios for Scenario 1, 2, 3
├── docker-compose.yml           # PostgreSQL, Redis, FastAPI, Celery services
├── Dockerfile                   # Container image
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment template
├── README.md                    # Comprehensive documentation
└── IMPLEMENTATION_REVIEW.md     # Verification checklist
```

---

## Quick Start (Local Development)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Up Environment
```bash
cp .env.example .env
# Edit .env to add OPENAI_API_KEY if you want LLM-as-Judge
```

### 3. Start Services with Docker Compose
```bash
docker-compose up -d
```

This starts:
- PostgreSQL (port 5432)
- Redis (port 6379)
- FastAPI (port 8000)
- Celery worker
- Celery Beat scheduler

### 4. Run Test Scenarios
```bash
python test_scenarios.py
```

Expected output:
```
════════════════════════════════════════════════════════════════════════════════
                     SCENARIO 1: Tool Call Date Format Error Detection
════════════════════════════════════════════════════════════════════════════════

✅ PASS | Conversation 1: Date format '04/17/2024'
✅ PASS | Conversation 2: Date format '17-04-2024'
... (10 total)

────────────────────────────────────────────────────────────────────────────────
Scenario 1 Summary:
  ├─ Conversations created: 10
  ├─ Date errors detected: 10/10
  ├─ Average score: 0.35 (expect < 0.6)
  └─ Status: ✅ PASS

════════════════════════════════════════════════════════════════════════════════
                        SCENARIO 2: Multi-Turn Context Loss Detection
════════════════════════════════════════════════════════════════════════════════

Created 6-turn conversation (ID: 1)
  Turn 1: User specifies budget preference
  Turns 2-5: Conversation progresses
  Turn 6: Agent recommends premium option (contradicts preference)

MultiTurnEvaluator Result:
  ├─ Score: 0.42
  ├─ Method: heuristic
  ├─ Turn count: 6
  ├─ Context violations: 1

✅ PASS | Context Loss Detection
     └─ Score: 0.42 (expect < 0.7 for context loss)

════════════════════════════════════════════════════════════════════════════════
                    SCENARIO 3: Annotator Disagreement & Tiebreaker Routing
════════════════════════════════════════════════════════════════════════════════

Human Optimistic:
  ├─ Human rating: 5.0/5 → 1.00 (normalized)
  ├─ Evaluator score: 0.30
  ├─ Disagreement delta: 0.70
  ├─ Detected type: human_optimistic
  └─ Status: ✅

✅ PASS | Human Optimistic - Disagreement Detected
     └─ Delta 0.70 >= threshold 0.30

Human Pessimistic:
  ├─ Human rating: 2.0/5 → 0.40 (normalized)
  ├─ Evaluator score: 0.90
  ├─ Disagreement delta: 0.50
  ├─ Detected type: human_pessimistic
  └─ Status: ✅

✅ PASS | Human Pessimistic - Disagreement Detected
     └─ Delta 0.50 >= threshold 0.30

Major Disagreement:
  ├─ Human rating: 5.0/5 → 1.00 (normalized)
  ├─ Evaluator score: 0.20
  ├─ Disagreement delta: 0.80
  ├─ Detected type: major_disagreement
  └─ Status: ✅

✅ PASS | Major Disagreement - Disagreement Detected
     └─ Delta 0.80 >= threshold 0.30

────────────────────────────────────────────────────────────────────────────────
Tiebreaker Routing Summary:

  Disagreement: Human Optimistic
    ├─ Routed to: route_to_human_review
    ├─ Status: pending
    └─ Reason: Disagreement between human_annotator (label: excellent) and ...

════════════════════════════════════════════════════════════════════════════════
                                FINAL SUMMARY
════════════════════════════════════════════════════════════════════════════════

✅ PASS | Scenario 1: Date Format Errors
✅ PASS | Scenario 2: Context Loss
✅ PASS | Scenario 3: Annotator Disagreement

────────────────────────────────────────────────────────────────────────────────
Results: 3/3 scenarios passed
Status: ✅ ALL TESTS PASSED
────────────────────────────────────────────────────────────────────────────────
```

---

## Test Scenario Details

### Scenario 1: Tool Call Date Format Errors
**What it tests:** ToolCallEvaluator detects invalid date formats

**Mock Data:** 10 conversations with flight_search tool calls using wrong formats:
- `04/17/2024` (MM/DD/YYYY)
- `17-04-2024` (DD-MM-YYYY)
- `2024/04/17` (YYYY/MM/DD with slashes)
- `04-17-2024` (MM-DD-YYYY)
- `April 17, 2024` (Month name)
- And 5 more variations

**Validation:**
- ✅ Each conversation's tool call is evaluated
- ✅ Invalid date formats are detected
- ✅ Scores are low (< 0.6)
- ✅ Issue details show detected errors

---

### Scenario 2: Multi-Turn Context Loss
**What it tests:** MultiTurnEvaluator detects when agent ignores context

**Mock Data:** 6-turn conversation
```
Turn 1 (USER):      "I prefer budget airlines only. Price is my main concern."
Turn 2 (ASSISTANT): "I'll help you find budget flights to Paris."
Turn 3 (USER):      "What are the options?"
Turn 4 (ASSISTANT): "I found several flights. EasyJet, Ryanair... also Air France..."
Turn 5 (USER):      "Remind me, which one is cheapest?"
Turn 6 (ASSISTANT): "The best option is Air France premium business class..." ❌
```

**Validation:**
- ✅ Conversation has 6 turns (>= 5 threshold)
- ✅ Context loss detected (contradicts preference)
- ✅ Score is low (< 0.7)
- ✅ Context violations counted

---

### Scenario 3: Annotator Disagreement
**What it tests:** SelfUpdatingService detects and routes disagreements

**Mock Data:** 3 test cases
1. **Human Optimistic**
   - Human feedback: 5/5 (normalized: 1.0)
   - Evaluator score: 0.3
   - Delta: 0.7 (>= threshold 0.3) ✅
   - Type: `human_optimistic`

2. **Human Pessimistic**
   - Human feedback: 2/5 (normalized: 0.4)
   - Evaluator score: 0.9
   - Delta: 0.5 (>= threshold 0.3) ✅
   - Type: `human_pessimistic`

3. **Major Disagreement**
   - Human feedback: 5/5 (normalized: 1.0)
   - Evaluator score: 0.2
   - Delta: 0.8 (>= threshold 0.3) ✅
   - Type: `major_disagreement`

**Validation:**
- ✅ All disagreements detected (delta >= 0.3)
- ✅ Types classified correctly
- ✅ Routed to tiebreaker (status: PENDING)
- ✅ Tiebreaker routing info generated

---

## API Testing

### Test Ingestion
```bash
curl -X POST "http://localhost:8000/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user_1",
    "agent_id": "agent_v1",
    "title": "Test Query",
    "turns": [
      {
        "role": "user",
        "content": "What is 2+2?"
      },
      {
        "role": "assistant",
        "content": "2+2 equals 4"
      }
    ]
  }'
```

Response:
```json
{
  "status": "ingested",
  "conversation_id": 1,
  "task_id": "abc123...",
  "message": "Conversation queued for evaluation",
  "turns_count": 2,
  "created_at": "2024-04-17T12:00:00"
}
```

### Check Task Status
```bash
curl -X GET "http://localhost:8000/task/abc123.../status"
```

### Get Suggestions
```bash
curl -X GET "http://localhost:8000/suggestions?min_confidence=0.7&limit=5"
```

Response:
```json
{
  "status": "success",
  "suggestions": [
    {
      "id": "suggestion_001",
      "failure_pattern": "Incorrect date format in tool parameters",
      "current_issue": "Agent not following specified date formats",
      "proposed_improvement": "Add explicit format specification...",
      "rationale": "Detected 250 invalid date format errors...",
      "confidence": 0.87,
      "confidence_percentage": "87.0%",
      "affected_conversations": 250,
      "evaluator_types": ["tool_call"],
      "created_at": "2024-04-17T12:00:00"
    }
  ],
  "total_count": 3,
  "filtered_count": 1,
  "min_confidence": 0.7
}
```

---

## Dashboard

### Start Dashboard
```bash
streamlit run dashboard.py
```

Visit: `http://localhost:8501`

**Features:**
- Real-time metrics (Response Quality, Tool Accuracy, Speed, Satisfaction)
- Interactive charts (distribution, timeline trends)
- Top 5 improvement suggestions with rationale
- Time range filter (6h, 24h, 7d)
- Auto-refresh every 5 minutes

---

## Celery Workers & Scheduling

### Start Worker (Manual)
```bash
celery -A app.celery worker -l info -Q evaluation,analysis
```

### Start Beat Scheduler (Manual)
```bash
celery -A app.celery beat -l info
```

### Beat Schedule (Automatic)
- **Hourly:** Analyze last 1 hour of evaluations
- **Daily:** Analyze last 24 hours of evaluations

---

## Scaling for 100x Load

### Single Instance (Baseline)
```bash
# FastAPI
uvicorn app.main:app --workers 4

# Celery (1 worker, 4 concurrency)
celery -A app.celery worker -c 4
```

**Capacity:** ~10-20 conversations/sec

### Scaled (100x)
```bash
# FastAPI (4 instances behind load balancer)
for i in {1..4}; do
  uvicorn app.main:app --port $((8000+i)) &
done

# Celery (10 workers)
for i in {1..10}; do
  celery -A app.celery worker -c 4 -n worker$i &
done

# Redis Cluster (3+ nodes)
redis-server --port 6379 --cluster-enabled yes
redis-server --port 6380 --cluster-enabled yes
redis-server --port 6381 --cluster-enabled yes
```

**Capacity:** 1000+ conversations/sec

---

## Troubleshooting

### Database Connection Error
```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Verify connection string in .env
docker-compose logs postgres
```

### Celery Tasks Not Running
```bash
# Check Redis is running
docker-compose ps redis

# Monitor Celery worker
celery -A app.celery events

# Check task queue
celery -A app.celery inspect active
```

### Dashboard Not Displaying Data
```bash
# Ensure data exists (run test_scenarios.py first)
python test_scenarios.py

# Check database query
psql postgresql://postgres:postgres@localhost:5432/eval_pipeline -c "SELECT COUNT(*) FROM evaluations;"
```

---

## Key Metrics to Monitor

1. **Ingestion Rate:** conversations/sec
   - Target: 1000+/min
   - Monitor: `/ingest` endpoint response time

2. **Evaluation Latency:** seconds per conversation
   - Target: < 5 seconds
   - Monitor: Celery task execution time

3. **Suggestion Confidence:** 0-1
   - Target: > 0.7 for recommendations
   - Monitor: `/suggestions` endpoint

4. **Annotator Agreement:** % without disagreement
   - Target: > 95%
   - Monitor: SelfUpdatingService disagreement count

5. **Context Retention:** score 0-1
   - Target: > 0.8
   - Monitor: MultiTurnEvaluator scores

---

## Dependencies

Core:
- FastAPI 0.104.1 - Web framework
- SQLAlchemy 2.0.23 - ORM
- Pydantic - Data validation
- Celery 5.3.4 - Task queue
- Redis 5.0.1 - Message broker
- PostgreSQL 15 - Database

Dashboard:
- Streamlit 1.28.1 - UI framework
- Plotly 5.17.0 - Charting
- Pandas 2.1.3 - Data manipulation

See `requirements.txt` for complete list.

---

## Next Steps

1. ✅ Run `python test_scenarios.py` to verify implementation
2. ✅ Check Dashboard: `streamlit run dashboard.py`
3. ✅ Test API: Use curl examples above
4. ✅ Deploy: Follow Docker Compose or Kubernetes guides in README
5. ✅ Monitor: Use Celery events and database queries

---

**Last Updated:** April 17, 2026
