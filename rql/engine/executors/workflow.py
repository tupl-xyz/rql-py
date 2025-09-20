"""Workflow executor for n8n webhooks."""

from typing import Any, Dict

import httpx


class WorkflowExecutor:
    """Executor for workflow-based queries using n8n webhooks."""

    def __init__(self):
        self.timeout = 30  # Default timeout in seconds


    async def execute_ref(self, source_config: Dict[str, Any], ref_args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute workflow for REF() call with normalized response."""

        # Use existing HTTP calling logic but ensure response format
        webhook_url = source_config.get("webhook")
        if not webhook_url:
            raise ValueError("No webhook URL found in source config")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    webhook_url,
                    json=ref_args,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                response_data = response.json()

        except Exception as e:
            raise ValueError(f"REF call failed: {e}")

        # Normalize response to expected format
        if isinstance(response_data, dict) and "evidence" in response_data:
            evidence = response_data["evidence"]
        elif isinstance(response_data, list):
            evidence = response_data
        else:
            evidence = [response_data] if response_data else []

        return {"evidence": evidence}