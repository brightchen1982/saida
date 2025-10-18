from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from .config import Settings
from .exceptions import ConfigurationError, ExternalServiceError

logger = logging.getLogger(__name__)


@dataclass
class DashScopeResult:
    """Structured representation of the DashScope multimodal response."""

    summary: str
    fire_detected: bool
    confidence: Optional[float]
    raw_response: Dict[str, Any]


class DashScopeClient:
    """Encapsulate DashScope API calls with retry-aware pooled HTTP sessions."""

    def __init__(self, session: requests.Session, settings: Settings) -> None:
        self._session = session
        self._api_key = settings.dashscope_api_key
        self._endpoint = settings.dashscope_endpoint
        self._model = settings.dashscope_model
        self._timeout = settings.dashscope_timeout
        self._force_mock = settings.dashscope_force_mock
        self._analysis_prompt = settings.analysis_prompt

        if not self._endpoint:
            raise ConfigurationError("DashScope endpoint is not configured.")

    def analyze_image(
        self,
        image_bytes: bytes,
        image_format: str,
        request_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> DashScopeResult:
        """Submit an image for analysis, handling retries, parsing, and mock fallbacks."""
        if (not self._api_key) and not self._force_mock:
            raise ConfigurationError(
                "DashScope API key is not configured. Set DASHSCOPE_API_KEY or enable mock mode."
            )

        if self._force_mock or not self._api_key:
            return self._mock_response(context)

        encoded_image = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:image/{image_format or 'jpeg'};base64,{encoded_image}"
        messages = self._build_messages(data_url, context)
        payload = {"model": self._model, "messages": messages}

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        logger.info("Dispatching DashScope request %s for model %s", request_id, self._model)
        try:
            response = self._session.post(
                self._endpoint,
                headers=headers,
                json=payload,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            logger.exception("DashScope HTTP call failed for request %s", request_id)
            raise ExternalServiceError(
                "Failed to connect to DashScope service.",
                details={"request_id": request_id, "error": str(exc)},
            ) from exc

        if response.status_code >= 400:
            truncated_body = response.text[:600]
            logger.error(
                "DashScope returned HTTP %s for request %s: %s",
                response.status_code,
                request_id,
                truncated_body,
            )
            raise ExternalServiceError(
                f"DashScope API returned HTTP {response.status_code}.",
                details={"body": truncated_body, "request_id": request_id},
            )

        try:
            payload_json = response.json()
        except json.JSONDecodeError as exc:
            logger.exception("DashScope response was not valid JSON for request %s", request_id)
            raise ExternalServiceError(
                "DashScope response parsing failed.",
                details={"body": response.text[:600], "request_id": request_id},
            ) from exc

        summary = self._extract_summary(payload_json)
        confidence = self._extract_confidence(summary)
        fire_detected = self._infer_fire_detection(summary, context, confidence)

        logger.info(
            "DashScope completed request %s fire_detected=%s confidence=%s",
            request_id,
            fire_detected,
            f"{confidence:.3f}" if confidence is not None else "unknown",
        )

        return DashScopeResult(
            summary=summary or "DashScope analysis completed without textual summary.",
            fire_detected=fire_detected,
            confidence=confidence,
            raw_response=payload_json,
        )

    def _mock_response(self, context: Optional[Dict[str, Any]]) -> DashScopeResult:
        local_probability = float(context.get("local_probability", 0.0)) if context else 0.0
        fire_detected = local_probability >= 0.5
        summary = (
            "[Mock] Local heuristic indicates a {0:.1f}% probability of visible fire or smoke. "
            "No external analysis was performed.".format(local_probability * 100)
        )
        confidence = local_probability if fire_detected else None
        return DashScopeResult(
            summary=summary,
            fire_detected=fire_detected,
            confidence=confidence,
            raw_response={
                "mock": True,
                "local_probability": local_probability,
                "note": "DashScope mock mode is enabled (no API key configured).",
            },
        )

    def _build_messages(self, data_url: str, context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        context_lines: List[str] = []
        if context:
            filename = context.get("filename")
            if filename:
                context_lines.append(f"Filename: {filename}")
            local_probability = context.get("local_probability")
            if local_probability is not None:
                context_lines.append(
                    f"Local heuristic fire probability: {float(local_probability) * 100:.1f}%"
                )
        if context_lines:
            user_prompt = "\n".join(context_lines)
        else:
            user_prompt = (
                "Please analyse the attached forest scene for early signs of smoke, flame, or smouldering. "
                "Summarise the risk level and key observations."
            )
        return [
            {"role": "system", "content": [{"type": "text", "text": self._analysis_prompt}]},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]

    def _extract_summary(self, payload: Dict[str, Any]) -> str:
        try:
            choices = payload.get("choices")
            if not choices:
                return ""
            first_choice = choices[0]
            message = first_choice.get("message", {})
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                texts = [
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                joined = "\n".join(filter(None, map(str.strip, texts)))
                if joined:
                    return joined
                # If the list contains nested dicts with different structure
                fallback = "\n".join(
                    filter(
                        None,
                        (
                            str(block)
                            for block in content
                            if not isinstance(block, dict)
                        ),
                    )
                )
                return fallback.strip()
            if content:
                return str(content)
        except Exception as exc:
            logger.debug("Failed to extract summary from payload: %s", exc)
        return ""

    def _extract_confidence(self, summary: str) -> Optional[float]:
        if not summary:
            return None
        pattern = re.compile(r"(confidence|probability|likelihood)\s*[:=]\s*(\d+(?:\.\d+)?)%?", re.IGNORECASE)
        match = pattern.search(summary)
        if not match:
            return None
        value = float(match.group(2))
        if match.group(0).strip().endswith("%") and value > 1:
            value = max(0.0, min(100.0, value)) / 100.0
        else:
            value = max(0.0, min(1.0, value))
        return value

    def _infer_fire_detection(
        self,
        summary: str,
        context: Optional[Dict[str, Any]],
        confidence: Optional[float],
    ) -> bool:
        if not summary:
            return (confidence or 0.0) >= 0.5 or bool(
                context and float(context.get("local_probability", 0.0)) >= 0.5
            )

        text = summary.lower()
        negative_tokens = [
            "no fire",
            "no visible fire",
            "absence of fire",
            "unlikely",
            "not detected",
            "no smoke",
            "no flames",
            "no sign of fire",
            "no obvious fire",
        ]
        for token in negative_tokens:
            if token in text:
                return False

        affirmative_tokens = ["fire", "flame", "smoke", "burn", "blaze", "ignition"]
        if any(token in text for token in affirmative_tokens):
            if any(f"no {token}" in text for token in affirmative_tokens):
                return False
            return True

        if confidence is not None:
            return confidence >= 0.5

        if context and float(context.get("local_probability", 0.0)) >= 0.5:
            return True

        return False
