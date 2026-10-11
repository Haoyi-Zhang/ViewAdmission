"""Owned synthetic, same-information exact/randomized admission comparisons."""
from copy import deepcopy
import itertools
import random
import unittest
from unittest.mock import patch

import protocol_controls as controls
from recovery import factorized as fp
from recovery.checker import verify, verify_replay
from recovery.engine import Epoch, guarded_recover, log_index
from recovery.algebra import evaluate
from recovery.publication import Store, PARTS, RecoveryPending


def image_from_rows(r, s):
    """Independent nested-loop specification, not producer/checker algebra."""
    image = {name: [] for name in fp.RELATION_ARITIES}
    image["r"], image["s"] = sorted(r), sorted(s)
    image["selection"] = [row[:] for row in image["r"] if row[1] % 2 == 0]
    totals = {}
    for k, a, rw in image["r"]:
        for sk, b, sw in image["s"]:
            if k == sk:
                image["joined"].append([k, a, b, rw * sw])
                totals[k] = totals.get(k, 0) + rw * sw
    image["joined"].sort()
    image["grouped"] = [[k, w] for k, w in sorted(totals.items())]
    return image


def paired_cases():
    # 3^4 complete small bag endpoints plus 31 seeded richer cases = 112.
    for weights in itertools.product(range(3), repeat=4):
        r = [[k, k, w] for k, w in enumerate(weights[:2]) if w]
        s = [[k, -k, w] for k, w in enumerate(weights[2:]) if w]
        yield make_case(r, s)
    rng = random.Random(112)
    for _ in range(31):
        r = [[k, a, rng.randrange(1, 4)] for k in range(-2, 3)
             for a in range(-2, 4) if rng.randrange(3) == 0]
        s = [[k, b, rng.randrange(1, 4)] for k in range(-2, 3)
             for b in range(-3, 3) if rng.randrange(3) == 0]
        yield make_case(r, s)


def make_case(r, s):
    # No sorted-authority assumption: include cancellation, repeated tuples,
    # signed intermediates, shuffled epochs, an exact duplicate and a future row.
    first = {"id": 1, "r": [[99, 99, -1]], "s": [[98, 98, 1]]}
    second = {"id": 2, "r": list(reversed(r)) + [[99, 99, 1]],
              "s": list(reversed(s)) + [[98, 98, -1]]}
    future = {"id": 4, "r": [[-8, -7, 1]], "s": []}
    return [second, first, deepcopy(second), future], 2, image_from_rows(r, s)


