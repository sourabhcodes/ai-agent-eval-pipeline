"""
AI Agent Evaluation Pipeline application package.
"""
from app.celery import celery_app

__all__ = ["celery_app"]
