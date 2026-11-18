import json, sys, collections
path = sys.argv[1]
types = collections.Counter()
keys_by_type = collections.defaultdict(collections.Counter)
roles = collections.Counter()
content_types = collections.Counter()
n = 0
first_ts = last_ts = None
usage_keys = collections.Counter()
models = collections.Counter()
with open(path) as f:
    for line in f:
        n += 1
        try:
            o = json.loads(line)
        except Exception as e:
            types['<bad json>'] += 1
            continue
        t = o.get('type')
        types[t] += 1
        for k in o:
            keys_by_type[t][k] += 1
        ts = o.get('timestamp')
        if ts:
            if first_ts is None: first_ts = ts
            last_ts = ts
        msg = o.get('message')
        if isinstance(msg, dict):
            roles[msg.get('role')] += 1
            if msg.get('model'): models[msg['model']] += 1
            u = msg.get('usage')
            if u:
                for k in u: usage_keys[k] += 1
            c = msg.get('content')
            if isinstance(c, list):
                for blk in c:
                    if isinstance(blk, dict):
                        content_types[(msg.get('role'), blk.get('type'))] += 1
            else:
                content_types[(msg.get('role'), type(c).__name__)] += 1
print('lines', n)
print('types', dict(types))
for t, kc in keys_by_type.items():
    print('keys', t, dict(kc))
print('roles', dict(roles))
print('models', dict(models))
print('usage_keys', dict(usage_keys))
print('content_types', dict(content_types))
print('first_ts', first_ts, 'last_ts', last_ts)
