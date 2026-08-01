import subprocess

from pydantic_ai import Tool


def run_shell_command(command: str) -> str:
    """Executes a shell command (like ruff check or pytest) and returns the output."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
        return f"EXIT CODE: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 15 seconds."
    except Exception as e:
        return f"Error executing command: {str(e)}"


# Define as a Tool
shell_tool = Tool(run_shell_command, description="Executes a shell command")
