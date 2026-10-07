"""Owned benign relations only; no adaptive/control attack workflows or I/O."""
from copy import deepcopy
from itertools import product
import unittest
from unittest.mock import patch
from recovery import factorized as fp
from recovery.publication import Store, PARTS


def cases():
    r_keys = list(product((-1, 0), (-2, 1)))
    s_keys = list(product((-1, 1), (-1, 2)))
    for index, (rw, sw) in enumerate(product(product(range(3), repeat=4), product(range(2), repeat=4))):
        records = [dict(id=1, r=[[*key, w] for key, w in zip(r_keys, rw) if w],
                        s=[[*key, w] for key, w in zip(s_keys, sw) if w])]
        yield 'grid-' + str(index), records, 1
    for bits in range(64):
        initial = dict(id=1, r=[[k, 2, 2] for k in range(3)], s=[[k, 3, 2] for k in range(3)])
        deleted = dict(id=2, r=[[k, 2, -2] for k in range(3) if bits >> k & 1],
                       s=[[k, 3, -2] for k in range(3) if bits >> (k + 3) & 1])
        restored = dict(id=3, r=[[k, 2, 1] for k in range(3) if bits >> k & 1],
                        s=[[k, 3, 1] for k in range(3) if bits >> (k + 3) & 1])
        records = [initial, deleted, restored]
        for h in range(4):
            yield f'signed-{bits}-prefix-{h}', records, h
    yield 'empty', [], 0
    yield 'max-supported-weight', [dict(id=1, r=[[0, 2, fp.MAX_INT]], s=[[0, 3, 1]])], 1


def definition(records, h):
    """Primitive full-prefix replay plus nested-loop join, not core algebra."""
    epochs = {row['id']: row for row in records}
    bases = {side: {} for side in ('r', 's')}
    for i in range(1, h + 1):
        for side in bases:
            for key, value, weight in epochs[i][side]:
                pair = (key, value)
                bases[side][pair] = bases[side].get(pair, 0) + weight
    bases = {side: {key: w for key, w in rows.items() if w} for side, rows in bases.items()}
    joined, grouped = {}, {}
    for (k, a), rw in bases['r'].items():
        for (other, b), sw in bases['s'].items():
            if k == other:
                joined[(k, a, b)] = rw * sw
                grouped[(k,)] = grouped.get((k,), 0) + rw * sw
    maps = dict(**bases, selection={key: w for key, w in bases['r'].items() if key[1] % 2 == 0},
                joined=joined, grouped=grouped)
    return {name: [[*key, w] for key, w in sorted(rows.items()) if w] for name, rows in maps.items()}


def injected_tag(index, domain, coords):
    # Deterministic round/domain-separated functional control, not random evidence.
    return (17 * (index + 1) + sum((i + 1) * ord(c) for i, c in enumerate(domain))
            + sum((i + 5) * (value + 7) for i, value in enumerate(coords))) % fp.FIELD


def fingerprints(image, rounds):
    values = {name: [0] * rounds for name in fp.RELATION_ARITIES}
    for name, rows in image.items():
        for row in rows:
            *coords, weight = row
            for i in range(rounds):
                if name in ('r', 's', 'selection'):
                    stem = 'sel' if name == 'selection' else name
                    term = weight * injected_tag(i, stem + '-key', (coords[0],)) * injected_tag(i, stem + '-value', (coords[1],))
                elif name == 'joined':
                    term = weight * injected_tag(i, 'join-key', (coords[0],))
                    term *= injected_tag(i, 'join-r-value', (coords[1],)) * injected_tag(i, 'join-s-value', (coords[2],))
                else:
                    term = weight * injected_tag(i, 'group-key', (coords[0],))
                values[name][i] = (values[name][i] + term) % fp.FIELD
    return values


class GroupTotalTests(unittest.TestCase):
    def test_complete_benign_images_rounds_and_historical_keys(self):
        for _, records, h in cases():
            image, saved = definition(records, h), deepcopy(records)
            commitment = fp.commit_image(image)
            keys = {row[0] for epoch in records if epoch['id'] <= h for side in ('r', 's') for row in epoch[side]}
            self.assertTrue(fp.verify_structural(records, h, image))
            for rounds in (1, 2, 8):
                report = fp.verify_factorized(records, h, image, commitment=commitment,
                                              seed=b'owned-benign-test-seed-32-bytes!!', rounds=rounds)
                self.assertTrue(report.accepted)
                self.assertEqual(report.distinct_join_keys, len(keys))
                self.assertEqual(report.peak_accumulator_keys, len(keys))
                self.assertEqual(report.tag_cache_entries, 0)
                self.assertEqual(report.expected_join_pairs_enumerated, 0)
            self.assertEqual(records, saved)

    def test_every_component_against_expanded_fingerprint_definition(self):
        selected = list(cases())[::71]
        selected += list(cases())[-2:]
        for _, records, h in selected:
            image = definition(records, h)
            for rounds in (1, 2, 8):
                captured = []
                original = fp._compare_fingerprints
                def compare(expected, observed):
                    captured.append((deepcopy(expected), deepcopy(observed)))
                    original(expected, observed)
                with patch.object(fp, '_compare_fingerprints', compare):
                    report = fp._verify_factorized(records, h, image, commitment=fp.commit_image(image),
                        seed=b'owned-benign-test-seed-32-bytes!!', rounds=rounds, _tag_override=injected_tag)
                exact = fingerprints(image, rounds)
                self.assertEqual(captured, [(exact, exact)])
                self.assertTrue(report.accepted)

    def test_benign_publication_and_ordinary_parameter_boundaries(self):
        records = [dict(id=1, r=[[0, 2, 2]], s=[[0, 3, 1]])]
        image = definition(records, 1)
        initial = {**definition([], 0), 'metadata': {'target': 0}}
        for rounds in (1, 2, 8):
            store = Store(initial, records=records, target=1, rounds=rounds,
                          _entropy=lambda: b'owned-post-commit-test-seed-32bytes')
            target = {**image, 'metadata': {'target': 1}}
            store.prepare(target); store.commit(); store.challenge()
            self.assertTrue(store.admit())
            for part in PARTS:
                store.flush(part)
            store.publish(); store.crash()
            self.assertEqual(store.read_committed(1), target)
        commitment = fp.commit_image(image)
        for rounds in (0, 9, True):
            with self.assertRaisesRegex(fp.FactorizedRejected, 'round count'):
                fp.verify_factorized(records, 1, image, commitment=commitment, seed=b'a' * 32, rounds=rounds)
        for q in (17, True):
            with self.assertRaisesRegex(fp.FactorizedRejected, 'production field'):
                fp.verify_factorized(records, 1, image, commitment=commitment, seed=b'a' * 32, q=q)


if __name__ == '__main__':
    unittest.main()
