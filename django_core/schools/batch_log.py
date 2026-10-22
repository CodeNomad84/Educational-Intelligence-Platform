"""Batch log for reversible management commands (changes/0010 S2; R-a, S3: signed).

A command that writes data records, in a JSON batch file, exactly the rows it ACTUALLY changed (not the rows it
planned), and writes the file inside the same transaction, before it commits: if the file cannot be written the
changes roll back. The file is created exclusively (an existing file is never overwritten) with mode 0600. No default
location is used: the operator names the file. Ids only, no names and no personal data. A later ``--revert-batch``
verifies every row it touches against the values recorded here and undoes only those.

R-a (S3): every batch carries an HMAC-SHA256 ``signature`` (key: this installation's ``SECRET_KEY``) over all other
fields. A hand-edited batch, or one written by another installation, is refused before any row is read, so an edited
file cannot re-activate or delete rows the batch did not change. The key is not rotated lightly: a batch must be
reverted while the ``SECRET_KEY`` that signed it is in force.
"""
import hashlib
import hmac
import json
import os
import stat
from datetime import datetime, timezone

from django.conf import settings
from django.core.management.base import CommandError

VERSION = 3          # 3: signed (R-a). 2: rows carry user_id/school_id (membership batches), the rows actually updated
MAX_ID = 2 ** 63 - 1  # largest id the supported databases accept


def valid_id(value):
    """True only for a real integer in 1..MAX_ID: no bool, float, string, None, zero, negative or huge value."""
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= MAX_ID


def _given(opts, name):
    return opts.get(name) is not None


def check_path_options(opts):
    """An option that was GIVEN must be a usable path: an empty or whitespace-only value (typically an unset shell
    variable) and a path containing a NUL byte are errors, never 'absent' (S2 review R2)."""
    for name in ('batch_file', 'revert_batch'):
        value = opts.get(name)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise CommandError(f'--{name.replace("_", "-")} was given an empty value; give a path.')
        if '\0' in value:
            raise CommandError(f'--{name.replace("_", "-")} contains a NUL byte; give a valid path.')


def ensure_new(path):
    """Fail early (before any database work) when the batch file path is already taken."""
    if os.path.lexists(path):
        raise CommandError('The batch file already exists; it is never overwritten. Choose a new path.')


def _digest(data):
    body = json.dumps({k: v for k, v in data.items() if k != 'signature'}, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True)
    return hmac.new(settings.SECRET_KEY.encode('utf-8'), body.encode('utf-8'), hashlib.sha256).hexdigest()


def sign(data):
    """Return ``data`` with its ``signature`` (used by ``write_batch``; tests use it to build valid hand-made batches)."""
    return {**data, 'signature': _digest(data)}


def write_batch(path, command, payload):
    data = sign({'command': command, 'version': VERSION,
                 'created_at': datetime.now(timezone.utc).isoformat(), **payload})
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise CommandError('The batch file already exists; it is never overwritten. Choose a new path.')
    except OSError as exc:
        raise CommandError(f'Cannot create the batch file: {exc.strerror}')
    except (ValueError, TypeError):
        raise CommandError('The batch file path is not valid (empty, NUL byte or wrong type).')
    created = None   # identity of the file THIS call created (set inside the try: the fstat itself can fail)
    handle = None
    try:
        created = os.fstat(fd)
        handle = os.fdopen(fd, 'w', encoding='utf-8')
        with handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException as exc:  # incl. KeyboardInterrupt/MemoryError: clean up, then let it propagate
        if handle is None:
            try:
                os.close(fd)  # never leak the descriptor when fdopen was not reached
            except OSError:
                pass
        _remove_if_same_file(path, created)
        if isinstance(exc, (OSError, ValueError, TypeError)):
            raise CommandError(f'Cannot write the batch file: {getattr(exc, "strerror", None) or "write failed"}')
        raise
    return data


def _remove_if_same_file(path, created):
    """Unlink ``path`` only if it is still the file this call created (never a file or symlink swapped in meanwhile).

    ``lstat`` does not follow symlinks: a symlink put at the path is never removed through its target's identity.
    When the identity of the created file is unknown (the fstat itself failed) only a still-empty regular file is removed.
    """
    try:
        current = os.lstat(path)
        if not stat.S_ISREG(current.st_mode):
            return
        if created is None:
            same = current.st_size == 0
        else:
            same = (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino)
        if same:
            os.unlink(path)
    except OSError:
        pass


def read_batch(path, command):
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError, RecursionError):
        raise CommandError('The batch file cannot be read as JSON.')
    if not isinstance(data, dict) or data.get('command') != command:
        raise CommandError(f'This is not a batch file of "{command}".')
    version = data.get('version')
    if type(version) is not int or version != VERSION:  # exact int: True and 1.0 are not versions
        found = version if type(version) is int else 'unknown'
        raise CommandError(
            f'Unsupported batch version {found}: this tool reads version {VERSION}. A batch written by an older '
            'version must be reverted with the code version that wrote it.')
    signature = data.get('signature')
    if not isinstance(signature, str) or not hmac.compare_digest(signature, _digest(data)):
        raise CommandError('The batch file signature is missing or does not match: the file was edited or was written '
                           'by another installation. Nothing was changed.')
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
    check_path_options(opts)
    if _given(opts, revert):
        others = [name for name in ('apply', 'batch_file', 'deactivate', 'accept_visibility_change')
                  if (_given(opts, name) if name == 'batch_file' else opts.get(name))]
        if others:
            raise CommandError('--revert-batch cannot be combined with ' + ', '.join('--' + n.replace('_', '-') for n in others) + '.')
    if opts.get('apply') and apply_requires and not opts.get(apply_requires):
        raise CommandError(f'--apply needs --{apply_requires.replace("_", "-")}.')
    for name in needs_apply:
        if (_given(opts, name) if name == 'batch_file' else opts.get(name)) and not opts.get('apply'):
            raise CommandError(f'--{name.replace("_", "-")} only works together with --apply.')
