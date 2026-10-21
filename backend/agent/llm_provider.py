import os
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class BaseLLMProvider(ABC):
    @abstractmethod
    def generate_patch(
        self,
        leaking_code: str,
        suspect_commit: Dict[str, Any],
        error_trace: Optional[str] = None,
        attempt: int = 1
    ) -> Dict[str, Any]:
        pass

class CachedProvider(BaseLLMProvider):
    """
    Cached response provider allowing complete offline demo execution with zero API keys.
    Emits attempt 1 flawed patch to exercise sandbox failure, then attempt 2 working patch.
    """
    def __init__(self):
        self.cached_dir = Path(__file__).resolve().parent / "cached_responses"

    def generate_patch(
        self,
        leaking_code: str,
        suspect_commit: Dict[str, Any],
        error_trace: Optional[str] = None,
        attempt: int = 1
    ) -> Dict[str, Any]:
        logger.info(f"Using CachedProvider for attempt #{attempt}")
        file_to_load = self.cached_dir / f"attempt_{attempt}.json"
        if not file_to_load.exists():
            file_to_load = self.cached_dir / "attempt_2.json"
        
        with open(file_to_load, "r") as f:
            data = json.load(f)
        return data

class GeminiProvider(BaseLLMProvider):
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")

    def generate_patch(
        self,
        leaking_code: str,
        suspect_commit: Dict[str, Any],
        error_trace: Optional[str] = None,
        attempt: int = 1
    ) -> Dict[str, Any]:
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not configured. Falling back to CachedProvider.")
            return CachedProvider().generate_patch(leaking_code, suspect_commit, error_trace, attempt)

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            
            prompt = (
                f"You are an SRE autonomous fixing agent. Repair the following leaking code.\n"
                f"Suspect Commit: {suspect_commit.get('sha')} - {suspect_commit.get('message')}\n"
                f"File: {suspect_commit.get('file', 'analytics/views.py')}\n"
                f"Leaking Code:\n{leaking_code}\n\n"
            )
            if error_trace:
                prompt += f"Previous attempt failed in test sandbox with stack trace:\n{error_trace}\n"

            prompt += (
                "Return a JSON object with keys: patch (full python function), "
                "unified_diff (standard git diff), reasoning (1 sentence), confidence (0.0 to 1.0), risk ('Low'|'Med'|'High')."
            )

            response = model.generate_content(prompt)
            # Parse json from response
            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
            return json.loads(text.strip())
        except Exception as e:
            logger.warning(f"Gemini API call failed ({e}). Falling back to CachedProvider.")
            return CachedProvider().generate_patch(leaking_code, suspect_commit, error_trace, attempt)

class VertexAIProvider(BaseLLMProvider):
    def __init__(self, project_id: str = None, location: str = "us-central1"):
        self.project_id = project_id or os.environ.get("VERTEX_PROJECT_ID", "")
        self.location = location or os.environ.get("VERTEX_LOCATION", "us-central1")

    def generate_patch(
        self,
        leaking_code: str,
        suspect_commit: Dict[str, Any],
        error_trace: Optional[str] = None,
        attempt: int = 1
    ) -> Dict[str, Any]:
        if not self.project_id:
            logger.warning("VERTEX_PROJECT_ID not set. Falling back to CachedProvider.")
            return CachedProvider().generate_patch(leaking_code, suspect_commit, error_trace, attempt)
        # Fallback to cached if credentials not authenticated
        return CachedProvider().generate_patch(leaking_code, suspect_commit, error_trace, attempt)

def get_llm_provider(mode: str = "cached") -> BaseLLMProvider:
    if mode == "live" and os.environ.get("GEMINI_API_KEY"):
        return GeminiProvider()
    elif mode == "vertex":
        return VertexAIProvider()
    return CachedProvider()
