"""Persistent friendly-battle tracker; shared by HTTP and the daily CLI job."""
import hashlib
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import click
import requests
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask.cli import with_appcontext
from .blueprints.admin.routes import _csrf_token, _validate_csrf

bp = Blueprint('clash', __name__)
SEEDS = [('Jer', '#C9C8YQ2C'), ('Will', '#LJVC8Y9P9'), ('Win', '#J00JQYVG0'), ('Leo', '#9Y9G0LJQ')]
SCORES = [[0, 0, 3, 1], [1, 0, 2, 1], [0, 0, 0, 0], [0, 0, 1, 0]]


class TrackerError(Exception):
    pass


def normalize_tag(value):
    tag = '#' + value.strip().upper().lstrip('#')
    if not re.fullmatch(r'#[0289PYLQGRJCUV]{3,15}', tag):
        raise TrackerError('Enter a valid Clash Royale player tag.')
    return tag


@contextmanager
def database():
    path = Path(current_app.config['CLASH_ROYALE_DATABASE_PATH'])
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        with db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS players (
                    tag TEXT PRIMARY KEY, name TEXT NOT NULL, position INTEGER NOT NULL,
                    registered REAL NOT NULL, baseline REAL, log TEXT NOT NULL DEFAULT '[]',
                    synced REAL, error TEXT, gap INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS scores (
                    winner TEXT, loser TEXT, wins INTEGER NOT NULL,
                    PRIMARY KEY(winner, loser));
                CREATE TABLE IF NOT EXISTS matches (fingerprint TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts (ip TEXT NOT NULL, at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS attempts_ip ON attempts(ip, at);
            ''')
            db.execute('BEGIN IMMEDIATE')
            if not db.execute("SELECT 1 FROM state WHERE key='seeded'").fetchone():
                for i, (name, tag) in enumerate(SEEDS):
                    db.execute('INSERT INTO players(tag,name,position,registered) VALUES (?,?,?,?)', (tag, name, i, time.time()))
                    for j, (_, other) in enumerate(SEEDS):
                        if i != j:
                            db.execute('INSERT INTO scores VALUES (?,?,?)', (tag, other, SCORES[i][j]))
                db.execute("INSERT INTO state VALUES ('seeded','1')")
            db.commit()
            yield db
    finally:
        db.close()


def api(tag, suffix=''):
    token = current_app.config.get('CLASH_ROYALE_API_TOKEN')
    if not token:
        raise TrackerError('Tracking unavailable: the server API token is not configured.')
    try:
        response = requests.get(current_app.config['CLASH_ROYALE_API_BASE_URL'].rstrip('/') + '/players/' + quote(tag, safe='') + suffix,
                                headers={'Authorization': 'Bearer ' + token}, timeout=(5, 10))
        if response.status_code == 404:
            raise TrackerError('Player not found. Check the tag.')
        if response.status_code == 403:
            raise TrackerError('API access denied. Check the API key and its allowed server IP addresses.')
        if response.status_code != 200:
            raise TrackerError(f'Clash Royale API unavailable (HTTP {response.status_code}).')
        data = response.json()
    except (requests.RequestException, ValueError):
        raise TrackerError('Clash Royale API could not be reached. Please try again.') from None
    if suffix and (not isinstance(data, list) or not all(isinstance(x, dict) and all(isinstance(x.get(side), list) and all(isinstance(p, dict) for p in x[side]) for side in ('team', 'opponent')) for x in data)):
        raise TrackerError('Unexpected battle log response.')
    if not suffix and (not isinstance(data, dict) or data.get('tag') != tag or not isinstance(data.get('name'), str)):
        raise TrackerError('Unexpected player response.')
    return data


def battle_record(battle):
    """Canonical participant-aligned data, independent of log perspective."""
    sides = [battle.get('team', []), battle.get('opponent', [])]
    if battle.get('type') != 'friendly' or any(not isinstance(side, list) or len(side) != 1 or not isinstance(side[0], dict) for side in sides):
        return None
    try:
        players = sorted((normalize_tag(side[0]['tag']), side[0]['crowns']) for side in sides)
        if players[0][0] == players[1][0] or any(type(c) is not int or c < 0 for _, c in players):
            return None
        mode = battle.get('gameMode')
        if not isinstance(mode, dict) or type(mode.get('id')) is not int:
            return None
        occurred = datetime.strptime(battle['battleTime'], '%Y%m%dT%H%M%S.%fZ').replace(tzinfo=timezone.utc).timestamp()
        payload = json.dumps([battle['battleTime'], battle['type'], battle.get('gameMode', {}).get('id'), players], separators=(',', ':'))
        return hashlib.sha256(payload.encode()).hexdigest(), occurred, players, payload
    except (KeyError, TypeError, ValueError, AttributeError, TrackerError):
        return None


def log_keys(log):
    return {json.dumps([b.get('battleTime'), sorted(p.get('tag', '') for side in ('team', 'opponent') for p in b.get(side, [])), b.get('type')]) for b in log}


def sync(manual=False):
    if not current_app.config.get('CLASH_ROYALE_API_TOKEN'):
        raise TrackerError('Tracking unavailable: the server API token is not configured.')
    owner, now = secrets.token_hex(16), time.time()
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        state = dict(db.execute('SELECT key,value FROM state').fetchall())
        if float(state.get('lease_until', '0')) > now:
            raise TrackerError('A sync is already running. Please try again shortly.')
        if manual and now - float(state.get('manual_at', '0')) < 60:
            raise TrackerError('Please wait 60 seconds between manual syncs.')
        for key, value in [('lease_owner', owner), ('lease_until', str(now + 90))] + ([('manual_at', str(now))] if manual else []):
            db.execute('INSERT OR REPLACE INTO state VALUES (?,?)', (key, value))
        players = db.execute('SELECT * FROM players ORDER BY position').fetchall()
        verified = state.get('verified') == '1'
    added, failures = 0, []
    try:
        for player in players:
            try:
                with database() as db:
                    db.execute('BEGIN IMMEDIATE')
                    if db.execute("SELECT value FROM state WHERE key='lease_owner'").fetchone()[0] != owner:
                        raise TrackerError('Sync lease expired. Please retry.')
                    db.execute("UPDATE state SET value=? WHERE key='lease_until'", (str(time.time() + 90),))
                log = api(player['tag'], '/battlelog')
            except TrackerError as exc:
                failures.append(player['name'] + ': ' + str(exc))
                with database() as db:
                    db.execute('UPDATE players SET error=? WHERE tag=?', (str(exc), player['tag']))
                continue
            with database() as db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute("SELECT value FROM state WHERE key='lease_owner'").fetchone()[0] != owner:
                    raise TrackerError('Sync lease expired. Please retry.')
                previous = json.loads(player['log'])
                gap = bool(previous and log and not log_keys(previous).intersection(log_keys(log)))
                registered = {p['tag']: p for p in db.execute('SELECT * FROM players')}
                if verified and player['baseline'] is not None:
                    for battle in log:
                        record = battle_record(battle)
                        if not record:
                            continue
                        fingerprint, occurred, participants, payload = record
                        tags = [p[0] for p in participants]
                        if player['tag'] not in tags or any(tag not in registered or registered[tag]['baseline'] is None for tag in tags):
                            continue
                        if occurred <= max(max(registered[t]['registered'], registered[t]['baseline']) for t in tags):
                            continue
                        inserted = db.execute('INSERT OR IGNORE INTO matches VALUES (?,?)', (fingerprint, payload)).rowcount
                        if inserted and participants[0][1] != participants[1][1]:
                            winner, loser = sorted(participants, key=lambda p: p[1], reverse=True)
                            db.execute('INSERT INTO scores VALUES (?,?,1) ON CONFLICT(winner,loser) DO UPDATE SET wins=wins+1', (winner[0], loser[0]))
                            added += 1
                db.execute('UPDATE players SET log=?,synced=?,error=NULL,gap=?,baseline=COALESCE(baseline,?) WHERE tag=?',
                           (json.dumps(log), time.time(), gap, now if verified else None, player['tag']))
        with database() as db:
            db.execute("INSERT OR REPLACE INTO state VALUES ('last_sync',?)", (str(time.time()),))
        message = f'Sync complete: {added} new wins.'
        if not verified:
            message += ' Score tracking awaits live friendly-battle verification.'
        if failures:
            message += ' Some accounts failed: ' + '; '.join(failures)
        return message, bool(failures)
    finally:
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT value FROM state WHERE key='lease_owner'").fetchone()[0] == owner:
                db.execute("UPDATE state SET value='0' WHERE key='lease_until'")


def add_account(value, ip):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        now = time.time()
        db.execute('DELETE FROM attempts WHERE at<?', (now - 600,))
        limited = db.execute('SELECT COUNT(*) FROM attempts WHERE ip=?', (ip,)).fetchone()[0] >= 5
        if not limited:
            db.execute('INSERT INTO attempts VALUES (?,?)', (ip, now))
    if limited:
        raise TrackerError('Too many attempts. Please try again in ten minutes.')
    tag = normalize_tag(value)
    with database() as db:
        if db.execute('SELECT 1 FROM players WHERE tag=?', (tag,)).fetchone():
            return 'That account is already in the table.'
    profile, log = api(tag), api(tag, '/battlelog')
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM players WHERE tag=?', (tag,)).fetchone():
            return 'That account is already in the table.'
        now = time.time()
        position = db.execute('SELECT COALESCE(MAX(position),-1)+1 FROM players').fetchone()[0]
        verified = db.execute("SELECT value FROM state WHERE key='verified'").fetchone()
        db.execute('INSERT INTO players(tag,name,position,registered,baseline,log,synced) VALUES (?,?,?,?,?,?,?)',
                   (tag, profile['name'], position, now, now if verified and verified[0] == '1' else None, json.dumps(log), now))
    return profile['name'] + ' added. Future friendly battles will count after tracking is activated.'


@bp.get('/will-sucks', strict_slashes=False)
def page():
    with database() as db:
        players = db.execute('SELECT * FROM players ORDER BY position').fetchall()
        scores = {(r['winner'], r['loser']): r['wins'] for r in db.execute('SELECT * FROM scores')}
        state = dict(db.execute('SELECT key,value FROM state').fetchall())
    last = state.get('last_sync')
    return render_template('will_sucks.html', players=players, scores=scores, csrf_token=_csrf_token(),
                           configured=bool(current_app.config.get('CLASH_ROYALE_API_TOKEN')), verified=state.get('verified') == '1',
                           last_sync=datetime.fromtimestamp(float(last), timezone.utc).isoformat() if last else None)


def client_ip():
    # Nginx overwrites X-Real-IP; only trust it from the loopback-bound proxy.
    if request.remote_addr in ('127.0.0.1', '::1'):
        value = request.headers.get('X-Real-IP')
        if value:
            import ipaddress
            try:
                return str(ipaddress.ip_address(value))
            except ValueError:
                pass
    return request.remote_addr or 'unknown'


@bp.after_request
def fresh_response(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.post('/will-sucks/<action>')
def change(action):
    if action not in ('accounts', 'sync'):
        return 'Not found', 404
    if not _validate_csrf(request.form.get('csrf_token')):
        return 'Your form expired. Reload the page and try again.', 400
    try:
        message, error = (sync(manual=True) if action == 'sync' else (add_account(request.form.get('tag', ''), client_ip()), False))
        flash(message, 'error' if error else 'success')
    except TrackerError as exc:
        flash(str(exc), 'error')
    except (sqlite3.Error, OSError):
        current_app.logger.exception('Clash tracker storage unavailable')
        flash('Storage unavailable. Please try again.', 'error')
    return redirect(url_for('clash.page'), code=303)


@click.command('init-clash-db')
@with_appcontext
def init_command():
    with database():
        pass
    click.echo('Clash Royale database initialized; existing scores preserved.')


@click.command('sync-clash')
@with_appcontext
def sync_command():
    try:
        message, errors = sync()
    except TrackerError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(message)
    if errors:
        raise click.ClickException('Some accounts failed; see sync output.')


@click.command('verify-clash-friendly')
@with_appcontext
def verify_command():
    """Confirm a live 1v1 friendly payload before activating score updates."""
    try:
        with database() as db:
            tags = [r[0] for r in db.execute('SELECT tag FROM players')]
        for tag in tags:
            for battle in api(tag, '/battlelog'):
                if battle_record(battle):
                    with database() as db:
                        db.execute("INSERT OR REPLACE INTO state VALUES ('verified','1')")
                    click.echo('Live 1v1 friendly payload verified. Run sync-clash to baseline accounts.')
                    return
    except TrackerError as exc:
        raise click.ClickException(str(exc)) from None
    raise click.ClickException('No valid live 1v1 friendly found. Play one, then retry verification.')
