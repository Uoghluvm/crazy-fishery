"""Run: python test_mvp.py (uses the locally installed Playwright)."""
from pathlib import Path
from playwright.sync_api import sync_playwright


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


def wood(page):
    return page.evaluate('window.__ff.run.wood')


def hp(page):
    return page.evaluate('window.__ff.run.hp')


def sail(page, want='fight'):
    """按航点类型挑航道：fight 跳过补给与事件，supply 专找补给点。

    海图是随机的，第 2~4 天可能摆着事件节点，所以不能"点第一张"，否则会打开事件弹窗。
    """
    page.locator('#sailBtn').click()
    rows = page.locator('.sail-row')
    for i in range(rows.count()):
        cls = rows.nth(i).get_attribute('class') or ''
        is_supply = 'supply' in cls
        is_stop = is_supply or 'event' in cls
        if want == 'supply' and is_supply:
            rows.nth(i).click()
            return
        if want != 'supply' and not is_stop:
            rows.nth(i).click()
            return
    rows.first.click()


def pick_loot(page):
    """三选一里挑非木材的一张，保持木材数量可断言。"""
    cards = page.locator('.loot-card')
    for i in range(cards.count()):
        if '木材' not in cards.nth(i).inner_text():
            cards.nth(i).click()
            return
    cards.first.click()


def take_reward(page):
    page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
    pick_loot(page)
    page.get_by_role('button', name='领取并整备下一天', exact=True).click()


def check_adventure(page):
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(Path(__file__).with_name('mvp.html').as_uri())
    page.emulate_media(reduced_motion='reduce')
    page.get_by_role('button', name='开始五日冒险', exact=True).click()
    assert wood(page) == 18
    assert page.locator('[data-cat="attack"] b').inner_text() == '30', '两座弩炮应吃到弹药架加成'
    page.locator('#buildBtn').click()
    page.locator('.tool[data-id="ballista"]').click()
    page.locator('.cell').nth(5).focus()
    assert page.locator('.cell.ghost').count() == 1, '悬停应给出放置预览'
    page.locator('#sailBtn').click()
    body = page.locator('#journeyBody').inner_text()
    assert '攻击 30' in body and '船损' in body, body
    assert page.locator('.sail-row').count() == 3, '第一天应有三张船票：巡游 / 险航 / 事件'
    page.get_by_role('button', name='返回整备', exact=True).click()
    page.keyboard.press('Escape')
    assert wood(page) == 18, '只是看航线不该花钱'

    def build(kind, index):
        page.locator('#buildBtn').click()
        page.locator('.tool[data-id="' + kind + '"]').click()
        page.locator('.cell').nth(index).focus()
        page.locator('.cell').nth(index).press('Enter')
        page.keyboard.press('Escape')

    build('ballista', 5)
    build('ballista', 7)
    assert page.locator('[data-cat="attack"] b').inner_text() == '60'
    assert wood(page) == 2
    build('beacon', 2)  # 14 木材买不起：既不能免费放置，也不能出现负余额
    assert 'empty' in page.locator('.cell').nth(2).get_attribute('class')
    assert wood(page) == 2
    page.locator('#growBtn').click()  # 扩建要 15 木材，仍应停在 3×3
    assert page.locator('.cell').count() == 9
    assert wood(page) == 2

    # 五日：固定走 1a→2b→3a→4a→5，全程战斗航点，结果可复现
    page.locator('#shopBtn').click()
    page.locator('#buyWood').click()
    page.get_by_role('button', name='返回海面', exact=True).click()
    assert wood(page) == 102, '测试金币换 100 木材'
    page.locator('#growBtn').click()
    assert page.locator('.cell').count() == 16
    for index in [2, 6, 8, 9, 10]:
        build('ballista', index)
    assert page.locator('[data-cat="attack"] b').inner_text() == '90'

    def heal():
        while hp(page) < 100 and wood(page) >= 10:
            page.locator('#repairBtn').click()

    for day in range(1, 6):
        heal()
        sail(page)
        page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
        if day == 5:
            assert page.locator('#journeyTitle').inner_text() == '你征服了「深海巨兽」！'
        else:
            assert '遭遇胜利' in page.locator('#journeyTitle').inner_text()
            take_reward(page)
            if day == 2:
                before_atk = int(page.locator('[data-cat="attack"] b').inner_text())
                for index in [12, 13]:
                    build('ballista', index)
                # 遗物是随机的，这里只断言"扩建后火力确实变强"
                assert int(page.locator('[data-cat="attack"] b').inner_text()) > before_atk
        assert hp(page) > 0, '每一战都要活着并进入下一天'
    page.screenshot(path=str(Path(__file__).with_name('preview-victory.png')))

    page.get_by_role('button', name='再来一局', exact=True).click()
    assert hp(page) == 100 and wood(page) == 18
    # 全额返还 + 零火力失败
    for index in [1, 3]:
        page.locator('.cell').nth(index).focus()
        page.locator('.cell').nth(index).press('Delete')
    assert wood(page) == 34, '拆除应全额返还 8+8'
    assert page.locator('[data-cat="attack"] b').inner_text() == '0'
    sail(page)
    page.wait_for_function("document.querySelector('#journey').open")
    assert page.locator('#journeyTitle').inner_text() == '木筏沉没了'

    # 修船与付费扩建（用第一战的真实损伤与回收）
    page.get_by_role('button', name='再来一局', exact=True).click()
    sail(page)
    page.wait_for_function("document.querySelector('#journey').open")
    assert hp(page) < 100, '第一战应造成船体损伤'
    take_reward(page)
    hp_now, wood_now = hp(page), wood(page)
    assert hp_now < 100
    page.locator('#repairBtn').click()
    assert hp(page) == min(100, hp_now + 25)
    assert wood(page) == wood_now - 10
    page.locator('#growBtn').click()
    assert page.locator('.cell').count() == 16
    assert wood(page) == wood_now - 25
    assert not errors, errors


