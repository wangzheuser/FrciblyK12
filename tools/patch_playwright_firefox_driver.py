"""Patch local Playwright Firefox driver crashes seen with Camoufox/Node 24.

The bundled Playwright driver can terminate the whole Node driver process when
Firefox emits incomplete PageError/WebSocket bookkeeping events.  The patch is
idempotent and only touches the local virtualenv copy used by dev-start.
"""

from __future__ import annotations

from pathlib import Path
import sys


PAGE_ERROR_OLD = """this.addObjectListener(BrowserContext.Events.PageError, (pageError, page) => {
          this._dispatchEvent("pageError", {
            error: serializeError(pageError.error),
            page: PageDispatcher.from(this, page),
            location: {
              url: pageError.location.url,
              line: pageError.location.lineNumber,
              column: pageError.location.columnNumber
            }
          });
        });"""

PAGE_ERROR_NEW = """this.addObjectListener(BrowserContext.Events.PageError, (pageError, page) => {
          const location = pageError.location || {};
          this._dispatchEvent("pageError", {
            error: serializeError(pageError.error),
            page: PageDispatcher.from(this, page),
            location: {
              url: location.url || "",
              line: location.lineNumber || 0,
              column: location.columnNumber || 0
            }
          });
        });"""

WEBSOCKET_OLD = """const request2 = this._webSocketRequests.get(event.requestId);
        assert(request2);
        const response2 = this._webSocketResponses.get(event.requestId);
        assert(response2);"""

WEBSOCKET_NEW = """const request2 = this._webSocketRequests.get(event.requestId);
        if (!request2)
          return;
        const response2 = this._webSocketResponses.get(event.requestId);
        if (!response2)
          return;"""


def patch_text(text: str) -> tuple[str, bool]:
    patched = text
    changed = False
    if PAGE_ERROR_OLD in patched and PAGE_ERROR_NEW not in patched:
        patched = patched.replace(PAGE_ERROR_OLD, PAGE_ERROR_NEW)
        changed = True
    if WEBSOCKET_OLD in patched and WEBSOCKET_NEW not in patched:
        patched = patched.replace(WEBSOCKET_OLD, WEBSOCKET_NEW)
        changed = True
    return patched, changed


def default_core_bundle_path(root: Path | None = None) -> Path:
    base = root or Path(__file__).resolve().parents[1]
    return base / ".venv" / "Lib" / "site-packages" / "playwright" / "driver" / "package" / "lib" / "coreBundle.js"


def patch_file(path: Path) -> str:
    if not path.exists():
        return f"skip: {path} not found"
    original = path.read_text(encoding="utf-8")
    patched, changed = patch_text(original)
    if not changed:
        return "already-patched"
    path.write_text(patched, encoding="utf-8")
    return "patched"


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    path = Path(args[0]) if args else default_core_bundle_path()
    print(patch_file(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
