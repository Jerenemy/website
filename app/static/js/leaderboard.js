(async function(){
  const r = await fetch('/api/leaderboard');
  const data = await r.json();
  document.getElementById('lb').textContent = JSON.stringify(data,null,2);
})();