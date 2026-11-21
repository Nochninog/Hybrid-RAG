"""The experiment checks source quotes and renders its own source links."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import evaluation.saturn_grounded as experiment
from evaluation.saturn_grounded import inspect_quotes, parse_draft, render_markdown


class GroundedSaturnTests(unittest.TestCase):
    def setUp(self):
        self.source = 'As of 2006,\n  Saturn has 56 moons. H2 is predicted by models.'
        self.draft = {'sections': [{'heading': 'Moons', 'paragraphs': [{
            'text': 'The source gives 56 moons as of 2006.',
            'quotes': ['As of 2006, Saturn has 56 moons.'],
        }]}]}

    def test_whitespace_normalized_quotes_and_fixed_source_links(self):
        draft = parse_draft(json.dumps(self.draft))
        checked = inspect_quotes(draft, self.source)
        self.assertTrue(checked[0]['found'])
        self.assertEqual(checked[0]['start'], 0)
        markdown = render_markdown(draft, self.source, 67, 'Saturn')
        self.assertEqual(markdown.count('](document:67)'), 1)
        self.assertNotIn('As of 2006, Saturn has 56 moons.', markdown)

    def test_invented_or_shortened_quote_prevents_rendering(self):
        for quote in ['Cassini ended in 2017.', 'As of 2006, ... 56 moons.']:
            with self.subTest(quote=quote):
                draft = copy.deepcopy(self.draft)
                draft['sections'][0]['paragraphs'][0]['quotes'] = [quote]
                self.assertFalse(inspect_quotes(draft, self.source)[0]['found'])
                with self.assertRaises(ValueError):
                    render_markdown(draft, self.source, 67, 'Saturn')

    def test_existing_quote_does_not_prove_the_claim(self):
        self.draft['sections'][0]['paragraphs'][0]['text'] = 'Cassini ended in 2017.'
        self.assertTrue(inspect_quotes(self.draft, self.source)[0]['found'])
        # This passes the literal check: a manual semantic review must catch it.
        self.assertIn('2017', render_markdown(self.draft, self.source, 67, 'Saturn'))

    def test_empty_wrong_types_extra_fields_and_duplicate_keys_rejected(self):
        bad = [{'sections': []}, {'sections': 'text'}, {'sections': [1]},
               {'sections': [{'heading': 'Moons', 'paragraphs': []}]},
               {'sections': [{'heading': 'Moons', 'paragraphs': [{'text': 'Claim', 'quotes': []}]}]},
               {**self.draft, 'extra': True}]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_draft(json.dumps(value))
        with self.assertRaises(ValueError):
            parse_draft('{"sections": [], "sections": []}')

    def test_model_markdown_and_html_cannot_replace_renderer_links(self):
        self.draft['sections'][0]['heading'] = '<img> [x](document:99)'
        self.draft['sections'][0]['paragraphs'][0]['text'] = '[wrong](document:99)\n\n# Other'
        markdown = render_markdown(self.draft, self.source, 67, 'Saturn')
        self.assertNotIn('](document:99)', markdown)
        self.assertNotIn('<img>', markdown)
        self.assertEqual(markdown.count('](document:67)'), 1)
        with self.assertRaises(ValueError):
            render_markdown(self.draft, self.source, True, 'Saturn')

    def test_failed_quote_rebuild_is_offline_and_keeps_the_raw_answer(self):
        self.draft['sections'][0]['paragraphs'][0]['quotes'] = ['An absent quote.']
        with TemporaryDirectory() as temporary, patch.object(experiment, 'OUT', Path(temporary)):
            folder = Path(temporary)
            raw = json.dumps(self.draft).encode('utf-8')
            (folder / 'response.raw.json').write_bytes(raw)
            (folder / 'source.txt').write_text(self.source, encoding='utf-8')
            experiment.write_json(folder / 'state.json', {
                'status': 'response_saved', 'generation_attempts': 1,
                'response_sha256': experiment.digest(folder / 'response.raw.json')})
            with patch('corpdb.llm.gigachat.generate_text') as generate:
                experiment.materialize()
            generate.assert_not_called()
            self.assertEqual((folder / 'response.raw.json').read_bytes(), raw)
            self.assertFalse((folder / 'draft.md').exists())
            self.assertTrue((folder / 'preview.md').exists())
            self.assertEqual(experiment.read_json(folder / 'state.json')['status'], 'quote_check_failed')


if __name__ == '__main__':
    unittest.main()
