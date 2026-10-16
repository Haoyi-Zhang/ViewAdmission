"""Check the diagram's actual cut and control-flow specifications without plotting."""
import ast
from pathlib import Path
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'figures/draw_schematics.py'


class FigureContractTests(unittest.TestCase):
    def specification(self,name):
        for node in ast.parse(SOURCE.read_text(encoding='utf-8')).body:
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets):
                return ast.literal_eval(node.value)
        self.fail('missing executable diagram specification: '+name)

    def test_mixed_cut_membership_matches_the_five_epoch_fixture(self):
        self.assertEqual(self.specification('CUTS'),{'A':(1,3,5),'B':(2,4),'P':(1,2,3)})

    def test_fallback_recommits_before_another_fresh_challenge(self):
        self.assertEqual(set(self.specification('PROTOCOL_EDGES')),{
            ('build','commit'),('commit','challenge'),('challenge','verify'),
            ('verify','objects'),('objects','root'),('verify','fallback'),('fallback','commit')})


if __name__=='__main__':unittest.main()
