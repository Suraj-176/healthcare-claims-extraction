"""
Tests for llm_escalation.py with multi-provider support.

Tests verify: 
(1) The module behaves correctly with no API key configured (graceful skip, not a crash)
(2) The request is constructed correctly and responses are parsed correctly
(3) Error handling works correctly (never crashes)

These tests work with the multi-provider architecture (Azure OpenAI, OpenAI, Gemini, 
Anthropic, Groq, Ollama). They mock the provider-specific call functions to avoid 
requiring real API keys during testing.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
from extraction.llm_escalation import escalate_low_confidence_fields


def test_no_api_key_skips_gracefully():
    """Test that when NO provider keys are configured, escalation is skipped gracefully."""
    # Mock LLM_PROVIDER to be None (simulating no API keys configured)
    with patch("extraction.llm_escalation.LLM_PROVIDER", None):
        img = np.zeros((50, 50), dtype=np.uint8)
        result = escalate_low_confidence_fields(img, [{"word": "patient_dob", "confidence": 40.0}])
        assert result["status"] == "skipped"
        assert result["escalated"] is False
        assert "No LLM API key configured" in result["reason"]


def test_no_low_confidence_fields_skips_without_calling_api():
    """Test that when there are no low-confidence fields, no API call is made."""
    img = np.zeros((50, 50), dtype=np.uint8)
    result = escalate_low_confidence_fields(img, [])
    assert result["status"] == "ok"
    assert result["escalated"] is False


def test_mocked_api_call_constructs_request_and_parses_response():
    """
    Verifies the request payload shape and response parsing logic without a real network
    call — proves the code path is correct up to the actual API boundary.
    
    This test works with any configured provider by mocking the provider-specific function.
    """
    img = np.zeros((50, 50), dtype=np.uint8)
    
    # Mock the Azure OpenAI call function (since it's the default provider when configured)
    with patch("extraction.llm_escalation.LLM_PROVIDER", "azure_openai"):
        with patch("extraction.llm_escalation._call_azure_openai") as mock_call:
            mock_call.return_value = "patient_dob: 12-02-1932"
            
            result = escalate_low_confidence_fields(img, [{"word": "patient_dob", "confidence": 40.0}])

        assert result["status"] == "ok"
        assert result["escalated"] is True
        assert "patient_dob: 12-02-1932" in result["llm_output"]
        assert result["extraction_method"] == "llm_escalated"
        assert result["provider"] == "azure_openai"
        
        # Verify the function was called with correct parameters
        assert mock_call.called
        call_args = mock_call.call_args
        assert len(call_args[0]) == 2  # image_b64, prompt
        assert "patient_dob" in call_args[0][1]  # prompt contains the field name


def test_api_failure_never_crashes():
    """Test that API failures are caught and returned as failed status, not exceptions."""
    img = np.zeros((50, 50), dtype=np.uint8)
    
    # Mock the Azure OpenAI call to raise an exception
    with patch("extraction.llm_escalation.LLM_PROVIDER", "azure_openai"):
        with patch("extraction.llm_escalation._call_azure_openai") as mock_call:
            mock_call.side_effect = Exception("simulated network failure")
            
            result = escalate_low_confidence_fields(img, [{"word": "patient_dob", "confidence": 40.0}])

        assert result["status"] == "failed"
        assert result["escalated"] is False
        assert "simulated network failure" in result["reason"]
