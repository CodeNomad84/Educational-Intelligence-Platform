"""Dump the database to a timestamped file in a backup directory (platform operator, terminal only).

    manage.py backup_db [--output DIR]

* PostgreSQL: runs the server's ``pg_dump`` with the connection settings of ``settings.DATABASES['default']``.
  The password is handed to ``pg_dump`` through the ``PGPASSWORD`` environment variable and is never echoed
  or placed on the command line.
* Any other engine (SQLite in local/dev): falls back to ``manage.py dumpdata`` (JSON fixtures) with the
  transient tables (content types, sessions) excluded.

The command never overwrites an existing file (the filename carries a timestamp) and prints the absolute
path of the file it wrote. The default directory is ``/backups``; bind-mount it (or pass ``--output``) so the
file outlives the container.
"""
import os
import subprocess
import sys
from datetime import datetime

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections


class PgDumpMissing(Exception):
    """``pg_dump`` is not installed on the image; the caller should fall back to ``dumpdata``."""


class Command(BaseCommand):
    help = 'Dump the database to a timestamped file (pg_dump for PostgreSQL, dumpdata otherwise).'

    def add_arguments(self, parser):
        parser.add_argument('--output', default=os.environ.get('EIP_BACKUP_DIR', '/backups'),
                            help='destination directory (default: /backups or $EIP_BACKUP_DIR)')

    def handle(self, *args, **options):
        out_dir = options['output']
        os.makedirs(out_dir, exist_ok=True)

        connection = connections['default']
        engine = connection.settings_dict['ENGINE']
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')

        if engine == 'django.db.backends.postgresql':
            path = os.path.join(out_dir, f'backup-{stamp}.sql')
            try:
                self._pg_dump(connection.settings_dict, path)
            except PgDumpMissing as exc:
                self.stderr.write(self.style.WARNING(f'{exc}; falling back to dumpdata (JSON fixtures).'))
                path = os.path.join(out_dir, f'backup-{stamp}.json')
                self._dumpdata(path)
        else:
            path = os.path.join(out_dir, f'backup-{stamp}.json')
            self._dumpdata(path)

        self.stdout.write(self.style.SUCCESS(f'backup written: {path}'))

    def _pg_dump(self, db, path):
        pg_dump = os.environ.get('PG_DUMP', 'pg_dump')
        args = [pg_dump, '--no-owner', '--no-privileges', '-f', path]
        if db.get('HOST'):
            args += ['-h', str(db['HOST'])]
        if db.get('PORT'):
            args += ['-p', str(db['PORT'])]
        args += ['-U', str(db.get('USER') or ''), str(db.get('NAME') or '')]

        env = dict(os.environ)
        env['PGPASSWORD'] = str(db.get('PASSWORD') or '')
        try:
            result = subprocess.run(args, env=env, capture_output=True, text=True)
        except FileNotFoundError:
            raise PgDumpMissing(f'pg_dump not found (looked for {pg_dump!r}); set PG_DUMP or install postgresql-client.') from None
        if result.returncode != 0:
            # Never echo the password: pg_dump's stderr does not contain it, but be defensive anyway.
            secret = str(db.get('PASSWORD') or '')
            detail = (result.stderr or '').replace(secret, '***') if secret else (result.stderr or '')
            raise CommandError(f'pg_dump failed (exit {result.returncode}): {detail.strip()}')

    def _dumpdata(self, path):
        # Redirect the dump to the file without going through the shell.
        with open(path, 'w') as target:
            old_stdout = sys.stdout
            try:
                sys.stdout = target
                call_command('dumpdata', '--indent', '2', exclude=['contenttypes', 'sessions'])
            finally:
                sys.stdout = old_stdout