class StreamingTests(unittest.TestCase):
    def methods(self, records, h, image):
        empty = {name: [] for name in fp.RELATION_ARITIES}
        cert = {"target": h, "r_cut": [], "s_cut": [],
                "anchor": empty, "recovered": image}
        return {
            "SQL-both": lambda: verify(records, h, cert),
            "SQL-target": lambda: verify_replay(records, h, image),
            "structural": lambda: fp.verify_structural(records, h, image),
            "streaming": lambda: fp.verify_streaming(records, h, image),
            "factorized": lambda: fp.verify_factorized(records, h, image,
                commitment=fp.commit_image(image), seed=b"paired-owned-fixture" * 2),
        }

    def test_112_paired_targets_and_560_component_mutations(self):
        cases = list(paired_cases())
        self.assertEqual(len(cases), 112)
        for i, (records, h, image) in enumerate(cases):
            for name, call in self.methods(records, h, image).items():
                with self.subTest(case=i, mode=name, positive=True):
                    self.assertTrue(call())
            for part, arity in fp.RELATION_ARITIES.items():
                bad = deepcopy(image)
                if bad[part]:
                    bad[part][0][-1] += 1
                else:
                    bad[part] = [[0] * arity + [1]]
                for name, call in self.methods(records, h, bad).items():
                    with self.subTest(case=i, mode=name, component=part):
                        with self.assertRaises(ValueError):
                            call()

    def test_merge_boundaries_and_malformed_rows(self):
        records, h, good = make_case([[0, -2, 2], [0, 1, 1], [4, 2, 1]],
                                     [[-1, 1, 1], [0, -1, 1], [0, 2, 3]])
        self.assertTrue(fp.verify_streaming(records, h, good))
        for part in fp.RELATION_ARITIES:
            for alteration in ("missing", "extra", "duplicate", "unsorted", "zero", "negative", "bool"):
                bad = deepcopy(good)
                if alteration == "missing": bad[part].pop()
                elif alteration == "extra": bad[part].append([99] * fp.RELATION_ARITIES[part] + [1])
                elif alteration == "duplicate": bad[part].append(bad[part][-1][:])
                elif alteration == "unsorted": bad[part].reverse()
                elif alteration == "zero": bad[part][0][-1] = 0
                elif alteration == "negative": bad[part][0][-1] = -1
                else: bad[part][0][0] = True
                # Reversing a singleton is unchanged, not a negative case.
                if bad == good: continue
                with self.subTest(part=part, alteration=alteration):
                    with self.assertRaises(ValueError):
                        fp.verify_streaming(records, h, bad)
        empty = {name: [] for name in fp.RELATION_ARITIES}
        self.assertTrue(fp.verify_streaming(records, 0, empty))
        for bad_records, marker in ((records, 3), (records + [{"id": 4, "r": [], "s": []}], 2),
                                    ([{"id": 1, "r": [[0, 0, -1]], "s": []}], 1)):
            with self.assertRaises(ValueError):
                fp.verify_streaming(bad_records, marker, empty)

    def test_common_integer_domain_and_all_publication_gates(self):
        self.assertTrue(all(row["accepted"] == row["expected"]
                            for row in controls.domain_rows(include_streaming=True)))
        self.assertTrue(all(row["rejected"] for row in
                            controls.protocol_rows(modes=("streaming",))))

    def test_streaming_is_actual_store_checker_and_mode_is_bound(self):
        store = controls.store("streaming")
        store.prepare(controls.TARGET)
        store.commit()
        store.challenge()
        with patch("recovery.publication.verify_streaming", wraps=fp.verify_streaming) as actual:
            store.admit()
            actual.assert_called_once()
        controls.flush(store)
        store.publish()
        self.assertEqual(store.read_committed(1), controls.TARGET)
        # The trusted descriptor binds the mode; changing it invalidates service.
        store._Store__config["mode"] = "structural"
        with self.assertRaises(ValueError): store.read_committed(1)

    def test_guarded_streaming_primary_and_checked_fallback(self):
        log = log_index([Epoch(1, ((1, 2, 1),), ((1, 3, 1),))])
        for poison in (False, True):
            old = evaluate({}, {})
            if poison: old.joined[(99, 99, 99)] = 1
            cert, fallback = guarded_recover(log, 1, [], [], old, admission="streaming")
            self.assertEqual(fallback, poison)
            self.assertEqual(cert["recovered"], controls.GOOD)

    def test_paired_store_crash_cuts_direct_and_fallback(self):
        for mode in ("target", "structural", "streaming", "factorized"):
            for poison in (False, True):
                for order in (PARTS, tuple(reversed(PARTS))):
                    for cut in range(13):
                        entropy = iter((b"a" * 32, b"b" * 32, b"c" * 32))
                        store = Store(controls.INITIAL, records=controls.RECORDS, target=1,
                                      mode=mode, _entropy=lambda: next(entropy))
                        primary = deepcopy(controls.TARGET)
                        if poison: primary["joined"][0][-1] += 1
                        sid = None
                        events = ("prepare", "commit", "challenge", "admit", "binding", *order, "publish")
                        def admit():
                            nonlocal sid
                            try: store.admit()
                            except ValueError:
                                store.prepare(controls.TARGET)
                                sid = store.commit()
                                store.challenge()
                                store.admit()
                        for event in events[:cut]:
                            if event == "prepare": store.prepare(primary)
                            elif event == "commit": sid = store.commit()
                            elif event == "challenge": store.challenge()
                            elif event in ("admit", "binding"): admit()
                            elif event == "publish": store.publish()
                            else: store.flush(event)
                        store.crash()
                        if cut == 12:
                            self.assertEqual(store.read_committed(1), controls.TARGET)
                        else:
                            with self.assertRaises(RecoveryPending): store.read_committed(1)
                        if sid is None:
                            store.prepare(primary)
                            sid = store.commit()
                        else: store.resume(sid)
                        store.challenge()
                        admit()
                        for part in PARTS: store.flush(part)
                        store.publish()
                        store.crash()
                        self.assertEqual(store.read_committed(1), controls.TARGET)


if __name__ == "__main__":
    unittest.main()
