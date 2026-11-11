"""Validate exact store evidence and bound transport recovery."""


def normalize(data, request, store):
    expected = dict(app=request['identities'][store], version=request['version'],
                    build=request['build'], platform='ios' if store == 'asc' else 'android',
                    track='testflight' if store == 'asc' else request['track'])
    if not isinstance(data, dict) or any(data.get(k) != v for k, v in expected.items()):
        raise ValueError('store evidence does not match exact app/version/build/platform/track')
    if data.get('publish_authorized') is not True:
        raise ValueError('store publication permission is unverified or read-only')
    state = data.get('state')
    if state not in ('absent', 'processing', 'accepted', 'rejected', 'unknown'):
        raise ValueError('unknown store state')
    if state == 'absent' and (data.get('complete') is not True or data.get('version_available') is not True):
        raise ValueError('incomplete version history or duplicate build number; do not guess a higher number')
    if state == 'accepted' and not data.get('reference'):
        raise ValueError('acceptance needs a store build/release reference')
    return state


def transfer(query, upload, max_attempts=2):
    """At most two transport attempts, each preceded and followed by a query.

    Adapters must never translate an incomplete listing into ``absent``. In
    particular, a missing processed ASC build does not prove Apple never received it.
    """
    if max_attempts <= 0:
        current = query()
        return 'unknown' if current == 'absent' else current
    for attempt in range(max_attempts):
        before = query()
        if before != 'absent':
            return before
        outcome = upload()
        after = query()
        if after != 'absent':
            return after
        if outcome != 'transient' or attempt == max_attempts - 1:
            return 'unknown'
    return 'unknown'
