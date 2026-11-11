"""Pin artifact bytes between release preparation, inspection, and upload."""
import hashlib
import json
from pathlib import Path
import sys


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def main():
    mode, manifest, identity, *files = sys.argv[1:]
    target = Path(manifest)
    state = {'identity': identity, 'artifacts': {
        str(Path(file).resolve()): digest(Path(file)) for file in files}}
    if not files:
        raise ValueError('no artifacts selected')
    if mode == 'record':
        target.write_text(json.dumps(state, indent=2) + '\n')
    elif mode == 'verify':
        if json.loads(target.read_text()) != state:
            raise ValueError('prepared release changed; prepare and inspect it again')
    else:
        raise ValueError('unknown manifest operation')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        sys.exit(f'error: {error}')
