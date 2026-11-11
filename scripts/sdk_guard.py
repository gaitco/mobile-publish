"""Validate the installed SDK before a legacy preparation build."""
import json
from pathlib import Path
import subprocess
import sys

from release_request import sdk_context


def main():
    app = Path(sys.argv[1])
    sdk = sdk_context(app, {})
    # The legacy builder invokes flutter directly. FVM/custom commands belong in
    # the coordinated project profile, never validated then silently ignored.
    if sdk['command'] != ['flutter']:
        raise ValueError('SDK-manager projects require a coordinated release profile')
    result = subprocess.run(['flutter', '--version', '--machine'], cwd=app,
                            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=45)
    if result.returncode or json.loads(result.stdout).get('frameworkVersion') != sdk['version']:
        raise ValueError('SDK mismatch')
    print(sdk['version'])


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError):
        sys.exit('error: verify the exact project SDK pin and installed toolchain')
