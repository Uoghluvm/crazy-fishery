"""Run: python test_mvp.py (uses the locally installed Playwright)."""
from pathlib import Path
from playwright.sync_api import sync_playwright
from ui_helpers import *


def check_game(page):
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(Path(__file__).with_name('mvp.html').as_uri())
    page.get_by_role('button', name='自由构筑', exact=True).click()
    cells = page.locator('.cell')
    assert cells.count() == 9
    assert page.locator('[data-cat="attack"] b').inner_text() == '70'
    cells.nth(4).focus()
    assert '灯塔' in page.locator('.status').inner_text()
    cells.nth(4).press('Enter')
    assert '灯塔' in cells.nth(4).get_attribute('aria-label'), 'Inspect must not delete'

    page.locator('#resetBtn').click()
    def place(building, index):
        page.locator('#buildBtn').click()
        page.locator('.tool[data-id="' + building + '"]').click()
        cell = cells.nth(index)
        box = cell.bounding_box()
        page.mouse.click(box['x']+box['width']/2, box['y']+box['height']/2)
        assert building == cell.get_attribute('data-building')
        assert not page.locator('#drawer').is_visible()
    place('ammo', 4)
    place('net', 1)
    page.keyboard.press('Escape')
    cells.nth(1).focus()
    assert '弹药架' not in page.locator('.status').inner_text(), 'Ammo must not buff resources'
    assert page.locator('[data-cat="resource"] b').inner_text() == '5'
    place('ballista', 3)
    place('beacon', 0)
    page.keyboard.press('Escape')
    cells.nth(3).focus()
    assert '弹药架 +5' in page.locator('.status').inner_text()
    assert '灯塔 ×1.5' in page.locator('.status').inner_text()
    assert '23' == cells.nth(3).locator('.val').inner_text()
    assert page.locator('.links line').count() == 2
    cells.nth(3).press('Delete')
    assert 'empty' in cells.nth(3).get_attribute('class')
    assert page.locator('[data-cat="attack"] b').inner_text() == '0'
    page.locator('#growBtn').click()
    assert cells.count() == 16
    page.locator('#growBtn').click()
    assert cells.count() == 25
    assert page.locator('#growBtn').is_disabled()
    assert page.locator('[data-cat="space"] b').inner_text() == '3/25'
    assert page.locator('.cell:not(.empty)').count() == 3
    page.emulate_media(reduced_motion='reduce')
    assert page.locator('.raft').evaluate("e=>getComputedStyle(e).animationName") == 'none'
    page.locator('#removeBtn').click()
    assert page.locator('#removeBtn').get_attribute('aria-pressed') == 'true'
    target=cells.nth(0)
    box=target.bounding_box()
    page.mouse.click(box['x']+box['width']/2,box['y']+box['height']/2)
    assert 'empty' in target.get_attribute('class')
    page.keyboard.press('Escape')
    assert page.locator('#removeBtn').get_attribute('aria-pressed') == 'false'
    page.locator('#buildBtn').click()
    page.locator('#soundBtn').click()
    assert page.locator('#soundBtn').get_attribute('aria-pressed') == 'false'
    page.keyboard.press('Escape')
    assert not errors, errors


