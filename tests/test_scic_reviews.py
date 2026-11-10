import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.blueprints.scic import DAILY_LIMIT, database


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = create_app()
        self.app.config.update(TESTING=True, SECRET_KEY='test',
                               SCIC_REVIEWS_DATABASE_PATH=str(Path(self.temp.name) / 'reviews.sqlite3'))
        self.context = self.app.app_context()
        self.context.push()
        self.addCleanup(self.context.pop)
        self.client = self.app.test_client()

    def post(self, **data):
        self.client.get('/scic/reviews')
        with self.client.session_transaction() as session:
            data.setdefault('csrf_token', session['csrf_token'])
        return self.client.post('/scic/reviews', data=data)

    def rows(self):
        with database() as db:
            return db.execute('SELECT name, rating, text FROM reviews ORDER BY id').fetchall()

    def test_empty_page_and_hub_link(self):
        page = self.client.get('/scic/reviews')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'No reviews yet.', page.data)
        self.assertIn(b'href="/scic/reviews"', self.client.get('/scic').data)

    def test_post_shows_review_and_average(self):
        response = self.post(name='  Ada   L ', rating='5', text='Fixed my MATLAB loop.')
        self.assertEqual(response.status_code, 303)
        self.post(rating='4', text='Good help with SQL.')
        self.assertEqual([tuple(r) for r in self.rows()],
                         [('Ada L', 5, 'Fixed my MATLAB loop.'), ('', 4, 'Good help with SQL.')])
        page = self.client.get('/scic/reviews').data
        self.assertIn(b'4.5', page)
        self.assertIn(b'Anonymous', page)
        self.assertIn(b'2 reviews', page)

    def test_bad_input_is_refused(self):
        for data in ({'rating': '0', 'text': 'x'}, {'rating': '6', 'text': 'x'}, {'rating': 'abc', 'text': 'x'},
                     {'rating': '3', 'text': '   '}, {'rating': '3', 'text': 'x' * 2001},
                     {'rating': '3', 'text': 'x', 'name': 'n' * 61}):
            self.assertEqual(self.post(**data).status_code, 400, data)
        self.assertEqual(self.post(rating='3', text='x', csrf_token='wrong').status_code, 400)
        self.assertEqual(self.rows(), [])

    def test_text_is_escaped(self):
        self.post(rating='3', text='<script>alert(1)</script>')
        page = self.client.get('/scic/reviews').data
        self.assertNotIn(b'<script>alert(1)</script>', page)
        self.assertIn(b'&lt;script&gt;', page)

    def test_honeypot_and_daily_limit(self):
        self.assertEqual(self.post(rating='5', text='spam', website='x').status_code, 303)
        self.assertEqual(self.rows(), [])
        for _ in range(DAILY_LIMIT):
            self.assertEqual(self.post(rating='5', text='ok').status_code, 303)
        self.assertEqual(self.post(rating='5', text='one more').status_code, 400)
        self.assertEqual(len(self.rows()), DAILY_LIMIT)

    def test_admin_removes_a_review(self):
        self.post(rating='1', text='rude')
        self.assertEqual(self.client.get('/admin/reviews').status_code, 302)
        with self.client.session_transaction() as session:
            session['admin_authenticated'] = True
            token = session['csrf_token']
        self.assertIn(b'rude', self.client.get('/admin/reviews').data)
        with database() as db:
            review_id = db.execute('SELECT id FROM reviews').fetchone()[0]
        self.client.post(f'/admin/reviews/{review_id}/delete', data={'csrf_token': token})
        self.assertEqual(self.rows(), [])


if __name__ == '__main__':
    unittest.main()
