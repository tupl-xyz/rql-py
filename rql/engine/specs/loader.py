import hashlib
import json
import yaml
from pathlib import Path
from typing import Dict, Any
from .registry import TaskSpec

def load_spec(spec_path: Path) -> TaskSpec:
    """Load a task specification from a YAML file."""
    with open(spec_path) as f:
        spec_data = yaml.safe_load(f)

    # Compute deterministic hash
    spec_data["spec_hash"] = compute_spec_hash(spec_data)

    return TaskSpec(**spec_data)

def compute_spec_hash(spec_data: Dict[str, Any]) -> str:
    """Compute deterministic hash of specification."""
    # Remove hash field if present, sort keys for deterministic hashing
    clean_data = {k: v for k, v in spec_data.items() if k != "spec_hash"}
    content = json.dumps(clean_data, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(content.encode()).hexdigest()