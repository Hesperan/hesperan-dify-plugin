from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.hesperan_client import HesperanError, validate_key


class HesperanProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            validate_key(credentials.get("hesperan_api_key") or "")
        except HesperanError as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
