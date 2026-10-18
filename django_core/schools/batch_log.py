"""Batch log for reversible management commands (changes/0010 S2).

A command that writes data records, in a JSON batch file, exactly the rows it ACTUALLY changed (not the rows it
planned), and writes the file inside the same transaction, before it commits: if the file cannot be written the
changes roll back. The file is created exclusively (an existing file is never overwritten) with mode 0600. No default
location is used: the operator names the file. Ids only, no names and no personal data. A later ``--revert-batch``
verifies every row it touches against the values recorded here and undoes only those.
"""
import json
import os
from datetime import datetime, timezone

from django.core.management.base import CommandError

VERSION = 2          # 2: rows carry user_id/school_id (membership batches) and are the rows actually updated
MAX_ID = 2 ** 63 - 1  # largest id the supported databases accept


def valid_id(value):
    """True only for a real integer in 1..MAX_ID: no bool, float, string, None, zero, negative or huge value."""
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= MAX_ID


def ensure_new(path):
    """Fail early (before any database work) when the batch file path is already taken."""
    if os.path.lexists(path):
        raise CommandError('The batch file already exists; it is never overwritten. Choose a new path.')


def write_batch(path, command, payload):
    data = {'command': command, 'version': VERSION,
            'created_at': datetime.now(timezone.utc).isoformat(), **payload}
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise CommandError('The batch file already exists; it is never overwritten. Choose a new path.')
    except OSError as exc:
        raise CommandError(f'Cannot create the batch file: {exc.strerror}')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
    except (OSError, ValueError, TypeError) as exc:
        try:
            os.unlink(path)  # never leave a truncated batch behind
        except OSError:
            pass
        raise CommandError(f'Cannot write the batch file: {getattr(exc, "strerror", None) or "write failed"}')
    return data


def read_batch(path, command):
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError, RecursionError):
        raise CommandError('The batch file cannot be read as JSON.')
    if not isinstance(data, dict) or data.get('command') != command or data.get('version') != VERSION:
        raise CommandError(f'This is not a batch file of "{command}" (version {VERSION}).')
    return data


def id_rows(data, key, fields):
    """Validated list of dicts: every field of every row must satisfy ``valid_id``. One validator for all reverts."""
    rows = data.get(key)
    if not isinstance(rows, list) or not all(
            isinstance(row, dict) and all(valid_id(row.get(field)) for field in fields) for row in rows):
        raise CommandError(f'The batch file field "{key}" must be a list of rows with integer ids '
                           f'({", ".join(fields)}) between 1 and {MAX_ID}.')
    return rows


def require_valid_id(data, key):
    if not valid_id(data.get(key)):
        raise CommandError(f'The batch file field "{key}" must be an integer id between 1 and {MAX_ID}.')
    return data[key]


def reject_flag_combinations(opts, *, revert, apply_requires=None, needs_apply=()):
    """Operator-facing contract: a flag that would be silently ignored is an error.

    ``revert``: name of the revert option (excludes every other write option); ``apply_requires``: option that
    ``--apply`` needs to be meaningful (or None); ``needs_apply``: options that are only valid together with --apply.
    """
    if opts.get(revert):
        others = [name for name in ('apply', 'batch_file', 'deactivate', 'accept_visibility_change') if opts.get(name)]
        if others:
            raise CommandError('--revert-batch cannot be combined with ' + ', '.join('--' + n.replace('_', '-') for n in others) + '.')
    if opts.get('apply') and apply_requires and not opts.get(apply_requires):
        raise CommandError(f'--apply needs --{apply_requires.replace("_", "-")}.')
    for name in needs_apply:
        if opts.get(name) and not opts.get('apply'):
            raise CommandError(f'--{name.replace("_", "-")} only works together with --apply.')
