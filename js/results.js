// Results board — data/results.json, группировка по ипподрому
(function () {
  function esc(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function placeCell(place) {
    if (place == null || place === '') {
      return '<td class="col-place result-card__pending">—</td>';
    }
    const p = Number(place);
    const cls = p === 1 ? 'place-1' : p === 2 ? 'place-2' : p === 3 ? 'place-3' : '';
    return '<td class="col-place ' + cls + '">' + esc(place) + '</td>';
  }

  function horseRows(horses) {
    const list = (horses || []).slice().sort((a, b) => {
      const pa = a.place == null ? 999 : Number(a.place);
      const pb = b.place == null ? 999 : Number(b.place);
      if (pa !== pb) return pa - pb;
      return (a.post || 0) - (b.post || 0);
    });
    return list
      .map((h) => {
        const ml = h.ml != null ? h.ml : '—';
        return (
          '<tr>' +
          '<td class="col-post">' + esc(h.post != null ? h.post : '') + '</td>' +
          '<td class="col-name">' + esc(h.name || h.horse || '') + '</td>' +
          '<td class="col-ml">' + esc(ml) + '</td>' +
          placeCell(h.place) +
          '</tr>'
        );
      })
      .join('');
  }

  function raceCard(race) {
    const status = race.status || 'pending';
    const badge =
      status === 'official'
        ? '<span class="result-badge result-badge--ok">official</span>'
        : '<span class="result-badge result-badge--pending">pending</span>';
    const meta = [race.time, race.distance, race.purse].filter(Boolean).join(' · ');
    const hasPlace = (race.horses || []).some((h) => h.place != null);
    return (
      '<article class="result-card race-card--nested' + (hasPlace ? ' result-card--done' : '') + '">' +
      '<div class="result-card__header">' +
      '<span>' + esc(race.title || 'Race') + '</span>' + badge +
      '</div>' +
      (meta ? '<div class="result-card__title" style="font-weight:400;opacity:.75;font-size:0.85rem">' + esc(meta) + '</div>' : '') +
      '<div class="race-table-wrap"><table class="race-table">' +
      '<thead><tr><th class="col-post">№</th><th class="col-name">Лошадь</th><th class="col-ml">ML</th><th class="col-place">Место</th></tr></thead>' +
      '<tbody>' + horseRows(race.horses) + '</tbody></table></div></article>'
    );
  }

  function groupByTrack(races) {
    const map = new Map();
    races.forEach((r) => {
      const k = r.track || 'Track';
      if (!map.has(k)) map.set(k, []);
      map.get(k).push(r);
    });
    for (const list of map.values()) {
      list.sort((a, b) => {
        const na = parseInt(String(a.title || a.id || '').replace(/\D/g, ''), 10) || 0;
        const nb = parseInt(String(b.title || b.id || '').replace(/\D/g, ''), 10) || 0;
        return na - nb;
      });
    }
    // треки с местами выше
    return [...map.entries()].sort((a, b) => {
      const ap = a[1].some((r) => (r.horses || []).some((h) => h.place != null)) ? 0 : 1;
      const bp = b[1].some((r) => (r.horses || []).some((h) => h.place != null)) ? 0 : 1;
      if (ap !== bp) return ap - bp;
      return a[0].localeCompare(b[0], 'en');
    });
  }

  async function loadResults() {
    const board = document.getElementById('resultsBoard');
    const meta = document.getElementById('resultsMeta');
    if (!board) return;

    try {
      const res = await fetch('data/results.json?t=' + Date.now());
      if (!res.ok) throw new Error('results.json ' + res.status);
      const data = await res.json();
      const races = data.races || [];
      const withPlace = races.filter((r) => (r.horses || []).some((h) => h.place != null));

      if (meta) {
        const parts = [];
        if (data.date) parts.push('Дата: ' + data.date);
        parts.push(withPlace.length + ' с местами / ' + races.length);
        if (data.source) parts.push(data.source);
        meta.textContent = parts.join(' · ');
      }

      if (!races.length) {
        board.innerHTML = '<div class="loading-placeholder">Результатов пока нет</div>';
        return;
      }

      const groups = groupByTrack(races);
      board.innerHTML = groups.map(([track, list], idx) => {
        const open = idx === 0 ? ' is-open' : '';
        const done = list.filter((r) => (r.horses || []).some((h) => h.place != null)).length;
        return (
          '<div class="track-group' + open + '">' +
          '<button type="button" class="track-group__toggle" aria-expanded="' + (idx === 0) + '">' +
          '<span class="track-group__name">🏇 ' + esc(track) + '</span>' +
          '<span class="track-group__meta">' + done + '/' + list.length + ' official</span>' +
          '<span class="track-group__chevron" aria-hidden="true">▾</span></button>' +
          '<div class="track-group__body"><div class="track-group__races">' +
          list.map(raceCard).join('') +
          '</div></div></div>'
        );
      }).join('');

      board.querySelectorAll('.track-group__toggle').forEach((btn) => {
        btn.addEventListener('click', () => {
          const group = btn.closest('.track-group');
          if (!group) return;
          const open = group.classList.toggle('is-open');
          btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        });
      });
    } catch (err) {
      console.error(err);
      board.innerHTML = '<div class="loading-placeholder results-error">Не удалось загрузить результаты</div>';
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadResults);
  } else {
    loadResults();
  }
})();
