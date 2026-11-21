"""Метрики и сохранение ошибок без обращений к БД или моделям."""
import itertools
import json
from pathlib import Path
import tempfile
import unittest

import httpx

from evaluation.wiki_links_reference.run import run, summarize
from evaluation.wiki_links_reference.validate import load_reference


class WikiReferenceRunTests(unittest.TestCase):
    def test_direction_mapping_metrics_and_uncertain_exclusion(self):
        reference, pages = load_reference()
        expected = {(c['source_page_id'], c['target_page_id']): c['expected_create']
                    for c in reference['cases']}
        predictions = {key: True if value is None else value for key, value in expected.items()}
        predictions[10, 12] = False  # пропущенная связь
        predictions[10, 16] = True  # лишняя связь
        records = []
        for a, b in itertools.combinations(sorted(p['id'] for p in pages), 2):
            records.append({'page_a_id': a, 'page_b_id': b, 'status': 'ok', 'result': {
                'a_to_b': {'create': predictions[a, b], 'explanation': 'Прямое'},
                'b_to_a': {'create': predictions[b, a], 'explanation': 'Обратное'}}})
        metrics, rows = summarize(reference, records)
        self.assertEqual([metrics[k] for k in ('tp', 'fp', 'tn', 'fn')], [14, 1, 14, 1])
        self.assertAlmostEqual(metrics['precision'], 14 / 15)
        self.assertAlmostEqual(metrics['recall'], 14 / 15)
        self.assertAlmostEqual(metrics['f1'], 14 / 15)
        self.assertEqual(metrics['uncertain_directions'], 12)
        self.assertEqual(metrics['coverage'], 1)
        reverse = next(r for r in rows if r['case_id'] == '12_to_10')
        self.assertEqual(reverse['model_explanation'], 'Обратное')
        self.assertEqual(reverse['outcome'], 'tp')

    def test_complete_run_uses_snapshot_and_preserves_inputs_raw_and_results(self):
        calls = []
        def generate(messages, **kwargs):
            calls.append(messages)
            self.assertEqual(kwargs['response_schema']['additionalProperties'], False)
            self.assertEqual(set(json.loads(messages[1]['content'])), {'A', 'B'})
            self.assertNotIn('expected_create', messages[1]['content'])
            return json.dumps({'create': True, 'explanation': 'Решение направления'})
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'run'
            report = run(output, generate)
            self.assertEqual(report['status'], 'complete')
            self.assertEqual(len(calls), 42)
            self.assertEqual(len(list(output.glob('*.raw.txt'))), 42)
            first, reverse = [json.loads(c[1]['content']) for c in calls[:2]]
            self.assertEqual(first['A'], reverse['B'])
            self.assertEqual(first['B'], reverse['A'])
            self.assertTrue((output / 'summary.md').exists())
            self.assertEqual(load_reference(output)[0]['annotation_status'], 'user_approved')
            with self.assertRaises(FileExistsError):
                run(output, generate)

    def test_invalid_json_preserved_and_is_not_a_negative_prediction(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'run'
            report = run(output, lambda *args, **kwargs: 'broken JSON')
            self.assertEqual(report['status'], 'incomplete')
            self.assertEqual(report['metrics']['error_directions'], 30)
            self.assertEqual(report['metrics']['evaluated_directions'], 0)
            self.assertIsNone(report['metrics']['precision'])
            self.assertEqual((output / 'direction-10-12.raw.txt').read_text(), 'broken JSON')
            self.assertEqual(report['pairs'][0]['error_stage'], 'parse')

    def test_transport_failure_stops_without_retry_and_reports_missing_coverage(self):
        calls = []
        def fail(*args, **kwargs):
            calls.append(1)
            raise httpx.ConnectTimeout('test')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'run'
            report = run(output, fail)
            self.assertEqual(len(calls), 1)
            self.assertEqual(report['metrics']['coverage'], 0)
            self.assertEqual(report['metrics']['error_directions'], 2)
            self.assertEqual(report['metrics']['not_run_directions'], 28)
            self.assertIsNone(report['metrics']['accuracy'])
            self.assertEqual(report['pairs'][0]['error_stage'], 'api')
            self.assertFalse((output / 'direction-10-12.raw.txt').exists())
            self.assertTrue((output / 'report.json').exists())


if __name__ == '__main__':
    unittest.main()
