"""
Self-Updating Mechanism for the Evaluation Pipeline.
Analyzes evaluation patterns and suggests prompt improvements.
Handles annotator disagreement with tiebreaker routing.
"""
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, Counter
import re
from datetime import datetime, timedelta

from app.models import Evaluation, Conversation, Feedback, EvaluatorTypeEnum


class TiebreakerStatus(str, Enum):
    """Status for annotator disagreement."""
    PENDING = "pending"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


@dataclass
class PromptSuggestion:
    """Container for a suggested prompt improvement."""
    suggestion_id: str
    failure_pattern: str
    current_prompt_issue: str
    proposed_improvement: str
    rationale: str
    confidence: float  # 0-1
    affected_conversations: int
    evaluator_types: List[str]
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AnnotatorDisagreement:
    """Container for annotator disagreement record."""
    conversation_id: int
    annotator_1: str
    annotator_1_label: str
    annotator_2: str
    annotator_2_label: str
    disagreement_type: str
    confidence_delta: float  # How different their scores are
    status: TiebreakerStatus = TiebreakerStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)


class SelfUpdatingService:
    """
    Service for analyzing evaluations and generating self-improvements.
    Implements pattern detection and annotator disagreement handling.
    """

    # Minimum confidence for suggesting improvements
    MIN_SUGGESTION_CONFIDENCE = 0.7

    # Threshold for annotator disagreement
    DISAGREEMENT_THRESHOLD = 0.3  # Score difference >= 0.3 is disagreement

    def __init__(self):
        """Initialize SelfUpdatingService."""
        self.pattern_registry = defaultdict(list)
        self.disagreement_log = []

    def analyze_evaluations(
        self,
        evaluations: List[Evaluation],
        conversations: List[Conversation],
        window_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Analyze a batch of evaluations to identify patterns and suggest improvements.

        Args:
            evaluations: List of Evaluation records to analyze
            conversations: Associated Conversation records
            window_hours: Time window for analysis (hours)

        Returns:
            Dictionary with suggestions, patterns, and metrics
        """
        if not evaluations:
            return {
                "suggestions": [],
                "patterns": {},
                "metrics": {"total_evaluations": 0},
                "disagreements": []
            }

        # Filter evaluations within time window
        cutoff_time = datetime.utcnow() - timedelta(hours=window_hours)
        recent_evals = [
            e for e in evaluations
            if e.created_at and e.created_at > cutoff_time
        ]

        # Build conversation lookup
        conv_lookup = {c.id: c for c in conversations}

        # Analyze patterns by evaluator type
        patterns = self._extract_failure_patterns(recent_evals, conv_lookup)

        # Generate suggestions based on patterns
        suggestions = self._generate_suggestions(patterns)

        # Detect annotator disagreements
        disagreements = self._detect_annotator_disagreements(recent_evals, conv_lookup)

        return {
            "suggestions": suggestions,
            "patterns": patterns,
            "metrics": {
                "total_evaluations": len(recent_evals),
                "evaluations_analyzed": len(recent_evals),
                "time_window_hours": window_hours,
                "total_suggestions": len(suggestions),
                "disagreement_count": len(disagreements),
            },
            "disagreements": disagreements
        }

    def _extract_failure_patterns(
        self,
        evaluations: List[Evaluation],
        conv_lookup: Dict[int, Conversation]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract failure patterns from evaluations.

        Args:
            evaluations: Evaluations to analyze
            conv_lookup: Lookup table for conversations

        Returns:
            Dictionary of patterns by type
        """
        patterns = defaultdict(list)
        low_scores = [e for e in evaluations if e.score < 0.6]

        for eval_obj in low_scores:
            conv = conv_lookup.get(eval_obj.conversation_id)
            if not conv:
                continue

            evaluator_type = eval_obj.evaluator_type

            # Extract details from evaluation
            pattern_entry = {
                "conversation_id": eval_obj.conversation_id,
                "score": eval_obj.score,
                "evaluator_type": evaluator_type.value,
                "details": eval_obj.details or {},
                "metrics": eval_obj.metrics or {},
                "turn_count": len(conv.turns),
                "timestamp": eval_obj.created_at
            }

            patterns[evaluator_type.value].append(pattern_entry)

        return dict(patterns)

    def _generate_suggestions(
        self,
        patterns: Dict[str, List[Dict[str, Any]]]
    ) -> List[PromptSuggestion]:
        """
        Generate prompt improvement suggestions from patterns.

        Args:
            patterns: Failure patterns dictionary

        Returns:
            List of PromptSuggestion objects
        """
        suggestions = []

        # Generate heuristic-specific suggestions
        if EvaluatorTypeEnum.HEURISTIC.value in patterns:
            heuristic_suggestions = self._suggest_heuristic_improvements(
                patterns[EvaluatorTypeEnum.HEURISTIC.value]
            )
            suggestions.extend(heuristic_suggestions)

        # Generate tool call-specific suggestions
        if EvaluatorTypeEnum.TOOL_CALL.value in patterns:
            tool_suggestions = self._suggest_tool_call_improvements(
                patterns[EvaluatorTypeEnum.TOOL_CALL.value]
            )
            suggestions.extend(tool_suggestions)

        # Generate LLM judge-specific suggestions
        if EvaluatorTypeEnum.LLM_JUDGE.value in patterns:
            llm_suggestions = self._suggest_llm_judge_improvements(
                patterns[EvaluatorTypeEnum.LLM_JUDGE.value]
            )
            suggestions.extend(llm_suggestions)

        return sorted(suggestions, key=lambda s: s.confidence, reverse=True)

    def _suggest_heuristic_improvements(
        self,
        pattern_list: List[Dict[str, Any]]
    ) -> List[PromptSuggestion]:
        """
        Generate suggestions for heuristic (latency) failures.

        Args:
            pattern_list: List of heuristic failure patterns

        Returns:
            List of PromptSuggestion objects
        """
        suggestions = []

        if not pattern_list:
            return suggestions

        # Analyze latency issues
        avg_latency = sum(
            p["metrics"].get("avg_latency_ms", 0)
            for p in pattern_list
        ) / len(pattern_list)

        violation_count = sum(
            p["details"].get("violations", 0)
            for p in pattern_list
        )

        if avg_latency > 1500 and violation_count > len(pattern_list) * 0.5:
            confidence = min(0.95, 0.6 + (violation_count / len(pattern_list)))

            suggestions.append(PromptSuggestion(
                suggestion_id=f"heuristic_{datetime.utcnow().timestamp()}",
                failure_pattern="High latency in agent responses",
                current_prompt_issue="Agent is likely over-thinking or making complex tool calls",
                proposed_improvement=(
                    "Add explicit instruction to agent: "
                    "'Prioritize speed over exhaustiveness. Respond within 1 second for simple queries. "
                    "Break complex tasks into separate, faster turns.'"
                ),
                rationale=(
                    f"Detected {violation_count} latency violations "
                    f"across {len(pattern_list)} conversations. "
                    f"Average latency: {avg_latency:.0f}ms. "
                    "Simpler prompts and chunked reasoning reduce latency."
                ),
                confidence=confidence,
                affected_conversations=len(pattern_list),
                evaluator_types=[EvaluatorTypeEnum.HEURISTIC.value]
            ))

        return suggestions

    def _suggest_tool_call_improvements(
        self,
        pattern_list: List[Dict[str, Any]]
    ) -> List[PromptSuggestion]:
        """
        Generate suggestions for tool call (accuracy/hallucination) failures.

        Args:
            pattern_list: List of tool call failure patterns

        Returns:
            List of PromptSuggestion objects
        """
        suggestions = []

        if not pattern_list:
            return suggestions

        # Analyze date format issues
        date_issues = sum(
            p["metrics"].get("invalid_date_formats", 0)
            for p in pattern_list
        )

        hallucinations = sum(
            p["metrics"].get("hallucinated_parameters", 0)
            for p in pattern_list
        )

        # Suggest improvements for date format issues
        if date_issues > 0:
            confidence = min(0.9, 0.65 + (date_issues / (len(pattern_list) * 3)))

            suggestions.append(PromptSuggestion(
                suggestion_id=f"tool_call_date_{datetime.utcnow().timestamp()}",
                failure_pattern="Incorrect date format in tool parameters",
                current_prompt_issue="Agent not following specified date formats in tool calls",
                proposed_improvement=(
                    "Add explicit format specification in tool documentation: "
                    "'All dates MUST use YYYY-MM-DD format. "
                    "Example: 2024-04-17. Never use other formats.'"
                ),
                rationale=(
                    f"Detected {date_issues} invalid date format errors "
                    f"across {len(pattern_list)} conversations. "
                    "Explicit format examples reduce hallucinated formats."
                ),
                confidence=confidence,
                affected_conversations=len(pattern_list),
                evaluator_types=[EvaluatorTypeEnum.TOOL_CALL.value]
            ))

        # Suggest improvements for hallucinated parameters
        if hallucinations > 0:
            confidence = min(0.92, 0.7 + (hallucinations / (len(pattern_list) * 2)))

            suggestions.append(PromptSuggestion(
                suggestion_id=f"tool_call_hallucination_{datetime.utcnow().timestamp()}",
                failure_pattern="Hallucinated tool parameters",
                current_prompt_issue="Agent generating parameters not defined in tool schema",
                proposed_improvement=(
                    "Add strict parameter validation prompt: "
                    "'ONLY use parameters defined in the tool schema. "
                    "If a parameter is not listed, do NOT create it. "
                    "Always validate parameters before calling the tool.'"
                ),
                rationale=(
                    f"Detected {hallucinations} hallucinated parameter errors "
                    f"across {len(pattern_list)} conversations. "
                    "Explicit validation instructions and schema clarity prevent hallucinations."
                ),
                confidence=confidence,
                affected_conversations=len(pattern_list),
                evaluator_types=[EvaluatorTypeEnum.TOOL_CALL.value]
            ))

        return suggestions

    def _suggest_llm_judge_improvements(
        self,
        pattern_list: List[Dict[str, Any]]
    ) -> List[PromptSuggestion]:
        """
        Generate suggestions for LLM judge (coherence/quality) failures.

        Args:
            pattern_list: List of LLM judge failure patterns

        Returns:
            List of PromptSuggestion objects
        """
        suggestions = []

        if not pattern_list:
            return suggestions

        # Analyze context loss in multi-turn conversations
        long_conversations = [
            p for p in pattern_list
            if p["turn_count"] >= 5
        ]

        if long_conversations:
            avg_score = sum(p["score"] for p in long_conversations) / len(long_conversations)

            if avg_score < 0.6:
                confidence = min(0.88, 0.65 + (1 - avg_score))

                suggestions.append(PromptSuggestion(
                    suggestion_id=f"llm_judge_context_{datetime.utcnow().timestamp()}",
                    failure_pattern="Context loss in multi-turn conversations",
                    current_prompt_issue="Agent loses track of conversation history in long exchanges",
                    proposed_improvement=(
                        "Add context retention instructions: "
                        "'Explicitly reference earlier user messages. "
                        "If the user mentioned something important in turn 1, refer back to it in later turns. "
                        "Maintain a mental model of the conversation arc.'"
                    ),
                    rationale=(
                        f"Detected low coherence scores ({avg_score:.2f}) "
                        f"in {len(long_conversations)} conversations with 5+ turns. "
                        "Explicit instructions to track context improve long-turn quality."
                    ),
                    confidence=confidence,
                    affected_conversations=len(long_conversations),
                    evaluator_types=[EvaluatorTypeEnum.LLM_JUDGE.value]
                ))

        return suggestions

    def _detect_annotator_disagreements(
        self,
        evaluations: List[Evaluation],
        conv_lookup: Dict[int, Conversation]
    ) -> List[AnnotatorDisagreement]:
        """
        Detect and classify annotator disagreements (Scenario 3).
        Routes conversations with disagreements to tiebreaker status.

        Args:
            evaluations: List of Evaluation records
            conv_lookup: Lookup table for conversations

        Returns:
            List of AnnotatorDisagreement records
        """
        disagreements = []

        # Group evaluations by conversation and evaluator type
        conv_evals = defaultdict(lambda: defaultdict(list))

        for eval_obj in evaluations:
            conv_id = eval_obj.conversation_id
            evaluator = eval_obj.evaluator_type.value
            conv_evals[conv_id][evaluator].append(eval_obj)

        # Check for disagreements within each conversation
        for conv_id, evaluator_scores in conv_evals.items():
            conv = conv_lookup.get(conv_id)
            if not conv:
                continue

            # Check feedback vs evaluator scores
            if conv.feedback:
                feedback_score = conv.feedback.user_rating / 5.0  # Normalize to 0-1

                for evaluator_type, eval_list in evaluator_scores.items():
                    if len(eval_list) > 0:
                        avg_eval_score = sum(e.score for e in eval_list) / len(eval_list)
                        score_delta = abs(feedback_score - avg_eval_score)

                        if score_delta >= self.DISAGREEMENT_THRESHOLD:
                            disagreement_type = self._classify_disagreement(
                                feedback_score,
                                avg_eval_score
                            )

                            disagreements.append(AnnotatorDisagreement(
                                conversation_id=conv_id,
                                annotator_1="human_annotator",
                                annotator_1_label=self._score_to_label(feedback_score),
                                annotator_2=evaluator_type,
                                annotator_2_label=self._score_to_label(avg_eval_score),
                                disagreement_type=disagreement_type,
                                confidence_delta=score_delta,
                                status=TiebreakerStatus.PENDING
                            ))

        return disagreements

    def _classify_disagreement(self, score1: float, score2: float) -> str:
        """
        Classify the type of disagreement.

        Args:
            score1: First annotator's score
            score2: Second annotator's score

        Returns:
            String classification of disagreement type
        """
        if score1 > 0.7 and score2 < 0.5:
            return "human_optimistic"
        elif score1 < 0.5 and score2 > 0.7:
            return "human_pessimistic"
        elif abs(score1 - score2) >= 0.5:
            return "major_disagreement"
        else:
            return "moderate_disagreement"

    def _score_to_label(self, score: float) -> str:
        """
        Convert normalized score to label.

        Args:
            score: Normalized score (0-1)

        Returns:
            Label string
        """
        if score >= 0.8:
            return "excellent"
        elif score >= 0.6:
            return "good"
        elif score >= 0.4:
            return "fair"
        else:
            return "poor"

    def route_to_tiebreaker(
        self,
        disagreement: AnnotatorDisagreement
    ) -> Dict[str, Any]:
        """
        Route a disagreement to tiebreaker resolution.
        This typically involves a human review or escalation to a higher-tier evaluator.

        Args:
            disagreement: AnnotatorDisagreement record

        Returns:
            Tiebreaker routing information
        """
        return {
            "conversation_id": disagreement.conversation_id,
            "tiebreaker_status": TiebreakerStatus.PENDING,
            "action": "route_to_human_review",
            "reason": (
                f"Disagreement between {disagreement.annotator_1} "
                f"(label: {disagreement.annotator_1_label}) and "
                f"{disagreement.annotator_2} "
                f"(label: {disagreement.annotator_2_label}). "
                f"Delta: {disagreement.confidence_delta:.2f}"
            ),
            "disagreement_type": disagreement.disagreement_type,
            "recommended_action": "Schedule manual review by senior evaluator",
            "created_at": datetime.utcnow().isoformat()
        }

    def resolve_tiebreaker(
        self,
        disagreement: AnnotatorDisagreement,
        final_label: str,
        resolver_notes: str
    ) -> Dict[str, Any]:
        """
        Resolve a tiebreaker disagreement.

        Args:
            disagreement: AnnotatorDisagreement record
            final_label: Final resolved label
            resolver_notes: Notes from the tiebreaker resolver

        Returns:
            Resolution information
        """
        disagreement.status = TiebreakerStatus.RESOLVED

        return {
            "conversation_id": disagreement.conversation_id,
            "tiebreaker_status": TiebreakerStatus.RESOLVED,
            "final_label": final_label,
            "resolver_notes": resolver_notes,
            "resolved_at": datetime.utcnow().isoformat(),
            "original_disagreement": {
                "annotator_1": disagreement.annotator_1,
                "annotator_1_label": disagreement.annotator_1_label,
                "annotator_2": disagreement.annotator_2,
                "annotator_2_label": disagreement.annotator_2_label,
                "disagreement_type": disagreement.disagreement_type,
            }
        }

    def escalate_tiebreaker(
        self,
        disagreement: AnnotatorDisagreement,
        escalation_reason: str
    ) -> Dict[str, Any]:
        """
        Escalate a tiebreaker to higher authority (e.g., team lead, third-party evaluator).

        Args:
            disagreement: AnnotatorDisagreement record
            escalation_reason: Reason for escalation

        Returns:
            Escalation information
        """
        disagreement.status = TiebreakerStatus.ESCALATED

        return {
            "conversation_id": disagreement.conversation_id,
            "tiebreaker_status": TiebreakerStatus.ESCALATED,
            "escalation_reason": escalation_reason,
            "escalated_at": datetime.utcnow().isoformat(),
            "escalation_target": "senior_evaluation_team",
            "original_disagreement": {
                "annotator_1": disagreement.annotator_1,
                "annotator_1_label": disagreement.annotator_1_label,
                "annotator_2": disagreement.annotator_2,
                "annotator_2_label": disagreement.annotator_2_label,
                "disagreement_type": disagreement.disagreement_type,
                "confidence_delta": disagreement.confidence_delta,
            }
        }

    def generate_self_update_report(
        self,
        analysis_results: Dict[str, Any],
        lookback_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive self-update report.

        Args:
            analysis_results: Results from analyze_evaluations
            lookback_hours: Lookback period in hours

        Returns:
            Comprehensive report
        """
        return {
            "report_type": "self_update_analysis",
            "generated_at": datetime.utcnow().isoformat(),
            "lookback_hours": lookback_hours,
            "summary": {
                "total_evaluations": analysis_results["metrics"]["total_evaluations"],
                "suggestions_count": analysis_results["metrics"]["total_suggestions"],
                "disagreements_count": analysis_results["metrics"]["disagreement_count"],
            },
            "suggestions": [
                {
                    "id": s.suggestion_id,
                    "pattern": s.failure_pattern,
                    "improvement": s.proposed_improvement,
                    "rationale": s.rationale,
                    "confidence": s.confidence,
                    "affected_count": s.affected_conversations,
                    "evaluators": s.evaluator_types,
                }
                for s in analysis_results["suggestions"]
            ],
            "disagreements": [
                {
                    "conversation_id": d.conversation_id,
                    "annotator_1": d.annotator_1,
                    "label_1": d.annotator_1_label,
                    "annotator_2": d.annotator_2,
                    "label_2": d.annotator_2_label,
                    "type": d.disagreement_type,
                    "delta": d.confidence_delta,
                    "status": d.status.value,
                    "action": "route_to_tiebreaker" if d.status == TiebreakerStatus.PENDING else "under_review",
                }
                for d in analysis_results["disagreements"]
            ],
            "patterns": analysis_results["patterns"],
            "recommendations": self._generate_recommendations(analysis_results),
        }

    def _generate_recommendations(
        self,
        analysis_results: Dict[str, Any]
    ) -> List[str]:
        """
        Generate actionable recommendations from analysis.

        Args:
            analysis_results: Results from analyze_evaluations

        Returns:
            List of recommendation strings
        """
        recommendations = []

        if analysis_results["metrics"]["total_suggestions"] > 0:
            top_suggestion = analysis_results["suggestions"][0]
            recommendations.append(
                f"Implement highest-confidence suggestion ({top_suggestion.confidence:.0%}): "
                f"{top_suggestion.failure_pattern}"
            )

        if analysis_results["metrics"]["disagreement_count"] > 0:
            recommendations.append(
                f"Review {analysis_results['metrics']['disagreement_count']} annotator disagreements "
                "and schedule tiebreaker resolutions"
            )

        if len(analysis_results["patterns"]) > 1:
            recommendations.append(
                "Multiple evaluator types showing patterns; consider cross-evaluator improvement strategy"
            )

        return recommendations
