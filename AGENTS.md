# AGENTS.md

## Code style

Disqualify a change if it:

- swallows a type/attribute error with try/except (only untrusted-input parsing and
  logged keep-alive loops may catch broadly, and must report)
- uses `cast()`, `# type: ignore`, or `Any` (third-party stub workarounds need an error
  code and a comment naming the library)
- uses `getattr(x, "k", default)` or `dict.get(k, default)` instead of an explicit check
- leaves a function without full parameter and return annotations
- blocks the UI thread: all network calls go through `threads.AsyncCall` (worker thread
  + Qt signal back)
- writes comments longer than two lines

Before saying a task is done: `python -m compileall xixi_echo` plus an offscreen smoke
test (`QT_QPA_PLATFORM=offscreen python -c "import xixi_echo.app"`).

## Cross-repo contract

- `xixi_echo/signing.py` mirrors the server-side signing implementation; keep the canonical
  string byte-identical on both sides.
- The server holds the upstream token; this client only ever holds its own issued key.
- Never persist images to disk except the user-triggered 另存为 dialog.
- Releases: bump `__version__` in `xixi_echo/__init__.py` and tag with the same `vX.Y.Z` —
  CI enforces the match and fails the build otherwise.
