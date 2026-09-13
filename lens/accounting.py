"""Explicit subsets, precise reference estimates, no guessed usage."""
import json
from decimal import Decimal
from pathlib import Path

FIELDS = ('input_tokens', 'cached_input_tokens', 'output_tokens',
          'reasoning_output_tokens', 'cache_write_input_tokens', 'total_tokens')
RATES = json.loads(Path(__file__).with_name('rates.json').read_text())


def normalize(raw):
    raw = raw if isinstance(raw, dict) else {}
    values, errors = {}, []
    for field in FIELDS:
        value = raw.get(field)
        if value is not None and (type(value) is not int or not 0 <= value <= 2**53 - 1):
            errors.append('Invalid ' + field)
            value = None
        values[field] = value
    i, c, o, r, w, t = (values[k] for k in FIELDS)
    if i is None or o is None:
        errors.append('Input or output count unavailable')
    for child, parent, label in ((c, i, 'Cached input'), (r, o, 'Reasoning output'), (w, i, 'Cache writes')):
        if child is not None and parent is not None and child > parent:
            errors.append(label + ' exceeds parent count')
    if t is not None and i is not None and o is not None and t != i + o:
        errors.append('Supplied total conflicts with input + output')
    values['uncached_input'] = i - c if i is not None and c is not None and c <= i else None
    values['other_output'] = o - r if o is not None and r is not None and r <= o else None
    values['displayed_total'] = i + o if i is not None and o is not None and not errors else None
    values['errors'] = errors
    return values


def estimate(usage, model, speed=None, timestamp='', provider='openai'):
    candidates = [s for s in RATES['snapshots'] if s['date'] <= timestamp[:10]]
    snapshot = candidates[-1] if candidates else RATES['snapshots'][-1]
    rate = snapshot['models'].get(model)
    result = {'total': None, 'parts': None, 'date': snapshot['date'], 'source': snapshot['source'],
              'basis': RATES['billing_basis'], 'assumption': 'Standard-rate estimate; speed unavailable',
              'historical': bool(candidates), 'reason': None}
    if speed in ('standard', 'default', 'normal'):
        result['assumption'] = 'Recorded Standard speed'
    elif speed in ('fast', 'priority'):
        result['assumption'] = 'Recorded Fast/priority tier; published Fast modifier'
    elif speed:
        result['reason'] = 'Unsupported recorded speed/tier'
    if not candidates:
        result['assumption'] += '; current-rate reference for older/undated activity'
    if provider != 'openai':
        result['reason'] = 'Provider billing basis not established'
    if not rate:
        result['reason'] = 'Model has no verified credit rate'
    if usage['errors'] or usage['uncached_input'] is None:
        result['reason'] = 'Usage or cache breakdown unavailable/inconsistent'
    if usage['cache_write_input_tokens']:
        result['reason'] = 'Cache-write credit rate not established'
    if result['reason']:
        return result
    multiplier = Decimal(rate['fast']) if speed in ('fast', 'priority') else Decimal(1)
    def part(value, key):
        return Decimal(value) * Decimal(rate[key]) * multiplier / Decimal(1000000)
    parts = [part(usage['uncached_input'], 'input'), part(usage['cached_input_tokens'], 'cached')]
    output = part(usage['output_tokens'], 'output')
    result['total'] = str(sum(parts) + output)
    if usage['reasoning_output_tokens'] is not None:
        result['parts'] = [str(x) for x in parts + [part(usage['reasoning_output_tokens'], 'output'), part(usage['other_output'], 'output')]]
    return result
