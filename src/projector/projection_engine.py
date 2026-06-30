"""
ProjectionEngine — output shaping and field selection engine.

The ``ProjectionEngine`` takes a merged :class:`~src.models.CandidateProfile`
and a :class:`~src.models.ProjectionConfig` and produces a consumer-specific
output dictionary (or JSON document).

Projection allows downstream consumers (ATS re-import, recruiter dashboards,
ML feature stores, etc.) to receive only the fields they need, in the
structure they expect.
"""

from __future__ import annotations

import re
from typing import Any

from src.models import CandidateProfile, ProjectionConfig
from src.models.config import OnMissingStrategy
from src.projector.exceptions import ProjectionError


class ProjectionEngine:
    """
    Applies a :class:`~src.models.ProjectionConfig` to a ``CandidateProfile``
    to produce a shaped output document.

    Usage
    -----
    ::

        config = ProjectionConfig.model_validate_json(...)
        engine = ProjectionEngine(config=config)
        output: dict = engine.project(merged_profile)
    """

    def __init__(self, config: ProjectionConfig) -> None:
        """
        Initialise the projection engine with a projection configuration.

        Parameters
        ----------
        config:
            The :class:`~src.models.ProjectionConfig` defining field mappings
            and output structure.
        """
        self.config = config

    def project(self, profile: CandidateProfile) -> dict[str, Any]:
        """
        Apply the projection config to ``profile`` and return an output dict.

        Parameters
        ----------
        profile:
            The merged :class:`~src.models.CandidateProfile` to project.

        Returns
        -------
        dict[str, Any]
            A shaped output dictionary ready for serialisation to JSON / YAML.
        """
        output: dict[str, Any] = {}

        for field_config in self.config.fields:
            # 1. Resolve value
            val = self._resolve_path(profile, field_config.from_field)

            # 2. Handle missing
            if val is None:
                # If required and strategy is raise, fail immediately
                if field_config.required and field_config.on_missing == OnMissingStrategy.RAISE:
                    raise ProjectionError(
                        f"Required field missing: {field_config.from_field}"
                    )

                strategy = field_config.on_missing
                if strategy == OnMissingStrategy.RAISE:
                    raise ProjectionError(
                        f"Field missing: {field_config.from_field} (strategy=RAISE)"
                    )
                elif strategy == OnMissingStrategy.OMIT:
                    continue  # Do not set the field
                elif strategy == OnMissingStrategy.DEFAULT:
                    val = field_config.default_value
                elif strategy == OnMissingStrategy.NULL:
                    val = None

            # 3. Insert into output dictionary
            self._set_nested_value(output, field_config.path, val)

        # 4. Optional: strip null fields
        if self.config.strip_null_fields:
            self._strip_nulls(output)

        # 5. Optional: include provenance
        if self.config.include_provenance:
            # Convert the list of ProvenanceRecords into a list of dicts.
            output["provenance"] = [
                p.model_dump(mode="json") for p in profile.provenance
            ]

        return output

    def _resolve_path(self, profile: CandidateProfile, path: str) -> Any:
        """
        Resolve a dot/bracket-notation path against ``profile``.

        Gracefully returns None if an intermediate object is None,
        an attribute is missing, or a list index is out of bounds.

        Raises ProjectionError for fundamentally malformed paths.
        """
        if not path:
            return None

        # Split on '.' but keep brackets attached to the segments for now.
        parts = path.split(".")
        
        current: Any = profile
        for part in parts:
            if current is None:
                return None

            # Extract bracket indices if present, e.g. "skills[0]" -> ("skills", [0])
            bracket_matches = list(re.finditer(r"\[(\d+)\]", part))
            
            # Check for malformed bracket syntax like `[a]`
            if "[" in part and not bracket_matches:
                 raise ProjectionError(f"Unparseable path segment: {part}")

            if bracket_matches:
                base_attr = part[:bracket_matches[0].start()]
            else:
                base_attr = part

            # Resolve the base attribute
            if base_attr:
                if hasattr(current, base_attr):
                    current = getattr(current, base_attr)
                elif isinstance(current, dict) and base_attr in current:
                    current = current[base_attr]
                else:
                    return None

            # Resolve any list indices
            for match in bracket_matches:
                if current is None:
                    return None
                
                try:
                    idx = int(match.group(1))
                except ValueError:
                    raise ProjectionError(f"Invalid index in path: {part}") from None

                if not isinstance(current, (list, tuple)):
                    return None

                try:
                    current = current[idx]
                except IndexError:
                    return None

        return current

    def _set_nested_value(self, target: dict[str, Any], path: str, value: Any) -> None:
        """
        Insert `value` into the `target` dictionary at the dot-separated `path`.
        
        Example: path="location.city", value="San Francisco"
        -> target["location"]["city"] = "San Francisco"
        """
        if not path:
            return

        parts = path.split(".")
        current = target

        # Traverse all parts except the very last one
        for i, part in enumerate(parts[:-1]):
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]

        # Set the value at the last key
        last_key = parts[-1]
        current[last_key] = value

    def _strip_nulls(self, target: dict[str, Any]) -> None:
        """
        Recursively remove all keys from `target` where the value is None.
        """
        keys_to_delete = []
        for k, v in target.items():
            if v is None:
                keys_to_delete.append(k)
            elif isinstance(v, dict):
                self._strip_nulls(v)
                if not v: # if it becomes empty, should we remove it? The prompt says "Remove all null-valued fields". We'll just remove None values.
                    pass # Let's stick strictly to null-valued.

        for k in keys_to_delete:
            del target[k]
