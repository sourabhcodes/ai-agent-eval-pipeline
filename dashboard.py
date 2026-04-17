"""
Streamlit Dashboard for AI Agent Evaluation Pipeline.
Displays evaluation summaries, metrics, and improvement suggestions.
"""
import os
import logging
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from sqlalchemy import create_engine, desc, func
from sqlalchemy.orm import sessionmaker

from app.models import (
    Evaluation, Conversation, Feedback,
    EvaluatorTypeEnum
)
from app.self_updater import SelfUpdatingService

# ============================================================================
# CONFIGURATION
# ============================================================================

# Page configuration
st.set_page_config(
    page_title="Eval Pipeline Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Database connection
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/eval_pipeline"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_db():
    """Get database session."""
    return SessionLocal()


@st.cache_data(ttl=300)
def get_evaluation_summary(hours: int = 24) -> dict:
    """Get summary statistics for evaluations."""
    db = get_db()
    
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        # Get all recent evaluations
        evaluations = db.query(Evaluation).filter(
            Evaluation.created_at > cutoff_time
        ).all()
        
        if not evaluations:
            return {
                "total_evaluations": 0,
                "avg_heuristic_score": 0,
                "avg_tool_call_score": 0,
                "avg_llm_judge_score": 0,
                "total_conversations": 0
            }
        
        # Group by evaluator type
        heuristic_scores = [e.score for e in evaluations if e.evaluator_type == EvaluatorTypeEnum.HEURISTIC]
        tool_call_scores = [e.score for e in evaluations if e.evaluator_type == EvaluatorTypeEnum.TOOL_CALL]
        llm_judge_scores = [e.score for e in evaluations if e.evaluator_type == EvaluatorTypeEnum.LLM_JUDGE]
        
        # Get unique conversations
        conv_ids = set(e.conversation_id for e in evaluations)
        
        return {
            "total_evaluations": len(evaluations),
            "avg_heuristic_score": sum(heuristic_scores) / len(heuristic_scores) if heuristic_scores else 0,
            "avg_tool_call_score": sum(tool_call_scores) / len(tool_call_scores) if tool_call_scores else 0,
            "avg_llm_judge_score": sum(llm_judge_scores) / len(llm_judge_scores) if llm_judge_scores else 0,
            "total_conversations": len(conv_ids),
            "heuristic_count": len(heuristic_scores),
            "tool_call_count": len(tool_call_scores),
            "llm_judge_count": len(llm_judge_scores),
        }
    
    finally:
        db.close()


@st.cache_data(ttl=300)
def get_evaluation_trends(hours: int = 24):
    """Get evaluation trends over time."""
    db = get_db()
    
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        evaluations = db.query(Evaluation).filter(
            Evaluation.created_at > cutoff_time
        ).all()
        
        if not evaluations:
            return pd.DataFrame()
        
        # Convert to DataFrame
        data = [
            {
                "timestamp": e.created_at,
                "evaluator_type": e.evaluator_type.value,
                "score": e.score,
                "conversation_id": e.conversation_id
            }
            for e in evaluations
        ]
        
        df = pd.DataFrame(data)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        
        return df
    
    finally:
        db.close()


@st.cache_data(ttl=300)
def get_suggestions():
    """Get automated prompt improvement suggestions."""
    db = get_db()
    
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        
        evaluations = db.query(Evaluation).filter(
            Evaluation.created_at > cutoff_time
        ).all()
        
        if not evaluations:
            return []
        
        conv_ids = set(e.conversation_id for e in evaluations)
        conversations = db.query(Conversation).filter(
            Conversation.id.in_(conv_ids)
        ).all()
        
        # Run analysis
        service = SelfUpdatingService()
        analysis = service.analyze_evaluations(
            evaluations,
            conversations,
            window_hours=24
        )
        
        return analysis.get("suggestions", [])
    
    finally:
        db.close()


@st.cache_data(ttl=300)
def get_quality_metrics(hours: int = 24) -> dict:
    """Get quality metrics summary."""
    db = get_db()
    
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        # Get conversations with feedback
        conversations_with_feedback = db.query(Conversation).filter(
            Conversation.created_at > cutoff_time,
            Conversation.feedback.isnot(None)
        ).all()
        
        if not conversations_with_feedback:
            return {
                "avg_user_rating": 0,
                "conversations_with_feedback": 0,
                "satisfaction_rate": 0
            }
        
        ratings = [c.feedback.user_rating for c in conversations_with_feedback if c.feedback]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0
        
        # Calculate satisfaction (rating >= 3 out of 5)
        satisfied = sum(1 for r in ratings if r >= 3)
        satisfaction_rate = (satisfied / len(ratings) * 100) if ratings else 0
        
        return {
            "avg_user_rating": avg_rating,
            "conversations_with_feedback": len(conversations_with_feedback),
            "satisfaction_rate": satisfaction_rate
        }
    
    finally:
        db.close()


def create_score_gauge(score: float, label: str) -> go.Figure:
    """Create a gauge chart for a score."""
    fig = go.Figure(data=[go.Indicator(
        mode="gauge+number+delta",
        value=score * 100,
        domain={"x": [0, 1], "y": [0, 1]},
        title={"text": label},
        delta={"reference": 80},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "darkblue"},
            "steps": [
                {"range": [0, 50], "color": "#ffcccc"},
                {"range": [50, 80], "color": "#ffffcc"},
                {"range": [80, 100], "color": "#ccffcc"}
            ],
            "threshold": {
                "line": {"color": "red", "width": 4},
                "thickness": 0.75,
                "value": 90
            }
        }
    )])
    
    fig.update_layout(
        height=400,
        margin=dict(l=0, r=0, t=50, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        font_size=12
    )
    
    return fig


def create_distribution_chart(df: pd.DataFrame) -> go.Figure:
    """Create a distribution chart of scores by evaluator."""
    if df.empty:
        return go.Figure()
    
    fig = px.box(
        df,
        x="evaluator_type",
        y="score",
        color="evaluator_type",
        title="Score Distribution by Evaluator Type",
        labels={"evaluator_type": "Evaluator Type", "score": "Score"}
    )
    
    fig.update_layout(
        height=400,
        showlegend=False,
        hovermode="x unified"
    )
    
    return fig


def create_timeline_chart(df: pd.DataFrame) -> go.Figure:
    """Create a timeline of scores over time."""
    if df.empty:
        return go.Figure()
    
    # Aggregate by hour
    df["hour"] = df["timestamp"].dt.floor("H")
    hourly = df.groupby(["hour", "evaluator_type"])["score"].mean().reset_index()
    
    fig = px.line(
        hourly,
        x="hour",
        y="score",
        color="evaluator_type",
        title="Average Scores Over Time",
        labels={"hour": "Time", "score": "Average Score", "evaluator_type": "Evaluator"}
    )
    
    fig.update_layout(
        height=400,
        hovermode="x unified"
    )
    
    return fig


# ============================================================================
# DASHBOARD LAYOUT
# ============================================================================

st.title("📊 AI Agent Evaluation Pipeline Dashboard")
st.markdown("Real-time monitoring and insights for the evaluation system")

# Sidebar controls
with st.sidebar:
    st.header("⚙️ Filters")
    
    time_range = st.selectbox(
        "Time Range",
        ["Last 6 Hours", "Last 24 Hours", "Last 7 Days"],
        index=1
    )
    
    time_map = {
        "Last 6 Hours": 6,
        "Last 24 Hours": 24,
        "Last 7 Days": 7 * 24
    }
    
    hours = time_map[time_range]
    
    st.markdown("---")
    st.markdown("### 📈 Refresh Settings")
    st.info("Dashboard auto-refreshes every 5 minutes")

# ============================================================================
# MAIN METRICS ROW
# ============================================================================

st.markdown("## 📈 Overall Performance Scores")

summary = get_evaluation_summary(hours=hours)
quality = get_quality_metrics(hours=hours)

# Create metric columns
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="Response Quality",
        value=f"{summary['avg_llm_judge_score'] * 100:.1f}%",
        delta=f"+{summary['avg_llm_judge_score'] * 100 - 80:.1f}%" if summary['avg_llm_judge_score'] > 0.8 else None,
        help="Coherence and quality score from LLM-as-Judge"
    )

