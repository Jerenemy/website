// The leaderboard on /game: reads /api/leaderboard ([{player, score}, …]) and writes it into #lb
// as a table (static/site/site.css styles `.table table`).
(async function () {
  const box = document.getElementById('lb');
  if (!box) return;
  try {
    const r = await fetch('/api/leaderboard');
    if (!r.ok) throw new Error(r.status);
    const rows = await r.json();
    const table = document.createElement('table');
    const head = table.createTHead().insertRow();
    ['Rank', 'Player', 'Score'].forEach(function (name) {
      const th = document.createElement('th');
      th.scope = 'col';
      th.textContent = name;
      head.appendChild(th);
    });
    const body = table.createTBody();
    rows.forEach(function (row, i) {
      const tr = body.insertRow();
      const rank = document.createElement('th');
      rank.scope = 'row';
      rank.textContent = String(i + 1).padStart(2, '0');
      tr.appendChild(rank);
      tr.insertCell().textContent = row.player;
      tr.insertCell().textContent = row.score;
    });
    box.replaceChildren(rows.length ? table : Object.assign(document.createElement('p'), { className: 'note', textContent: 'No scores yet.' }));
  } catch (e) {
    box.replaceChildren(Object.assign(document.createElement('p'), { className: 'note', textContent: 'The leaderboard is unavailable.' }));
  }
})();
