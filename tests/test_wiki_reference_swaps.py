import unittest

from evaluation.wiki_links_reference.run_swaps import PAIRS, comparisons, decision


def record(a, b, ab, ba):
    return {'page_a_id': a, 'page_b_id': b, 'status': 'ok', 'result': {
        'a_to_b': {'create': ab}, 'b_to_a': {'create': ba}}}


class WikiReferenceSwapTests(unittest.TestCase):
    def test_compare_by_page_ids_not_position(self):
        baseline = {'pairs': [record(a, b, True, False) for a, b in PAIRS]}
        records = [r for a, b in PAIRS for r in
                   (record(a, b, True, False), record(b, a, False, True))]
        rows = comparisons(baseline, records)
        self.assertEqual(len(rows), 8)
        self.assertTrue(all(r['swapped_matches_repeat'] for r in rows))
        self.assertEqual(decision(records[1], 12, 10), False)
        records[1]['result']['a_to_b']['create'] = True
        changed = comparisons(baseline, records)
        self.assertFalse(changed[1]['swapped_matches_repeat'])
        self.assertTrue(changed[0]['swapped_matches_repeat'])

    def test_error_and_unattempted_are_not_negative_decisions(self):
        baseline = {'pairs': [record(a, b, False, False) for a, b in PAIRS]}
        records = [{'page_a_id': 10, 'page_b_id': 12, 'status': 'error'}]
        rows = comparisons(baseline, records)
        self.assertTrue(all(r['repeat'] is None and r['swapped'] is None for r in rows))
        self.assertTrue(all(r['swapped_matches_repeat'] is None for r in rows))


if __name__ == '__main__':
    unittest.main()
