"""Actual library pipeline with fake transport; no external API calls."""
import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation import llm_judge as storage
from evaluation import ragas_faithfulness as runner

HAS_RAGAS = importlib.util.find_spec('ragas') is not None


class EligibilityTests(unittest.TestCase):
    def test_refusal_and_missing_context_do_not_become_zero_or_one(self):
        self.assertEqual(runner.eligibility(dict(status='system_error')), 'system_error')
        self.assertEqual(runner.eligibility(dict(status='answer', response=runner.NO_ANSWER, retrieved_contexts=[])), 'not_applicable_refusal')
        self.assertEqual(runner.eligibility(dict(status='answer', response='Some fact', retrieved_contexts=[])), 'not_evaluable_empty_context')

    def test_alignment_rejects_dropped_or_rewritten_statements(self):
        calls = [dict(response_model='StatementGeneratorOutput', parsed=dict(statements=['A', 'B'])),
                 dict(response_model='NLIStatementOutput', parsed=dict(statements=[dict(statement='A', verdict=1, reason='yes')]))]
        self.assertTrue(runner.check_alignment(calls))

    def test_non_binary_nli_verdict_is_not_accepted_as_supported(self):
        calls = [dict(response_model='StatementGeneratorOutput', parsed=dict(statements=['A'])),
                 dict(response_model='NLIStatementOutput', parsed=dict(statements=[dict(statement='A', verdict=2, reason='yes')]))]
        self.assertIn('non_binary_nli_verdict', runner.check_alignment(calls))


@unittest.skipUnless(HAS_RAGAS, 'Run library integration tests in the isolated Ragas environment')
class RagasIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ca = self.root / 'ca.txt'
        self.ca.write_text('synthetic certificate placeholder', encoding='utf8')
        self.env = patch.dict('os.environ', {'GIGACHAT_CA_BUNDLE': str(self.ca), 'GIGACHAT_SCOPE': 'TEST_SCOPE'})
        self.env.start()
        self.addCleanup(self.env.stop)
        source = self.root / 'source'
        bundle = dict(version=storage.VERSION, cases=[dict(case_id='q-raw', question_id='q', mode='raw', status='answer',
            quality=dict(reference='REFERENCE_MUST_STAY_HIDDEN'),
            grounding=dict(question='When and where?', answer='Monday in Paris.',
                           fragments=[dict(source_id=1, text='Anna arrived on Monday.')]))])
        storage.save(source / 'inputs.json', bundle)
        storage.save(source / 'manifest.json', dict(inputs_sha256=storage.file_hash(source / 'inputs.json'),
            implementation_sha256=storage.file_hash(storage.__file__)))
        self.output = self.root / 'experiment'
        runner.prepare(source, self.output, ['q'])
        self.requests = []

    def client(self, endpoint, payload):
        self.requests.append(payload)
        if payload['response_format']['schema']['title'] == 'StatementGeneratorOutput':
            content = dict(statements=['Anna arrived on Monday.', 'Anna arrived in Paris.'])
        else:
            content = dict(statements=[dict(statement='Anna arrived on Monday.', reason='Directly stated.', verdict=1),
                                       dict(statement='Anna arrived in Paris.', reason='No location given.', verdict=0)])
        return dict(model='fake-model', usage=dict(prompt_tokens=10, completion_tokens=10, total_tokens=20),
            choices=[dict(finish_reason='stop', message=dict(content=json.dumps(content)))])

    def test_library_score_and_reference_isolation(self):
        asyncio.run(runner.run(self.output, client=self.client))
        summary = runner.report(self.output)
        self.assertEqual(summary['rows'][0]['value'], .5)
        self.assertEqual(len(self.requests), 2)
        self.assertNotIn('REFERENCE_MUST_STAY_HIDDEN', json.dumps(self.requests))
        self.assertNotIn('REFERENCE_MUST_STAY_HIDDEN', (self.output / 'inputs.json').read_text('utf8'))
        self.assertEqual(summary['usage']['tokens']['total_tokens'], 40)
        self.assertEqual(self.requests[0]['messages'][0]['role'], 'user')

    def test_no_automatic_retries_or_secret_exception_text(self):
        def fail(endpoint, payload):
            self.requests.append(payload)
            raise RuntimeError('credential-secret-example')
        asyncio.run(runner.run(self.output, client=fail))
        asyncio.run(runner.run(self.output, client=fail))
        self.assertEqual(len(self.requests), 1)
        record_text = (self.output / 'results/q-raw.json').read_text('utf8')
        self.assertNotIn('credential-secret-example', record_text)
        self.assertEqual(runner.report(self.output)['rows'][0]['status'], 'judge_error')

    def test_resume_does_not_repeat_successful_requests(self):
        asyncio.run(runner.run(self.output, client=self.client))
        asyncio.run(runner.run(self.output, client=self.client))
        self.assertEqual(len(self.requests), 2)

    def test_alignment_error_retains_library_value_without_accepting_it(self):
        def omit(endpoint, payload):
            result = self.client(endpoint, payload)
            if payload['response_format']['schema']['title'] == 'NLIStatementOutput':
                value = json.loads(result['choices'][0]['message']['content'])
                value['statements'] = value['statements'][:1]
                result['choices'][0]['message']['content'] = json.dumps(value)
            return result
        asyncio.run(runner.run(self.output, client=omit))
        row = runner.report(self.output)['rows'][0]
        self.assertEqual(row['status'], 'alignment_error')
        self.assertEqual(row['library_value'], 1.0)
        self.assertIsNone(row['value'])


if __name__ == '__main__':
    unittest.main()