def check_adventure(page):
    """Pinned chart #4242: day-1 tickets are fixed, so the opening numbers can be asserted exactly."""
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.emulate_media(reduced_motion='reduce')
    start_adventure(page, 4242)
    assert hud(page) == {'hp': 100, 'wood': 18}
    page.locator('#buildBtn').click()
    page.locator('.tool[data-id="ballista"]').click()
    page.locator('.cell').nth(5).focus()
    assert page.locator('.cell.ghost').count() == 1
    open_chart(page)
    body = page.locator('#journeyBody').inner_text()
    assert '攻击 30' in body and '海图 #4242' in body
    first = tickets(page)
    assert [(t['kind'], t['net']) for t in first] == [('fight', 10), ('elite', 22)], first
    assert '预计船损 10' in page.locator('.sail-row').first.get_attribute('aria-label')
    page.get_by_role('button', name='返回整备', exact=True).click()
    assert hud(page)['wood'] == 18  # a hover preview and a peek at the chart cost nothing
    build(page, 'ballista', 5)
    build(page, 'ballista', 7)
    assert page.locator('[data-cat="attack"] b').inner_text() == '60'
    assert hud(page)['wood'] == 2
    build(page, 'beacon', 2)  # unaffordable: no free building or negative balance
    assert 'empty' in page.locator('.cell').nth(2).get_attribute('class')
    assert hud(page)['wood'] == 2
    page.locator('#growBtn').click()
    assert page.locator('.cell').count() == 9
    open_chart(page)
    assert tickets(page)[0]['net'] == 5  # the extra firepower shows up in the forecast
    page.get_by_role('button', name='返回整备', exact=True).click()

    # Full five-day clear on the pinned chart with the adaptive build order.
    outcome = None
    for day in range(1, 6):
        assert page.evaluate('window.__ff.run.day') == day
        strengthen(page)
        open_chart(page)
        ts = tickets(page)
        pick = min([t for t in ts if not t['wreck']], key=lambda t: t['net'] or 0)
        if day == 5:
            assert pick['kind'] == 'boss' and len(ts) == 1
        page.locator('.sail-row[data-node="%s"]' % pick['node']).click()
        outcome = settle_stop(page)
        if day < 5:
            assert outcome in ('win', 'supply'), outcome
    assert outcome == 'victory'
    assert page.locator('#journeyTitle').inner_text() == '你驶出了深海！'
    assert hud(page)['hp'] > 0
    page.screenshot(path=str(Path(__file__).with_name('preview-victory.png')))
    page.get_by_role('button', name='再来一局', exact=True).click()
    assert hud(page) == {'hp': 100, 'wood': 18}
    assert page.evaluate('window.__ff.run.day') == 1
    # Full refund and zero-attack defeat.
    for index in [1, 3]:
        page.locator('.cell').nth(index).focus()
        page.locator('.cell').nth(index).press('Delete')
    assert hud(page)['wood'] == 34
    assert page.locator('[data-cat="attack"] b').inner_text() == '0'
    open_chart(page)
    assert all(t['wreck'] for t in tickets(page) if t['kind'] != 'supply'), tickets(page)
    page.locator('.sail-row').first.click()
    wait_for_dialog(page)
    assert page.locator('#journeyTitle').inner_text() == '木筏沉没了'
    page.get_by_role('button', name='再来一局', exact=True).click()
    # Restart, win day 1, then repair and paid expansion.
    open_chart(page)  # a fresh run draws a random chart, so don't assume which monsters day 1 holds
    page.locator('.sail-row.fight').first.click()
    # Skip the repair/wood cards: a repair card would top the hull back up and hide the damage we measure.
    assert settle_stop(page, loot=('relic', 'build')) == 'win'
    hp = hud(page)['hp']
    assert hp < 100
    wood = hud(page)['wood']
    page.locator('#repairBtn').click()
    assert hud(page) == {'hp': min(100, hp + 25), 'wood': wood - 10}
    while hud(page)['hp'] < 100 and not page.locator('#repairBtn').is_disabled():
        page.locator('#repairBtn').click()
    assert page.locator('#repairBtn').is_disabled()
    wood = hud(page)['wood']
    page.locator('#growBtn').click()
    assert page.locator('.cell').count() == 16
    assert hud(page)['wood'] == wood - 15
    assert not errors, errors


def check_combat_animation(page):
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    seen = None
    for mode in ['watch', 'skip', 'reduce_midway']:
        page.emulate_media(reduced_motion='no-preference')
        start_adventure(page, 4242)
        build(page, 'shield', 2)
        open_chart(page)
        page.locator('.sail-row.fight').first.click()
        assert page.locator('#battleView').is_visible()
        assert page.locator('.dock').evaluate('e=>e.inert')
        assert page.locator('.voyage-actions').evaluate('e=>e.inert')
        page.locator('.cell').nth(1).dispatch_event('contextmenu')
        assert 'empty' not in page.locator('.cell').nth(1).get_attribute('class')
        page.wait_for_function("document.querySelectorAll('.projectile').length>0")
        if mode == 'watch':
            page.wait_for_timeout(150)
            page.screenshot(path=str(Path(__file__).with_name('preview-combat-' + str(page.viewport_size['width']) + '.png')))
            page.wait_for_function("document.querySelectorAll('.shield-ring').length>0")
            page.wait_for_timeout(100)
            page.screenshot(path=str(Path(__file__).with_name('preview-shield-' + str(page.viewport_size['width']) + '.png')))
            enemy_left = page.locator('#enemy').bounding_box()['x']
            page.wait_for_function('(x)=>document.querySelector("#enemy").getBoundingClientRect().left < x-20', arg=enemy_left, timeout=3000)
        elif mode == 'skip':
            page.locator('#skipBattle').click()
        else:
            page.emulate_media(reduced_motion='reduce')
        wait_for_dialog(page, 10000)
        assert page.locator('#journeyTitle').inner_text() == '第 1 天 · 遭遇胜利'
        # All three ways of watching must settle to identical hull and wood.
        result = (hud(page)['hp'], hud(page)['wood'])
        if seen is None:
            seen = result
        assert result == seen, (mode, result, seen)
        assert page.locator('[data-combat]').count() == 0
        assert not page.locator('#battleView').is_visible()
        wood = hud(page)['wood']
        claim_loot(page, ('relic',))  # a relic changes no wood, so the next-day totals stay comparable
        next_day(page)
        page.wait_for_timeout(1100)  # Old round timers must not mutate the next day.
        assert '第 2 / 5 天' in page.locator('#voyageHud').inner_text()
        assert hud(page)['wood'] == wood
        assert not page.locator('.dock').evaluate('e=>e.inert')
    assert not errors, errors


