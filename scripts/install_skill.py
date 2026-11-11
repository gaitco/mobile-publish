"""Install/update an approved skill revision without replacing local work or secrets."""
import argparse
from pathlib import Path
import re
import subprocess
import sys

REPOSITORY = 'git@github.com:gaitco/mobile-publish.git'
START = '<!-- mobile-publish:start -->'
END = '<!-- mobile-publish:end -->'
RULE = '''For every mobile application store-upload or OTA-patch request (including «ارفع»
in a mobile-app context), read and use the installed mobile-publish skill first.
Follow mobile-publish.config.json and existing release workflows. Standard Flutter
projects must not install, authenticate to, or use Shorebird. Preserve Shorebird
projects' runtime; missing access never authorizes a plain-Flutter fallback.
Use the operator's own authorized credentials or an already approved CI workflow.
Never copy another developer's credentials. An upload request does not authorize
runtime migration, billing changes, or converting a store release to an OTA patch.
If this skill is missing, resolve its installation from gaitco/mobile-publish before
publishing. This rule does not route backend, website, or arbitrary file uploads.
'''


def git(*args):
    result = subprocess.run(['git', *map(str, args)], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Git operation failed; inspect repository access/state (output suppressed)')
    return result.stdout.strip()


def origin_key(value):
    return value.rstrip('/').removesuffix('.git').replace('git@github.com:', 'https://github.com/')


def inspect(target, source):
    if not target.exists():
        return 'missing'
    if not target.is_dir() or not (target / '.git').exists():
        raise ValueError(f'{target}: existing directory is not a skill Git checkout')
    if Path(git('-C', target, 'rev-parse', '--show-toplevel')).resolve() != target.resolve():
        raise ValueError(f'{target}: not an independent skill checkout')
    if origin_key(git('-C', target, 'remote', 'get-url', 'origin')) != origin_key(source):
        raise ValueError(f'{target}: origin differs; left unchanged')
    if git('-C', target, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError(f'{target}: local changes found; left unchanged')
    return git('-C', target, 'rev-parse', 'HEAD')


def register_rule(path):
    content = path.read_text() if path.exists() else ''
    block = f'{START}\n{RULE}{END}'
    if START in content or END in content:
        if content.count(START) != 1 or content.count(END) != 1 or content.index(END) < content.index(START):
            raise ValueError(f'{path}: malformed managed rule; left unchanged')
        content = content[:content.index(START)] + block + content[content.index(END) + len(END):]
    else:
        content = content.rstrip() + ('\n\n' if content.strip() else '') + block + '\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default=REPOSITORY, help='trusted Git source; defaults to the company repository')
    parser.add_argument('--revision', required=True, help='approved full 40-character commit SHA')
    parser.add_argument('--target', choices=['codex', 'claude', 'all'], required=True)
    parser.add_argument('--register', action='store_true', help='add the managed mobile-upload rule to this operator’s instructions')
    parser.add_argument('--check', action='store_true', help='inspect local state only; never fetch or write')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-fA-F]{40}', args.revision):
        raise ValueError('--revision must be an approved full commit SHA')
    home = Path.home()
    targets = {
        'codex': (home / '.agents/skills/mobile-publish', home / '.codex/AGENTS.md'),
        'claude': (home / '.claude/skills/mobile-publish', home / '.claude/CLAUDE.md'),
    }
    selected = list(targets.values()) if args.target == 'all' else [targets[args.target]]
    # Inspect every target before changing any of them.
    states = [(target, rules, inspect(target, args.source)) for target, rules in selected]
    if args.check:
        for target, _, revision in states:
            print(f'{target}: {revision}')
        return 0 if all(revision == args.revision for _, _, revision in states) else 1
    for target, rules, revision in states:
        if revision == 'missing':
            target.parent.mkdir(parents=True, exist_ok=True)
            git('clone', '--no-checkout', args.source, target)
        if revision != args.revision:
            git('-C', target, 'fetch', '--no-tags', 'origin', args.revision)
            if revision == 'missing':
                git('-C', target, 'checkout', '--detach', args.revision)
            else:
                git('-C', target, 'merge', '--ff-only', args.revision)
        if args.register:
            register_rule(rules)
        print(f'{target}: ready at {args.revision}')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError) as error:
        sys.exit(f'error: {error}')
