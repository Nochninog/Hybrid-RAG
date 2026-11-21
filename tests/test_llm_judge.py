"""Оценщик: изоляция эталона, проверка доказательств, сбои и возобновление."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation import llm_judge as judge


class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.quality_data = dict(question='Срок?', answer='Пять дней.', reference='Пять дней.',
            expected_abstention=False, required_facts=[{'id': 1, 'text': 'Пять дней.'}],
            constraints=[{'id': 2, 'text': 'Не обещать один день.'}])
        self.grounding_data = dict(question='Срок?', answer='Пять дней.',
            fragments=[{'source_id': 1, 'text': 'Срок: пять дней.'}])
        self.quality = dict(correctness=2, reason='Верно.',
            facts=[dict(id=1, covered=True, evidence='Пять дней.', reason='Есть срок.')],
            constraints=[dict(id=2, violated=False, evidence='', reason='Нет обещания.')], issues=[])
        self.grounding = dict(is_abstention=False, reason='Есть опора.', claims=[
            dict(statement='Пять дней.', verdict='supported',
                 support=[dict(source_id=1, quote='пять дней')], reason='Срок совпадает.')])

    def bundle(self):
        return dict(version=judge.VERSION, prompts={'quality': judge.QUALITY_PROMPT, 'grounding': judge.GROUNDING_PROMPT},
            cases=[dict(case_id='q-raw', question_id='q', mode='raw', status='answer',
                        quality=self.quality_data, grounding=self.grounding_data),
                   dict(case_id='q-wiki', question_id='q', mode='wiki', status='system_error')])

    def write_bundle(self, output):
        judge.save(output / 'inputs.json', self.bundle())
        judge.save(output / 'manifest.json', dict(inputs_sha256=judge.file_hash(output / 'inputs.json'),
                                                implementation_sha256=judge.file_hash(judge.__file__)))

    def response(self, value, finish='stop'):
        value = deepcopy(value)
        if 'correctness' in value:
            for field in ('facts', 'constraints'):
                for row in value[field]:
                    row['evidence_range'] = dict(start=1, end=1) if row.pop('evidence') else dict(start=0, end=0)
            for row in value['issues']:
                row.pop('statement')
                row['answer_range'] = dict(start=1, end=1)
        else:
            for row in value['claims']:
                row['proposition'] = row.pop('statement')
                row['answer_range'] = dict(start=1, end=1)
                for support in row['support']:
                    support.pop('quote')
                    support.update(start=1, end=1)
            value['nonfactual'] = []
        value['version'] = 4
        return dict(model='actual-judge', usage={'total_tokens': 42}, choices=[
            dict(finish_reason=finish, message={'content': json.dumps(value)})])

    def test_metrics_and_reference_isolation(self):
        metrics = judge.validate_quality(self.quality, self.quality_data)
        self.assertEqual((metrics['correctness'], metrics['completeness']), (2, 1))
        self.assertEqual(judge.validate_grounding(self.grounding, self.grounding_data)['faithfulness'], 1)
        msg = json.loads(judge.messages(self.bundle(), self.bundle()['cases'][0], 'grounding')[1]['content'])
        self.assertEqual(set(msg), {'question', 'answer_units', 'fragments'})
        self.assertNotIn('mode', msg)

    def test_missing_duplicate_or_fabricated_rubric(self):
        for facts in ([], self.quality['facts'] * 2, [{**self.quality['facts'][0], 'id': 10}]):
            with self.subTest(facts=facts), self.assertRaises(ValueError):
                judge.validate_quality({**self.quality, 'facts': facts}, self.quality_data)

    def test_wrong_types_and_inconsistent_correctness(self):
        for score in (True, 3, '2'):
            with self.subTest(score=score), self.assertRaises(ValueError):
                judge.validate_quality({**self.quality, 'correctness': score}, self.quality_data)
        bad = deepcopy(self.quality)
        bad['constraints'][0].update(violated=True, evidence='Пять дней.')
        with self.assertRaises(ValueError):
            judge.validate_quality(bad, self.quality_data)
        with self.assertRaises(ValueError):
            judge.validate_quality({**self.quality, 'correctness': 1}, self.quality_data)

    def test_fabricated_quotes_sources_and_duplicate_claims(self):
        for source_id, quote in ((3, 'пять дней'), (True, 'пять дней'), (1, 'шесть дней')):
            bad = deepcopy(self.grounding)
            bad['claims'][0]['support'] = [dict(source_id=source_id, quote=quote)]
            with self.subTest(source=source_id, quote=quote), self.assertRaises(ValueError):
                judge.validate_grounding(bad, self.grounding_data)
        with self.assertRaises(ValueError):
            judge.validate_grounding({**self.grounding, 'claims': self.grounding['claims'] * 2}, self.grounding_data)
        bad = deepcopy(self.quality)
        bad['facts'][0]['evidence'] = 'Шесть дней.'
        with self.assertRaises(ValueError):
            judge.validate_quality(bad, self.quality_data)

    def test_refusal_na_and_unsupported_claim(self):
        result = judge.validate_grounding(dict(is_abstention=True, reason='Отказ.', claims=[]), self.grounding_data)
        self.assertIsNone(result['faithfulness'])
        with self.assertRaises(ValueError):
            judge.validate_grounding(dict(is_abstention=False, reason='Пусто.', claims=[]), self.grounding_data)
        bad = deepcopy(self.grounding)
        bad['claims'][0].update(verdict='insufficient', support=[])
        self.assertEqual(judge.validate_grounding(bad, self.grounding_data)['faithfulness'], 0)

    def test_resume_errors_preserves_history_and_denominators(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            self.write_bundle(output)
            config = judge.configure(output, 'judge', 'https://example.invalid/v1')
            calls = []
            def client(config, messages, key):
                calls.append(messages)
                return self.response(self.quality if len(calls) == 1 else self.grounding,
                                     finish='length' if len(calls) == 2 else 'stop')
            judge.run(output, config, 'secret', client=client)
            judge.run(output, config, 'secret', client=client)
            self.assertEqual(len(calls), 2)
            summary = judge.report(output)
            self.assertEqual(summary['modes']['raw']['correctness']['n'], 1)
            self.assertEqual(summary['modes']['raw']['faithfulness']['n'], 0)
            self.assertEqual(summary['modes']['wiki']['system_errors'], 1)
            self.assertEqual(summary['paired']['correctness']['n'], 0)
            judge.run(output, config, 'secret', retry_errors=True, client=client)
            record = judge.read(output / 'results/q-raw-grounding.json')
            self.assertEqual(len(record['attempts']), 2)
            self.assertEqual(judge.report(output)['modes']['raw']['faithfulness']['mean'], 1)
            self.assertNotIn('secret', (output / 'results/q-raw-grounding.json').read_text(encoding='utf-8'))

    def test_input_and_config_changes_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            self.write_bundle(output)
            judge.configure(output, 'judge', 'https://example.invalid/v1')
            with self.assertRaises(ValueError):
                judge.configure(output, 'other', 'https://example.invalid/v1')
            judge.save(output / 'inputs.json', {})
            with self.assertRaises(ValueError):
                judge.load_bundle(output)

    def test_gigachat_uses_existing_oauth_transport_and_stage_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = judge.configure(Path(tmp), 'GigaChat-3-Ultra', 'https://api.giga.chat/v1',
                                     timeout=60, provider='gigachat')
            with patch('corpdb.llm.gigachat._post', return_value=self.response(self.quality)) as post:
                for stage in judge.STAGES:
                    judge.request_api(config, judge.messages(self.bundle(), self.bundle()['cases'][0], stage), 'secret')
                    endpoint, payload = post.call_args.args
                    self.assertEqual(endpoint, 'chat/completions')
                    self.assertEqual(payload['model'], 'GigaChat-3-Ultra')
                    self.assertEqual(payload['temperature'], 0)
                    self.assertEqual(payload['response_format'], config['response_format'][stage])
                    self.assertEqual(payload['response_format']['type'], 'json_schema')
                    self.assertNotIn('secret', json.dumps(payload))

    def test_gigachat_rejects_misleading_endpoint_and_timeout(self):
        for url, timeout in (('https://example.invalid/v1', 60), ('https://api.giga.chat/v1', 180)):
            with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
                judge.configure(Path(tmp), 'GigaChat-3-Ultra', url, timeout=timeout, provider='gigachat')

    def test_fatal_provider_error_stops_without_sending_remaining_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            self.write_bundle(output)
            config = judge.configure(output, 'judge', 'https://example.invalid/v1')
            calls = []
            def client(config, messages, key):
                calls.append(messages)
                raise judge.JudgeTransportError('Judge HTTP 402', 402)
            judge.run(output, config, 'secret', client=client)
            self.assertEqual(len(calls), 1)
            summary = judge.report(output)
            self.assertEqual(summary['modes']['raw']['quality_statuses']['judge_error'], 1)
            self.assertEqual(summary['modes']['raw']['grounding_statuses']['pending'], 1)
            self.assertEqual(judge.read(output / 'results/q-raw-quality.json')['attempts'][0]['error']['status_code'], 402)

    def test_malformed_output_and_crash_do_not_become_zero_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            self.write_bundle(output)
            config = judge.configure(output, 'judge', 'https://example.invalid/v1')
            def client(config, messages, key):
                raise RuntimeError('secret')
            judge.run(output, config, 'secret', client=client)
            summary = judge.report(output)
            self.assertIsNone(summary['modes']['raw']['correctness']['mean'])
            self.assertNotIn('secret', (output / 'results/q-raw-quality.json').read_text(encoding='utf-8'))

    def test_prepare_from_trace_checks_context_and_separates_constraints(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / 'source', Path(tmp) / 'output'
            judge.save(source / 'settings.json', {'required_counts': {'q': 1}})
            judge.save(source / 'questions.json', [dict(question_id='q', question='Срок?',
                question_type='basic', answer_facts=['Пять дней.', 'Не один день.'], gold_answer='Пять дней.')])
            trace = dict(finished=True, question_id='q', question='Срок?',
                settings_sha256=judge.file_hash(source / 'settings.json'),
                result=dict(answer='Пять дней.', selected_chunks=[{'text': 'Срок: пять дней.'}]),
                calls=[dict(stage='answer', messages=[{'content': json.dumps(self.grounding_data)}])])
            for mode in ('raw', 'wiki'):
                judge.save(source / 'traces' / f'q-{mode}.json', {**trace, 'mode': mode})
            bundle = judge.prepare(source, output)
            self.assertEqual(len(bundle['cases'][0]['quality']['required_facts']), 1)
            self.assertEqual(bundle['cases'][0]['quality']['constraints'][0]['id'], 2)
            with self.assertRaises(ValueError):
                judge.prepare(source, output)
            trace['calls'][0]['messages'][0]['content'] = json.dumps({**self.grounding_data, 'fragments': []})
            judge.save(source / 'traces/q-raw.json', {**trace, 'mode': 'raw'})
            with self.assertRaises(ValueError):
                judge.prepare(source, Path(tmp) / 'bad')

    def test_unit_ranges_preserve_markdown_and_newlines(self):
        text = 'Заголовок\r\n\r\n- **2048** [1].\r\nХвост'
        self.assertEqual(judge.resolve_units([1, 2], text), 'Заголовок\r\n\r\n- **2048** [1].')
        for ids in ([True], [0], [4], [2, 1], [1, 1]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                judge.resolve_units(ids, text, True)

    def wire(self, value):
        return json.loads(self.response(value)['choices'][0]['message']['content'])

    def test_referenced_evidence_cannot_fabricate_source_or_unit(self):
        for field, replacement in (('source_id', 12), ('end', 12), ('start', True)):
            value = self.wire(self.grounding)
            value['claims'][0]['support'][0][field] = replacement
            with self.subTest(field=field, value=replacement), self.assertRaises(ValueError):
                judge.validate('grounding', value, self.grounding_data)

    def test_every_answer_line_must_be_accounted_for(self):
        value = self.wire(self.grounding)
        data = {**self.grounding_data, 'answer': 'Пять дней.\nТакже гарантирован возврат денег.'}
        with self.assertRaisesRegex(ValueError, 'неразобранные'):
            judge.validate('grounding', value, data)
        value['nonfactual'] = [dict(answer_id=1, kind='heading', reason='Заголовок')]
        with self.assertRaisesRegex(ValueError, 'одновременно'):
            judge.validate('grounding', value, self.grounding_data)

    def test_atomic_claims_can_share_one_answer_line(self):
        value = self.wire(self.grounding)
        other = deepcopy(value['claims'][0])
        other.update(proposition='Это рабочие дни.', verdict='insufficient', support=[])
        value['claims'].append(other)
        self.assertEqual(judge.validate('grounding', value, self.grounding_data)['faithfulness'], .5)
        value['claims'][1]['proposition'] = value['claims'][0]['proposition']
        with self.assertRaises(ValueError):
            judge.validate('grounding', value, self.grounding_data)

    def test_referenced_refusal_is_na_even_without_sources(self):
        value = dict(version=4, is_abstention=True, reason='Отказ.', claims=[], nonfactual=[
            dict(answer_id=1, kind='refusal', reason='Недостаточно сведений в найденном контексте.')])
        data = dict(question='Вопрос', answer='В найденных источниках недостаточно сведений для ответа.', fragments=[])
        self.assertIsNone(judge.validate('grounding', value, data)['faithfulness'])
        value['is_abstention'] = False
        with self.assertRaises(ValueError):
            judge.validate('grounding', value, data)

    def test_quality_references_do_not_allow_extra_rubric_items(self):
        value = self.wire(self.quality)
        value['constraints'].append(dict(id=99, violated=False, evidence_range=dict(start=0, end=0), reason='Лишнее'))
        with self.assertRaisesRegex(ValueError, 'пункты рубрики'):
            judge.validate('quality', value, self.quality_data)


if __name__ == '__main__':
    unittest.main()
