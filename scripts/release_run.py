"""Application-scoped local lock and durable, private release journal."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import uuid
import re

from prepared_release import digest


def now():
    return datetime.now(timezone.utc).isoformat()


def state_root():
    return Path.home() / '.local/state/mobile-publish'


def application_root(request, root):
    key = request['application'] + '|' + request['environment']
    return Path(root) / hashlib.sha256(key.encode()).hexdigest()


def private_directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)


@contextmanager
def application_lock(request, root=None):
    directory = application_root(request, root or state_root())
    private_directory(directory)
    with (directory / 'release.lock').open('a') as lock:
        os.chmod(lock.name, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('application is locked by another local release') from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


class Journal:
    def __init__(self, path, data):
        self.path, self.data = path, data

    @classmethod
    def open(cls, request, root=None):
        directory = application_root(request, root or state_root())
        private_directory(directory)
        runs = []
        for path in directory.glob('*/run.json'):
            data = json.loads(path.read_text())
            runs.append((path, data))
        for path, data in sorted(runs, key=lambda item: item[1]['created'], reverse=True):
            if data['request'] == request and data.get('stage') != 'closed_preparation':
                return cls(path.parent, data)
        if any(not cls.complete(data) and data.get('stage') != 'closed_preparation' for _, data in runs):
            raise ValueError('a different pending release exists; inspect it before starting another')
        identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-') + uuid.uuid4().hex[:12]
        path = directory / identifier
        private_directory(path)
        journal = cls(path, dict(id=identifier, created=now(), request=request,
                                stage='readiness', artifacts={}, events=[],
                                stores={s: {'state': 'pending'} for s in request['stores']}))
        journal.save()
        return journal

    @staticmethod
    def complete(data):
        return bool(data['stores']) and all(s['state'] == 'accepted' for s in data['stores'].values())

    @classmethod
    def close_prepared(cls, request, identifier, root=None):
        if not re.fullmatch(r'\d{8}T\d{6}-[a-f0-9]{12}', identifier):
            raise ValueError('invalid release run ID')
        path = application_root(request, root or state_root()) / identifier
        data = json.loads((path / 'run.json').read_text())
        if any(event.get('state') == 'transport' for event in data['events']):
            raise ValueError('transport was attempted; reconcile exact store state before closing any release')
        journal = cls(path, data)
        journal.stage('closed_preparation')
        return journal

    def save(self):
        temporary = self.path / 'run.json.tmp'
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, 'w') as output:
            json.dump(self.data, output, indent=2)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(self.path / 'run.json')
        descriptor = os.open(self.path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def transition(self, store, state, reference=None, elapsed=None):
        allowed = {'pending', 'querying', 'absent', 'transport', 'processing', 'accepted',
                   'rejected', 'unknown', 'blocked'}
        if state not in allowed or store not in self.data['stores']:
            raise ValueError('invalid release transition')
        entry = {'state': state}
        # Store references are opaque IDs, never arbitrary tool output or URLs.
        if reference is not None:
            if not isinstance(reference, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}', reference):
                raise ValueError('unsafe store reference')
            entry['reference'] = reference
        self.data['stores'][store] = entry
        event = dict(store=store, state=state, at=now())
        if elapsed is not None:
            event['seconds'] = round(elapsed, 3)
        self.data['events'].append(event)
        self.save()

    def stage(self, name, seconds=None):
        self.data['stage'] = name
        event = dict(stage=name, at=now())
        if seconds is not None:
            event['seconds'] = round(seconds, 3)
        self.data['events'].append(event)
        self.save()

    def archive(self, artifacts):
        records = {}
        for store, source in artifacts.items():
            if store not in self.data['stores']:
                raise ValueError('artifact store is outside request')
            source = Path(source)
            before = digest(source)
            target = self.path / (store + source.suffix)
            shutil.copyfile(source, target)
            target.chmod(0o400)
            if digest(source) != before or digest(target) != before:
                raise ValueError('artifact changed while archiving')
            records[store] = dict(file=target.name, sha256=before)
        self.data['artifacts'] = records
        self.stage('prepared')

    def artifact(self, store):
        name = self.data['artifacts'][store]['file']
        if Path(name).name != name:
            raise ValueError('invalid artifact path')
        return self.path / name

    def verify_artifacts(self):
        for store, record in self.data['artifacts'].items():
            if digest(self.artifact(store)) != record['sha256']:
                raise ValueError('archived artifact changed; upload blocked')

    def prune(self, keep=20):
        completed = []
        for path in self.path.parent.glob('*/run.json'):
            if path.parent == self.path:
                continue
            data = json.loads(path.read_text())
            if self.complete(data) or data.get('stage') == 'closed_preparation':
                completed.append((data['created'], path.parent))
        for _, path in sorted(completed, reverse=True)[max(keep - 1, 0):]:
            shutil.rmtree(path)
