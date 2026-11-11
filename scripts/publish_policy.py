"""Resolve the project's approved runtime and stores without consulting credentials."""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys

POLICY_FILE = 'mobile-publish.config.json'
STORES = ('play', 'asc', 'agc')


@dataclass(frozen=True)
class PublishPolicy:
    runtime: str
    stores: tuple
    shorebird_warning_users: int = 400


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate policy field')
        result[key] = value
    return result


def load_policy(app, requested='all'):
    app = Path(app)
    if requested not in (*STORES, 'all'):
        raise ValueError('unsupported store')
    config = app / POLICY_FILE
    shorebird = app / 'shorebird.yaml'
    declared = 'shorebird.yaml' in (app / 'pubspec.yaml').read_text()
    if declared and not shorebird.is_file():
        raise ValueError('declared shorebird.yaml is missing; restore the project configuration')
    if not config.exists():
        if shorebird.exists():
            raise ValueError('Shorebird configuration found; record the reviewed project policy before publishing')
        if requested == 'all':
            raise ValueError('record approved project stores or select --store explicitly; credentials do not select stores')
        return PublishPolicy('flutter', (requested,))
    data = json.loads(config.read_text(), object_pairs_hook=unique_keys)
    required = {'schema_version', 'runtime', 'stores'}
    if not isinstance(data, dict) or not required.issubset(data) or set(data) - required - {'shorebird_warning_users'}:
        raise ValueError('policy fields are schema_version, runtime, stores and optional shorebird_warning_users; no credentials')
    if type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ValueError('unsupported project policy schema')
    runtime, stores = data['runtime'], data['stores']
    if runtime not in ('flutter', 'shorebird'):
        raise ValueError('runtime must be flutter or shorebird')
    if not isinstance(stores, list) or not stores or any(store not in STORES for store in stores):
        raise ValueError('stores must be a nonempty list of supported stores')
    if len(set(stores)) != len(stores):
        raise ValueError('duplicate project store')
    warning_users = data.get('shorebird_warning_users', 400)
    if type(warning_users) is not int or warning_users < 1:
        raise ValueError('shorebird_warning_users must be a positive integer')
    if (runtime == 'shorebird') != shorebird.is_file():
        raise ValueError('runtime policy conflicts with Shorebird configuration; do not change the runtime automatically')
    if requested != 'all' and requested not in stores:
        raise ValueError('requested store is outside the approved project policy')
    return PublishPolicy(runtime, tuple(stores if requested == 'all' else [requested]), warning_users)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=Path)
    parser.add_argument('--store', default='all')
    args = parser.parse_args()
    policy = load_policy(args.app, args.store)
    print(policy.runtime)
    print(' '.join(policy.stores))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        sys.exit(f'error: {error}')
