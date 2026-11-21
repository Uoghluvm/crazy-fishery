"""Run: python test_map_codex.py. Random sea chart + item codex.

与旧版的差别（疯狂渔场 → 疯狂水世界 v0.6 之后）：
- 海图改成 3/3/3/3/1 五层，节点里多出 kind:'event' 的航路事件（lamp / storm）；
  风暴只会出现在第 4 天，第 2~4 天至少有一处补给。
- 存档用 run.mapSeed 记编号（run.seed 仍是局内随机），校验时只看存档自己那张图。
- 建筑 18 种、宝藏 6 种；图鉴记录存在 crazy-fishery.codex.v1，不进冒险存档。
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from ui_helpers import *

LEGACY_IDS = '1a,1b,1c,2a,2b,2c,3a,3b,3c,4a,4b,4c,5'
BUILDING_TOTAL = 18
RELIC_TOTAL = 6


def start(page, query=''):
    seed = int(query.split('=')[1]) if query else None
    start_adventure(page, seed)


def check_map_structure(page):
    """1500 seeds: every generated chart must satisfy the structural guarantees."""
    bad = page.evaluate("""() => {
      const out = [];
      const sizes = [3, 3, 3, 3, 1];
      const sigs = new Set();
      for (let seed = 1; seed <= 1500; seed++) {
        const nodes = window.__ff.buildMap(seed);
        const again = window.__ff.buildMap(seed);
        if (JSON.stringify(nodes) !== JSON.stringify(again)) out.push([seed, 'not deterministic']);
        const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
        if (Object.keys(byId).length !== nodes.length) out.push([seed, 'duplicate ids']);
        for (let d = 1; d <= 5; d++) {
          if (nodes.filter(n => n.day === d).length !== sizes[d - 1]) out.push([seed, 'layer size ' + d]);
        }
        const incoming = new Set(nodes.flatMap(n => n.links));
        for (const n of nodes) {
          if (n.day < 5 && n.links.length === 0) out.push([seed, 'dead end ' + n.id]);
          if (n.day > 1 && !incoming.has(n.id)) out.push([seed, 'unreachable ' + n.id]);
          for (const to of n.links) {
            if (!byId[to] || byId[to].day !== n.day + 1) out.push([seed, 'bad link ' + n.id + '->' + to]);
          }
          if (new Set(n.links).size !== n.links.length) out.push([seed, 'dup link ' + n.id]);
          if (n.day === 5 && n.kind !== 'boss') out.push([seed, 'day 5 not boss']);
          if (n.day < 5 && n.kind === 'boss') out.push([seed, 'early boss']);
          // 事件节点：灯影在第 1~3 天、风暴固定在第 4 天
          if (n.kind === 'event') {
            if (!['lamp', 'storm'].includes(n.event)) out.push([seed, 'unknown event ' + n.event]);
            if (n.event === 'storm' && n.day !== 4) out.push([seed, 'storm outside day 4']);
            if (n.event === 'lamp' && n.day > 3) out.push([seed, 'lamp after day 3']);
          }
          if (n.kind !== 'event' && n.event) out.push([seed, 'stray event tag ' + n.id]);
          if (n.kind === 'supply' && n.day === 1) out.push([seed, 'supply on day 1']);
          // 第 1~3 天的每个节点都要连着一条要打的航道，不能被事件/补给堵死
          if (n.day <= 3 && !n.links.some(to => ['fight', 'elite'].includes(byId[to].kind))) {
            out.push([seed, 'no combat link from ' + n.id]);
          }
        }
        const events = nodes.filter(n => n.kind === 'event');
        if (events.filter(n => n.day === 1).length !== 1) out.push([seed, 'day 1 needs exactly one lamp']);
        if (events.filter(n => n.day === 4).length !== 1) out.push([seed, 'day 4 needs exactly one storm']);
        if (events.length < 2 || events.length > 4) out.push([seed, 'event count ' + events.length]);
        for (let d = 1; d <= 4; d++) {
          if (!nodes.some(n => n.day === d && n.kind === 'fight')) out.push([seed, 'no fight on day ' + d]);
        }
        if (!nodes.some(n => n.day >= 2 && n.day <= 4 && n.kind === 'supply')) out.push([seed, 'no supply']);
        // Every node must be reachable from day 1 and reach the boss.
        const reach = new Set(nodes.filter(n => n.day === 1).map(n => n.id));
        for (const n of nodes) if (reach.has(n.id)) n.links.forEach(t => reach.add(t));
        if (reach.size !== nodes.length) out.push([seed, 'not all reachable']);
        sigs.add(nodes.map(n => n.id + n.col + n.kind + n.links.join('')).join('|'));
      }
      if (sigs.size < 300) out.push(['variety', 'only ' + sigs.size + ' distinct charts in 1500 seeds']);
      return out.slice(0, 10);
    }""")
    assert not bad, bad


def check_events_covered(page):
    """Both event kinds must show up, and the fixed legacy chart must stay 13 nodes."""
    got = page.evaluate("""() => {
      const kinds = new Set();
      for (let seed = 1; seed <= 200; seed++) {
        for (const n of window.__ff.buildMap(seed)) {
          if (n.kind === 'event') kinds.add(n.event);
        }
      }
      return { kinds: [...kinds].sort(), legacy: window.__ff.buildMap(null).length };
    }""")
    assert got['kinds'] == ['lamp', 'storm'], got
    assert got['legacy'] == 13, got
    # 旧图：灯影在第 1 天、风暴在第 4 天；随机图不许把风暴挪走
    assert page.evaluate("window.__ff.buildMap(null).filter(n=>n.kind==='event').map(n=>n.event+n.day).join(',')") == 'lamp1,storm4'


def check_encounters(page):
    """Every day/elite pair must resolve to known monsters."""
    bad = page.evaluate("""() => {
      const out = [];
      const ff = window.__ff;
      for (let day = 1; day <= 5; day++) {
        for (const elite of [false, true]) {
          const foes = ff.encounter(day, elite);
          if (!foes.length || foes.some(id => !ff.MONSTERS[id])) out.push([day, elite, foes]);
        }
      }
      return out;
    }""")
    assert not bad, bad
    legacy = page.evaluate("window.__ff.encounter(1,false)")
    assert legacy == ['tentacle'], legacy


def check_seed_run(page, width):
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    start(page, '?seed=4242')
    save = page.evaluate('(k)=>JSON.parse(localStorage.getItem(k))', SAVE_KEY)
    assert save['run']['mapSeed'] == 4242, save['run']
    expected = page.evaluate('window.__ff.buildMap(4242).map(n=>n.id+n.kind+n.links.join(","))')
    actual = page.evaluate('window.__ff.MAP_NODES.map(n=>n.id+n.kind+n.links.join(","))')
    assert expected == actual
    page.locator('#sailBtn').click()
    assert '海图 #4242' in page.locator('#journeyBody').inner_text()
    page.screenshot(path=str(Path(__file__).with_name('preview-seedmap-%d.png' % width)))
    rows = page.locator('.sail-row')
    assert rows.count() == 3  # 第 1 天永远三张船票
    page.get_by_role('button', name='返回整备', exact=True).click()
    # A different explicit seed gives a different chart.
    page.evaluate("window.__ff.useMap(7)")
    other = page.evaluate('window.__ff.MAP_NODES.map(n=>n.id+n.kind+n.links.join(","))')
    assert other != expected
    assert not errors, errors


def check_resume_same_map(page):
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.emulate_media(reduced_motion='reduce')
    start(page, '?seed=31337')
    before = page.evaluate('window.__ff.MAP_NODES.map(n=>n.id+n.kind+n.links.join(","))')
    page.locator('#sailBtn').click()
    first = page.locator('.sail-row.fight, .sail-row.elite').first
    node = first.get_attribute('data-node')
    first.click()
    assert not page.locator('#journeyTitle').inner_text().startswith('第 1 天 · 漂流补给'), 'day 1 must not be a supply node'
    snap = page.evaluate('(k)=>JSON.parse(localStorage.getItem(k))', SAVE_KEY)
    assert snap['run']['route'][0]['node'] == node
    # Reload without ?seed: the chart must come from the save, not from a fresh draw.
    page.goto(URL)
    page.get_by_role('button').filter(has_text='继续上次冒险').click()
    after = page.evaluate('window.__ff.MAP_NODES.map(n=>n.id+n.kind+n.links.join(","))')
    assert after == before, (before, after)
    assert page.evaluate('window.__ff.run.mapSeed') == 31337
    assert page.locator('#journeyTitle').inner_text().endswith('遭遇胜利'), page.locator('#journeyTitle').inner_text()
    # Route validity is judged against the save's own chart: the same two-step route is
    # valid under the seed it was taken on, and invalid under a seed where those nodes are not linked.
    probe = page.evaluate("""() => {
      const ff = window.__ff, A = 31337;
      const chart = ff.buildMap(A);
      const a = chart.find(n => n.day === 1 && n.links.length);
      const b = a.links[0];
      for (let seed = 1; seed < 5000; seed++) {
        if (seed === A) continue;
        const other = ff.buildMap(seed).find(n => n.id === a.id);
        if (other && !other.links.includes(b)) return { a: a.id, b, other: seed };
      }
      return null;
    }""")
    assert probe, 'could not find a seed with a different link structure'
    forged = json.loads(json.dumps(snap))
    forged['run'].update({'day': 3, 'phase': 'build', 'hp': 80, 'mapSeed': 31337,
                          'route': [{'day': 1, 'node': probe['a']}, {'day': 2, 'node': probe['b']}]})
    forged['run'].pop('result', None)
    assert page.evaluate('(d)=>window.__ff.validSave(d)', forged), 'route valid on its own seed'
    forged['run']['mapSeed'] = probe['other']
    assert not page.evaluate('(d)=>window.__ff.validSave(d)', forged), 'same route must fail on a chart without that link'
    forged['run']['mapSeed'] = 31337
    for bad_seed in [0, -1, 1.5, 10 ** 7, 'x']:
        forged['run']['mapSeed'] = bad_seed
        assert not page.evaluate('(d)=>window.__ff.validSave(d)', forged), bad_seed
    assert not errors, errors


def check_legacy_save(page):
    """A save with no chart number (written before random charts) still loads on the fixed chart."""
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    start(page)
    snap = page.evaluate('(k)=>JSON.parse(localStorage.getItem(k))', SAVE_KEY)
    del snap['run']['mapSeed']
    snap['run'].pop('seed', None)
    page.evaluate('([k,raw])=>localStorage.setItem(k,raw)', [SAVE_KEY, json.dumps(snap)])
    page.reload()
    page.get_by_role('button').filter(has_text='继续上次冒险').click()
    assert page.evaluate('window.__ff.MAP_NODES.length') == 13
    assert page.evaluate('window.__ff.MAP_NODES.map(n=>n.id).join(",")') == LEGACY_IDS
    page.locator('#sailBtn').click()
    assert page.locator('.sail-row').count() == 3
    assert '海图 #' not in page.locator('#journeyBody').inner_text()
    assert not errors, errors


def check_codex(page, width):
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(URL)
    page.evaluate('(k)=>localStorage.removeItem(k)', CODEX_KEY)
    page.reload()
    # The codex is reachable from the welcome flow and from free build.
    page.get_by_role('button', name='自由构筑', exact=True).click()
    page.locator('#codexBtn').click()
    assert page.locator('#codex').is_visible()
    assert page.locator('.codex-card').count() == BUILDING_TOTAL
    assert '建筑 0 / %d' % BUILDING_TOTAL in page.locator('#codexProgress').inner_text()
    page.get_by_role('button', name='关闭', exact=True).click()
    assert not page.locator('#codex').is_visible()

    page.locator('#helpBtn').click()
    page.get_by_role('button', name='开始五日冒险', exact=True).click()
    page.locator('#codexBtn').click()
    # Starting layout is ballista x2 + ammo + net: collected and marked as held.
    assert '建筑 3 / %d' % BUILDING_TOTAL in page.locator('#codexProgress').inner_text()
    ballista = page.locator('[data-codex="ballista"]')
    assert 'own' in ballista.get_attribute('class')
    assert '本局持有 2' in ballista.inner_text()
    assert 'locked' in page.locator('[data-codex="beacon"]').get_attribute('class')
    assert '未收集' in page.locator('[data-codex="beacon"]').inner_text()
    # The effect line must match the real building data, not a hand-written copy.
    assert '上下左右相邻 · +5' in page.locator('[data-codex="ammo"]').inner_text()
    assert '同一行 · 同行×1.5' in page.locator('[data-codex="trawl"]').inner_text()
    assert '周围 3×3 · +2' in page.locator('[data-codex="coral"]').inner_text()
    page.screenshot(path=str(Path(__file__).with_name('preview-codex-%d.png' % width)))

    # Relics stay hidden until earned.
    page.get_by_role('button', name='宝藏', exact=True).click()
    assert page.locator('.codex-card.locked').count() == RELIC_TOTAL
    assert '破浪撞角' not in page.locator('#codexGrid').inner_text()
    page.get_by_role('button', name='关闭', exact=True).click()

    # Winning a relic and a stocked building unlocks them, and the record survives a new run + reload.
    page.evaluate("""() => {
      const ff = window.__ff;
      ff.applyReward('relic:ram');
      ff.applyReward('build:tidemark');
      ff.paint();
    }""")
    page.locator('#codexBtn').click()
    assert '建筑 4 / %d' % BUILDING_TOTAL in page.locator('#codexProgress').inner_text()
    assert '库存 1' in page.locator('[data-codex="tidemark"]').inner_text()
    page.get_by_role('button', name='宝藏', exact=True).click()
    assert '破浪撞角' in page.locator('#codexGrid').inner_text()
    assert page.locator('.codex-card.locked').count() == RELIC_TOTAL - 1
    page.screenshot(path=str(Path(__file__).with_name('preview-codex-relic-%d.png' % width)))
    page.get_by_role('button', name='关闭', exact=True).click()
    page.reload()
    page.get_by_role('button', name='开始五日冒险', exact=True).click()
    page.locator('#codexBtn').click()
    assert '宝藏 1 / %d' % RELIC_TOTAL in page.locator('#codexProgress').inner_text()
    assert 'seen' in page.locator('[data-codex="tidemark"]').get_attribute('class') or \
        'own' in page.locator('[data-codex="tidemark"]').get_attribute('class')
    assert '本局持有' not in page.locator('[data-codex="tidemark"]').inner_text()  # new run has no stock
    page.get_by_role('button', name='宝藏', exact=True).click()
    assert '本局持有' not in page.locator('[data-codex="ram"]').inner_text()
    assert '已获得' in page.locator('[data-codex="ram"]').inner_text()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.get_by_role('button', name='关闭', exact=True).click()

    # A corrupted record must not break the page, and unknown ids are dropped.
    page.evaluate('([k,v])=>localStorage.setItem(k,v)', [CODEX_KEY, json.dumps({'b': ['ballista', 'nope'], 'r': ['ram', 7]})])
    page.reload()
    page.get_by_role('button', name='自由构筑', exact=True).click()
    page.locator('#codexBtn').click()
    assert '建筑 1 / %d · 宝藏 1 / %d' % (BUILDING_TOTAL, RELIC_TOTAL) in page.locator('#codexProgress').inner_text()
    page.get_by_role('button', name='关闭', exact=True).click()
    page.evaluate('([k,v])=>localStorage.setItem(k,v)', [CODEX_KEY, '{broken'])
    page.reload()
    page.get_by_role('button', name='自由构筑', exact=True).click()
    page.locator('#codexBtn').click()
    assert '建筑 0 / %d' % BUILDING_TOTAL in page.locator('#codexProgress').inner_text()
    assert not errors, errors


def check_codex_blocked_during_battle(page):
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.emulate_media(reduced_motion='no-preference')
    start(page, '?seed=4242')
    page.locator('#sailBtn').click()
    page.locator('.sail-row.fight, .sail-row.elite').first.click()
    assert page.locator('#battleView').is_visible()
    # The action bar is inert during combat, so the codex cannot be opened mid-fight.
    assert page.locator('.voyage-actions').evaluate('e=>e.inert')
    page.evaluate("document.querySelector('#codexBtn').click()")
    assert not page.locator('#codex').is_visible()
    page.locator('#skipBattle').click()
    assert not errors, errors


def check_full_playthrough(page):
    """Click through all five days on several charts, taking whatever the first open ticket is."""
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.emulate_media(reduced_motion='reduce')
    for seed in [1, 77, 4242, 31337, 999999]:
        start(page, '?seed=%d' % seed)
        # Plenty of firepower so the walk is about the chart, not about balance.
        page.evaluate("() => { window.__ff.run.relics = Array(12).fill('ram'); window.__ff.run.hp = 100; }")
        for day in range(1, 6):
            assert page.evaluate('window.__ff.run.day') == day, (seed, day)
            # The walk checks chart traversal, not balance: loot is random, so keep the hull full.
            page.evaluate("() => { window.__ff.run.hp = 100; }")
            page.locator('#sailBtn').click()
            page.locator('.sail-row').first.click()
            if page.locator('[data-supply]').count():
                page.locator('[data-supply="wood"]').click()
                page.get_by_role('button', name='继续航行', exact=True).click()
            elif page.locator('[data-event]').count():
                page.locator('[data-event]').first.click()
                page.get_by_role('button', name='继续航行', exact=True).click()
            elif day < 5:
                assert '遭遇胜利' in page.locator('#journeyTitle').inner_text(), (seed, day, page.locator('#journeyTitle').inner_text())
                page.locator('[data-loot]').first.click()
                page.get_by_role('button', name='领取并整备下一天', exact=True).click()
            else:
                title = page.locator('#journeyTitle').inner_text()
                assert title.startswith('你征服了'), (seed, title)
        route = page.evaluate('window.__ff.run.route.map(r=>r.node)')
        assert len(route) == 5 and route[-1] == '5', (seed, route)
        chart = {n['id']: n for n in page.evaluate('window.__ff.MAP_NODES')}
        for a, b in zip(route, route[1:]):
            assert b in chart[a]['links'], (seed, route)
    # The fixed old chart always had the same three day-1 kinds; random charts must vary them.
    firsts = page.evaluate("""() => {
      const out = new Set();
      for (let seed = 1; seed <= 60; seed++) {
        const day1 = window.__ff.buildMap(seed).filter(n => n.day === 1);
        out.add(day1.map(n => n.kind).sort().join('+'));
      }
      return out.size;
    }""")
    assert firsts >= 2, firsts
    assert not errors, errors


if __name__ == '__main__':
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        page.goto(URL)
        check_map_structure(page)
        check_events_covered(page)
        check_encounters(page)
        page.close()
        print('PASS map generator: 1500 seeds deterministic, connected, boss last, supply and events in place')
        page = browser.new_page(viewport={'width': 390, 'height': 844})
        check_full_playthrough(page)
        page.close()
        print('PASS playthrough: 5 seeded charts cleared day 1 to boss through the UI, routes follow chart links')
        for width, height in [(1440, 900), (390, 844)]:
            page = browser.new_page(viewport={'width': width, 'height': height})
            check_seed_run(page, width)
            page.close()
            page = browser.new_page(viewport={'width': width, 'height': height})
            check_codex(page, width)
            page.close()
            print('PASS %d: seeded run + chart, codex collect/lock/persist/corrupt' % width)
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        check_resume_same_map(page)
        page.close()
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        check_legacy_save(page)
        page.close()
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        check_codex_blocked_during_battle(page)
        page.close()
        print('PASS saves: resume keeps the same chart, forged/invalid seeds rejected, seedless legacy save loads')
        browser.close()
