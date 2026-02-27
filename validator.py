"""
Enterprise-Level Validation Module for Resume Parser
=====================================================
Strict validation between LLM raw output and expected Pydantic structure.
Provides detailed error reporting for retry mechanism.
"""

import re
import logging
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""
    ERROR = "error"      # Must be fixed - blocks successful parsing
    WARNING = "warning"  # Should be fixed - but can proceed


@dataclass
class ValidationIssue:
    """Represents a single validation issue."""
    field_path: str           # e.g., "education[0].level"
    issue_type: str           # e.g., "missing_field", "type_mismatch"
    message: str              # Human-readable description
    severity: ValidationSeverity
    expected_type: Optional[str] = None
    actual_value: Optional[Any] = None


@dataclass
class ValidationResult:
    """Result of validating LLM output against schema."""
    is_valid: bool
    errors: List[ValidationIssue] = field(default_factory=list)
    warnings: List[ValidationIssue] = field(default_factory=list)
    
    def add_error(self, field_path: str, issue_type: str, message: str, 
                  expected_type: str = None, actual_value: Any = None):
        """Add an error to the validation result."""
        self.errors.append(ValidationIssue(
            field_path=field_path,
            issue_type=issue_type,
            message=message,
            severity=ValidationSeverity.ERROR,
            expected_type=expected_type,
            actual_value=actual_value
        ))
        self.is_valid = False
    
    def add_warning(self, field_path: str, issue_type: str, message: str,
                    expected_type: str = None, actual_value: Any = None):
        """Add a warning to the validation result."""
        self.warnings.append(ValidationIssue(
            field_path=field_path,
            issue_type=issue_type,
            message=message,
            severity=ValidationSeverity.WARNING,
            expected_type=expected_type,
            actual_value=actual_value
        ))
    
    def get_error_summary(self) -> str:
        """Get a concise summary of all errors for retry prompt."""
        if not self.errors:
            return "No errors"
        
        summary_lines = []
        for error in self.errors:
            summary_lines.append(f"- {error.field_path}: {error.message}")
        
        return "\n".join(summary_lines)
    
    def get_detailed_report(self) -> str:
        """Get a detailed report of all validation issues."""
        lines = ["=" * 50, "VALIDATION REPORT", "=" * 50]
        
        if self.errors:
            lines.append(f"\nERRORS ({len(self.errors)}):")
            for e in self.errors:
                lines.append(f"  [{e.field_path}] {e.message}")
                if e.expected_type:
                    lines.append(f"    Expected: {e.expected_type}")
                if e.actual_value is not None:
                    lines.append(f"    Got: {type(e.actual_value).__name__} = {str(e.actual_value)[:50]}")
        
        if self.warnings:
            lines.append(f"\nWARNINGS ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"  [{w.field_path}] {w.message}")
        
        if self.is_valid:
            lines.append("\n✓ Validation PASSED")
        else:
            lines.append("\n✗ Validation FAILED")
        
        return "\n".join(lines)


# ============== SCHEMA DEFINITIONS ==============

# Define the expected schema for LLM output
RESUME_SCHEMA = {
    "name": {"type": str, "required": True, "description": "Full name of the person"},
    "email": {"type": list, "required": True, "item_type": str, "description": "List of email addresses"},
    "phone": {"type": list, "required": True, "item_type": str, "description": "List of phone numbers"},
    "linkedin": {"type": list, "required": True, "item_type": str, "description": "List of LinkedIn URLs"},
    "github": {"type": list, "required": True, "item_type": str, "description": "List of GitHub URLs"},
    "education": {"type": list, "required": True, "item_schema": {
        "level": {"type": str, "required": True},
        "qualification": {"type": str, "required": True},
        "institution": {"type": str, "required": True},
        "location": {"type": (str, type(None)), "required": False},
        "percentage": {"type": str, "required": True},
        "year": {"type": str, "required": True}
    }},
    "experience": {"type": list, "required": True, "item_schema": {
        "job_title": {"type": str, "required": True},
        "company": {"type": str, "required": True},
        "duration": {"type": str, "required": True},
        "description": {"type": str, "required": True}
    }},
    "skills": {"type": list, "required": True, "item_type": str, "description": "List of skills"},
    "projects": {"type": list, "required": True, "item_schema": {
        "title": {"type": str, "required": True},
        "description": {"type": str, "required": True},
        "technologies": {"type": list, "required": True, "item_type": str},
        "link": {"type": str, "required": True}
    }},
    "hobbies": {"type": list, "required": True, "item_schema": {
        "name": {"type": str, "required": True},
        "description": {"type": str, "required": True}
    }},
    "miscellaneous": {"type": dict, "required": False, "schema": {
        "coding_profiles": {"type": list, "required": True, "item_schema": {
            "platform": {"type": str, "required": True},
            "username": {"type": str, "required": True},
            "link": {"type": str, "required": True},
            "rating": {"type": str, "required": True}
        }},
        "certifications": {"type": list, "required": True, "item_schema": {
            "name": {"type": str, "required": True},
            "issuer": {"type": str, "required": True},
            "date": {"type": str, "required": True},
            "link": {"type": str, "required": True}
        }},
        "expertise": {"type": list, "required": True, "item_type": str},
        "other_links": {"type": list, "required": True, "item_type": str}
    }}
}

# Top-level required keys that MUST be present
REQUIRED_TOP_LEVEL_KEYS = {"name", "email", "phone", "linkedin", "github", 
                           "education", "experience", "skills", "projects", "hobbies"}


# ============== VALIDATION FUNCTIONS ==============

def validate_type(value: Any, expected_type: Any, field_path: str) -> Tuple[bool, str]:
    """
    Validate that a value matches the expected type.
    
    Args:
        value: The value to check
        expected_type: Expected type (can be tuple for multiple allowed types)
        field_path: Path to the field for error messages
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if expected_type is None:
        return True, ""
    
    # Handle None values for optional fields
    if value is None:
        if isinstance(expected_type, tuple) and type(None) in expected_type:
            return True, ""
        return False, f"Value is None but {field_path} is required"
    
    # Check type
    try:
        if isinstance(expected_type, tuple):
            if not isinstance(value, expected_type):
                type_names = [t.__name__ for t in expected_type if t is not type(None)]
                return False, f"Expected one of {type_names}, got {type(value).__name__}"
        else:
            if not isinstance(value, expected_type):
                return False, f"Expected {expected_type.__name__}, got {type(value).__name__}"
    except Exception as e:
        return False, f"Type check failed: {str(e)}"
    
    return True, ""


def validate_dict_schema(data: Dict[str, Any], schema: Dict[str, Any], 
                         path_prefix: str = "", is_strict: bool = True) -> ValidationResult:
    """
    Validate a dictionary against a schema definition.
    
    Args:
        data: Dictionary to validate
        schema: Schema definition
        path_prefix: Prefix for field paths in error messages
        is_strict: If True, missing required fields are errors; if False, warnings
    
    Returns:
        ValidationResult with errors and warnings
    """
    result = ValidationResult(is_valid=True)
    
    for field_name, field_def in schema.items():
        field_path = f"{path_prefix}.{field_name}" if path_prefix else field_name
        expected_type = field_def.get("type")
        is_required = field_def.get("required", False)
        
        # Check if field exists
        if field_name not in data:
            if is_required and is_strict:
                result.add_error(
                    field_path=field_path,
                    issue_type="missing_field",
                    message=f"Required field '{field_name}' is missing",
                    expected_type=expected_type.__name__ if hasattr(expected_type, '__name__') else str(expected_type)
                )
            continue
        
        value = data[field_name]
        
        # Skip None values for optional fields
        if value is None and not is_required:
            continue
        
        # Validate type
        type_valid, type_error = validate_type(value, expected_type, field_path)
        if not type_valid:
            result.add_error(
                field_path=field_path,
                issue_type="type_mismatch",
                message=type_error,
                expected_type=str(expected_type),
                actual_value=value
            )
            continue
        
        # Validate list items
        if isinstance(value, list):
            item_type = field_def.get("item_type")
            item_schema = field_def.get("item_schema")
            
            for idx, item in enumerate(value):
                item_path = f"{field_path}[{idx}]"
                
                if item_type:
                    # Simple list of primitives
                    type_valid, type_error = validate_type(item, item_type, item_path)
                    if not type_valid:
                        result.add_error(
                            field_path=item_path,
                            issue_type="invalid_list_item",
                            message=f"Invalid item type: {type_error}",
                            expected_type=item_type.__name__,
                            actual_value=item
                        )
                
                elif item_schema:
                    # List of objects
                    if not isinstance(item, dict):
                        result.add_error(
                            field_path=item_path,
                            issue_type="invalid_list_item",
                            message=f"Expected dict, got {type(item).__name__}",
                            expected_type="dict",
                            actual_value=item
                        )
                    else:
                        # Recursively validate nested schema
                        nested_result = validate_dict_schema(
                            item, item_schema, item_path, is_strict
                        )
                        result.errors.extend(nested_result.errors)
                        result.warnings.extend(nested_result.warnings)
                        if not nested_result.is_valid:
                            result.is_valid = False
        
        # Validate nested dict schema
        elif isinstance(value, dict) and "schema" in field_def:
            nested_schema = field_def["schema"]
            nested_result = validate_dict_schema(value, nested_schema, field_path, is_strict)
            result.errors.extend(nested_result.errors)
            result.warnings.extend(nested_result.warnings)
            if not nested_result.is_valid:
                result.is_valid = False
    
    return result


def validate_llm_output(data: Any, strict: bool = True) -> ValidationResult:
    """
    Enterprise-level validation of LLM output against ResumeData schema.
    
    Args:
        data: Raw output from LLM (should be a dictionary)
        strict: If True, apply strict validation rules
    
    Returns:
        ValidationResult with detailed errors and warnings
    """
    result = ValidationResult(is_valid=True)
    
    # Check if data is a dict
    if not isinstance(data, dict):
        result.add_error(
            field_path="root",
            issue_type="invalid_root_type",
            message=f"LLM output must be a dictionary, got {type(data).__name__}",
            expected_type="dict",
            actual_value=str(data)[:100] if data else None
        )
        return result  # Can't continue validation
    
    # Check for required top-level keys
    present_keys = set(data.keys())
    missing_keys = REQUIRED_TOP_LEVEL_KEYS - present_keys
    
    if missing_keys:
        for key in sorted(missing_keys):
            if strict:
                result.add_error(
                    field_path=key,
                    issue_type="missing_required_key",
                    message=f"Required top-level key '{key}' is missing from LLM output"
                )
            else:
                result.add_warning(
                    field_path=key,
                    issue_type="missing_key",
                    message=f"Key '{key}' is missing"
                )
    
    # Validate against full schema
    schema_result = validate_dict_schema(data, RESUME_SCHEMA, "", strict)
    result.errors.extend(schema_result.errors)
    result.warnings.extend(schema_result.warnings)
    
    if not schema_result.is_valid:
        result.is_valid = False
    
    # Log validation result
    if result.is_valid:
        logger.info("✓ LLM output validation PASSED")
    else:
        logger.warning(f"✗ LLM output validation FAILED with {len(result.errors)} errors")
        logger.warning(result.get_error_summary())
    
    return result


def sanitize_llm_output(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize LLM output to fix common issues before validation.
    
    Args:
        data: Raw LLM output dictionary
    
    Returns:
        Sanitized dictionary
    """
    if not isinstance(data, dict):
        return {}
    
    sanitized = {}
    
    for key, expected_def in RESUME_SCHEMA.items():
        if key not in data:
            # Initialize missing required fields with defaults
            if expected_def.get("required"):
                if expected_def["type"] == str:
                    sanitized[key] = ""
                elif expected_def["type"] == list:
                    sanitized[key] = []
                elif expected_def["type"] == dict:
                    sanitized[key] = {}
            continue
        
        value = data[key]
        expected_type = expected_def["type"]
        
        # Convert single values to lists where lists are expected
        if expected_type == list and isinstance(value, str):
            if value.strip():
                sanitized[key] = [value]
            else:
                sanitized[key] = []
        elif expected_type == list and not isinstance(value, list):
            sanitized[key] = []
        elif expected_type == str and isinstance(value, list):
            sanitized[key] = value[0] if value else ""
        elif expected_type == str and not isinstance(value, str):
            sanitized[key] = str(value) if value is not None else ""
        else:
            sanitized[key] = value
    
    return sanitized


# ============== HELPER FOR RETRY PROMPT ==============

def generate_retry_prompt(original_prompt: str, validation_result: ValidationResult, 
                          attempt: int) -> str:
    """
    Generate an enhanced prompt for retry attempts based on validation errors.
    
    Args:
        original_prompt: The original LLM prompt
        validation_result: Result from previous validation
        attempt: Current attempt number (1-indexed)
    
    Returns:
        Enhanced prompt with validation feedback
    """
    error_summary = validation_result.get_error_summary()
    
    retry_instruction = f"""

═══════════════════════════════════════════════════════════════
⚠️ VALIDATION ERROR - RETRY ATTEMPT {attempt}
═══════════════════════════════════════════════════════════════

Your previous JSON output had the following validation errors:

{error_summary}

CRITICAL REQUIREMENTS:
1. Return ONLY valid JSON - no markdown, no comments, no explanations
2. ALL required fields MUST be present:
   - name (string)
   - email (array of strings)
   - phone (array of strings)
   - linkedin (array of strings)
   - github (array of strings)
   - education (array of objects)
   - experience (array of objects)
   - skills (array of strings)
   - projects (array of objects)
   - hobbies (array of objects)
   - miscellaneous (object with coding_profiles, certifications, expertise, other_links)

3. For array fields: use [] if no data found (NEVER use null or string)
4. For string fields: use "" if no data found (NEVER use null)
5. Each education entry must have: level, qualification, institution, location, percentage, year
6. Each experience entry must have: job_title, company, duration, description
7. Each project entry must have: title, description, technologies (array), link
8. Each hobby entry must have: name, description

═══════════════════════════════════════════════════════════════
"""
    
    return original_prompt + retry_instruction


# ============== DECORATOR FOR VALIDATION RETRY ==============

def with_validation_retry(max_retries: int = 3):
    """
    Decorator to add validation retry logic to LLM parsing functions.
    
    Usage:
        @with_validation_retry(max_retries=3)
        def parse_with_llm(text: str) -> dict:
            ...
    """
    def decorator(func):
        def wrapper(text: str, *args, **kwargs):
            last_result = None
            
            for attempt in range(1, max_retries + 1):
                # Call the original function
                llm_output = func(text, *args, **kwargs)
                
                # Validate the output
                validation_result = validate_llm_output(llm_output, strict=True)
                
                if validation_result.is_valid:
                    logger.info(f"Validation passed on attempt {attempt}")
                    return llm_output
                
                last_result = llm_output
                logger.warning(f"Validation failed on attempt {attempt}/{max_retries}")
                
                # If not the last attempt, enhance the prompt with errors
                if attempt < max_retries:
                    text = generate_retry_prompt(
                        text, 
                        validation_result, 
                        attempt
                    )
            
            # All retries exhausted
            logger.error(f"All {max_retries} validation attempts failed")
            return None  # Signal that validation failed
        
        return wrapper
    return decorator