import json, jsonschema
from pathlib import Path

def validate_with(schema_path: str, payload: dict) -> None:
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    jsonschema.validate(payload, schema)
