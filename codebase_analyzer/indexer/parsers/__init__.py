"""Parser implementations — auto-register via @register_parser decorator."""

from .php_parser import PHPParser  # noqa: F401
from .go_parser import GoParser  # noqa: F401
from .typescript_parser import TypeScriptParser, TSXParser, JavaScriptParser  # noqa: F401
