"""Tests for intent classification."""
from __future__ import annotations

import pytest

from daily_task_assistant.llm.intent_classifier import (
    ClassifiedIntent,
    _quick_classify,
    INTENT_PROFILES,
)


class TestQuickClassify:
    """Test keyword-based quick classification."""
    
    def test_action_intent_mark_done(self):
        """Action keywords should return action intent."""
        result = _quick_classify("mark it done", has_selected_images=False)
        assert result is not None
        assert result.intent == "action"
        assert result.confidence >= 0.9
        assert "update_task" in result.tools_needed
    
    def test_action_intent_change_status(self):
        """Change status should trigger action intent."""
        result = _quick_classify("change status to blocked", has_selected_images=False)
        assert result is not None
        assert result.intent == "action"
    
    def test_action_intent_mark_complete(self):
        """Mark complete should trigger action intent."""
        result = _quick_classify("mark as complete please", has_selected_images=False)
        assert result is not None
        assert result.intent == "action"
    
    def test_action_intent_close_this(self):
        """Close this should trigger action intent."""
        result = _quick_classify("close this task", has_selected_images=False)
        assert result is not None
        assert result.intent == "action"
    
    def test_visual_intent_with_images(self):
        """Visual keywords with selected images should return visual intent."""
        result = _quick_classify("what do you see in this image?", has_selected_images=True)
        assert result is not None
        assert result.intent == "visual"
        assert result.include_images is True
    
    def test_visual_intent_without_images(self):
        """Visual keywords without selected images should still return visual intent."""
        result = _quick_classify("describe the picture", has_selected_images=False)
        assert result is not None
        assert result.intent == "visual"
        assert result.include_images is False  # No images to include
    
    def test_research_intent(self):
        """Research keywords should return research intent."""
        result = _quick_classify("research the best practices for this", has_selected_images=False)
        assert result is not None
        assert result.intent == "research"
        assert "web_search" in result.tools_needed
    
    def test_email_intent(self):
        """Email keywords should return email intent."""
        result = _quick_classify("draft an email to the client", has_selected_images=False)
        assert result is not None
        assert result.intent == "email"
    
    def test_ambiguous_returns_none(self):
        """Ambiguous messages should return None for LLM classification."""
        result = _quick_classify("what should I do next?", has_selected_images=False)
        assert result is None  # Needs LLM
    
    def test_general_question_returns_none(self):
        """General questions should return None for LLM classification."""
        result = _quick_classify("can you help me with this task?", has_selected_images=False)
        assert result is None  # Needs LLM


class TestIntentProfiles:
    """Test intent profile configuration."""
    
    def test_all_intents_have_profiles(self):
        """All intent types should have configured profiles."""
        expected_intents = ["action", "visual", "conversational", "research", "email", "planning"]
        for intent in expected_intents:
            assert intent in INTENT_PROFILES
    
    def test_action_profile_no_history(self):
        """Action intent should not include history."""
        profile = INTENT_PROFILES["action"]
        assert profile["include_history"] is False
    
    def test_conversational_includes_history(self):
        """Conversational intent should include history."""
        profile = INTENT_PROFILES["conversational"]
        assert profile["include_history"] is True
    
    def test_visual_includes_images(self):
        """Visual intent should include images."""
        profile = INTENT_PROFILES["visual"]
        assert profile["include_images"] is True


class TestClassifiedIntent:
    """Test ClassifiedIntent dataclass."""
    
    def test_default_values(self):
        """Test default values for ClassifiedIntent."""
        intent = ClassifiedIntent(intent="conversational")
        assert intent.intent == "conversational"
        assert intent.tools_needed == []
        assert intent.include_images is False
        assert intent.include_history is True
        assert intent.include_workspace is True
        assert intent.confidence == 0.9
        assert intent.suggested_model == "claude-sonnet"

