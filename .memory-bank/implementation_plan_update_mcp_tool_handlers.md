# Implementation Plan: Update MCP Tool Handlers for Boolean Parameter Handling

## Objective
Fix the boolean parameter validation issue in MCP tool handlers, specifically for the `is_active` parameter in the `create_project` tool and any other affected tools, by implementing explicit input coercion or validation.

## Background
- MCP tools currently rely on automatic input schema generation via Pydantic based on function signatures.
- Boolean parameters may receive inputs as strings or nulls, causing validation errors.
- The Web UI handles boolean inputs correctly via FastAPI form parsing.
- Updating MCP tool handlers to coerce or validate boolean inputs will align behavior and fix validation errors.

## Scope
- Update `create_project` MCP tool handler to coerce `is_active` input to boolean.
- No other MCP tool handlers currently have boolean parameters requiring coercion.
- Ensure backward compatibility and no impact on existing functionality.
- Add unit tests to verify correct boolean handling in MCP tool handlers.

## Tasks

### 1. Analyze MCP Tool Handlers
- Identify all MCP tool handlers with boolean parameters.
- Confirm current parameter handling and validation.

### 2. Implement Input Coercion
- Modify MCP tool handlers to explicitly convert inputs like "true", "false", None to boolean True/False.
- Use helper functions or Pydantic validators if appropriate.

### 3. Update Unit Tests
- Add or update tests to cover boolean parameter edge cases.
- Test with string inputs, nulls, and proper booleans.

### 4. Manual Testing
- Test MCP tool calls with various boolean input formats.
- Verify validation errors are resolved.
- Confirm no regressions in other tool functionalities.

### 5. Documentation
- Update relevant documentation to reflect input handling changes.
- Note any client-side requirements for boolean parameters.

## Timeline
- Estimated 1-2 hours for implementation and testing.
- Additional time for documentation updates and review.

## Risks and Mitigations
- Risk: Input coercion may inadvertently accept invalid inputs.
  - Mitigation: Implement strict validation and comprehensive tests.
- Risk: Changes may affect clients expecting strict typing.
  - Mitigation: Communicate changes and maintain backward compatibility.

## Next Steps
- Await approval to proceed with implementation.
- Begin with `create_project` tool handler update.
- Progress to other tools as needed.

---

This plan outlines a clear, step-by-step approach to resolve the boolean parameter validation issue in MCP tool handlers.