with col2:
    st.metric(
        label="Tool Accuracy",
        value=f"{summary['avg_tool_call_score'] * 100:.1f}%",
        delta=f"+{summary['avg_tool_call_score'] * 100 - 85:.1f}%" if summary['avg_tool_call_score'] > 0.85 else None,
        help="Tool call correctness (no hallucinations/format errors)"
    )

with col3:
    st.metric(
        label="Response Speed",
        value=f"{summary['avg_heuristic_score'] * 100:.1f}%",
        delta=f"+{summary['avg_heuristic_score'] * 100 - 75:.1f}%" if summary['avg_heuristic_score'] > 0.75 else None,
        help="Latency compliance (under 1000ms threshold)"
    )

with col4:
    st.metric(
        label="User Satisfaction",
        value=f"{quality['satisfaction_rate']:.1f}%",
        delta=f"+{len([c for c in [quality['conversations_with_feedback']] if quality['satisfaction_rate'] > 70]):.0f}" if quality['satisfaction_rate'] > 70 else None,
        help="Conversations rated 3+ out of 5"
    )

# ============================================================================
# DETAILED CHARTS
# ============================================================================

st.markdown("## 📊 Evaluation Metrics")

# Get trends data
trends_df = get_evaluation_trends(hours=hours)

if not trends_df.empty:
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        st.plotly_chart(
            create_distribution_chart(trends_df),
            use_container_width=True
        )
    
    with chart_col2:
        st.plotly_chart(
            create_timeline_chart(trends_df),
            use_container_width=True
        )
