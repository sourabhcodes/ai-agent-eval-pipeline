"""
FastAPI application for the Evaluation Pipeline.
Handles high-throughput data ingestion and provides evaluation endpoints.
"""
import os
import logging
from typing import List, Optional
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from app.celery import celery_app
from app.models import (
    Base,
    Conversation, Turn, Feedback, Evaluation,
    ConversationCreate, ConversationRead, ConversationWithTurnsCreate,
    FeedbackCreate, EvaluationCreate,
    PromptSuggestionRead,
    TiebreakerRoutingRequest,
    SelfUpdateAnalysisResult
)
from app.evaluators import (
    HeuristicEvaluator, ToolCallEvaluator, MultiTurnEvaluator,
    EvaluationResult
)
from app.self_updater import SelfUpdatingService

# ============================================================================
# CONFIGURATION
# ============================================================================

# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/eval_pipeline"
)

# Redis/Celery configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================================
# DATABASE SETUP
# ============================================================================

engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,  # For Celery compatibility
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# FASTAPI APP SETUP
# ============================================================================

app = FastAPI(
    title="AI Agent Evaluation Pipeline",
    description="Automated eval pipeline with self-updating mechanism",
    version="1.0.0"
)


# ============================================================================
# CELERY TASKS
# ============================================================================

@celery_app.task(bind=True, name="evaluate_conversation")
def evaluate_conversation_task(
    self,
    conversation_id: int,
    include_llm_judge: bool = True
) -> dict:
    """
    Celery task to evaluate a single conversation asynchronously.
    Runs all evaluators (Heuristic, ToolCall, MultiTurn/LLM-as-Judge).

    Args:
        conversation_id: ID of conversation to evaluate
        include_llm_judge: Whether to include LLM-as-judge evaluator

    Returns:
        Dictionary with evaluation results
    """
    db = SessionLocal()
    
    try:
        logger.info(f"Starting evaluation for conversation {conversation_id}")
        
        # Fetch conversation from database
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()
        
        if not conversation:
            logger.error(f"Conversation {conversation_id} not found")
            return {"status": "error", "message": "Conversation not found"}
        
        # Initialize evaluators
        heuristic_eval = HeuristicEvaluator()
        tool_call_eval = ToolCallEvaluator()
        multi_turn_eval = MultiTurnEvaluator()  # Can optionally pass LLM client
        
        evaluators = [
            heuristic_eval,
            tool_call_eval,
        ]
        
        if include_llm_judge:
            evaluators.append(multi_turn_eval)
        
        # Run evaluations
        evaluation_results = []
        
        for evaluator in evaluators:
            try:
                result: EvaluationResult = evaluator.evaluate(conversation)
                
                # Store evaluation in database
                db_evaluation = Evaluation(
                    conversation_id=conversation_id,
                    evaluator_type=result.evaluator_type,
                    score=result.score,
                    details=result.details,
                    metrics=result.metrics
                )
                db.add(db_evaluation)
                
                evaluation_results.append({
                    "evaluator": result.evaluator_type.value,
                    "score": result.score,
                    "metrics": result.metrics
                })
                
                logger.info(
                    f"Evaluator {result.evaluator_type.value} "
                    f"scored {conversation_id}: {result.score:.2f}"
                )
                
            except Exception as e:
                logger.error(
                    f"Error running {evaluator.name} on conversation {conversation_id}: {str(e)}"
                )
                continue
        
        # Commit evaluations
        db.commit()
        
        logger.info(f"Evaluation complete for conversation {conversation_id}")
        
        return {
            "status": "success",
            "conversation_id": conversation_id,
            "evaluations": evaluation_results
        }
        
    except Exception as e:
        logger.error(f"Task error for conversation {conversation_id}: {str(e)}")
        db.rollback()
        return {"status": "error", "message": str(e)}
        
    finally:
        db.close()


