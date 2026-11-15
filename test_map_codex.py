"""Run: python test_map_codex.py. Random sea chart + item codex."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = Path(__file__).with_name('mvp.html').as_uri()
SAVE_KEY = 'crazy-fishery.save.v1'
CODEX_KEY = 'crazy-fishery.codex.v1'


def start(page, query=''):
    page.goto(URL + query)
    page.get_by_role('button', name='开始五日冒险', exact=True).click()


def check_map_structure(page):
    """1500 seeds: every generated chart must satisfy the structural guarantees."""
    bad = page.evaluate("""() => {
      const out = [];
      const sizes = [2, 3, 3, 2, 1];
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
        }
        for (let d = 1; d <= 4; d++) {
          if (!nodes.some(n => n.day === d && n.kind === 'fight')) out.push([seed, 'no fight on day ' + d]);
        }
        if (!nodes.some(n => (n.day === 2 || n.day === 3) && n.kind === 'supply')) out.push([seed, 'no supply']);
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


def check_encounters(page):
    """Variants must always resolve to known monsters and a finite forecast."""
    bad = page.evaluate("""() => {
      const out = [];
      const ff = window.__ff;
      for (let day = 1; day <= 5; day++) {
        for (const elite of [false, true]) {
          for (let variant = 0; variant < 4; variant++) {
            const foes = ff.encounter(day, elite, { variant });
            if (!foes.length || foes.some(id => !ff.MONSTERS[id])) out.push([day, elite, variant, foes]);
          }
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
    assert save['run']['seed'] == 4242, save['run']
    expected = page.evaluate('window.__ff.buildMap(4242).map(n=>n.id+n.kind+n.links.join(","))')
    actual = page.evaluate('window.__ff.MAP_NODES.map(n=>n.id+n.kind+n.links.join(","))')
    assert expected == actual
    page.locator('#sailBtn').click()
    assert '海图 #4242' in page.locator('#journeyBody').inner_text()
    page.screenshot(path=str(Path(__file__).with_name('preview-seedmap-%d.png' % width)))
    rows = page.locator('.sail-row')
    assert rows.count() == 2  # day 1 always offers two charts
    page.get_by_role('button', name='返回整备', exact=True).click()
    # A different explicit seed gives a different chart; a plain restart draws a fresh seed.
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
    first = page.locator('.sail-row').first
    node = first.get_attribute('data-node')
    first.click()
    if page.locator('#journeyTitle').inner_text().startswith('第 1 天 · 漂流补给'):
        raise AssertionError('day 1 must not be a supply node')
    snap = page.evaluate('(k)=>JSON.parse(localStorage.getItem(k))', SAVE_KEY)
    assert snap['run']['route'][0]['node'] == node
    # Reload without ?seed: the chart must come from the save, not from a fresh draw.
    page.goto(URL)
    page.get_by_role('button').filter(has_text='继续上次冒险').click()
    after = page.evaluate('window.__ff.MAP_NODES.map(n=>n.id+n.kind+n.links.join(","))')
    assert after == before, (before, after)
    assert page.evaluate('window.__ff.run.seed') == 31337
    assert page.locator('#journeyTitle').inner_text().endswith('遭遇胜利'), page.locator('#journeyTitle').inner_text()
    # Route validity is judged against the save's own seeded chart: the same two-step route is
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
    forged['run'].update({'day': 3, 'phase': 'build', 'hp': 80, 'seed': 31337,
                          'route': [{'day': 1, 'node': probe['a']}, {'day': 2, 'node': probe['b']}]})
    forged['run'].pop('result', None)
    assert page.evaluate('(d)=>window.__ff.validSave(d)', forged), 'route valid on its own seed'
    forged['run']['seed'] = probe['other']
    assert not page.evaluate('(d)=>window.__ff.validSave(d)', forged), 'same route must fail on a chart without that link'
    forged['run']['seed'] = 31337
    for bad_seed in [0, -1, 1.5, 10 ** 7, 'x']:
        forged['run']['seed'] = bad_seed
        assert not page.evaluate('(d)=>window.__ff.validSave(d)', forged), bad_seed
    assert not errors, errors


def check_legacy_save(page):
    """A save with no seed (written before random charts) still loads on the fixed chart."""
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    start(page)
    snap = page.evaluate('(k)=>JSON.parse(localStorage.getItem(k))', SAVE_KEY)
    del snap['run']['seed']
    page.evaluate('([k,raw])=>localStorage.setItem(k,raw)', [SAVE_KEY, json.dumps(snap)])
    page.reload()
    page.get_by_role('button').filter(has_text='继续上次冒险').click()
    assert page.evaluate('window.__ff.MAP_NODES.length') == 11
    assert page.evaluate('window.__ff.MAP_NODES.map(n=>n.id).join(",")') == '1a,1b,2a,2b,2c,3a,3b,3c,4a,4b,5'
    page.locator('#sailBtn').click()
    assert page.locator('.sail-row').count() == 2
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
    assert page.locator('.codex-card').count() == 14
    assert '建筑 0 / 14' in page.locator('#codexProgress').inner_text()
    page.get_by_role('button', name='关闭', exact=True).click()
    assert not page.locator('#codex').is_visible()

    page.locator('#helpBtn').click()
    page.get_by_role('button', name='开始五日冒险', exact=True).click()
    page.locator('#codexBtn').click()
    # Starting layout is ballista x2 + ammo + net: collected and marked as held.
    assert '建筑 3 / 14' in page.locator('#codexProgress').inner_text()
    ballista = page.locator('[data-codex="ballista"]')
    assert 'own' in ballista.get_attribute('class')
    assert '本局持有 2' in ballista.inner_text()
    assert 'locked' in page.locator('[data-codex="beacon"]').get_attribute('class')
    assert '未收集' in page.locator('[data-codex="beacon"]').inner_text()
    # The effect line must match the real building data, not a hand-written copy.
    assert '上下左右相邻 · +5' in page.locator('[data-codex="ammo"]').inner_text()
    assert '同一行 · 同行×1.5' in page.locator('[data-codex="trawl"]').inner_text()
    page.screenshot(path=str(Path(__file__).with_name('preview-codex-%d.png' % width)))

    # Relics stay hidden until earned.
    page.get_by_role('button', name='宝藏', exact=True).click()
    assert page.locator('.codex-card.locked').count() == 6
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
    assert '建筑 4 / 14' in page.locator('#codexProgress').inner_text()
    assert '库存 1' in page.locator('[data-codex="tidemark"]').inner_text()
    page.get_by_role('button', name='宝藏', exact=True).click()
    assert '破浪撞角' in page.locator('#codexGrid').inner_text()
    assert page.locator('.codex-card.locked').count() == 5
    page.screenshot(path=str(Path(__file__).with_name('preview-codex-relic-%d.png' % width)))
    page.get_by_role('button', name='关闭', exact=True).click()
    page.reload()
    page.get_by_role('button', name='开始五日冒险', exact=True).click()
    page.locator('#codexBtn').click()
    assert '宝藏 1 / 6' in page.locator('#codexProgress').inner_text()
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
    assert '建筑 1 / 14 · 宝藏 1 / 6' in page.locator('#codexProgress').inner_text()
    page.get_by_role('button', name='关闭', exact=True).click()
    page.evaluate('([k,v])=>localStorage.setItem(k,v)', [CODEX_KEY, '{broken'])
    page.reload()
    page.get_by_role('button', name='自由构筑', exact=True).click()
    page.locator('#codexBtn').click()
    assert '建筑 0 / 14' in page.locator('#codexProgress').inner_text()
    assert not errors, errors


def check_codex_blocked_during_battle(page):
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.emulate_media(reduced_motion='no-preference')
    start(page, '?seed=4242')
    page.locator('#sailBtn').click()
    page.locator('.sail-row').first.click()
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
            row = page.locator('.sail-row').first
            row.click()
            if page.locator('[data-supply]').count():
                page.locator('[data-supply="wood"]').click()
                page.get_by_role('button', name='继续航行', exact=True).click()
            elif day < 5:
                assert '遭遇胜利' in page.locator('#journeyTitle').inner_text(), (seed, day, page.locator('#journeyTitle').inner_text())
                page.locator('[data-loot]').first.click()
                page.get_by_role('button', name='领取并整备下一天', exact=True).click()
            else:
                assert page.locator('#journeyTitle').inner_text() == '你驶出了深海！', (seed, page.locator('#journeyTitle').inner_text())
        route = page.evaluate('window.__ff.run.route.map(r=>r.node)')
        assert len(route) == 5 and route[-1] == '5', (seed, route)
        chart = {n['id']: n for n in page.evaluate('window.__ff.MAP_NODES')}
        for a, b in zip(route, route[1:]):
            assert b in chart[a]['links'], (seed, route)
    # The fixed old chart always put the same monsters on day 1; random charts must vary them.
    firsts = page.evaluate("""() => {
      const out = new Set();
      for (let seed = 1; seed <= 60; seed++) {
        for (const n of window.__ff.buildMap(seed)) {
          if (n.day === 1) out.add(n.kind + ':' + window.__ff.encounter(1, n.kind === 'elite', n).join('+'));
        }
      }
      return out.size;
    }""")
    assert firsts >= 3, firsts
    assert not errors, errors


if __name__ == '__main__':
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        page.goto(URL)
        check_map_structure(page)
        check_encounters(page)
        page.close()
        print('PASS map generator: 1500 seeds deterministic, connected, no dead ends, boss last, supply present; encounters valid')
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
