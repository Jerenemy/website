import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import requests
from app import create_app
from app.blueprints.clash_royale import SEEDS, SCORES, TrackerError, add_account, api, battle_record, database, normalize_tag, sync


def battle(winner=0, loser=1, timestamp=None, crowns=(1, 0), kind='friendly'):
    return {'type': kind, 'battleTime': datetime.fromtimestamp(timestamp or time.time(), timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'),
            'gameMode': {'id': 72000006}, 'team': [{'tag': SEEDS[winner][1], 'crowns': crowns[0]}],
            'opponent': [{'tag': SEEDS[loser][1], 'crowns': crowns[1]}]}


class ClashTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = create_app()
        self.app.config.update(TESTING=True, SECRET_KEY='test', CLASH_ROYALE_API_TOKEN='test',
                               CLASH_ROYALE_DATABASE_PATH=str(Path(self.temp.name) / 'clash.sqlite3'))
        self.context = self.app.app_context()
        self.context.push()
        self.addCleanup(self.context.pop)
        self.client = self.app.test_client()

    def ready(self):
        with database() as db:
            db.execute("INSERT INTO state VALUES ('verified','1')")
        with patch('app.blueprints.clash_royale.api', return_value=[]):
            sync()
        with database() as db:
            db.execute('UPDATE players SET registered=?, baseline=?', (time.time()-100, time.time()-100))

    def wins(self, winner=0, loser=1):
        with database() as db:
            return db.execute('SELECT wins FROM scores WHERE winner=? AND loser=?', (SEEDS[winner][1], SEEDS[loser][1])).fetchone()[0]

    def post(self, action, **data):
        self.client.get('/will-sucks')
        with self.client.session_transaction() as session:
            data['csrf_token'] = session['csrf_token']
        return self.client.post('/will-sucks/' + action, data=data, follow_redirects=True)

    def test_seed_persistence_and_page(self):
        self.assertEqual(self.client.get('/will-sucks/').status_code, 200)
        self.assertEqual(self.app.test_cli_runner().invoke(args=['init-clash-db']).exit_code, 0)
        with database() as db:
            self.assertEqual([(r['name'], r['tag']) for r in db.execute('SELECT * FROM players ORDER BY position')], SEEDS)
            for i in range(4):
                for j in range(4):
                    if i != j:
                        self.assertEqual(self.wins(i, j), SCORES[i][j])
            db.execute('UPDATE scores SET wins=9 WHERE winner=? AND loser=?', (SEEDS[0][1], SEEDS[1][1]))
        self.app.test_cli_runner().invoke(args=['init-clash-db'])
        self.assertEqual(self.wins(), 9)
        self.assertIn('.table { overflow-x: auto; }', Path('app/static/site/site.css').read_text())

    def test_baseline_and_verification_gate(self):
        with patch('app.blueprints.clash_royale.api', return_value=[battle(timestamp=time.time()-20)]):
            sync()
            self.assertEqual(self.wins(), 0)
            with database() as db:
                self.assertIsNone(db.execute('SELECT baseline FROM players').fetchone()[0])
            result = self.app.test_cli_runner().invoke(args=['verify-clash-friendly'])
            self.assertEqual(result.exit_code, 0, result.output)
            sync()
            sync()
        self.assertEqual(self.wins(), 0)

    def test_dedup_direction_and_modes(self):
        self.ready()
        match = battle()
        reverse = dict(match, team=match['opponent'], opponent=match['team'])
        self.assertEqual(battle_record(match)[0], battle_record(reverse)[0])
        logs = [match, reverse, battle(crowns=(0, 0)), battle(kind='PvP'), battle(timestamp=time.time()-1000)]
        two = battle(); two['team'] = two['team'] * 2; logs.append(two)
        with patch('app.blueprints.clash_royale.api', return_value=logs):
            sync(); sync()
        self.assertEqual(self.wins(), 1)
        self.assertEqual(self.wins(1, 0), 1)

    def test_partial_failure_cache_and_gaps(self):
        self.ready()
        old = battle(timestamp=time.time()-500)
        with database() as db:
            db.execute('UPDATE players SET log=?', (json.dumps([old]),))
        def fetch(tag, suffix):
            if tag == SEEDS[1][1]:
                raise TrackerError('Timed out')
            return [battle(timestamp=time.time()-5)]
        with patch('app.blueprints.clash_royale.api', side_effect=fetch):
            message, failed = sync()
        self.assertTrue(failed)
        self.assertEqual(self.wins(), 1)
        with database() as db:
            will = db.execute('SELECT * FROM players WHERE tag=?', (SEEDS[1][1],)).fetchone()
            self.assertEqual(json.loads(will['log']), [old])
            self.assertEqual(will['error'], 'Timed out')
            self.assertEqual(db.execute('SELECT gap FROM players WHERE tag=?', (SEEDS[0][1],)).fetchone()[0], 1)

    def test_add_normalization_duplicates_limits(self):
        self.ready()
        tag = '#PPY0289'
        self.assertEqual(normalize_tag(' ppy0289 '), tag)
        with patch('app.blueprints.clash_royale.api', side_effect=[{'name': '<New>', 'tag': tag}, []]):
            add_account('ppy0289', '127.0.0.1')
        with patch('app.blueprints.clash_royale.api') as fetch:
            add_account(tag, '127.0.0.1')
            fetch.assert_not_called()
        html = self.client.get('/will-sucks').text
        self.assertIn('&lt;New&gt;', html)
        with database() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM players').fetchone()[0], 5)
            db.execute('UPDATE players SET registered=? WHERE tag=?', (time.time()+100, tag))
        for _ in range(3):
            with self.assertRaises(TrackerError):
                add_account('bad!', '127.0.0.1')
        with self.assertRaisesRegex(TrackerError, 'Too many'):
            add_account(tag, '127.0.0.1')

    def test_failed_account_and_api_timeout(self):
        with patch('app.blueprints.clash_royale.api', side_effect=TrackerError('Player not found')):
            self.assertIn('Player not found', self.post('accounts', tag='#PPY0289').text)
        with patch('app.blueprints.clash_royale.requests.get', side_effect=requests.Timeout):
            with self.assertRaisesRegex(TrackerError, 'could not be reached'):
                api(SEEDS[0][1])
        with database() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM players').fetchone()[0], 4)

    def test_csrf_missing_credentials_cooldown(self):
        self.assertEqual(self.client.post('/will-sucks/sync').status_code, 400)
        with patch('app.blueprints.clash_royale.api', return_value=[]):
            sync(manual=True)
            with self.assertRaisesRegex(TrackerError, '60 seconds'):
                sync(manual=True)
        self.app.config['CLASH_ROYALE_API_TOKEN'] = None
        self.assertIn('Tracking unavailable', self.client.get('/will-sucks').text)
        with self.assertRaisesRegex(TrackerError, 'not configured'):
            sync()

    def test_concurrent_sync_lease(self):
        self.ready()
        started, finish = Event(), Event()
        def fetch(*args):
            started.set()
            finish.wait(5)
            return []
        def run():
            with self.app.app_context():
                return sync()
        with patch('app.blueprints.clash_royale.api', side_effect=fetch), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run)
            try:
                self.assertTrue(started.wait(5))
                with self.assertRaisesRegex(TrackerError, 'already running'):
                    sync()
            finally:
                finish.set()
            future.result()

    def test_malformed_payload_and_proxy_ip(self):
        from app.blueprints.clash_royale import client_ip
        for malformed in ({}, dict(battle(), team=None), dict(battle(), gameMode=None), dict(battle(), battleTime='bad')):
            self.assertIsNone(battle_record(malformed))
        with self.app.test_request_context(headers={'X-Real-IP': '203.0.113.7'}, environ_base={'REMOTE_ADDR': '127.0.0.1'}):
            self.assertEqual(client_ip(), '203.0.113.7')
        with self.app.test_request_context(headers={'X-Real-IP': '203.0.113.7'}, environ_base={'REMOTE_ADDR': '198.51.100.1'}):
            self.assertEqual(client_ip(), '198.51.100.1')

    def test_registration_cutoff(self):
        self.ready()
        with database() as db:
            db.execute('UPDATE players SET registered=? WHERE tag=?', (time.time()+100, SEEDS[1][1]))
        with patch('app.blueprints.clash_royale.api', return_value=[battle()]):
            sync()
        self.assertEqual(self.wins(), 0)


if __name__ == '__main__':
    unittest.main()