def check_map_shop(page):
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.add_init_script('Math.random = () => 0')
    page.emulate_media(reduced_motion='reduce')
    start_adventure(page, 4242)
    page.locator('#shopBtn').click()
    assert '金币 ∞' in page.locator('.shop-banner').inner_text()
    page.locator('[data-buy="shield"]').click()
    page.get_by_role('button', name='十连', exact=True).click()
    assert page.locator('.recruit-card').count() == 10
    assert page.locator('.recruit-card.legendary').count() == 0
    page.get_by_role('button', name='十连', exact=True).click()
    assert page.locator('.recruit-card.legendary').count() == 1
    assert '弩炮 ×19' in page.locator('.stock').inner_text()
    assert '灯塔 ×1' in page.locator('.stock').inner_text()
    page.screenshot(path=str(Path(__file__).with_name('preview-recruit-' + str(page.viewport_size['width']) + '.png')))
    page.locator('#buyWood').click()
    assert hud(page)['wood'] == 118
    page.get_by_role('button', name='去建造', exact=True).click()
    page.locator('.tool[data-id="shield"]').click()
    page.locator('.cell').nth(2).focus()
    page.locator('.cell').nth(2).press('Enter')
    page.keyboard.press('Escape')
    assert hud(page)['wood'] == 118  # stocked shield is placed for free
    page.locator('#shopBtn').click()
    assert '护盾塔' not in page.locator('.stock').inner_text()
    page.get_by_role('button', name='返回海面', exact=True).click()

    # Day 1 chart: 11 nodes, exactly the two day-1 nodes are open, everything else is locked.
    open_chart(page)
    chart = '.chart .node'
    assert page.locator(chart).count() == 11
    assert page.locator(chart + '.open').count() == 2
    assert page.locator(chart + '.lock').count() == 9
    assert page.locator('.chart .edge.open').count() == 2
    assert page.locator('.sail-row').count() == 2
    page.screenshot(path=str(Path(__file__).with_name('preview-map-' + str(page.viewport_size['width']) + '.png')))
    # Hovering a ticket lights its node on the chart.
    row = page.locator('.sail-row').first
    row.hover()
    assert page.locator(chart + '.lit').count() == 1
    assert page.locator(chart + '.lit').get_attribute('data-id') == row.get_attribute('data-node')
    taken = row.get_attribute('data-node')
    row.click()
    assert settle_stop(page) == 'win'
    # Day 2: the node we sailed is on the trail, only its links are open, off-route nodes fade out.
    open_chart(page)
    assert page.locator(chart + '.here').count() == 1
    assert page.locator(chart + '.here').get_attribute('data-id') == taken
    links = page.evaluate('(id)=>window.__ff.NODE_MAP[id].links', taken)
    opened = page.locator(chart + '.open')
    assert sorted(opened.nth(i).get_attribute('data-id') for i in range(opened.count())) == sorted(links)
    assert page.locator('.sail-row').count() == len(links)
    assert page.locator(chart + '.dead').count() >= 1
    assert page.evaluate('window.__ff.routeNodes()') == [taken]
    # The chart only ever offers what is linked from where we are; nothing locked can be sailed.
    assert {t['node'] for t in tickets(page)} == set(links)
    assert not errors, errors


if __name__ == '__main__':
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width, height in [(1440, 900), (390, 844)]:
            page = browser.new_page(viewport={'width': width, 'height': height})
            check_game(page)
            page.locator('nav [data-preset="beacon"]').click()
            page.keyboard.press('Escape')
            page.mouse.move(0, 0)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(Path(__file__).with_name('preview-'+str(width)+'.png')))
            page.reload()
            page.emulate_media(reduced_motion='reduce')
            page.mouse.move(0,0)
            page.screenshot(path=str(Path(__file__).with_name('preview-start-'+str(width)+'.png')))
            page.close()
            print(f'PASS {width}x{height}: placement, removal, effects, expansion, reduced motion')
        page=browser.new_page(viewport={'width':390,'height':844})
        check_adventure(page)
        page.screenshot(path=str(Path(__file__).with_name('preview-adventure.png')))
        print('PASS adventure: 5-day victory, defeat, restart, refunds, costs, repair, paid expansion')
        for width,height in [(1440,900),(390,844)]:
            page=browser.new_page(viewport={'width':width,'height':height})
            check_combat_animation(page)
            page.close()
            print(f'PASS combat {width}: watched/skip/reduced-motion parity, input lock, timer cleanup')
        for width,height in [(1440,900),(390,844)]:
            page=browser.new_page(viewport={'width':width,'height':height})
            check_map_shop(page)
            page.close()
            print(f'PASS map/shop {width}: node locks, route history, pity, inventory, unlimited gold purchases')
        browser.close()
