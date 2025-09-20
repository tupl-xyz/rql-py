"""LLM executor for Google Gemini via the google-genai SDK."""

import os
from typing import Any, Dict, List, Optional

import structlog

from google import genai
from google.genai import types

from ...runtime.session import RQLSession

logger = structlog.get_logger(__name__)


class LLMExecutor:
    """Wrapper around the Gemini SDK with schema-aware JSON mode."""

    def __init__(self) -> None:
        self._client: Optional[genai.Client] = None

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    async def execute_deterministic(
        self,
        messages: List[Dict[str, str]],
        decode_config: Dict[str, Any],
        session: RQLSession,
    ) -> Dict[str, Any]:
        """Execute a request against Gemini with deterministic settings."""

        model = session.get_setting("model", "gemini-2.5-flash")
        contents = self._messages_to_content(messages)
        generation_config = self._build_generation_config(decode_config)

        # JSON mode extras -------------------------------------------------
        if decode_config.get("json_mode"):
            generation_config["response_mime_type"] = "application/json"

            schema_obj = decode_config.get("json_schema")
            if schema_obj:
                sanitized = self._sanitize_schema(schema_obj)
                # Don't use types.Schema() - pass the dict directly
                generation_config["response_schema"] = sanitized

                if session.is_verbose():
                    logger.info(
                        "llm.json_mode",
                        schema_type=type(sanitized).__name__,
                        keys=list(sanitized.keys()) if isinstance(sanitized, dict) else None,
                    )

        client = self._get_client(session)

        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(**generation_config),
            )
            if session.is_verbose():
                logger.debug(
                    "llm.response.raw",
                    text=getattr(response, "text", None),
                    candidates=getattr(response, "candidates", None),
                )
        except Exception as exc:  # pragma: no cover - network layer
            logger.error(
                "llm.generate_content.failed",
                error=str(exc),
                model=model,
                json_mode=bool(decode_config.get("json_mode")),
                has_schema="response_schema" in generation_config,
            )
            raise

        return {
            "content": self._extract_content(response),
            "model": model,
            "decode_config": generation_config,
            "usage": self._extract_usage(response),
            "provider_fingerprint": getattr(response, "model_version", None),
        }

    # ------------------------------------------------------------------
    # Client & config helpers
    # ------------------------------------------------------------------
    def _get_client(self, session: RQLSession) -> genai.Client:
        if self._client is not None:
            return self._client

        api_key = self._get_api_key(session)
        try:
            self._client = genai.Client(api_key=api_key)
        except ImportError as exc:  # pragma: no cover - SDK missing
            raise RuntimeError(
                "Google Gen AI library not installed. Install with: pip install google-genai"
            ) from exc

        logger.debug("llm.client.initialized", model=session.get_setting("model"))
        return self._client

    def _get_api_key(self, session: RQLSession) -> str:
        api_key = session.config.llm.api_key or os.getenv(session.config.llm.api_key_env)
        if not api_key:
            raise ValueError(
                f"API key not found in config or environment variable: {session.config.llm.api_key_env}"
            )
        return api_key

    def _build_generation_config(self, decode_config: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "temperature": decode_config.get("temperature", 0),
            "top_p": decode_config.get("top_p", 0),
            "top_k": decode_config.get("top_k", 1),
            "candidate_count": decode_config.get("candidate_count", 1),
            "max_output_tokens": decode_config.get("max_tokens", 2048),
        }

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------
    def _messages_to_content(self, messages: List[Dict[str, str]]) -> str:
        parts: List[str] = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
            else:
                parts.append(content)
        return "\n\n".join(parts)

    def _extract_usage(self, response: Any) -> Dict[str, Any]:
        usage = getattr(response, "usage_metadata", None)
        if not usage:
            return {}
        return {
            "prompt_tokens": getattr(usage, "prompt_token_count", 0),
            "completion_tokens": getattr(usage, "candidates_token_count", 0),
            "total_tokens": getattr(usage, "total_token_count", 0),
        }

    def _extract_content(self, response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str) and text:
            return text

        candidates = getattr(response, "candidates", None)
        if candidates:
            for cand in candidates:
                # Check for MAX_TOKENS finish reason before processing content
                finish_reason = getattr(cand, "finish_reason", None)
                if finish_reason and str(finish_reason) == "FinishReason.MAX_TOKENS":
                    raise ValueError(
                        "Response was truncated due to token limit. "
                        "Increase max_output_tokens or simplify the request."
                    )

                content = getattr(cand, "content", None)
                if not content:
                    continue
                # content may be a list of parts or a single object with .text
                if isinstance(content, list):
                    for part in content:
                        part_text = getattr(part, "text", None)
                        if part_text:
                            return part_text
                else:
                    part_text = getattr(content, "text", None)
                    if part_text:
                        return part_text
                    parts = getattr(content, "parts", None)
                    if parts:
                        for part in parts:
                            part_text = getattr(part, "text", None)
                            if part_text:
                                return part_text

        return ""

    # ------------------------------------------------------------------
    # Schema handling
    # ------------------------------------------------------------------
    def _sanitize_schema(self, schema: Any) -> Any:
        if not isinstance(schema, dict):
            return schema

        # Validate that schema is compatible with Gemini before proceeding
        self._validate_gemini_schema_compatibility(schema)

        # Clean unsupported properties but keep the structure intact
        return self._clean_schema_properties(schema)

    def _validate_gemini_schema_compatibility(self, schema: Dict[str, Any]) -> None:
        """Validate that the schema is compatible with Gemini's limitations."""
        errors = []

        # Check for unsupported root structure
        if not self._is_valid_gemini_root_schema(schema):
            errors.append("Schema root must be a simple object with 'type': 'object' and 'properties'")

        # Recursively validate the schema structure
        self._validate_schema_structure(schema, errors, path="root")

        if errors:
            error_msg = "Schema is not compatible with Google Gemini API:\n" + "\n".join(f"- {error}" for error in errors)
            error_msg += "\n\nGemini supports only:\n"
            error_msg += "- Simple objects with string/number/integer/boolean properties\n"
            error_msg += "- No arrays, nested objects, or complex JSON Schema features\n"
            error_msg += "- Example: {\"type\": \"object\", \"properties\": {\"name\": {\"type\": \"string\"}, \"age\": {\"type\": \"integer\"}}}"
            raise ValueError(error_msg)

    def _is_valid_gemini_root_schema(self, schema: Dict[str, Any]) -> bool:
        """Check if root schema follows Gemini requirements."""
        return (
            schema.get("type") == "object" and
            "properties" in schema and
            isinstance(schema["properties"], dict)
        )

    def _validate_schema_structure(self, schema: Any, errors: List[str], path: str) -> None:
        """Recursively validate schema structure for Gemini compatibility."""
        if not isinstance(schema, dict):
            return

        schema_type = schema.get("type")

        # Check for unsupported types
        if schema_type == "array":
            errors.append(f"Arrays not supported at {path} - use simple object properties instead")
            return

        if schema_type == "object" and "properties" in schema:
            # Nested objects are not well supported
            if path != "root":
                errors.append(f"Nested objects not supported at {path} - flatten to root level properties")

            # Validate each property
            properties = schema.get("properties", {})
            for prop_name, prop_schema in properties.items():
                prop_path = f"{path}.{prop_name}" if path != "root" else prop_name
                self._validate_schema_structure(prop_schema, errors, prop_path)

        elif schema_type not in ["string", "number", "integer", "boolean", None]:
            errors.append(f"Unsupported type '{schema_type}' at {path} - use string, number, integer, or boolean")

        # Check for unsupported keywords
        unsupported_keywords = {
            "additionalProperties", "$schema", "$id", "$ref", "definitions",
            "allOf", "anyOf", "oneOf", "not", "if", "then", "else",
            "const", "enum", "pattern", "format", "items"
        }

        for keyword in unsupported_keywords:
            if keyword in schema:
                errors.append(f"Unsupported keyword '{keyword}' at {path}")

    def _clean_schema_properties(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Clean schema by removing unsupported properties while preserving structure."""
        unsupported = {
            "additionalProperties", "$schema", "$id", "$ref", "definitions",
            "allOf", "anyOf", "oneOf", "not", "if", "then", "else",
            "const", "enum", "pattern", "format"
        }

        def _clean(value: Any) -> Any:
            if isinstance(value, dict):
                cleaned = {}
                for key, val in value.items():
                    if key in unsupported:
                        continue
                    cleaned_val = _clean(val)
                    if cleaned_val is not None:
                        cleaned[key] = cleaned_val
                return cleaned
            elif isinstance(value, list):
                return [_clean(item) for item in value if _clean(item) is not None]
            return value

        return _clean(schema)

