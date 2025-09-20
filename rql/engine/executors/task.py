from typing import Dict, Any, List, Optional
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
import structlog

from .base import ExecResult
from ..ast import TaskInvocation, RefCall, DeterminismLevel
from ..specs.registry import SpecRegistry
from ..retrieval import RefResolver
from ...runtime.session import RQLSession

logger = structlog.get_logger(__name__)

class TaskExecutor:
    """Executor for canonical tasks with deterministic behavior."""

    def __init__(self):
        self.spec_registry = SpecRegistry()
        self.ref_resolver = RefResolver()

        # Setup Jinja2 for prompt templates
        template_dir = Path(__file__).parent.parent / "specs" / "templates"
        self.template_env = Environment(loader=FileSystemLoader(template_dir))

    def execute(self, stmt, session: RQLSession) -> ExecResult:
        """Execute a SELECT statement (synchronous interface)."""
        import asyncio

        # Extract task invocation and parameters from statement
        task = stmt.task_invocation
        with_params = stmt.with_params or {}
        determinism_level = stmt.determinism_level

        if session.is_verbose():
            logger.info(
                "task.execute.start",
                task_name=task.name,
                determinism_level=determinism_level.name,
                with_params=list(with_params.keys()) if with_params else [],
                return_format=stmt.return_format
            )

        # Add return format to parameters for strong determinism check
        with_params["return_format"] = stmt.return_format

        # Run async execution in sync wrapper
        try:
            result = asyncio.run(self.execute_task(task, session, determinism_level, with_params))
            if session.is_verbose():
                logger.info(
                    "task.execute.complete",
                    success=result.success,
                    has_output=bool(result.output),
                    confidence=result.confidence if hasattr(result, 'confidence') else None
                )
            return result
        except Exception as e:
            if session.is_verbose():
                logger.error("task.execute.failed", error=str(e), task_name=task.name)
            return ExecResult(success=False, error=f"Task execution failed: {str(e)}")

    async def execute_task(self, task: TaskInvocation, session: RQLSession,
                          determinism_level: DeterminismLevel = DeterminismLevel.PROVIDER,
                          with_params: Dict[str, Any] = None) -> ExecResult:
        """Execute task with specified determinism level."""

        # 1. Load task specification
        spec = self.spec_registry.load_spec(task.name.lower())
        if session.is_verbose():
            logger.debug(
                "task.spec.loaded",
                task_name=task.name,
                spec_keys=list(spec.__dict__.keys()) if hasattr(spec, '__dict__') else None
            )

        # 2. Validate parameters
        self._validate_task_params(task, spec)

        # 3. Resolve all REF() calls to evidence
        evidence_data = await self._resolve_all_refs(task.args, session)
        if session.is_verbose():
            evidence_count = len(evidence_data.get("evidence", []))
            logger.debug(
                "task.evidence.resolved",
                evidence_count=evidence_count,
                has_evidence=evidence_count > 0
            )

        # 4. Determine execution strategy based on determinism level
        if session.is_verbose():
            logger.info(
                "task.execution.strategy",
                determinism_level=determinism_level.name,
                strategy="strong" if determinism_level == DeterminismLevel.STRONG else "provider"
            )

        if determinism_level == DeterminismLevel.STRONG:
            return await self._execute_strong(task, spec, evidence_data, session, with_params)
        else:
            return await self._execute_provider(task, spec, evidence_data, session, with_params)

    async def _execute_provider(self, task: TaskInvocation, spec, evidence_data: Dict[str, Any],
                               session: RQLSession, with_params: Dict[str, Any]) -> ExecResult:
        """Execute with provider-level determinism."""

        schema = task.args.get("schema")

        # 1. Build messages from task and evidence
        messages = self._build_messages(task, spec, evidence_data, schema, determinism="provider", session=session)

        # 2. Configure deterministic decoding
        decode_config = self._build_decode_config(spec, with_params, determinism_level="provider")

        # 3. Execute LLM call
        from .llm import LLMExecutor
        llm_executor = LLMExecutor()
        response = await llm_executor.execute_deterministic(messages, decode_config, session)

        # 4. Apply validation
        validated_output = await self._apply_validation(response["content"], spec, evidence_data, session)

        # 5. Create reasoning contract
        contract = self._create_reasoning_contract(
            task, spec, evidence_data, response, "provider", decode_config
        )

        return ExecResult(
            success=True,
            output=validated_output,
            evidence=evidence_data.get("evidence", []),
            confidence=self._calculate_confidence(response),
            reasoning_contract=contract
        )

    async def _execute_strong(self, task: TaskInvocation, spec, evidence_data: Dict[str, Any],
                             session: RQLSession, with_params: Dict[str, Any]) -> ExecResult:
        """Execute with strong determinism (two-pass if needed)."""

        # Strong determinism requires JSON return format, not JSON spec mode
        # Check if user requested JSON return format
        return_format = with_params.get("return_format", "TEXT").upper()
        if return_format != "JSON" and task.name != "EXTRACT":
            raise ValueError(f"Strong determinism requires RETURN JSON for task {task.name}")

        if session.is_verbose():
            logger.debug(
                "task.strong.validation",
                task_name=task.name,
                return_format=return_format,
                passed_format_check=True
            )

        # Get JSON schema from task args or use default for ANSWER tasks
        json_schema = task.args.get("schema") or spec.render.get("json_schema")
        schema_source = "task_args" if task.args.get("schema") else "spec_default"

        if not json_schema and task.name == "ANSWER":
            # Conservative default schema for ANSWER (minimize JSON pitfalls)
            json_schema = {
                "type": "object",
                "properties": {
                    "answer": {"type": "string"}
                },
                "required": ["answer"]
            }
            schema_source = "answer_default"
        elif not json_schema:
            raise ValueError(f"Strong determinism requires JSON schema for task {task.name}")

        if isinstance(json_schema, dict):
            original_keys = list(json_schema.keys())
            json_schema = self._sanitize_schema_for_provider(json_schema)
            sanitized_keys = list(json_schema.keys())

            if session.is_verbose():
                logger.debug(
                    "task.schema.processed",
                    schema_source=schema_source,
                    original_keys=original_keys,
                    sanitized_keys=sanitized_keys,
                    removed_unsupported=original_keys != sanitized_keys
                )

        # For tasks with retrieval: use two-pass execution
        has_evidence = bool(evidence_data.get("evidence"))
        execution_mode = "two_pass" if has_evidence else "single_pass"

        if session.is_verbose():
            logger.info(
                "task.strong.mode",
                execution_mode=execution_mode,
                has_evidence=has_evidence,
                evidence_count=len(evidence_data.get("evidence", []))
            )

        if has_evidence:
            return await self._execute_two_pass(task, spec, evidence_data, session, with_params, json_schema)
        else:
            return await self._execute_single_pass_json(task, spec, evidence_data, session, with_params, json_schema)

    async def _execute_two_pass(self, task: TaskInvocation, spec, evidence_data: Dict[str, Any],
                               session: RQLSession, with_params: Dict[str, Any], json_schema: Dict[str, Any]) -> ExecResult:
        """Execute two-pass strong determinism: gather evidence, then render JSON."""

        # Pass 1: Gather and process evidence (already done in evidence_data)
        # Pass 2: Render-only call with strict JSON mode

        messages = self._build_messages(task, spec, evidence_data, json_schema, determinism="strong", session=session)

        # Configure for strict JSON rendering
        decode_config = self._build_decode_config(spec, with_params, determinism_level="strong")
        decode_config["json_mode"] = True
        decode_config["json_schema"] = json_schema

        from .llm import LLMExecutor
        llm_executor = LLMExecutor()
        response = await llm_executor.execute_deterministic(messages, decode_config, session)

        # Validate and canonicalize JSON
        validated_output = self._validate_and_canonicalize_json(response["content"], json_schema, session)

        # Create reasoning contract with normalized output hash
        import hashlib
        output_hash = hashlib.sha256(validated_output.encode()).hexdigest()
        contract = self._create_reasoning_contract(
            task, spec, evidence_data, response, "strong", decode_config, output_hash
        )

        return ExecResult(
            success=True,
            output=validated_output,
            evidence=evidence_data.get("evidence", []),
            confidence=1.0,  # Strong determinism implies high confidence
            reasoning_contract=contract
        )

    async def _execute_single_pass_json(self, task: TaskInvocation, spec, evidence_data: Dict[str, Any],
                                       session: RQLSession, with_params: Dict[str, Any], json_schema: Dict[str, Any]) -> ExecResult:
        """Execute single-pass strong determinism with JSON output."""

        messages = self._build_messages(task, spec, evidence_data, json_schema, determinism="strong", session=session)

        # Configure for strict JSON rendering
        decode_config = self._build_decode_config(spec, with_params, determinism_level="strong")
        decode_config["json_mode"] = True
        decode_config["json_schema"] = json_schema

        from .llm import LLMExecutor
        llm_executor = LLMExecutor()
        response = await llm_executor.execute_deterministic(messages, decode_config, session)

        # Validate and canonicalize JSON
        validated_output = self._validate_and_canonicalize_json(response["content"], json_schema, session)

        # Create reasoning contract with normalized output hash
        import hashlib
        output_hash = hashlib.sha256(validated_output.encode()).hexdigest()
        contract = self._create_reasoning_contract(
            task, spec, evidence_data, response, "strong", decode_config, output_hash
        )

        return ExecResult(
            success=True,
            output=validated_output,
            evidence=evidence_data.get("evidence", []),
            confidence=1.0,  # Strong determinism implies high confidence
            reasoning_contract=contract
        )

    def _build_messages(
        self,
        task: TaskInvocation,
        spec,
        evidence_data: Dict[str, Any],
        json_schema: Optional[Dict[str, Any]] = None,
        determinism: str = "provider",
        session: Optional[RQLSession] = None,
    ) -> List[Dict[str, str]]:
        """Build messages using internal prompt templates."""

        # Load task-specific template
        template_name = f"{task.name.lower()}.j2"
        template_source = "task_specific"
        try:
            template = self.template_env.get_template(template_name)
        except:
            # Fallback to basic template
            template_source = "fallback"
            template = self.template_env.from_string(
                "{{ system_rules | join('\\n') }}\\n\\n"
                "Task: {{ task_name }}\\n"
                "Parameters: {{ task_args | tojson }}\\n"
                "{% if evidence %}Evidence: {{ evidence | tojson }}{% endif %}"
            )

        if session and session.is_verbose():
            logger.debug(
                "task.template.loaded",
                template_name=template_name,
                template_source=template_source,
                determinism=determinism
            )

        # Render template with task data
        system_content = "\\n".join(spec.system_rules)

        # Provide safe defaults for template variables to avoid Jinja2
        # 'Undefined is not JSON serializable' errors when a caller forgets
        # to pass certain fields (e.g., schema for EXTRACT in provider mode).
        ctx = {
            "task_name": task.name,
            "task_args": task.args,
            "evidence": evidence_data.get("evidence", []),
            # Defaults only apply when not explicitly provided by the query
            "schema": task.args.get("schema", {}),
            "input_text": task.args.get("input_text", None),
            "json_schema": json_schema,
            "determinism_level": determinism,
        }
        if json_schema and not ctx.get("schema"):
            ctx["schema"] = json_schema
        # Make all args directly addressable in the template (args override defaults)
        ctx.update(task.args)

        user_content = template.render(**ctx)

        if session and session.is_verbose():
            logger.debug(
                "task.messages.built",
                system_content_length=len(system_content),
                user_content_length=len(user_content),
                has_evidence=len(evidence_data.get("evidence", [])) > 0,
                has_json_schema=json_schema is not None
            )

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]

    def _build_decode_config(self, spec, with_params: Dict[str, Any], determinism_level: str) -> Dict[str, Any]:
        """Build deterministic decoding configuration."""

        # Start with spec defaults
        config = spec.decode_defaults.copy()

        # Apply WITH parameter overrides (decode.*)
        if with_params:
            for key, value in with_params.items():
                if key.startswith("decode."):
                    param_name = key[7:]  # Remove 'decode.' prefix
                    config[param_name] = value

        # Ensure deterministic settings
        config.update({
            "temperature": config.get("temperature", 0),
            "top_p": config.get("top_p", 0),
            "top_k": config.get("top_k", 1),
            "candidate_count": config.get("candidate_count", 1)
        })

        return config

    async def _resolve_all_refs(self, task_args: Dict[str, Any], session: RQLSession) -> Dict[str, Any]:
        """Resolve all REF() calls in task arguments."""
        evidence_data = {"evidence": []}

        for key, value in task_args.items():
            if isinstance(value, RefCall):
                ref_result = await self.ref_resolver.resolve_ref(value, session)
                evidence_data.update(ref_result)
                break  # Only one REF per task for simplicity

        return evidence_data

    def _validate_and_canonicalize_json(self, output: str, schema: Dict[str, Any], session: Optional[RQLSession] = None) -> str:
        """Validate JSON against schema and canonicalize."""
        import json

        # With structured output mode, the response should already be valid JSON
        # Only attempt minimal cleanup if needed
        text = str(output).strip()

        if session and session.is_verbose():
            logger.debug(
                "json.validation.start",
                text_length=len(text),
                has_schema=schema is not None,
                text_preview=text[:100] if text else "(empty)"
            )

        try:
            # Try parsing directly first
            parsed = json.loads(text)
            canonical = json.dumps(parsed, sort_keys=True, separators=(',', ':'))

            if session and session.is_verbose():
                logger.debug(
                    "json.validation.success",
                    method="direct_parse",
                    canonical_length=len(canonical)
                )

            return canonical
        except json.JSONDecodeError as err:
            if session and session.is_verbose():
                logger.debug(
                    "json.validation.failed_direct",
                    error=str(err),
                    snippet=text[:200] if text else "(empty)",
                    attempting_cleanup=True
                )

            # If direct parsing fails, try one simple cleanup step
            if text.startswith("```") and text.endswith("```"):
                # Remove markdown code fences if present
                lines = text.split('\n')
                if len(lines) > 2:
                    text = '\n'.join(lines[1:-1])
                    try:
                        parsed = json.loads(text)
                        canonical = json.dumps(parsed, sort_keys=True, separators=(',', ':'))

                        if session and session.is_verbose():
                            logger.debug(
                                "json.validation.success",
                                method="fence_removal",
                                canonical_length=len(canonical)
                            )

                        return canonical
                    except json.JSONDecodeError:
                        if session and session.is_verbose():
                            logger.debug("json.validation.cleanup_failed", method="fence_removal")

            if session and session.is_verbose():
                logger.error(
                    "json.validation.failed",
                    final_error=str(err),
                    text_preview=text[:200] if text else "(empty)"
                )

            raise ValueError(f"JSON validation failed: {err}")


    def _sanitize_schema_for_provider(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Remove schema fields not supported by the current provider."""
        import copy

        # Google GenAI/Gemini API doesn't support additionalProperties in JSON schemas
        # and has limited schema support - keep only basic properties that work
        unsupported = {
            "additionalProperties",
            "$schema",
            "$id",
            "$ref",
            "definitions",
            "allOf",
            "anyOf",
            "oneOf",
            "not",
            "if",
            "then",
            "else",
            "const",
            "enum",  # Sometimes problematic
            "pattern",  # Regex patterns may not work
            "format",   # Custom formats may not work
        }

        def _clean(obj: Any) -> Any:
            if isinstance(obj, dict):
                cleaned: Dict[str, Any] = {}
                for key, value in obj.items():
                    if key in unsupported:
                        continue
                    cleaned[key] = _clean(value)
                return cleaned
            if isinstance(obj, list):
                return [_clean(item) for item in obj]
            return obj

        return _clean(copy.deepcopy(schema))


    def _validate_task_params(self, task: TaskInvocation, spec):
        """Validate task parameters against spec."""
        # Basic validation - could be expanded
        pass

    async def _apply_validation(self, output: str, spec, evidence_data: Dict[str, Any], session: RQLSession) -> str:
        """Apply output validation."""
        # Basic validation - could be expanded
        return output

    def _calculate_confidence(self, response: Dict[str, Any]) -> float:
        """Calculate confidence from response."""
        # Basic confidence calculation
        return 0.8

    def _create_reasoning_contract(self, task, spec, evidence_data, response, determinism_level, decode_config, output_hash=None):
        """Create reasoning contract for execution."""
        # Simplified contract creation
        return {
            "task": task.name,
            "determinism_level": determinism_level,
            "evidence_hash": evidence_data.get("evidence_hash"),
            "output_hash": output_hash
        }
