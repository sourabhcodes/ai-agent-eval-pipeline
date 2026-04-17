"""
SQLAlchemy ORM models and Pydantic schemas for the evaluation pipeline.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float, ForeignKey, 
    JSON, Boolean, Enum as SQLEnum, Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pydantic import BaseModel, Field, ConfigDict

# SQLAlchemy base
Base = declarative_base()


# ============================================================================
# ENUMS
# ============================================================================

class RoleEnum(str, Enum):
    """Role types in a conversation."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class EvaluatorTypeEnum(str, Enum):
    """Types of evaluators."""
    HEURISTIC = "heuristic"
    TOOL_CALL = "tool_call"
    LLM_JUDGE = "llm_judge"


class TiebreakerStatusEnum(str, Enum):
    """Status for annotator disagreement resolution."""
    PENDING = "pending"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


# ============================================================================
# SQLALCHEMY ORM MODELS
# ============================================================================

class Conversation(Base):
    """
    Represents a conversation thread between user and agent.
    A conversation contains multiple turns and can have feedback and evaluations.
    """
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    agent_id = Column(String, nullable=False)
    title = Column(String, nullable=True)
    meta = Column(JSON, nullable=True, default={})
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    turns = relationship("Turn", back_populates="conversation", cascade="all, delete-orphan")
    feedback = relationship("Feedback", back_populates="conversation", cascade="all, delete-orphan", uselist=False)
    evaluations = relationship("Evaluation", back_populates="conversation", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_user_id_created_at", "user_id", "created_at"),
    )


class Turn(Base):
    """
    Represents a single turn (exchange) in a conversation.
    A turn contains the role (user/assistant), content, and associated metadata.
    """
    __tablename__ = "turns"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(SQLEnum(RoleEnum), nullable=False)
    content = Column(Text, nullable=False)
    tool_calls = Column(JSON, nullable=True, default=[])  # For tracking tool calls
    metadata = Column(JSON, nullable=True, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="turns")

    __table_args__ = (
        Index("idx_conversation_id_created_at", "conversation_id", "created_at"),
    )


class Feedback(Base):
    """
    Represents feedback for a conversation.
    Includes user rating and detailed annotations.
    """
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, unique=True, index=True)
    user_rating = Column(Float, nullable=False)  # Scale: 1-5 or 0-1
    annotations = Column(JSON, nullable=True, default={})  # Structured feedback
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="feedback")


class Evaluation(Base):
    """
    Represents the evaluation results of a conversation.
    Stores results from different evaluators (heuristic, tool_call, llm_judge).
    """
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    evaluator_type = Column(SQLEnum(EvaluatorTypeEnum), nullable=False)
    score = Column(Float, nullable=False)  # Normalized score (0-1 or similar)
    details = Column(JSON, nullable=True, default={})  # Evaluator-specific details
    metrics = Column(JSON, nullable=True, default={})  # Additional metrics
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="evaluations")

    __table_args__ = (
        Index("idx_conversation_evaluator", "conversation_id", "evaluator_type"),
    )


# ============================================================================
# PYDANTIC SCHEMAS FOR API VALIDATION
# ============================================================================

class TurnBase(BaseModel):
    """Base schema for Turn data."""
    role: RoleEnum
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    meta: Optional[Dict[str, Any]] = None


class TurnCreate(TurnBase):
    """Schema for creating a new Turn."""
    pass


class TurnRead(TurnBase):
    """Schema for reading Turn data."""
    id: int
    conversation_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FeedbackBase(BaseModel):
    """Base schema for Feedback data."""
    user_rating: float = Field(..., ge=0, le=5, description="User rating (0-5)")
    annotations: Optional[Dict[str, Any]] = None
    comment: Optional[str] = None


class FeedbackCreate(FeedbackBase):
    """Schema for creating Feedback."""
    pass


class FeedbackRead(FeedbackBase):
    """Schema for reading Feedback data."""
    id: int
    conversation_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvaluationBase(BaseModel):
    """Base schema for Evaluation data."""
    evaluator_type: EvaluatorTypeEnum
    score: float = Field(..., ge=0, le=1, description="Normalized score (0-1)")
    details: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None


class EvaluationCreate(EvaluationBase):
    """Schema for creating Evaluation."""
    pass


class EvaluationRead(EvaluationBase):
    """Schema for reading Evaluation data."""
    id: int
    conversation_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationBase(BaseModel):
    """Base schema for Conversation data."""
    user_id: str
    agent_id: str
    title: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class ConversationCreate(ConversationBase):
    """Schema for creating a new Conversation."""
    pass


class ConversationRead(ConversationBase):
    """Schema for reading Conversation data with relationships."""
    id: int
    created_at: datetime
    updated_at: datetime
    turns: List[TurnRead] = Field(default_factory=list)
    feedback: Optional[FeedbackRead] = None
    evaluations: List[EvaluationRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ConversationUpdate(BaseModel):
    """Schema for updating a Conversation."""
    title: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# Convenience schemas for batch operations

class ConversationWithTurnsCreate(BaseModel):
    """Schema for creating a Conversation with initial Turns."""
    user_id: str
    agent_id: str
    title: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    turns: List[TurnCreate] = Field(default_factory=list)


class EvaluationBatchCreate(BaseModel):
    """Schema for batch creating Evaluations for a conversation."""
    conversation_id: int
    evaluations: List[EvaluationCreate]


# ============================================================================
# SELF-UPDATING AND DISAGREEMENT SCHEMAS
# ============================================================================

class PromptSuggestionBase(BaseModel):
    """Base schema for Prompt Suggestion data."""
    failure_pattern: str
    current_prompt_issue: str
    proposed_improvement: str
    rationale: str
    confidence: float = Field(..., ge=0, le=1, description="Confidence score (0-1)")
    affected_conversations: int
    evaluator_types: List[str] = Field(default_factory=list)


class PromptSuggestionCreate(PromptSuggestionBase):
    """Schema for creating a Prompt Suggestion."""
    pass


class PromptSuggestionRead(PromptSuggestionBase):
    """Schema for reading Prompt Suggestion data."""
    suggestion_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnnotatorDisagreementBase(BaseModel):
    """Base schema for Annotator Disagreement data."""
    conversation_id: int
    annotator_1: str
    annotator_1_label: str
    annotator_2: str
    annotator_2_label: str
    disagreement_type: str
    confidence_delta: float = Field(..., ge=0, le=1, description="Score difference")
    status: TiebreakerStatusEnum = TiebreakerStatusEnum.PENDING


class AnnotatorDisagreementCreate(AnnotatorDisagreementBase):
    """Schema for creating an Annotator Disagreement."""
    pass


class AnnotatorDisagreementRead(AnnotatorDisagreementBase):
    """Schema for reading Annotator Disagreement data."""
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SelfUpdateAnalysisResult(BaseModel):
    """Schema for self-update analysis results."""
    suggestions: List[PromptSuggestionRead] = Field(default_factory=list)
    patterns: Dict[str, Any] = Field(default_factory=dict)
    disagreements: List[AnnotatorDisagreementRead] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)


class TiebreakerRoutingRequest(BaseModel):
    """Schema for routing a conversation to tiebreaker review."""
    conversation_id: int
    disagreement_type: str
    annotator_1_label: str
    annotator_2_label: str
    confidence_delta: float


class TiebreakerResolution(BaseModel):
    """Schema for resolving a tiebreaker."""
    conversation_id: int
    final_label: str
    resolver_notes: str
    resolved_at: datetime = Field(default_factory=datetime.utcnow)
