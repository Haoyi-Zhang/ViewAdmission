import unittest
from fractions import Fraction
from copy import deepcopy
import protocol_controls as c
from recovery import factorized as fp
class ProtocolTests(unittest.TestCase):
    def test_publication_and_fallback_controls(self):
        rows=list(c.protocol_rows());self.assertTrue(rows)
        self.assertTrue(all(r['rejected']==1 for r in rows))
    def test_uniform_integer_domain(self):
        rows=list(c.domain_rows());self.assertTrue(all(r['accepted']==r['expected'] for r in rows))
    def test_actual_equation_mutations(self):
        self.assertEqual(len(list(c.tag_rows())),3)
    def test_probability_inequalities(self):
        p=Fraction(9,fp.FIELD**2)
        self.assertGreater(p,Fraction(9,2**254));self.assertLess(p,Fraction(1,2**250))
    def test_complete_canonical_binding(self):
        image=deepcopy(c.TARGET);s=c.store();s.prepare(image);sid=s.commit()
        image['joined'][0][-1]+=1
        s.challenge();s.admit();c.flush(s);s.publish();self.assertEqual(s.read_committed(1),c.TARGET)
    def test_unknown_session_and_foreign_root(self):
        s=c.store()
        with self.assertRaises(ValueError):s.resume(12)
        s.root='candidate:999'
        with self.assertRaises(ValueError):s.read_committed(1)
    def test_staging_change_after_admission(self):
        s=c.store();c.setup(s);s.staged['joined'][0][-1]+=1;c.flush(s)
        with self.assertRaises(ValueError):s.publish()
    def test_no_production_tag_injection(self):
        with self.assertRaises(TypeError):
            fp.verify_factorized(c.RECORDS,1,c.GOOD,commitment=fp.commit_image(c.GOOD),seed=b'x'*32,_tag_override=lambda *a:1)
if __name__=='__main__':unittest.main()


class CampaignReuseTests(unittest.TestCase):
    def test_equation_reuse_preserves_actual_transition_rows(self):
        from reproduce import publication_rows
        from recovery.publication import PARTS
        def semantic(rows):
            return [{k:v for k,v in r.items() if not k.startswith("equation_")} for r in rows]
        args={"targets":(1,4),"orders":(PARTS,tuple(reversed(PARTS))),"cuts":range(13)}
        reused=list(publication_rows(5,**args,memoize=True))
        direct=list(publication_rows(5,**args,memoize=False))
        self.assertEqual(len(reused), 2*2*13)
        self.assertEqual({r["h"] for r in reused}, {1,4})
        self.assertEqual(semantic(reused),semantic(direct))
        self.assertGreater(reused[-1]["equation_cache_hits"],0)
