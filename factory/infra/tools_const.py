import logging
_logger = logging.getLogger('orchestrator.security')
_STEER = '\n---\nTip: Use batch_read for broad discovery; read_file is for targeted line reads only.\nbatch_read format: line_ranges is ONE contiguous \'start-end\' range per file (e.g. {"src/foo.py": "400-500"}). NEVER use comma-joined multi-segments like \'400, 600-650, 760-800\' — that is a malformed range and the call fails. For non-contiguous slices, make separate batch_read calls (one range each).'
_REMEMBER_NUDGE = '\n---\nSince you are stateless across turns, you may call `remember("<note>")` to record anything you need to execute correctly on your next turn (e.g. a focused slice, an edit decision, or a collision to avoid). Use `remember`, not `bd`.'
MAX_BATCH_FILES = 20
_BATCH_READ_NO_PATHS = 'batch_read: no paths provided. You MUST pass paths=[...] (a list of file paths). Optionally pass line_ranges={path: "start-end"} per file; if you omit line_ranges the tool returns the first 250 lines of each file. Example: batch_read(paths=["src2/core/schemas/unified.py"], line_ranges={"src2/core/schemas/unified.py": "300-400"}).'
_BATCH_READ_DEFAULT_HEAD = 250
CODER_WRITE_ROOTS = ['factory/temp/']
_BATCH_READ_STEER = '\n---\nbatch_read line_ranges format: ONE contiguous \'start-end\' range per file ({"src/foo.py": "400-500"}). Do NOT use comma-joined multi-segments (\'400, 600-650, 760-800\') — that fails. For non-contiguous slices, make separate batch_read calls.'
_SRC_BAN_MSG = 'ERROR: src/ and src2/ are read-only. Harness edits are confined to factory/.'
__all__ = ['_logger', '_STEER', '_REMEMBER_NUDGE', 'MAX_BATCH_FILES', '_BATCH_READ_NO_PATHS', '_BATCH_READ_DEFAULT_HEAD', 'CODER_WRITE_ROOTS', '_BATCH_READ_STEER', '_SRC_BAN_MSG']