def check_combat_animation(page):
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    results = []
    for mode in ['watch', 'skip', 'reduce_midway']:
        page.emulate_media(reduced_motion='no-preference')
        # 固定海图编号：三种观看方式必须打同一张图，否则随机海图会换成不同的敌人组合
        page.goto(Path(__file__).with_name('mvp.html').as_uri() + '?seed=4242')
        page.get_by_role('button', name='开始五日冒险', exact=True).click()
        page.locator('#buildBtn').click()
        page.locator('.tool[data-id="shield"]').click()
        page.locator('.cell').nth(2).focus()
        page.locator('.cell').nth(2).press('Enter')
        page.keyboard.press('Escape')
        sail(page)
        assert page.locator('#battleView').is_visible()
        assert page.locator('.dock').evaluate('e=>e.inert')
        assert page.locator('.voyage-actions').evaluate('e=>e.inert')
        page.locator('.cell').nth(1).dispatch_event('contextmenu')
        assert 'empty' not in page.locator('.cell').nth(1).get_attribute('class'), '战斗中不能改动木筏'
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
        page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
        assert page.locator('#journeyTitle').inner_text() == '第 1 天 · 遭遇胜利'
        assert page.locator('[data-combat]').count() == 0
        assert not page.locator('#battleView').is_visible()
        results.append((hp(page), wood(page)))
        take_reward(page)
        page.wait_for_timeout(1100)  # 旧轮次计时器不得改动下一天
        assert '第 2 / 5 天' in page.locator('#voyageHud').inner_text()
        assert wood(page) == results[-1][1], '领取非木材战利品后木材不应再变'
        assert not page.locator('.dock').evaluate('e=>e.inert')
    assert len(set(results)) == 1, ('三种观看方式的结果必须一致', results)
    assert results[0][1] > 8, '胜利应回收木材'
    assert not errors, errors


def check_map_shop(page):
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.emulate_media(reduced_motion='reduce')
    page.goto(Path(__file__).with_name('mvp.html').as_uri())
    page.get_by_role('button', name='开始五日冒险', exact=True).click()
    # 固定随机种子：前 19 抽都不出传奇，第 20 抽由保底触发
    page.evaluate('window.__ff.setSeed(4)')
    page.locator('#shopBtn').click()
    assert '金币 ∞' in page.locator('.shop-banner').inner_text(), '测试金币应标明无限且无真实支付'
    page.locator('[data-buy="shield"]').click()
    page.get_by_role('button', name='十连', exact=True).click()
    assert page.locator('.recruit-card').count() == 10
    assert page.locator('.recruit-card.legendary').count() == 0, '前 19 抽不应出传奇'
    page.get_by_role('button', name='十连', exact=True).click()
    assert page.locator('.recruit-card.legendary').count() == 1, '第 20 抽应触发保底'
    stock_before = page.evaluate('window.__ff.stock.shield')
    assert stock_before >= 1, '购买的护盾塔应进仓库'
    page.screenshot(path=str(Path(__file__).with_name('preview-recruit-' + str(page.viewport_size['width']) + '.png')))
    page.locator('#buyWood').click()
    assert wood(page) == 118, '测试金币换 100 木材'
    page.get_by_role('button', name='去建造', exact=True).click()
    page.locator('.tool[data-id="shield"]').click()
    page.locator('.cell').nth(2).focus()
    page.locator('.cell').nth(2).press('Enter')
    page.keyboard.press('Escape')
    assert wood(page) == 118, '库存建筑应免费放置'
    assert page.evaluate('window.__ff.stock.shield') == stock_before - 1, '放置后应从仓库扣除'
    page.locator('#sailBtn').click()
    assert page.locator('#chart .node').count() == 13, '航线图应画出全部航点'
    assert page.locator('#chart .node.open').count() == 3, '第一天有三个可选航点'
    assert page.locator('.sail-row').count() == 3, '每个可选航点一张船票'
    page.screenshot(path=str(Path(__file__).with_name('preview-map-' + str(page.viewport_size['width']) + '.png')))
    # 第 1 天固定有一处灯影，点第一张可能打开事件：这里要的是战斗票
    page.locator('.sail-row.fight, .sail-row.elite').first.click()
    page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
    take_reward(page)
    page.locator('#sailBtn').click()
    assert page.locator('#chart .node.here').count() == 1, '走过的航点应标为当前位置'
    assert page.locator('#chart .node.taken').count() == 0
    assert page.locator('#chart .trail').count() == 1, '应留下金色航迹'
    assert page.locator('#sailBtn').inner_text().startswith('航线图')
    assert not errors, errors


if __name__ == '__main__':
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width, height in [(1440, 900), (390, 844)]:
            page = browser.new_page(viewport={'width': width, 'height': height})
            check_game(page)
            page.locator('#buildBtn').click()
            page.locator('#presetRow [data-preset="beacon"]').click()
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
