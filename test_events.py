"""Run: py -3 test_events.py
M3 第一步：航线事件节点（取舍、不可重复领取）与停靠期间存档不被写坏。
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = Path(__file__).with_name('mvp.html').as_uri()
KEY = 'crazy-fishery.save.v1'


def wood(page):
    return page.evaluate('window.__ff.run.wood')


def hp(page):
    return page.evaluate('window.__ff.run.hp')


def stored(page):
    raw = page.evaluate('(k)=>localStorage.getItem(k)', KEY)
    return json.loads(raw) if raw else None


def box(page, index):
    b = page.locator('.cell').nth(index).bounding_box()
    return b['x'] + b['width'] / 2, b['y'] + b['height'] / 2


def tap(page, index):
    x, y = box(page, index)
    page.mouse.click(x, y)


def build(page, kind, index):
    page.locator('#buildBtn').click()
    page.locator('.tool[data-id="' + kind + '"]').click()
    page.locator('.cell').nth(index).focus()
    page.locator('.cell').nth(index).press('Enter')
    page.keyboard.press('Escape')


def open_route(page):
    page.locator('#sailBtn').click()
    page.wait_for_timeout(60)


def sail(page, want='fight'):
    """want: fight 跳过补给与事件；'supply' / 'event' 精确匹配。"""
    open_route(page)
    rows = page.locator('.sail-row')
    for i in range(rows.count()):
        cls = rows.nth(i).get_attribute('class') or ''
        if want == 'supply' and 'supply' in cls:
            rows.nth(i).click(); return
        if want == 'event' and 'event' in cls:
            rows.nth(i).click(); return
        if want == 'fight' and 'supply' not in cls and 'event' not in cls:
            rows.nth(i).click(); return
    raise AssertionError('没有匹配的航道：' + want)


def pick_loot(page):
    cards = page.locator('.loot-card')
    for i in range(cards.count()):
        if '木材' not in cards.nth(i).inner_text():
            cards.nth(i).click(); return
    cards.first.click()


def take_battle_reward(page):
    page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
    assert '胜利' in page.locator('#journeyTitle').inner_text()
    pick_loot(page)
    page.get_by_role('button', name='领取并整备下一天', exact=True).click()


def check_route_options(page):
    page.emulate_media(reduced_motion='reduce')
    page.goto(URL)
    page.get_by_role('button', name='开始五日冒险', exact=True).click()
    open_route(page)
    rows = page.locator('.sail-row')
    assert rows.count() == 3, '第一天应有三张船票：巡游 / 险航 / 事件'
    kinds = [rows.nth(i).get_attribute('class') for i in range(rows.count())]
    assert sum('event' in k for k in kinds) == 1, kinds
    assert page.locator('#chart .node').count() == 13, '航线图应画出 13 个航点'
    assert page.locator('#chart .node.event').count() == 2, '两个事件航点'
    assert page.locator('#chart .node.open').count() == 3, '第一天三个可选航点'
    assert '事件' in page.locator('.powers').inner_text(), '可选航道类型里应出现"事件"'
    page.screenshot(path=str(Path(__file__).with_name('preview-event-route-' + str(page.viewport_size['width']) + '.png')))


def check_lamp_event(page):
    page.emulate_media(reduced_motion='reduce')
    page.goto(URL)
    page.get_by_role('button', name='开始五日冒险', exact=True).click()
    sail(page, want='event')
    page.wait_for_function("document.querySelector('#journey').open")
    assert page.locator('#journeyTitle').inner_text() == '第 1 天 · 海雾里的灯影'
    assert page.locator('[data-event]').count() == 2, '事件应给出两个选项'
    assert page.locator('#journeyActions button').is_disabled(), '未做选择前不能起航'

    stock_before = dict(page.evaluate('window.__ff.stock'))
    hp_before = hp(page)
    page.locator('[data-event="follow"]').click()
    page.wait_for_timeout(80)
    gained = {k: v for k, v in page.evaluate('window.__ff.stock').items() if v > stock_before.get(k, 0)}
    assert len(gained) == 1, '循灯应恰好给一件建筑：' + str(gained)
    assert hp(page) == hp_before - 8, '代价是船体 −8'
    assert page.locator('[data-event="avoid"]').is_disabled(), '另一选项必须锁掉，不能两个都拿'
    assert '打捞' in page.locator('#journeyBody').inner_text() or '捞到' in page.locator('#journeyBody').inner_text()
    assert not page.locator('#journeyActions button').is_disabled(), '选完应解锁起航'

    # 停靠期间的存档必须仍是出航前的合法整备档，否则读档会判非法
    snap = stored(page)
    assert snap['run']['phase'] == 'build', '停靠暂停不落盘：' + str(snap['run']['phase'])
    assert snap['run']['route'] == [], '停靠中的航点不应写进存档'
    assert page.evaluate('(d)=>window.__ff.validSave(d)', snap) is True
    assert gained.popitem()[0] not in snap['stock'], '尚未起航，奖励不应进存档'

    page.get_by_role('button', name='继续航行', exact=True).click()
    snap = stored(page)
    assert snap['run']['day'] == 2 and snap['run']['phase'] == 'build'
    assert len(snap['run']['route']) == 1 and snap['run']['route'][0]['node'] == '1c'
    assert page.evaluate('(d)=>window.__ff.validSave(d)', snap) is True
    assert sum(snap['stock'].values()) == sum(stock_before.values()) + 1, '奖励应恰好进账一次'


def check_event_cannot_farm(page):
    """刷新回到停靠前，重挑一次不会累积两次奖励。"""
    page.emulate_media(reduced_motion='reduce')
    page.goto(URL)
    page.get_by_role('button', name='开始五日冒险', exact=True).click()
    sail(page, want='event')
    page.wait_for_function("document.querySelector('#journey').open")
    page.locator('[data-event="follow"]').click()
    page.wait_for_timeout(80)
    total_after_pick = sum(page.evaluate('window.__ff.stock').values())
    page.reload()
    page.wait_for_timeout(150)
    page.get_by_role('button', name='继续上次冒险 · 第 1 天', exact=True).click()
    sail(page, want='event')
    page.wait_for_function("document.querySelector('#journey').open")
    page.locator('[data-event="follow"]').click()
    page.wait_for_timeout(80)
    assert sum(page.evaluate('window.__ff.stock').values()) == total_after_pick, '重挑不应叠成两件'


def check_storm_event(page, choice, expect):
    """走到 4c 风暴前夜，验证两个选项的代价与收益。"""
    page.emulate_media(reduced_motion='reduce')
    page.goto(URL)
    page.get_by_role('button', name='开始五日冒险', exact=True).click()
    page.locator('#shopBtn').click()
    page.locator('#buyWood').click()
    page.get_by_role('button', name='返回海面', exact=True).click()
    page.locator('#growBtn').click()
    for index in [2, 6, 8, 9, 10]:
        build(page, 'ballista', index)

    for _ in range(3):
        while hp(page) < 100 and wood(page) >= 10:
            page.locator('#repairBtn').click()
        sail(page)
        take_battle_reward(page)

    while hp(page) < 100 and wood(page) >= 10:
        page.locator('#repairBtn').click()
    assert hp(page) == 100
    if expect == 'sink':
        page.evaluate('window.__ff.run.hp=6; window.__ff.paint();')
    hp_before, wood_before = hp(page), wood(page)
    sail(page, want='event')
    page.wait_for_function("document.querySelector('#journey').open")
    assert page.locator('#journeyTitle').inner_text() == '第 4 天 · 风暴前夜'
    page.screenshot(path=str(Path(__file__).with_name('preview-event-storm-' + str(page.viewport_size['width']) + '.png')))
    page.locator('[data-event="' + choice + '"]').click()
    page.wait_for_timeout(80)
    if choice == 'plunder':
        assert wood(page) == wood_before + 55
        assert hp(page) == max(1, hp_before - 14), '事件最多把船体压到 1，不会直接沉没'
    else:
        assert hp(page) == min(100, hp_before + 20)
        assert wood(page) == wood_before
    page.get_by_role('button', name='继续航行', exact=True).click()
    assert page.evaluate('window.__ff.run.day') == 5


def check_supply_save_not_corrupted(page):
    """停靠补给点同样不能写入自身校验不过的存档（旧版会丢进度）。"""
    page.emulate_media(reduced_motion='reduce')
    page.goto(URL)
    page.get_by_role('button', name='开始五日冒险', exact=True).click()
    sail(page)
    take_battle_reward(page)
    open_route(page)
    row = page.locator('.sail-row.supply')
    if row.count() == 0:
        page.get_by_role('button', name='返回整备', exact=True).click()
        return
    row.first.click()
    page.wait_for_timeout(100)
    snap = stored(page)
    assert snap['run']['phase'] == 'build'
    assert page.evaluate('(d)=>window.__ff.validSave(d)', snap) is True, '补给暂停的存档必须能读回'
    page.locator('[data-supply]').first.click()
    page.wait_for_timeout(80)
    snap = stored(page)
    assert page.evaluate('(d)=>window.__ff.validSave(d)', snap) is True
    page.reload()
    page.wait_for_timeout(200)
    assert page.get_by_role('button', name='继续上次冒险', exact=False).count() == 1, '读档不应被拒绝'


if __name__ == '__main__':
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width, height in [(1440, 900), (390, 844)]:
            page = browser.new_page(viewport={'width': width, 'height': height})
            errs = []
            page.on('pageerror', lambda e: errs.append(str(e)))
            check_route_options(page)
            check_lamp_event(page)
            check_event_cannot_farm(page)
            assert not errs, errs
            page.close()
            print(f'PASS event route/choice/save-pause {width}x{height}')
        page = browser.new_page(viewport={'width': 1200, 'height': 800})
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        check_storm_event(page, 'plunder', 'plunder')
        check_storm_event(page, 'mend', 'mend')
        check_supply_save_not_corrupted(page)
        assert not errs, errs
        print('PASS storm trade-off, hp floor, supply save not corrupted')
        browser.close()