@celery_app.task(bind=True, name="analyze_and_suggest")
def analyze_and_suggest_task(
    self,
    window_hours: int = 24
) -> dict:
    """
    Celery task to analyze evaluations and generate suggestions.
    Runs periodically (via Celery Beat) to detect patterns and improvements.

    Args:
        window_hours: Time window for analysis

    Returns:
        Dictionary with analysis results and suggestions
    """
    db = SessionLocal()
    
    try:
        logger.info(f"Starting self-update analysis (window: {window_hours}h)")
        
        # Fetch recent evaluations
        cutoff_time = datetime.utcnow() - timedelta(hours=window_hours)
        evaluations = db.query(Evaluation).filter(
            Evaluation.created_at > cutoff_time
        ).all()
        
        # Fetch associated conversations
        if evaluations:
            conv_ids = set(e.conversation_id for e in evaluations)
            conversations = db.query(Conversation).filter(
                Conversation.id.in_(conv_ids)
            ).all()
        else:
            conversations = []
        
        # Run analysis
        service = SelfUpdatingService()
        analysis = service.analyze_evaluations(
            evaluations,
            conversations,
            window_hours=window_hours
        )
        
        # Generate report
        report = service.generate_self_update_report(analysis, window_hours)
        
        logger.info(f"Analysis complete: {len(analysis['suggestions'])} suggestions generated")
        
        return {
            "status": "success",
            "analysis": analysis,
            "report": report
        }
        
    except Exception as e:
        logger.error(f"Self-update analysis error: {str(e)}")
        return {"status": "error", "message": str(e)}
        
    finally:
        db.close()


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/health")
def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.post("/ingest")
def ingest_conversation(
    conversation: ConversationWithTurnsCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> dict:
    """
    Ingest a conversation and queue it for evaluation.
    High-throughput endpoint that offloads evaluation to Celery.

    Args:
        conversation: Conversation data with turns
        background_tasks: FastAPI background tasks
        db: Database session

    Returns:
        Ingestion confirmation with conversation ID and task ID
    """
    try:
        logger.info(f"Ingesting conversation for user {conversation.user_id}")
        
        # Create conversation record
        db_conversation = Conversation(
            user_id=conversation.user_id,
            agent_id=conversation.agent_id,
            title=conversation.title,
            metadata=conversation.metadata or {}
        )
        
        # Add turns
        for turn_data in conversation.turns:
            db_turn = Turn(
                role=turn_data.role,
                content=turn_data.content,
                tool_calls=turn_data.tool_calls or [],
                metadata=turn_data.metadata or {}
            )
            db_conversation.turns.append(db_turn)
        
        db.add(db_conversation)
        db.commit()
        db.refresh(db_conversation)
        
        conversation_id = db_conversation.id
        
        # Queue evaluation task with Celery (non-blocking)
        task = evaluate_conversation_task.apply_async(
            args=[conversation_id],
            kwargs={"include_llm_judge": True},
            queue="evaluation"
        )
        
        logger.info(
            f"Conversation {conversation_id} queued for evaluation. "
            f"Task ID: {task.id}"
        )
        
        return {
            "status": "ingested",
            "conversation_id": conversation_id,
            "task_id": task.id,
            "message": "Conversation queued for evaluation",
            "turns_count": len(conversation.turns),
            "created_at": db_conversation.created_at.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Ingestion error: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/ingest/batch")
def ingest_batch(
    conversations: List[ConversationWithTurnsCreate],
    db: Session = Depends(get_db)
) -> dict:
    """
    Ingest a batch of conversations for high-throughput ingestion.
    Queues all evaluations asynchronously.

    Args:
        conversations: List of conversations
        db: Database session

    Returns:
        Batch ingestion confirmation
    """
    try:
        logger.info(f"Ingesting batch of {len(conversations)} conversations")
        
        task_ids = []
        conversation_ids = []
        
        for conv_data in conversations:
            # Create conversation record
            db_conversation = Conversation(
                user_id=conv_data.user_id,
                agent_id=conv_data.agent_id,
                title=conv_data.title,
                metadata=conv_data.metadata or {}
            )
            
            # Add turns
            for turn_data in conv_data.turns:
                db_turn = Turn(
                    role=turn_data.role,
                    content=turn_data.content,
                    tool_calls=turn_data.tool_calls or [],
                    metadata=turn_data.metadata or {}
                )
                db_conversation.turns.append(db_turn)
            
            db.add(db_conversation)
            db.commit()
            db.refresh(db_conversation)
            
            conversation_ids.append(db_conversation.id)
            
            # Queue evaluation task
            task = evaluate_conversation_task.apply_async(
                args=[db_conversation.id],
                kwargs={"include_llm_judge": True}
            )
            task_ids.append(task.id)
        
        logger.info(f"Batch ingestion complete: {len(conversation_ids)} conversations queued")
        
        return {
            "status": "batch_ingested",
            "total_conversations": len(conversations),
            "conversation_ids": conversation_ids,
            "task_ids": task_ids,
            "message": "Batch queued for evaluation"
        }
        
    except Exception as e:
        logger.error(f"Batch ingestion error: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/suggestions")
def get_suggestions(
    min_confidence: float = Query(0.7, ge=0, le=1),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
) -> dict:
    """
    Retrieve automated prompt and tool improvements.
    These are suggestions generated from the self-updating mechanism.

    Args:
        min_confidence: Minimum confidence threshold for suggestions
        limit: Maximum number of suggestions to return
        db: Database session

    Returns:
        List of prompt suggestions with confidence scores and rationale
    """
    try:
        logger.info(f"Retrieving suggestions (confidence >= {min_confidence})")
        
        # Get recent evaluations (last 24 hours)
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        evaluations = db.query(Evaluation).filter(
            Evaluation.created_at > cutoff_time
        ).all()
        
        if not evaluations:
            return {
                "status": "success",
                "suggestions": [],
                "message": "No evaluations in the last 24 hours"
            }
        
        # Get associated conversations
        conv_ids = set(e.conversation_id for e in evaluations)
        conversations = db.query(Conversation).filter(
            Conversation.id.in_(conv_ids)
        ).all()
        
        # Run self-update analysis
        service = SelfUpdatingService()
        analysis = service.analyze_evaluations(
            evaluations,
            conversations,
            window_hours=24
        )
        
        # Filter by confidence threshold
        filtered_suggestions = [
            s for s in analysis["suggestions"]
            if s.confidence >= min_confidence
        ][:limit]
        
        # Format response
        suggestions_response = [
            {
                "id": s.suggestion_id,
                "failure_pattern": s.failure_pattern,
                "current_issue": s.current_prompt_issue,
                "proposed_improvement": s.proposed_improvement,
                "rationale": s.rationale,
                "confidence": s.confidence,
                "confidence_percentage": f"{s.confidence * 100:.1f}%",
                "affected_conversations": s.affected_conversations,
                "evaluator_types": s.evaluator_types,
                "created_at": s.created_at.isoformat()
            }
            for s in filtered_suggestions
        ]
        
        logger.info(f"Returned {len(suggestions_response)} suggestions")
        
        return {
            "status": "success",
            "suggestions": suggestions_response,
            "total_count": len(analysis["suggestions"]),
            "filtered_count": len(suggestions_response),
            "min_confidence": min_confidence,
            "metrics": analysis["metrics"]
        }
        
    except Exception as e:
        logger.error(f"Error retrieving suggestions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/conversation/{conversation_id}")
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db)
) -> ConversationRead:
    """
    Retrieve a specific conversation with all evaluations.

    Args:
        conversation_id: ID of conversation to retrieve
        db: Database session

    Returns:
        Conversation data with turns, feedback, and evaluations
    """
    try:
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return ConversationRead.model_validate(conversation)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving conversation {conversation_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/evaluations")
def get_evaluations(
    conversation_id: Optional[int] = None,
    evaluator_type: Optional[str] = None,
    min_score: float = Query(0, ge=0, le=1),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
) -> dict:
    """
    Retrieve evaluations with optional filtering.

    Args:
        conversation_id: Filter by conversation ID
        evaluator_type: Filter by evaluator type (heuristic, tool_call, llm_judge)
        min_score: Minimum score threshold
        limit: Maximum results to return
        db: Database session

    Returns:
        List of evaluations
    """
    try:
        query = db.query(Evaluation).filter(Evaluation.score >= min_score)
        
        if conversation_id:
            query = query.filter(Evaluation.conversation_id == conversation_id)
        
        if evaluator_type:
            query = query.filter(Evaluation.evaluator_type == evaluator_type)
        
        evaluations = query.order_by(
            desc(Evaluation.created_at)
        ).limit(limit).all()
        
        return {
            "status": "success",
            "evaluations": [
                {
                    "id": e.id,
                    "conversation_id": e.conversation_id,
                    "evaluator_type": e.evaluator_type.value,
                    "score": e.score,
                    "details": e.details,
                    "metrics": e.metrics,
                    "created_at": e.created_at.isoformat()
                }
                for e in evaluations
            ],
            "count": len(evaluations)
        }
        
    except Exception as e:
        logger.error(f"Error retrieving evaluations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/feedback/{conversation_id}")
def submit_feedback(
    conversation_id: int,
    feedback: FeedbackCreate,
    db: Session = Depends(get_db)
) -> dict:
    """
    Submit feedback (user rating and annotations) for a conversation.

    Args:
        conversation_id: ID of conversation
        feedback: Feedback data (rating, annotations)
        db: Database session

    Returns:
        Feedback confirmation
    """
    try:
        # Check conversation exists
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Create or update feedback
        existing_feedback = db.query(Feedback).filter(
            Feedback.conversation_id == conversation_id
        ).first()
        
        if existing_feedback:
            existing_feedback.user_rating = feedback.user_rating
            existing_feedback.annotations = feedback.annotations
            existing_feedback.comment = feedback.comment
            existing_feedback.updated_at = datetime.utcnow()
        else:
            existing_feedback = Feedback(
                conversation_id=conversation_id,
                user_rating=feedback.user_rating,
                annotations=feedback.annotations,
                comment=feedback.comment
            )
            db.add(existing_feedback)
        
        db.commit()
        db.refresh(existing_feedback)
        
        logger.info(f"Feedback submitted for conversation {conversation_id}")
        
        return {
            "status": "success",
            "message": "Feedback recorded",
            "conversation_id": conversation_id,
            "user_rating": existing_feedback.user_rating,
            "created_at": existing_feedback.created_at.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting feedback: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/task/{task_id}/status")
def get_task_status(task_id: str) -> dict:
    """
    Check the status of a Celery evaluation task.

    Args:
        task_id: Celery task ID

    Returns:
        Task status and result
    """
    try:
        task = celery_app.AsyncResult(task_id)
        
        response = {
            "task_id": task_id,
            "status": task.status,
            "ready": task.ready(),
            "successful": task.successful() if task.ready() else None,
            "failed": task.failed() if task.ready() else None,
        }
        
        if task.ready():
            if task.successful():
                response["result"] = task.result
            else:
                response["error"] = str(task.info)
        
        return response
        
    except Exception as e:
        logger.error(f"Error retrieving task status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# STARTUP/SHUTDOWN EVENTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    logger.info("🚀 Evaluation Pipeline starting up")
    logger.info(f"Database: {DATABASE_URL}")
    logger.info(f"Redis/Celery: {REDIS_URL}")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    logger.info("🛑 Evaluation Pipeline shutting down")


# ============================================================================
# ROOT ENDPOINT
# ============================================================================

@app.get("/")
def root() -> dict:
    """Root endpoint with API information."""
    return {
        "name": "AI Agent Evaluation Pipeline",
        "version": "1.0.0",
        "description": "Automated evaluation with self-updating mechanism",
        "endpoints": {
            "ingestion": "/ingest (POST) - Single conversation",
            "batch_ingestion": "/ingest/batch (POST) - Multiple conversations",
            "suggestions": "/suggestions (GET) - Prompt improvements",
            "conversation": "/conversation/{id} (GET) - Get conversation details",
            "evaluations": "/evaluations (GET) - List evaluations",
            "feedback": "/feedback/{id} (POST) - Submit feedback",
            "task_status": "/task/{id}/status (POST) - Check task status",
            "health": "/health (GET) - Health check"
        },
        "docs": "/docs - Swagger documentation"
    }
