import hashlib
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from pydantic import BaseModel

class TaskSpec(BaseModel):
    """Specification for a canonical task."""
    name: str
    version: str
    spec_id: str
    description: str
    system_rules: List[str]
    decode_defaults: Dict[str, Any]
    render: Dict[str, Any]  # output_mode, json_schema
    spec_hash: Optional[str] = None

class SpecRegistry:
    """Registry for loading and managing task specifications."""

    def __init__(self):
        self.specs: Dict[str, TaskSpec] = {}
        self.spec_dir = Path(__file__).parent
        self._load_builtin_specs()

    def load_spec(self, name: str, version: str = "1.0.0") -> TaskSpec:
        """Load task specification by name and version."""
        spec_key = f"{name.lower()}@{version}"

        if spec_key in self.specs:
            return self.specs[spec_key]

        # Load from YAML file
        spec_path = self.spec_dir / name.lower() / f"{version}.yaml"
        if not spec_path.exists():
            raise ValueError(f"Task spec not found: {spec_path}")

        with open(spec_path) as f:
            spec_data = yaml.safe_load(f)

        # Compute deterministic hash
        spec_data["spec_hash"] = self._compute_spec_hash(spec_data)

        spec = TaskSpec(**spec_data)
        self.specs[spec_key] = spec
        return spec

    def _compute_spec_hash(self, spec_data: Dict[str, Any]) -> str:
        """Compute deterministic hash of specification."""
        # Remove hash field if present, sort keys for deterministic hashing
        clean_data = {k: v for k, v in spec_data.items() if k != "spec_hash"}
        content = json.dumps(clean_data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(content.encode()).hexdigest()

    def get_spec(self, name: str, version: str = "1.0.0") -> Optional[TaskSpec]:
        """Get task specification by name and version, loading if needed."""
        try:
            return self.load_spec(name, version)
        except (FileNotFoundError, ValueError):
            return None

    def _load_builtin_specs(self):
        """Load all built-in task specifications."""
        for task_name in ["answer", "summarize", "extract"]:
            try:
                self.load_spec(task_name)
            except (FileNotFoundError, ValueError):
                pass  # Spec file may not exist yet during development