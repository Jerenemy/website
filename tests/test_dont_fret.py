import json
import tempfile
import unittest
import uuid
from pathlib import Path

from app import create_app
from app.blueprints.dont_fret import NEW_PER_DAY, database, manifest, stats, summary


class ListeningTestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = create_app()
        self.key_path = Path(self.temp.name) / 'key.json'
        self.app.config.update(TESTING=True, SECRET_KEY='test',
                               DONT_FRET_LISTENING_DATABASE_PATH=str(Path(self.temp.name) / 'listening.sqlite3'),
                               DONT_FRET_LISTENING_KEY_PATH=str(self.key_path))
        self.context = self.app.app_context()
        self.context.push()
        self.addCleanup(self.context.pop)
        self.client = self.app.test_client()
        self.manifest = manifest()
        # the real key is never in the repository: make one up, in each piece's file order
        self.key = {}
        for t in self.manifest['trials']:
            conditions = ['real', 'new', 'old', 'anchor'] if t['kind'] == 'pro' else ['new', 'old', 'anchor']
            self.key.update({s['file']: c for s, c in zip(t['stimuli'], conditions)})
        self.key_path.write_text(json.dumps(self.key))

    def answers(self, scores=None, finished=False, pieces=None, listener=None):
        """Valid answers: every piece's clips in manifest order, rated by condition from `scores`."""
        scores = scores or {'real': 90, 'new': 80, 'old': 40, 'anchor': 10}
        trials = self.manifest['trials'] if pieces is None else self.manifest['trials'][:pieces]
        return {
            'listener': listener or str(uuid.uuid4()),
            'info': {'experience': 'regular', 'playback': 'headphones'},
            'letters': {t['id']: [s['file'] for s in t['stimuli']] for t in self.manifest['trials']},
            'ratings': {t['id']: {s['file']: scores[self.key[s['file']]] for s in t['stimuli']} for t in trials},
            'finished': finished,
        }

    def post(self, body, address='203.0.113.7'):
        return self.client.post('/dont-fret/listening-test/answers', json=body, environ_base={'REMOTE_ADDR': address})

    def rows(self):
        with database() as db:
            return db.execute('SELECT * FROM answers ORDER BY created_at').fetchall()

    def admin(self):
        with self.client.session_transaction() as session:
            session['admin_authenticated'] = True

    def test_page_and_redirect(self):
        self.assertEqual(self.client.get('/dont-fret').headers['Location'], '/dont-fret/listening-test')
        page = self.client.get('/dont-fret/listening-test')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Guitar listening test', page.data)
        self.assertIn(b'data-manifest="/static/dont-fret/listening-test/manifest.json"', page.data)
        self.assertIn(b'CC BY 4.0', page.data)
        self.assertEqual(page.headers['X-Robots-Tag'], 'noindex')

    def test_clips_are_blind_and_complete(self):
        static = Path(self.app.static_folder) / 'dont-fret' / 'listening-test'
        self.assertNotIn('key', self.manifest)
        text = json.dumps(self.manifest['trials'])
        for word in ('real', 'new', 'old', 'anchor'):
            self.assertNotIn(f'"{word}"', text)
        for t in self.manifest['trials']:
            self.assertEqual(len(t['stimuli']), 4 if t['kind'] == 'pro' else 3, t['id'])
            for s in t['stimuli']:
                self.assertTrue((static / s['file']).is_file(), s['file'])
        # nothing about which clip is which ships with the site
        self.assertEqual([p for p in Path(self.app.root_path).rglob('*key*.json')], [])

    def test_answers_are_saved_then_updated(self):
        body = self.answers(pieces=2)
        self.assertEqual(self.post(body).status_code, 204)
        row = self.rows()[0]
        self.assertEqual((row['listener'], row['finished']), (body['listener'], 0))
        self.assertEqual(len(json.loads(row['ratings'])), 2)
        self.assertNotIn('203.0.113.7', row['source'])
        # finishing needs every piece
        self.assertEqual(self.post({**body, 'finished': True}).status_code, 400)
        self.assertEqual(self.post(self.answers(finished=True, listener=body['listener'])).status_code, 204)
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['finished'], 1)
        self.assertEqual(len(json.loads(rows[0]['ratings'])), len(self.manifest['trials']))

    def test_bad_answers_are_refused(self):
        good = self.answers()
        first = self.manifest['trials'][0]
        other = self.manifest['trials'][1]['stimuli'][0]['file']
        bad = [
            {**good, 'listener': 'not-a-uuid'},
            {**good, 'info': {'experience': 'rockstar'}},
            {**good, 'ratings': {'p99': {}}},
            {**good, 'ratings': {first['id']: {other: 50}}},
            {**good, 'ratings': {first['id']: {first['stimuli'][0]['file']: 101}}},
            {**good, 'ratings': {first['id']: {first['stimuli'][0]['file']: '50'}}},
            {**good, 'ratings': {first['id']: {first['stimuli'][0]['file']: True}}},
            {**good, 'letters': {first['id']: [first['stimuli'][0]['file']]}},
            ['not', 'an', 'object'],
        ]
        for body in bad:
            self.assertEqual(self.post(body).status_code, 400, body)
        self.assertEqual(self.client.post('/dont-fret/listening-test/answers', data='x' * 20000,
                                          content_type='application/json').status_code, 413)
        self.assertEqual(self.rows(), [])

    def test_new_listeners_are_limited_per_network(self):
        for _ in range(NEW_PER_DAY):
            self.assertEqual(self.post(self.answers(pieces=1)).status_code, 204)
        self.assertEqual(self.post(self.answers(pieces=1)).status_code, 429)
        self.assertEqual(self.post(self.answers(pieces=1), address='198.51.100.1').status_code, 204)
        # someone already counted can still save their progress
        listener = self.rows()[0]['listener']
        self.assertEqual(self.post(self.answers(pieces=3, listener=listener)).status_code, 204)

    def test_scores_and_screening(self):
        self.assertEqual(stats([]), {'n': 0, 'mean': None, 'ci': None})
        s = stats([70, 80, 90])
        self.assertAlmostEqual(s['mean'], 80)
        self.assertAlmostEqual(s['ci'], 4.30 * 10 / 3 ** 0.5, places=6)   # t(2) × sd / √n
        self.post(self.answers(finished=True))
        self.post(self.answers({'real': 70, 'new': 70, 'old': 30, 'anchor': 0}, finished=True))
        self.post(self.answers({'real': 10, 'new': 50, 'old': 50, 'anchor': 90}, finished=True))   # anchor above real: screened
        result = summary(self.rows(), self.key)
        self.assertEqual((result['listeners'], result['finished'], result['excluded']), (3, 3, 1))
        studio = {row['condition']: row for row in result['studio']}
        self.assertAlmostEqual(studio['real']['mean'], 80)
        self.assertAlmostEqual(studio['new']['mean'], 75)
        self.assertAlmostEqual(result['new_vs_old']['mean'], 40)
        self.assertAlmostEqual(result['new_vs_real']['at_least'], 0.5)
        self.assertNotIn('real', {row['condition'] for row in result['app']})
        everyone = summary(self.rows(), self.key, everyone=True)
        self.assertAlmostEqual({row['condition']: row for row in everyone['studio']}['real']['mean'], (90 + 70 + 10) / 3)

    def test_admin_results_and_csv(self):
        self.assertEqual(self.client.get('/admin/dont-fret/listening-test').status_code, 302)
        self.assertEqual(self.client.get('/admin/dont-fret/listening-test/ratings.csv').status_code, 302)
        self.admin()
        empty = self.client.get('/admin/dont-fret/listening-test')
        self.assertEqual(empty.status_code, 200)
        self.assertIn(b'Nobody has taken the test yet.', empty.data)
        self.post(self.answers(finished=True))
        page = self.client.get('/admin/dont-fret/listening-test').data
        self.assertIn(b'1 listener, 1 finished.', page)
        self.assertIn(b'80 \xc2\xb1 0', page)                              # the new engine's mean
        self.assertIn(b'href="/admin/dont-fret/listening-test"', self.client.get('/admin/wtt').data)
        csv = self.client.get('/admin/dont-fret/listening-test/ratings.csv')
        lines = csv.data.decode().strip().splitlines()
        self.assertTrue(lines[0].startswith('listener,piece,kind,condition,score'))
        self.assertEqual(len(lines) - 1, sum(len(t['stimuli']) for t in self.manifest['trials']))

    def test_results_wait_for_the_key(self):
        self.key_path.unlink()
        self.assertEqual(self.post(self.answers(pieces=1)).status_code, 204)       # answers still save
        self.admin()
        page = self.client.get('/admin/dont-fret/listening-test')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'1 listener so far.', page.data)
        self.assertIn(b'Answer key missing', page.data)
        self.assertEqual(self.client.get('/admin/dont-fret/listening-test/ratings.csv').status_code, 503)


if __name__ == '__main__':
    unittest.main()
