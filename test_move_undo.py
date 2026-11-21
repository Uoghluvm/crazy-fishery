"""Run: py -3 test_move_undo.py
M2 验收：移动/交换、单步撤销、跨版本迁移、多窗口冲突。
不依赖右键：移动与撤销都有可见按钮；拖拽同时覆盖指针与触屏事件。
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = Path(__file__).with_name('mvp.html').as_uri()
KEY = 'crazy-fishery.save.v1'


def layout(page):
    return page.evaluate("[...document.querySelectorAll('.cell')].map(c=>c.dataset.building||'.')")


def box(page, index):
    b = page.locator('.cell').nth(index).bounding_box()
    return b['x'] + b['width'] / 2, b['y'] + b['height'] / 2


def tap(page, index):
    x, y = box(page, index)
    page.mouse.click(x, y)


def drag(page, src, dst):
    x0, y0 = box(page, src)
    x1, y1 = box(page, dst)
    page.mouse.move(x0, y0)
    page.mouse.down()
    page.mouse.move(x0 + 40, y0 + 25, steps=5)
    page.mouse.move(x1, y1, steps=8)
    page.mouse.up()
    page.wait_for_timeout(60)


def wood(page):
    return page.evaluate('window.__ff.run.wood')


def depth(page):
    return page.evaluate('window.__ff.undoDepth')


def start_adventure(page):
    page.goto(URL)
    page.get_by_role('button', name='开始五日冒险', exact=True).click()


def check_move(page):
    start_adventure(page)
    base = layout(page)
    assert base[:5] == ['net', 'ballista', '.', 'ballista', 'ammo'], base
    start_wood, start_depth = wood(page), depth(page)
    assert start_depth == 0, '开局不应携带撤销记录'
    assert page.locator('#undoBtn').is_disabled()

    # 拖动到空格：建筑换位，木材与建筑数量不变
    drag(page, 0, 2)
    assert layout(page)[:3] == ['.', 'ballista', 'net'], layout(page)
    assert wood(page) == start_wood, '移动不得改变木材'
    assert depth(page) == 1

    # 拖动到已占格：交换而非覆盖
    drag(page, 1, 2)
    now = layout(page)
    assert now[:3] == ['.', 'net', 'ballista'], now
    assert wood(page) == start_wood
    assert depth(page) == 2

    # 撤销交换 → 再撤销移动
    page.locator('#undoBtn').click()
    assert layout(page)[:3] == ['.', 'ballista', 'net'], layout(page)
    page.locator('#undoBtn').click()
    assert layout(page)[:5] == base[:5], layout(page)
    assert page.locator('#undoBtn').is_disabled(), '撤到底后按钮应禁用'

    # 点击式移动（触屏备选路径），Esc 取消拿起
    page.locator('#moveBtn').click()
    assert page.locator('#moveBtn').get_attribute('aria-pressed') == 'true'
    tap(page, 1)
    assert '已拿起' in page.locator('#announcement').inner_text()
    page.keyboard.press('Escape')
    assert '放回原处' in page.locator('#announcement').inner_text()
    assert layout(page)[1] == 'ballista', 'Esc 不应移走建筑'
    tap(page, 1)
    tap(page, 8)
    assert layout(page)[8] == 'ballista' and layout(page)[1] == '.', layout(page)
    assert wood(page) == start_wood
    page.locator('#moveBtn').click()
    assert page.locator('#moveBtn').get_attribute('aria-pressed') == 'false'

    # 触屏指针事件：不依赖鼠标也能拖动
    x0, y0 = box(page, 3)
    x1, y1 = box(page, 5)
    page.evaluate(
        """([x0,y0,x1,y1])=>{
            const at=(x,y)=>document.elementFromPoint(x,y);
            const fire=(t,x,y)=>at(x,y).dispatchEvent(new PointerEvent(t,{bubbles:true,cancelable:true,pointerId:7,pointerType:'touch',isPrimary:true,clientX:x,clientY:y,button:0}));
            const el=at(x0,y0);
            el.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,cancelable:true,pointerId:7,pointerType:'touch',isPrimary:true,clientX:x0,clientY:y0,button:0}));
            window.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,cancelable:true,pointerId:7,pointerType:'touch',isPrimary:true,clientX:x0+50,clientY:y0+30,button:0}));
            window.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,cancelable:true,pointerId:7,pointerType:'touch',isPrimary:true,clientX:x1,clientY:y1,button:0}));
            window.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,cancelable:true,pointerId:7,pointerType:'touch',isPrimary:true,clientX:x1,clientY:y1,button:0}));
        }""", [x0, y0, x1, y1])
    page.wait_for_timeout(60)
    assert layout(page)[5] == 'ballista' and layout(page)[3] == '.', layout(page)


def check_undo(page):
    start_adventure(page)
    start_wood = wood(page)

    # 放置 → 撤销：木材回到原点
    page.locator('#buildBtn').click()
    page.locator('.tool[data-id="harpoon"]').click()
    tap(page, 8)
    assert wood(page) == start_wood - 5, wood(page)
    page.keyboard.press('Control+z')
    assert layout(page)[8] == '.', '撤销放置后格子应为空'
    assert wood(page) == start_wood

    # 拆除 → 撤销：建筑与返还的木材一起回来
    page.locator('#removeBtn').click()
    tap(page, 1)
    assert layout(page)[1] == '.' and wood(page) == start_wood + 8
    page.locator('#undoBtn').click()
    assert layout(page)[1] == 'ballista'
    assert wood(page) == start_wood
    page.keyboard.press('Escape')

    # 扩建 → 撤销：回到 3×3，木材退回，建筑保留
    page.locator('#growBtn').click()
    assert page.locator('.cell').count() == 16
    assert wood(page) == start_wood - 15
    page.locator('#undoBtn').click()
    assert page.locator('.cell').count() == 9
    assert wood(page) == start_wood
    assert layout(page)[:5] == ['net', 'ballista', '.', 'ballista', 'ammo'], layout(page)

    # 修船 → 撤销：船体与木材同时回退
    page.evaluate('window.__ff.run.hp=60; window.__ff.paint();')
    page.locator('#repairBtn').click()
    assert page.evaluate('window.__ff.run.hp') == 85
    page.locator('#undoBtn').click()
    assert page.evaluate('window.__ff.run.hp') == 60
    assert wood(page) == start_wood

    # 库存放置 → 撤销：库存回到仓库
    page.locator('#shopBtn').click()
    page.locator('[data-buy="ballista"]').click()
    page.get_by_role('button', name='返回海面', exact=True).click()
    assert page.evaluate('window.__ff.stock.ballista') == 1
    page.locator('#buildBtn').click()
    page.locator('.tool[data-id="ballista"]').click()
    tap(page, 7)
    assert page.evaluate('window.__ff.stock.ballista') == 0
    assert wood(page) == start_wood, '库存放置不应扣木材'
    page.locator('#undoBtn').click()
    assert page.evaluate('window.__ff.stock.ballista') == 1
    assert layout(page)[7] == '.', layout(page)

    # 空动作不产生撤销记录：按钮禁用，键盘撤销只提示不报错
    before = depth(page)
    assert page.locator('#undoBtn').is_disabled()
    page.keyboard.press('Control+z')
    assert depth(page) == before, '没有记录时点撤销不应报错或吞掉历史'
    assert '没有可撤销' in page.locator('#announcement').inner_text()


def check_reward_not_undoable(page):
    page.emulate_media(reduced_motion='reduce')
    start_adventure(page)
    page.locator('#sailBtn').click()
    # 第 1 天可能摆着灯影事件，按种类点战斗票才拿得到战报
    page.locator('.sail-row.fight, .sail-row.elite').first.click()
    page.wait_for_function("document.querySelector('#journeyTitle').textContent.includes('遭遇胜利')")
    assert page.locator('#undoBtn').is_disabled(), '结算阶段不能撤销'
    assert depth(page) == 0
    page.locator('.loot-card').first.click()
    wood_after_loot = wood(page)
    page.get_by_role('button', name='领取并整备下一天', exact=True).click()
    assert page.evaluate('window.__ff.run.day') == 2
    assert depth(page) == 0, '进入新一天必须清空撤销栈'
    assert page.locator('#undoBtn').is_disabled()
    page.keyboard.press('Control+z')
    assert wood(page) == wood_after_loot, '撤销不得倒退已领取的战斗奖励'
    assert page.evaluate('window.__ff.run.day') == 2


def check_migration(page):
    start_adventure(page)
    raw = json.loads(page.evaluate('(k)=>localStorage.getItem(k)', KEY))
    assert raw['version'] == 2 and isinstance(raw.get('savedAt'), int)
    legacy = dict(raw)
    legacy['version'] = 1
    legacy.pop('savedAt', None)
    page.evaluate('([k,v])=>localStorage.setItem(k,v)', [KEY, json.dumps(legacy)])
    page.reload()
    assert page.evaluate('(k)=>JSON.parse(localStorage.getItem(k)).version', KEY) == 2, '旧存档应被就地升级'
    page.get_by_role('button', name='继续上次冒险 · 第 1 天', exact=True).click()
    assert page.evaluate('window.__ff.run.day') == 1
    assert page.locator('.cell').count() == 9
    # 未来版本必须拒绝而不是误读
    future = dict(raw)
    future['version'] = 99
    page.evaluate('([k,v])=>localStorage.setItem(k,v)', [KEY, json.dumps(future)])
    page.reload()
    assert page.get_by_role('button', name='继续上次冒险', exact=False).count() == 0
    assert '存档不可读取' in page.locator('#journeyBody').inner_text()


def check_multi_window(browser):
    ctx = browser.new_context(viewport={'width': 1200, 'height': 800})
    a = ctx.new_page()
    errors = []
    a.on('pageerror', lambda e: errors.append('A:' + str(e)))
    start_adventure(a)
    b = ctx.new_page()
    b.on('pageerror', lambda e: errors.append('B:' + str(e)))
    b.goto(URL)
    assert b.get_by_role('button', name='继续上次冒险', exact=False).count() == 1

    # 另一窗口整备后，停在欢迎页的页面同步到新进度
    drag(a, 0, 2)
    b.wait_for_timeout(250)
    assert '同步' in b.locator('#announcement').inner_text()
    assert '继续上次冒险 · 第 1 天' in b.locator('#journeyActions').inner_text()

    b.get_by_role('button', name='继续上次冒险 · 第 1 天', exact=True).click()
    b.wait_for_timeout(120)

    # 两页进度分叉：后者只提示，不静默覆盖
    b.locator('#buildBtn').click()
    b.locator('.tool[data-id="harpoon"]').click()
    tap(b, 8)
    b.keyboard.press('Escape')
    a.wait_for_timeout(250)
    assert '另一个窗口保存了不同进度' in a.locator('#announcement').inner_text()
    assert '另一窗口有不同进度' in a.locator('#voyageHud').inner_text()
    assert layout(a)[8] == '.', '被覆盖了就说明冲突处理失败'

    # 玩家可以显式载入另一窗口的进度
    a.locator('#helpBtn').click()
    a.get_by_role('button', name='载入另一窗口 · 第 1 天（放弃本页）', exact=True).click()
    a.wait_for_timeout(120)
    assert layout(a)[8] == 'harpoon', layout(a)
    assert '另一窗口' not in a.locator('#voyageHud').inner_text()
    assert not errors, errors
    ctx.close()


if __name__ == '__main__':
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width, height in [(1440, 900), (390, 844)]:
            page = browser.new_page(viewport={'width': width, 'height': height})
            page.emulate_media(reduced_motion='reduce')
            errs = []
            page.on('pageerror', lambda e: errs.append(str(e)))
            check_move(page)
            check_undo(page)
            check_reward_not_undoable(page)
            check_migration(page)
            assert not errs, errs
            page.close()
            print(f'PASS move/swap/undo/migration {width}x{height}')
        page = browser.new_page(viewport={'width': 1200, 'height': 800})
        page.emulate_media(reduced_motion='reduce')
        check_multi_window(browser)
        page.close()
        print('PASS multi-window sync and conflict (no silent overwrite)')
        browser.close()
