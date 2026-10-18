"""Batch log for reversible management commands (changes/0010 S2).

A command that writes data first writes a JSON batch file (exclusive create: an existing file is never
overwritten) and only then changes the database, inside one transaction. The batch lists exactly the rows
touched, so a later ``--revert-batch`` undoes exactly those and nothing else. No default location is used: the
operator names the file. Ids only, no names and no personal data.
"""
import json
import os
from datetime import datetime, timezone

from django.core.management.base import CommandError

VERSION = 1


def write_batch(path, command, payload):
    data = {'command': command, 'version': VERSION,
            'created_at': datetime.now(timezone.utc).isoformat(), **payload}
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise CommandError('The batch file already exists; it is never overwritten. Choose a new path.')
    except OSError as exc:
        raise CommandError(f'Cannot create the batch file: {exc.strerror}')
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
    return data


def read_batch(path, command):
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        raise CommandError('The batch file cannot be read as JSON.')
    if not isinstance(data, dict) or data.get('command') != command or data.get('version') != VERSION:
        raise CommandError(f'This is not a batch file of "{command}" (version {VERSION}).')
    return data


def int_list(data, key):
    values = data.get(key)
    if not isinstance(values, list) or not all(isinstance(v, int) and not isinstance(v, bool) for v in values):
        raise CommandError(f'The batch file field "{key}" must be a list of integers.')
    return values
