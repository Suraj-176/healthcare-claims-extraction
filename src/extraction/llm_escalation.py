"""
llm_escalation.py

Skeleton Pass version: defines the interface for confidence-driven escalation without
requiring an API key to be present to run the rest of the pipeline. If ANTHROPIC_API_KEY is
set in the environment, a real cropped-region vision-LLM call is attempted; otherwise this
stage is cleanly skipped and reported as such — never a crash, never a silent no-op.

Depth Pass 4 expands this to: crop the actual low-confidence field's bounding box (not the
whole page) and send only that crop, tagging each escalated field with its extraction method
for cost tracking.
"""

from __future__ import annotations

import base64
import logging
import os

import numpy as np
from PIL import Image
import io

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional, env vars can be set manually

# Import retry logic for production resilience
try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type
    )
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False
    # Graceful degradation - create no-op decorator if tenacity not installed
    def retry(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    def stop_after_attempt(*args): pass
    def wait_exponential(*args, **kwargs): pass
    def retry_if_exception_type(*args): pass

logger = logging.getLogger(__name__)

# Auto-detect which LLM provider is configured (priority order)
LLM_PROVIDER = None
if os.environ.get("AZURE_OPENAI_KEY"):
    LLM_PROVIDER = "azure_openai"
elif os.environ.get("OPENAI_API_KEY"):
    LLM_PROVIDER = "openai"
elif os.environ.get("GOOGLE_API_KEY"):
    LLM_PROVIDER = "gemini"
elif os.environ.get("ANTHROPIC_API_KEY"):
    LLM_PROVIDER = "anthropic"
elif os.environ.get("GROQ_API_KEY"):
    LLM_PROVIDER = "groq"
elif os.environ.get("OLLAMA_BASE_URL"):
    LLM_PROVIDER = "ollama"


def _image_to_base64_png(img: np.ndarray) -> str:
    pil_img = Image.fromarray(img)
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    retry=retry_if_exception_type((Exception,)),
    reraise=True
)
def _call_azure_openai(image_b64: str, prompt: str) -> str:
    """Call Azure OpenAI GPT-4 Vision API with retry logic and timeout."""
    try:
        from openai import AzureOpenAI
    except ImportError:
        raise ImportError("openai package not installed. Run: pip install openai")
    
    client = AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        timeout=30.0  # 30 second timeout
    )
    
    response = client.chat.completions.create(
        model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
                ]
            }
        ],
        max_tokens=500
    )
    
    return response.choices[0].message.content


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    retry=retry_if_exception_type((Exception,)),
    reraise=True
)
def _call_gemini(image_b64: str, prompt: str) -> str:
    """Call Google Gemini Vision API with retry logic."""
    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError("google-generativeai package not installed. Run: pip install google-generativeai")
    
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    model_name = os.environ.get("GOOGLE_MODEL", "gemini-1.5-flash")
    model = genai.GenerativeModel(model_name)
    
    # Convert base64 to bytes for Gemini
    image_bytes = base64.b64decode(image_b64)
    
    # Gemini has built-in timeout handling, but we wrap for consistency
    response = model.generate_content(
        [
            prompt,
            {"mime_type": "image/png", "data": image_bytes}
        ],
        request_options={"timeout": 30}  # 30 second timeout
    )
    
    return response.text


def _call_anthropic(image_b64: str, prompt: str) -> str:
    """Call Anthropic Claude Vision API."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package not installed. Run: pip install anthropic")
    
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model_name = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    
    response = client.messages.create(
        model=model_name,
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_b64}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    
    return "".join(block.text for block in response.content if getattr(block, "type", None) == "text")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    retry=retry_if_exception_type((Exception,)),
    reraise=True
)
def _call_openai(image_b64: str, prompt: str) -> str:
    """Call OpenAI GPT-4 Vision API (standard API) with retry logic and timeout."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai package not installed. Run: pip install openai")
    
    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        timeout=30.0  # 30 second timeout
    )
    model_name = os.environ.get("OPENAI_MODEL", "gpt-4o")
    
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
                ]
            }
        ],
        max_tokens=500
    )
    
    return response.choices[0].message.content


def _call_groq(image_b64: str, prompt: str) -> str:
    """Call Groq Vision API."""
    try:
        from groq import Groq
    except ImportError:
        raise ImportError("groq package not installed. Run: pip install groq")
    
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    model_name = os.environ.get("GROQ_MODEL", "llama-3.2-90b-vision-preview")
    
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
                ]
            }
        ],
        max_tokens=500
    )
    
    return response.choices[0].message.content


def _call_ollama(image_b64: str, prompt: str) -> str:
    """Call Ollama (local/self-hosted) Vision API."""
    try:
        import requests
    except ImportError:
        raise ImportError("requests package not installed. Run: pip install requests")
    
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    model_name = os.environ.get("OLLAMA_MODEL", "llama3.2-vision")
    
    response = requests.post(
        f"{base_url}/api/generate",
        json={
            "model": model_name,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False
        }
    )
    response.raise_for_status()
    
    return response.json()["response"]


def escalate_low_confidence_fields(img: np.ndarray, low_confidence_words: list[dict]) -> dict:
    """
    Attempts to escalate low-confidence OCR words to a vision-LLM for re-reading. Never
    raises: missing API key, network failure, or malformed response all return a clearly
    tagged 'skipped' or 'failed' status rather than stopping the pipeline.
    
    Supports: Azure OpenAI, OpenAI, Google Gemini, Anthropic Claude, Groq, Ollama.
    Auto-detects which provider is configured via .env file.
    """
    if not low_confidence_words:
        return {"status": "ok", "stage": "llm_escalation", "escalated": False,
                "reason": "no low-confidence fields to escalate"}

    if not LLM_PROVIDER:
        return {"status": "skipped", "stage": "llm_escalation", "escalated": False,
                "reason": "No LLM API key configured. See .env file for supported providers"}

    try:
        image_b64 = _image_to_base64_png(img)
        words_hint = ", ".join(w["word"] for w in low_confidence_words[:20])
        
        prompt = (
            "This is a scanned healthcare claim form. Standard OCR had low "
            f"confidence on these words: {words_hint}. Please re-read the form "
            "carefully and provide the correct values for any of these fields you "
            "can identify, as plain text."
        )
        
        # Call appropriate LLM provider
        if LLM_PROVIDER == "azure_openai":
            text_out = _call_azure_openai(image_b64, prompt)
        elif LLM_PROVIDER == "openai":
            text_out = _call_openai(image_b64, prompt)
        elif LLM_PROVIDER == "gemini":
            text_out = _call_gemini(image_b64, prompt)
        elif LLM_PROVIDER == "anthropic":
            text_out = _call_anthropic(image_b64, prompt)
        elif LLM_PROVIDER == "groq":
            text_out = _call_groq(image_b64, prompt)
        elif LLM_PROVIDER == "ollama":
            text_out = _call_ollama(image_b64, prompt)
        else:
            return {"status": "failed", "stage": "llm_escalation", "escalated": False, 
                    "reason": f"Unknown LLM provider: {LLM_PROVIDER}"}
        
        return {
            "status": "ok", "stage": "llm_escalation", "escalated": True,
            "llm_output": text_out, "extraction_method": "llm_escalated",
            "fields_escalated": len(low_confidence_words),
            "provider": LLM_PROVIDER,
        }
    except Exception as exc:
        logger.error("LLM escalation call failed: %s", exc)
        return {"status": "failed", "stage": "llm_escalation", "escalated": False, "reason": str(exc)}