else:
    st.info("No evaluation data available for the selected time range")

# ============================================================================
# GAUGES
# ============================================================================

st.markdown("## 🎯 Performance Gauges")

gauge_col1, gauge_col2, gauge_col3 = st.columns(3)

with gauge_col1:
    st.plotly_chart(
        create_score_gauge(
            summary['avg_llm_judge_score'],
            "Response Quality"
        ),
        use_container_width=True
    )

with gauge_col2:
    st.plotly_chart(
        create_score_gauge(
            summary['avg_tool_call_score'],
            "Tool Accuracy"
        ),
        use_container_width=True
    )

with gauge_col3:
    st.plotly_chart(
        create_score_gauge(
            summary['avg_heuristic_score'],
            "Response Speed"
        ),
        use_container_width=True
    )

# ============================================================================
# IMPROVEMENT SUGGESTIONS
# ============================================================================

st.markdown("## 💡 Improvement Suggestions")
st.markdown("AI-generated recommendations based on evaluation patterns")

suggestions = get_suggestions()

if suggestions:
    # Sort by confidence (descending)
    sorted_suggestions = sorted(suggestions, key=lambda s: s.confidence, reverse=True)
    
    for idx, suggestion in enumerate(sorted_suggestions[:5], 1):  # Show top 5
        with st.container():
            # Confidence badge
            confidence_pct = suggestion.confidence * 100
            confidence_color = "🟢" if confidence_pct >= 80 else "🟡" if confidence_pct >= 60 else "🔴"
            
            st.markdown(f"### {idx}. {suggestion.failure_pattern}")
            
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                st.markdown(f"**Confidence:** {confidence_color} {confidence_pct:.0f}%")
            
            with col2:
                st.markdown(f"**Affected Convos:** {suggestion.affected_conversations}")
            
            with col3:
                evaluator_types = ", ".join(suggestion.evaluator_types)
                st.markdown(f"**Evaluators:** {evaluator_types}")
            
            # Current issue
            st.markdown(f"**Current Issue:** {suggestion.current_prompt_issue}")
            
            # Proposed improvement
            st.markdown(f"**Proposed Improvement:**")
            st.code(suggestion.proposed_improvement, language="text")
            
            # Rationale
            with st.expander("📖 Rationale"):
                st.markdown(suggestion.rationale)
            
            st.markdown("---")
else:
    st.info("No suggestions available. Keep collecting evaluation data!")

# ============================================================================
# STATISTICS
# ============================================================================

st.markdown("## 📋 Statistics")

stat_col1, stat_col2, stat_col3 = st.columns(3)

with stat_col1:
    st.metric(
        "Total Evaluations",
        f"{summary['total_evaluations']:,}",
        help=f"Heuristic: {summary['heuristic_count']}, Tool Call: {summary['tool_call_count']}, LLM Judge: {summary['llm_judge_count']}"
    )

with stat_col2:
    st.metric(
        "Conversations Evaluated",
        summary['total_conversations'],
        help="Unique conversations with evaluations"
    )

with stat_col3:
    st.metric(
        "Conversations with Feedback",
        quality['conversations_with_feedback'],
        help="User annotations collected"
    )

# ============================================================================
# FOOTER
# ============================================================================

st.markdown("---")
st.markdown(
    f"Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')} | "
    f"Time Range: {time_range} | "
    f"Auto-refresh: Every 5 minutes"
)
