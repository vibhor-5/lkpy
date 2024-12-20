"""
Console and related logging support
"""

import atexit
from logging import Handler, LogRecord

from rich.ansi import AnsiDecoder
from rich.console import Console
from rich.live import Live

console = Console(stderr=True)
_live: Live | None = None


class ConsoleHandler(Handler):
    """
    Lightweight Rich log handler for routing StructLog-formatted logs.
    """

    _decoder = AnsiDecoder()

    @property
    def supports_color(self) -> bool:
        return console.is_terminal and not console.no_color

    def emit(self, record: LogRecord) -> None:
        try:
            fmt = self.format(record)
            print(fmt)
            # console.print(*self._decoder.decode(fmt))
        except Exception:
            self.handleError(record)


def get_live() -> Live | None:
    return _live


def setup_console():
    global _live
    if _live is not None:
        return
    if not console.is_terminal:
        return

    _live = Live(console=console, transient=True)
    _live.start()


@atexit.register
def _stop_console():
    if _live is not None:
        _live.stop()
