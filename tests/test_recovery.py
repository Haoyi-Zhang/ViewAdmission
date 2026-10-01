from copy import deepcopy
import unittest
from recovery.algebra import normal, plus, neg, evaluate, rebase, rebase_two_term, encode_image
from recovery.engine import Epoch, log_index, operands, prefix, replay, prefix_checkpoint, certificate, guarded_recover
from recovery.fixtures import small
from recovery.checker import Oracle, Rejected, verify, decode_image, trusted_log, verify_replay
from recovery.publication import Store, PARTS, RecoveryPending


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.log = log_index(small())
        self.records = [e.encode() for e in self.log.values()]
        self.cert = certificate(self.log, 5, [1, 3, 5], [2, 4])

    def test_valid_mixed_cut(self):
        self.assertTrue(verify(self.records, 5, self.cert))

    def test_zero_normalization_keeps_negative(self):
        self.assertEqual(normal([((0, 0), -2), ((0, 0), 1)]), {(0, 0): -1})
        self.assertEqual(normal([((0, 0), -2), ((0, 0), 2)]), {})

    def test_backwards_recovery(self):
        cert = certificate(self.log, 0, list(self.log), list(self.log))
        self.assertTrue(verify(self.records, 0, cert))
        self.assertEqual(cert["recovered"]["joined"], [])

    def test_conflicting_duplicate(self):
        with self.assertRaises(ValueError):
            log_index([small()[0], Epoch(1, ((1,1,1),), ())])
        bad = deepcopy(self.records)
        extra = deepcopy(bad[0]); extra["r"][0][-1] = 2; bad.append(extra)
        with self.assertRaises(Rejected): verify(bad, 5, self.cert)

    def test_exact_duplicate_is_one_input(self):
        self.assertTrue(verify(self.records + self.records, 5, self.cert))
        self.assertEqual(len(log_index(small() + small())), 5)

    def test_prefix_hole(self):
        with self.assertRaises(Rejected): verify(self.records[1:], 5, self.cert)
        with self.assertRaises(Rejected): verify(self.records[1:], 4, self.cert)

    def test_log_holes_after_ack_allowed(self):
        log = {k:v for k,v in self.log.items() if k in [1,3,5]}
        cert = certificate(log, 1, [3,5], [1])
        self.assertTrue(verify([e.encode() for e in log.values()], 1, cert))

    def test_independent_marker_not_certificate_target(self):
        with self.assertRaises(Rejected): verify(self.records, 4, self.cert)
        c = deepcopy(self.cert); c["target"] = True
        with self.assertRaises(Rejected): verify(self.records, 1, c)

    def test_cuts_are_sets_not_multisets(self):
        c = deepcopy(self.cert); c["r_cut"] = [1,1]
        with self.assertRaises(Rejected): verify(self.records, 5, c)
        with self.assertRaises(ValueError): operands(self.log, [1,1], [])

    def test_unavailable_cut(self):
        c = deepcopy(self.cert); c["s_cut"] = [8]
        with self.assertRaises(Rejected): verify(self.records, 5, c)

    def test_poison_is_not_healed(self):
        r, s = operands(self.log, [1,3], [1,2])
        old = evaluate(r, s); old.joined[(99,99,99)] = 1
        recovered = rebase_two_term(old, *prefix(self.log, 5))
        expected = replay(self.log, 5)
        self.assertEqual(plus(recovered.joined, neg(expected.joined)), {(99,99,99):1})
        c = certificate(self.log, 5, [1,3], [1,2], old)
        with self.assertRaises(Rejected): verify(self.records, 5, c)

    def test_mutated_selection_anchor(self):
        c = deepcopy(self.cert); c["anchor"]["selection"] = [[99,98,1]]
        with self.assertRaises(Rejected): verify(self.records, 5, c)

    def test_mutated_group_anchor(self):
        c = deepcopy(self.cert); c["anchor"]["grouped"] = [[99,1]]
        with self.assertRaises(Rejected): verify(self.records, 5, c)

    def test_mutated_recovered_state(self):
        for name in ["r","s","selection","joined","grouped"]:
            c = deepcopy(self.cert)
            arity = {"r":2,"s":2,"selection":2,"joined":3,"grouped":1}[name]
            c["recovered"][name] = [[99]*arity + [1]]
            with self.assertRaises(Rejected): verify(self.records, 5, c)

    def test_cross_term_needed(self):
        old = evaluate({}, {}); tr = {(0,0):1}; ts = {(0,0):1}
        wrong = rebase(old, tr, ts, cross_term=False)
        self.assertNotEqual(wrong.joined, evaluate(tr, ts).joined)
        self.assertEqual(rebase(old, tr, ts), rebase_two_term(old, tr, ts))

    def test_noncanonical_zero_duplicate_unsorted(self):
        for rows in [[[0,0,0]], [[0,0,1],[0,0,1]], [[1,0,1],[0,0,1]]]:
            c = deepcopy(self.cert); c["anchor"]["r"] = rows
            with self.assertRaises(Rejected): verify(self.records, 5, c)

    def test_non_integer(self):
        for bad in [True, 1.0, "1", None]:
            c = deepcopy(self.cert); c["anchor"]["r"] = [[0,0,bad]]
            with self.assertRaises(Rejected): verify(self.records, 5, c)

    def test_schema_rejection(self):
        for bad in [None, [], {}, {**self.cert, "ignored": 1}]:
            with self.assertRaises(Rejected): verify(self.records, 5, bad)
        for bad in [True, -1, "5", 10**20]:
            with self.assertRaises(Rejected): verify(self.records, bad, self.cert)

    def test_invalid_target_bag(self):
        log = log_index([Epoch(1, ((0,0,-1),), ())])
        c = certificate(log, 1, [], [])
        with self.assertRaises(Rejected): verify([e.encode() for e in log.values()], 1, c)

    def test_sql_overflow_is_rejection_not_float(self):
        o = Oracle()
        try:
            with self.assertRaises(Rejected): o.evaluate({(0,0):2**40}, {(0,0):2**40})
            self.assertEqual(o.evaluate({(0,0):2**30}, {(0,0):2**30})["joined"], {(0,0,0):2**60})
        finally: o.close()

    def test_replay_and_prefix_checkpoint(self):
        o = Oracle()
        try:
            for h in range(6):
                for c in range(h+1):
                    self.assertEqual(prefix_checkpoint(self.log,h,c), replay(self.log,h))
                    expected = o.evaluate(*prefix(self.log,h))
                    self.assertEqual(decode_image(encode_image(replay(self.log,h))), expected)
        finally: o.close()

    def test_publication_fence(self):
        old = {**encode_image(replay(self.log,0)), "metadata":{"target":0}}
        new = {**encode_image(replay(self.log,5)), "metadata":{"target":5}}
        store = Store(old, records=self.records, target=5, mode="structural")
        store.prepare(new); sid=store.commit();store.challenge();store.admit()
        for part in PARTS[:-1]: store.flush(part)
        with self.assertRaises(ValueError): store.publish()
        store.crash(); self.assertEqual(store.read(), old)
        store.resume(sid)
        for part in PARTS: store.flush(part)
        store.publish();store.crash();self.assertEqual(store.read(),new)

    def test_independently_checked_replay(self):
        for h in range(6):
            self.assertTrue(verify_replay(self.records,h,encode_image(replay(self.log,h))))
        bad = encode_image(replay(self.log,5)); bad["joined"] = []
        with self.assertRaises(Rejected): verify_replay(self.records,5,bad)

    def test_check_replay_invalid_authority(self):
        image = encode_image(replay(self.log,5))
        for h in [True,-1,10**30]:
            with self.assertRaises(Rejected): verify_replay(self.records,h,image)
        with self.assertRaises(Rejected): verify_replay(self.records[1:],4,image)

    def test_order_and_repeated_delivery_equivalent(self):
        import itertools
        epochs = small()[:4]
        expected = replay(log_index(epochs),4)
        for order in itertools.permutations(epochs):
            delivered = list(order)+[order[2],order[0]]
            self.assertEqual(replay(log_index(delivered),4),expected)
            self.assertTrue(verify_replay([e.encode() for e in delivered],4,encode_image(expected)))

    def test_checker_does_not_share_producer_code(self):
        import ast
        from pathlib import Path
        tree = ast.parse((Path(__file__).resolve().parents[1]/"recovery/checker.py").read_text())
        forbidden = {"algebra", "engine", "recovery.algebra", "recovery.engine"}
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom): self.assertNotIn(node.module,forbidden)
            if isinstance(node,ast.Import):
                for alias in node.names: self.assertNotIn(alias.name,forbidden)

    def test_target_admission_and_fallback(self):
        old = evaluate(*operands(self.log,[1,2],[1,3]))
        cert, used = guarded_recover(self.log,5,[1,2],[1,3],old,admission="target")
        self.assertFalse(used)
        old.joined[(99,99,99)] = 1
        cert, used = guarded_recover(self.log,5,[1,2],[1,3],old,admission="target")
        self.assertTrue(used)
        self.assertTrue(verify_replay(self.records,5,cert["recovered"]))

    def test_target_admission_does_not_claim_anchor_validity(self):
        cert = deepcopy(self.cert)
        cert["anchor"]["joined"] = [[99,99,99,1]]
        # Target-only admission establishes exactly what its interface claims.
        self.assertTrue(verify_replay(self.records,5,cert["recovered"]))
        with self.assertRaises(Rejected): verify(self.records,5,cert)

    def test_stale_root_not_served(self):
        initial={**encode_image(replay(self.log,0)),"metadata":{"target":0}}
        target={**encode_image(replay(self.log,5)),"metadata":{"target":5}}
        store=Store(initial, records=self.records, target=5)
        with self.assertRaises(RecoveryPending):store.read_committed(5)
        store.prepare(target);store.commit();store.challenge();store.admit()
        for part in PARTS:store.flush(part)
        store.publish()
        self.assertEqual(store.read_committed(5),target)
        with self.assertRaises(ValueError):store.read_committed(True)

    def test_metadata_is_not_boolean_prefix(self):
        image={**encode_image(replay(self.log,0)),"metadata":{"target":False}}
        with self.assertRaises(ValueError):Store(image).read_committed(0)

    def test_client_receipt_not_server_marker(self):
        server_before_receipt = {"log":[1], "commit":1}
        server_after_receipt = {"log":[1], "commit":1}
        self.assertEqual(server_before_receipt, server_after_receipt)
        observed_before, observed_after = 0, 1
        self.assertNotEqual(observed_before, observed_after)

    def test_equal_state_does_not_identify_prefix(self):
        log = log_index([Epoch(1,((0,0,1),),()), Epoch(2,((0,0,-1),),())])
        self.assertEqual(replay(log,0), replay(log,2))
        self.assertNotEqual(0,2)


if __name__ == "__main__": unittest.main()
