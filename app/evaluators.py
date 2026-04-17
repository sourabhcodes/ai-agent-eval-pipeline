"""
Evaluators for the AI Agent Evaluation Pipeline.
Implements Strategy Pattern with multiple evaluation strategies.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass
import json
import re

from app.models import Conversation, Turn, Evaluation, EvaluatorTypeEnum, RoleEnum


@dataclass
class EvaluationResult:
    """Container for evaluation results."""
    evaluator_type: EvaluatorTypeEnum
    score: float  # Normalized 0-1
    details: Dict[str, Any]
    metrics: Dict[str, Any]


class Evaluator(ABC):
    """
    Abstract base class for all evaluators.
    Implements Strategy Pattern for pluggable evaluation strategies.
    """

    def __init__(self, name: str):
        """
        Initialize evaluator.
        
        Args:
            name: Name of the evaluator
        """
        self.name = name

    @abstractmethod
    def evaluate(self, conversation: Conversation) -> EvaluationResult:
        """
        Evaluate a conversation.
        
        Args:
            conversation: Conversation object to evaluate
            
        Returns:
            EvaluationResult with score and details
        """
        pass

    def _normalize_score(self, score: float, min_val: float = 0, max_val: float = 1) -> float:
        """
        Normalize score to 0-1 range.
        
        Args:
            score: Raw score value
            min_val: Minimum expected value
            max_val: Maximum expected value
            
        Returns:
            Normalized score in 0-1 range
        """
        if max_val == min_val:
            return 0.0
        normalized = (score - min_val) / (max_val - min_val)
        return max(0.0, min(1.0, normalized))


# ============================================================================
# CONCRETE EVALUATORS
# ============================================================================

class HeuristicEvaluator(Evaluator):
    """
    Evaluates conversations based on heuristic rules.
    Checks latency (response time) and format compliance.
    """

    LATENCY_THRESHOLD_MS = 1000  # Threshold in milliseconds
    MAX_LATENCY_MS = 5000  # Maximum latency for normalization

    def __init__(self):
        """Initialize HeuristicEvaluator."""
        super().__init__("HeuristicEvaluator")

    def evaluate(self, conversation: Conversation) -> EvaluationResult:
        """
        Evaluate conversation using heuristic rules.
        Primarily checks latency of assistant responses.
        
        Args:
            conversation: Conversation to evaluate
            
        Returns:
            EvaluationResult with latency score
        """
        if not conversation.turns or len(conversation.turns) < 2:
            return EvaluationResult(
                evaluator_type=EvaluatorTypeEnum.HEURISTIC,
                score=1.0,
                details={"reason": "Insufficient turns for evaluation"},
                metrics={}
            )

        latencies = []
        violations = 0

        # Extract latencies between user and assistant turns
        for i, turn in enumerate(conversation.turns):
            if turn.role == RoleEnum.ASSISTANT and i > 0:
                prev_turn = conversation.turns[i - 1]
                if prev_turn.created_at and turn.created_at:
                    latency_ms = (turn.created_at - prev_turn.created_at).total_seconds() * 1000
                    latencies.append(latency_ms)

                    # Check for threshold violations
                    if latency_ms > self.LATENCY_THRESHOLD_MS:
                        violations += 1

        if not latencies:
            return EvaluationResult(
                evaluator_type=EvaluatorTypeEnum.HEURISTIC,
                score=1.0,
                details={"reason": "No latency data available"},
                metrics={}
            )

        # Calculate score based on latency violations
        avg_latency = sum(latencies) / len(latencies)
        violation_ratio = violations / len(latencies)
        
        # Score: fewer violations and lower latency = higher score
        latency_score = 1.0 - min(1.0, avg_latency / self.MAX_LATENCY_MS)
        violation_score = 1.0 - violation_ratio

        # Weight latency and violations equally
        final_score = (latency_score + violation_score) / 2

        return EvaluationResult(
            evaluator_type=EvaluatorTypeEnum.HEURISTIC,
            score=final_score,
            details={
                "violations": violations,
                "total_responses": len(latencies),
                "violation_ratio": violation_ratio,
                "threshold_ms": self.LATENCY_THRESHOLD_MS,
            },
            metrics={
                "avg_latency_ms": avg_latency,
                "max_latency_ms": max(latencies),
                "min_latency_ms": min(latencies),
            }
        )


class ToolCallEvaluator(Evaluator):
    """
    Evaluates tool calls for accuracy and hallucination detection.
    Detects Scenario 1: Incorrect date formats and hallucinated parameters.
    """

    # Date format patterns
    VALID_DATE_FORMATS = [
        r'^\d{4}-\d{2}-\d{2}$',  # YYYY-MM-DD
        r'^\d{1,2}/\d{1,2}/\d{4}$',  # MM/DD/YYYY or M/D/YYYY
        r'^\d{1,2}-\d{1,2}-\d{4}$',  # MM-DD-YYYY or M-D-YYYY
    ]

    # Common tool parameter names
    KNOWN_PARAMETERS = {
        "date", "start_date", "end_date", "timestamp", "query", "id",
        "limit", "offset", "format", "user_id", "session_id", "action"
    }

    def __init__(self):
        """Initialize ToolCallEvaluator."""
        super().__init__("ToolCallEvaluator")

    def evaluate(self, conversation: Conversation) -> EvaluationResult:
        """
        Evaluate tool calls for correctness and hallucinations.
        
        Args:
            conversation: Conversation to evaluate
            
        Returns:
            EvaluationResult with tool call accuracy score
        """
        issues = {
            "invalid_date_formats": [],
            "hallucinated_parameters": [],
            "malformed_calls": []
        }
        total_tool_calls = 0

        # Iterate through turns and extract tool calls
        for turn in conversation.turns:
            if turn.role == RoleEnum.ASSISTANT and turn.tool_calls:
                tool_call_list = turn.tool_calls if isinstance(turn.tool_calls, list) else []
                
                for tool_call in tool_call_list:
                    total_tool_calls += 1

                    # Check if tool call is properly formatted
                    if not isinstance(tool_call, dict):
                        issues["malformed_calls"].append({"call": tool_call, "reason": "Not a dictionary"})
                        continue

                    # Extract parameters
                    params = tool_call.get("parameters", {})
                    if not isinstance(params, dict):
                        issues["malformed_calls"].append({"call": tool_call, "reason": "Parameters not a dictionary"})
                        continue

                    # Check for date format issues
                    date_issues = self._check_date_formats(params)
                    issues["invalid_date_formats"].extend(date_issues)

                    # Check for hallucinated parameters
                    hallucinated = self._detect_hallucinated_parameters(params)
                    issues["hallucinated_parameters"].extend(hallucinated)

        if total_tool_calls == 0:
            return EvaluationResult(
                evaluator_type=EvaluatorTypeEnum.TOOL_CALL,
                score=1.0,
                details={"reason": "No tool calls detected"},
                metrics={}
            )

        # Calculate score
        total_issues = (
            len(issues["invalid_date_formats"]) +
            len(issues["hallucinated_parameters"]) * 2 +  # Hallucinations are more severe
            len(issues["malformed_calls"]) * 3  # Malformed calls are most severe
        )

        issue_ratio = total_issues / total_tool_calls
        score = max(0.0, 1.0 - issue_ratio)

        return EvaluationResult(
            evaluator_type=EvaluatorTypeEnum.TOOL_CALL,
            score=score,
            details={
                "issues": issues,
                "total_tool_calls": total_tool_calls,
                "issue_count": total_issues,
            },
            metrics={
                "invalid_date_formats": len(issues["invalid_date_formats"]),
                "hallucinated_parameters": len(issues["hallucinated_parameters"]),
                "malformed_calls": len(issues["malformed_calls"]),
            }
        )

    def _check_date_formats(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Check parameters for invalid date formats (Scenario 1).
        
        Args:
            params: Tool call parameters
            
        Returns:
            List of date format issues
        """
        issues = []

        for key, value in params.items():
            if "date" in key.lower() or "time" in key.lower():
                if isinstance(value, str):
                    if not self._is_valid_date_format(value):
                        issues.append({
                            "parameter": key,
                            "value": value,
                            "issue": "Invalid date format"
                        })

        return issues

    def _is_valid_date_format(self, value: str) -> bool:
        """
        Validate date format against known patterns.
        
        Args:
            value: Date string to validate
            
        Returns:
            True if valid format, False otherwise
        """
        for pattern in self.VALID_DATE_FORMATS:
            if re.match(pattern, value):
                return True
        return False

    def _detect_hallucinated_parameters(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Detect hallucinated or unexpected parameters.
        
        Args:
            params: Tool call parameters
            
        Returns:
            List of hallucinated parameters
        """
        hallucinated = []

        for key in params.keys():
            if key.lower() not in self.KNOWN_PARAMETERS and not self._is_reasonable_parameter(key):
                hallucinated.append({
                    "parameter": key,
                    "value": params[key],
                    "reason": "Unexpected parameter name"
                })

        return hallucinated

    def _is_reasonable_parameter(self, param_name: str) -> bool:
        """
        Check if parameter name is reasonably formed.
        
        Args:
            param_name: Parameter name to check
            
        Returns:
            True if reasonable, False if clearly hallucinated
        """
        # Allow snake_case or camelCase parameters
        if re.match(r'^[a-z_][a-z0-9_]*$', param_name, re.IGNORECASE):
            return True
        
        # Reject obviously malformed names
        if len(param_name) > 50 or param_name.count("_") > 5:
            return False
        
        return True


class MultiTurnEvaluator(Evaluator):
    """
    Evaluates context retention across multiple turns.
    Detects Scenario 2: Context loss over 5+ turns using LLM-as-judge.
    """

    CONTEXT_LOSS_THRESHOLD_TURNS = 5

    def __init__(self, llm_client=None):
        """
        Initialize MultiTurnEvaluator.
        
        Args:
            llm_client: Optional OpenAI client for LLM-as-judge. If None, uses heuristic fallback.
        """
        super().__init__("MultiTurnEvaluator")
        self.llm_client = llm_client

    def evaluate(self, conversation: Conversation) -> EvaluationResult:
        """
        Evaluate context retention across conversation turns.
        Uses LLM-as-judge for multi-turn conversations (5+ turns).
        
        Args:
            conversation: Conversation to evaluate
            
        Returns:
            EvaluationResult with context retention score
        """
        turn_count = len(conversation.turns)

        if turn_count < self.CONTEXT_LOSS_THRESHOLD_TURNS:
            # For shorter conversations, use heuristic check
            return self._heuristic_context_check(conversation)

        # For longer conversations, use LLM-as-judge
        if self.llm_client:
            return self._llm_context_evaluation(conversation)
        else:
            return self._heuristic_context_check(conversation)

    def _heuristic_context_check(self, conversation: Conversation) -> EvaluationResult:
        """
        Heuristic check for context loss.
        Looks for indicators like repetition and lack of reference to prior messages.
        
        Args:
            conversation: Conversation to evaluate
            
        Returns:
            EvaluationResult
        """
        turn_count = len(conversation.turns)
        repetitions = 0
        context_violations = 0

        # Check for repeated phrases (indicator of context loss)
        assistant_messages = [
            turn.content for turn in conversation.turns
            if turn.role == RoleEnum.ASSISTANT
        ]

        # Simple repetition detection
        for i, msg in enumerate(assistant_messages):
            if i > 0 and self._has_high_similarity(msg, assistant_messages[i - 1]):
                repetitions += 1

        # Check for context violations: assistant not referencing prior context
        if turn_count >= self.CONTEXT_LOSS_THRESHOLD_TURNS:
            user_turns = [
                turn.content for turn in conversation.turns
                if turn.role == RoleEnum.USER
            ]
            
            # Check if assistant's recent responses reference earlier user inputs
            if len(user_turns) > 2:
                recent_assistant = assistant_messages[-1] if assistant_messages else ""
                early_user_content = " ".join(user_turns[:2]).lower()
                
                if not self._has_contextual_reference(recent_assistant, early_user_content):
                    context_violations += 1

        # Calculate score
        violation_ratio = (repetitions + context_violations) / max(1, len(assistant_messages))
        score = max(0.0, 1.0 - violation_ratio)

        return EvaluationResult(
            evaluator_type=EvaluatorTypeEnum.LLM_JUDGE,
            score=score,
            details={
                "method": "heuristic",
                "repetitions_detected": repetitions,
                "context_violations": context_violations,
                "turn_count": turn_count,
            },
            metrics={
                "repetition_ratio": repetitions / max(1, len(assistant_messages)),
                "context_violation_ratio": violation_ratio,
            }
        )

    def _llm_context_evaluation(self, conversation: Conversation) -> EvaluationResult:
        """
        Use LLM-as-judge to evaluate context retention.
        
        Args:
            conversation: Conversation to evaluate
            
        Returns:
            EvaluationResult
        """
        # Prepare conversation text for LLM evaluation
        conversation_text = self._format_conversation_for_llm(conversation)

        try:
            # Call LLM to evaluate context coherence and retention
            response = self.llm_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert evaluator of conversation quality.
                        Analyze the provided conversation for context loss and coherence.
                        Rate on a scale of 0-1 how well context is maintained across turns.
                        Look for: (1) Repetition of explanations, (2) Forgetting prior user statements,
                        (3) Inconsistent responses to similar queries.
                        Respond with ONLY a JSON object: {"score": <0-1>, "issues": [<list of issues>]}"""
                    },
                    {
                        "role": "user",
                        "content": f"Evaluate this conversation:\n\n{conversation_text}"
                    }
                ],
                temperature=0.2,
                max_tokens=500
            )

            # Parse LLM response
            try:
                result = json.loads(response.choices[0].message.content)
                score = float(result.get("score", 0.5))
                issues = result.get("issues", [])
            except (json.JSONDecodeError, ValueError):
                # Fallback to heuristic if LLM response parsing fails
                return self._heuristic_context_check(conversation)

            return EvaluationResult(
                evaluator_type=EvaluatorTypeEnum.LLM_JUDGE,
                score=score,
                details={
                    "method": "llm_as_judge",
                    "issues": issues,
                    "turn_count": len(conversation.turns),
                },
                metrics={
                    "llm_score": score,
                    "issue_count": len(issues),
                }
            )

        except Exception as e:
            # Fallback to heuristic on LLM call failure
            return self._heuristic_context_check(conversation)

    def _format_conversation_for_llm(self, conversation: Conversation) -> str:
        """
        Format conversation for LLM evaluation.
        
        Args:
            conversation: Conversation to format
            
        Returns:
            Formatted conversation string
        """
        lines = []
        for turn in conversation.turns:
            role = turn.role.value.upper()
            lines.append(f"{role}: {turn.content}")
        return "\n".join(lines)

    def _has_high_similarity(self, text1: str, text2: str, threshold: float = 0.7) -> bool:
        """
        Simple similarity check between two texts.
        
        Args:
            text1: First text
            text2: Second text
            threshold: Similarity threshold (0-1)
            
        Returns:
            True if texts are similar
        """
        # Simple word overlap check
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return False
        
        overlap = len(words1 & words2) / len(words1 | words2)
        return overlap > threshold

    def _has_contextual_reference(self, recent_text: str, early_context: str) -> bool:
        """
        Check if recent text references early context.
        
        Args:
            recent_text: Recent assistant message
            early_context: Early user context (lowercase)
            
        Returns:
            True if reference is found
        """
        recent_lower = recent_text.lower()
        
        # Extract key terms from early context
        key_terms = [word for word in early_context.split() if len(word) > 4]
        
        # Check for references to early context
        references = sum(1 for term in key_terms if term in recent_lower)
        
        return references > 0
