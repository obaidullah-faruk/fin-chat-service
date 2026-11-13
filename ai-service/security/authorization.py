from collections.abc import Sequence
import logging
from typing import Any

logger = logging.getLogger("finchat.security.authorization")

try:
    from langchain_core.tools import ToolException
except ImportError:
    class ToolException(Exception):  # type: ignore[no-redef]
        """Fallback tool exception if langchain_core is not installed."""
        pass


ROLE_CUSTOMER = "customer"
ROLE_MANAGER = "manager"
ROLE_ADMIN = "admin"
ROLE_SUPERADMIN = "superadmin"

# Permissions matrix matching FinChat architecture (Section 8.5)
ROLE_PERMISSIONS: dict[str, set[str] | str] = {
    ROLE_CUSTOMER: {
        "get_balance",
        "get_account_info",
        "get_transactions",
        "get_statement",
        "request_cheque_book",
    },
    ROLE_MANAGER: {
        "get_balance",
        "get_account_info",
        "get_transactions",
        "get_statement",
        "request_cheque_book",
        "update_address",
        "get_kyc_status",
    },
    ROLE_ADMIN: "__all__",
    ROLE_SUPERADMIN: "__all__",
}


class ToolAuthorizationError(ToolException):
    """Raised when an actor's role is not authorized to execute an agent tool."""

    def __init__(
        self,
        role: str,
        tool_name: str,
        message: str | None = None,
    ) -> None:
        self.role = role
        self.tool_name = tool_name
        error_msg = (
            message
            or f"Permission denied: role '{role}' is not authorized to execute tool '{tool_name}'."
        )
        super().__init__(error_msg)


def is_tool_allowed(role: str | None, tool_name: str) -> bool:
    """
    Check if a specific tool is permitted for the given role.
    Returns True if permitted, False otherwise.
    """
    if not role or not tool_name:
        return False

    normalized_role = role.strip().lower()
    allowed = ROLE_PERMISSIONS.get(normalized_role, set())
    if allowed == "__all__":
        return True
    return tool_name in allowed


def check_tool_authorization(role: str | None, tool_name: str) -> None:
    """
    Assert that the role is authorized to execute the tool.
    Raises ToolAuthorizationError if unauthorized.
    """
    if not is_tool_allowed(role, tool_name):
        logger.warning(
            "Authorization check failed: role='%s' attempted to execute tool='%s'",
            role,
            tool_name,
        )
        raise ToolAuthorizationError(role=role or "unknown", tool_name=tool_name)


def get_role_permissions(role: str | None) -> set[str] | str:
    """Return the set of allowed tool names or '__all__' for a given role."""
    if not role:
        return set()
    normalized_role = role.strip().lower()
    return ROLE_PERMISSIONS.get(normalized_role, set())


def filter_tools_for_role(
    tools: Sequence[Any],
    role: str | None,
) -> list[Any]:
    """
    Filter a sequence of tools or tool names down to only those allowed for the role.
    Accepts list of BaseTool/StructuredTool instances or list of string tool names.
    """
    allowed_items: list[Any] = []
    for item in tools:
        name = getattr(item, "name", None) or str(item)
        if is_tool_allowed(role, name):
            allowed_items.append(item)
    return allowed_items

