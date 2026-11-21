import json
from pathlib import Path
import tempfile
import unittest

import httpx

from evaluation.run_wikispeedia_links import initialize, run_pair, summarize


class WikispeediaRunTests(unittest.TestCase):
    def setUp(self):
        self.pages = [{'id': 1, 'title': 'A', 'content': 'Первый текст', 'group': 'x'},
                      {'id': 2, 'title': 'B', 'content': 'Второй текст', 'group': 'y'}]

    def test_production_pair_inputs_direction_mapping_and_cached_resume(self):
        calls = []
        def generate(messages, **kwargs):
            data = json.loads(messages[1]['content'])
            self.assertEqual(set(data), {'A', 'B'})
            self.assertEqual(set(data['A']), {'page_id', 'title', 'content'})
            calls.append(data['A']['page_id'])
            return json.dumps({'create': data['A']['page_id'] == 1, 'explanation': 'Проверка'})
        with tempfile.TemporaryDirectory() as d:
            initialize(self.pages, d)
            first = run_pair((1, 2), generate)
            self.assertEqual(calls, [1, 2])
            self.assertEqual([r['decision']['create'] for r in first['directions']], [True, False])
            self.assertEqual(first['new_calls'], 2)
            second = run_pair((1, 2), lambda *a, **k: self.fail('Must reuse raw responses'))
            self.assertEqual(second['new_calls'], 0)
            self.assertTrue(all(r['reused'] for r in second['directions']))
            self.assertEqual(len(list(Path(d).glob('*.raw.txt'))), 2)

    def test_second_call_transport_failure_keeps_first_direction_and_resumes_only_missing(self):
        calls = []
        def generate(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise httpx.ConnectTimeout('no secret in saved artifacts')
            return '{"create":true,"explanation":"Проверка"}'
        with tempfile.TemporaryDirectory() as d:
            initialize(self.pages, d)
            result = run_pair((1, 2), generate)
            self.assertTrue(result['pause'])
            self.assertEqual([r['status'] for r in result['directions']], ['ok', 'error'])
            resumed = run_pair((1, 2), generate)
            self.assertEqual(len(calls), 3)
            self.assertEqual(resumed['new_calls'], 1)
            self.assertTrue(all(r['status'] == 'ok' for r in resumed['directions']))

    def test_bad_json_is_saved_and_not_a_false_prediction(self):
        with tempfile.TemporaryDirectory() as d:
            initialize(self.pages, d)
            result = run_pair((1, 2), lambda *args, **kwargs: 'broken')
            self.assertEqual([r['status'] for r in result['directions']], ['error', 'not_run'])
            self.assertEqual((Path(d) / 'direction-1-2.raw.txt').read_text(), 'broken')

    def test_mismatched_cached_input_never_calls_api(self):
        with tempfile.TemporaryDirectory() as d:
            initialize(self.pages, d)
            (Path(d) / 'direction-1-2.input.json').write_text('{}')
            result = run_pair((1, 2), lambda *args, **kwargs: self.fail('Input mismatch must stop'))
            self.assertEqual(result['new_calls'], 0)
            self.assertEqual(result['directions'][0]['error_stage'], 'input')

    def test_metrics_keep_valid_half_pair_and_exclude_uncertain_and_errors(self):
        cases = [{'source_page_id': a, 'target_page_id': b, 'expected_create': value}
                 for a, b, value in [(1, 2, True), (2, 1, False), (1, 3, None), (3, 1, True)]]
        records = [{'source_page_id': a, 'target_page_id': b, 'status': status,
                    'decision': {'create': pred, 'explanation': 'Ответ'}}
                   for a, b, status, pred in [(1, 2, 'ok', True), (2, 1, 'error', False), (1, 3, 'ok', True)]]
        m, rows = summarize(cases, records)
        self.assertEqual((m['tp'], m['fp'], m['tn'], m['fn']), (1, 0, 0, 0))
        self.assertAlmostEqual(m['coverage'], 1 / 3)
        self.assertEqual(m['valid_responses'], 2)
        self.assertEqual([r['outcome'] for r in rows], ['tp', 'error', 'uncertain', 'not_run'])


if __name__ == '__main__':
    unittest.main()
