import unittest
import upstream_workload as workload

class UpstreamWorkloadTests(unittest.TestCase):
    def test_source_parser_and_supported_projection(self):
        full=workload.input_records(False)
        projected=workload.input_records()
        self.assertEqual([len(r['r']) for r in full],[6,1,1,1,1])
        self.assertEqual([len(r['s']) for r in full],[6,1,1,0,0])
        self.assertEqual(projected[0]['r'],[[1,0,1],[1,1,2],[2,2,3],[2,3,4]])
        self.assertEqual(projected[0]['s'],[[2,6,3],[2,7,4]])
        self.assertEqual(projected[-1]['r'],[[1,0,0]])
        self.assertEqual(projected[3]['r'],[])

    def test_actual_checkers_and_store_on_upstream_inputs(self):
        result=workload.run()
        self.assertEqual(result['positive_checks'],20)
        self.assertEqual(result['component_rejections'],100)
        self.assertEqual([r['join_rows'] for r in result['rows']],[4,6,6,6,6])
        self.assertEqual(result['rows'][-1]['candidate']['joined'],
            [[1,0,1,3],[1,1,1,2],[2,2,6,9],[2,2,7,12],[2,3,6,12],[2,3,7,16]])

if __name__=='__main__': unittest.main()
