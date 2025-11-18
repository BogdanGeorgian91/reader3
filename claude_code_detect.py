"""
Claude Code detection and authentication module.

Detects if Claude Code is available and properly authenticated via
environment variables and CLI checks.
"""

import os
import shutil
import subprocess


def is_claude_code_available() -> bool:
    """Check if Claude Code CLI is installed and available in PATH."""
    return shutil.which("claude") is not None


def _has_env_auth() -> bool:
    """Check for authentication via environment variables."""
    return bool(
        os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("ANTHROPIC_AUTH_TOKEN")
        or os.getenv("AWS_BEARER_TOKEN_BEDROCK")
    )


def _has_cli_auth() -> bool:
    """Check Claude Code CLI auth by testing if it can run a command."""
    try:
        result = subprocess.run(
            ["claude", "-p", "test"],
            capture_output=True,
            text=True,
            timeout=10
        )
        # Exit code 0 means command succeeded (authenticated)
        # Non-zero or auth errors in stderr mean not authenticated
        if result.returncode != 0:
            return False
        # Check stderr for auth-related errors
        if result.stderr and ("auth" in result.stderr.lower() or "unauthorized" in result.stderr.lower()):
            return False
        return True
    except subprocess.TimeoutExpired:
        # If it times out, assume authenticated (Claude Code is processing)
        return True
    except Exception:
        pass
    return False


def is_authenticated() -> bool:
    """Check if Claude Code is authenticated via environment or CLI."""
    return _has_env_auth() or _has_cli_auth()


def get_claude_code_status() -> dict:
    """
    Get the current Claude Code status.

    Returns:
        dict with keys:
            - available: bool, whether Claude Code is installed
            - authenticated: bool, whether Claude Code is authenticated
            - enabled: bool, whether Claude Code is both available and authenticated
    """
    available = is_claude_code_available()
    authenticated = is_authenticated() if available else False

    return {
        "available": available,
        "authenticated": authenticated,
        "enabled": available and authenticated,
    }
