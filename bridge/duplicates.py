"""Conservative review candidates; matching is never an instruction to delete."""
import re
import unicodedata
from collections import defaultdict


def normalize_phone(value):
    value = value.strip()
    digits = ''.join(str(unicodedata.digit(c)) for c in value if c.isdigit())
    if value.startswith('00'):
        digits = digits[2:]
    return digits if len(digits) >= 7 else ''


def normalize_name(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def find_duplicates(rows):
    numbers, names = defaultdict(dict), defaultdict(dict)
    for row in rows:
        name = normalize_name(row.get('name', ''))
        if name and name not in {'unnamed contact', 'unknown', 'no name'}:
            names[name][row['id']] = row
        for number in re.split(r'\s*·\s*', row.get('detail', '')):
            value = normalize_phone(number)
            if value:
                numbers[value][row['id']] = row
    groups = []
    for kind, source in [('Shared phone number', numbers), ('Same name — review carefully', names)]:
        for value, matches in sorted(source.items()):
            if len(matches) > 1:
                groups.append({'reason': kind, 'match': value,
                               'rows': sorted(matches.values(), key=lambda row: row.get('name','').casefold())})
    # A set of contacts matching both name and number should be reviewed once.
    unique = {}
    for group in groups:
        key = tuple(sorted(row['id'] for row in group['rows']))
        if key in unique:
            unique[key]['reason'] = 'Same name and full phone number'
        else:
            unique[key] = group
    return list(unique.values())


def validate_removals(groups, removed):
    for group in groups:
        if all(row['id'] in removed for row in group['rows']):
            raise ValueError('Keep at least one contact in every matching group.')
    return set(removed)
