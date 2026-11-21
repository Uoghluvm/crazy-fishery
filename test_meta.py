"""Run: py -3 test_meta.py
章节 / 等级 / 升级解锁武器：锁定、难度、经验、章节推进。
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = Path(__file__).with_name('mvp.html').as_uri()


def new_page(browser, w=1200, h=800):
    page = browser.new_page(viewport={'width': w, 'height': h})
    page.emulate_media(reduced_motion='reduce')
    page.errors = []
    page.on('pageerror', lambda e: page.errors.append(str(e)))
    return page


def start(page):
    page.goto(URL)
    page.get_by_role('button', name='开始五日冒险', exact=True).click()


def build(page, kind, index):
    page.locator('#buildBtn').click()
    page.locator('.tool[data-id="' + kind + '"]').click()
    page.locator('.cell').nth(index).focus()
    page.locator('.cell').nth(index).press('Enter')
    page.keyboard.press('Escape')


def wood(page):
    return page.evaluate('window.__ff.run.wood')


def check_default_and_locked(page):
    page.goto(URL)
    m = page.evaluate('window.__ff.meta')
    assert m['level'] == 1 and m['chapter'] == 1 and m['highest'] == 1, m
    assert 'Lv 1' in page.locator('#journeyBody').inner_text()
    # 第二章 chip 未解锁
    assert page.locator('.ch-chip[data-ch="2"]').is_disabled()
    start(page)
    page.locator('#buildBtn').click()
    # 三把进阶武器都应带锁
    for wid in ['chain', 'mortar', 'doom']:
        tool = page.locator('.tool[data-id="' + wid + '"]')
        assert 'locked' in (tool.get_attribute('class') or ''), wid + ' 应锁定'
        assert 'Lv' in tool.locator('.cost').inner_text()
    # 点击锁定武器不应选中
    page.locator('.tool[data-id="chain"]').click()
    assert page.evaluate('window.__ff.run') and page.locator('.tool[data-id="chain"]').get_attribute('aria-pressed') == 'false'
    assert not page.errors, page.errors


def check_level_unlock(page):
    start(page)
    page.evaluate('window.__ff.setLevel(2)')
    page.locator('#buildBtn').click()
    assert 'locked' not in (page.locator('.tool[data-id="chain"]').get_attribute('class') or ''), 'Lv2 应解锁链式弩'
    assert 'locked' in (page.locator('.tool[data-id="mortar"]').get_attribute('class') or ''), '震爆炮仍需 Lv3'
    assert page.locator('.tool[data-id="chain"] .cost').inner_text() == '11 木'
    page.keyboard.press('Escape')          # 关掉抽屉，再走标准建造流程
    # 解锁后能真的放下去
    build(page, 'chain', 2)
    assert page.locator('.cell').nth(2).get_attribute('data-building') == 'chain'
    assert not page.errors, page.errors


def check_chapter_difficulty(page):
    start(page)
    d1 = page.evaluate('window.__ff.forecast(true).damage')
    page.evaluate('window.__ff.setChapter(2)')
    d2 = page.evaluate('window.__ff.forecast(true).damage')
    assert d2 > d1, ('第二章应更难', d1, d2)


def check_xp_on_victory(page):
    page.evaluate('window.__ff.resetMeta()')
    start(page)
    page.locator('#sailBtn').click()
    page.locator('.sail-row').first.click()
    page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
    assert page.evaluate('window.__ff.meta.xp') == 10, ('普通胜利应 +10 经验', page.evaluate('window.__ff.meta.xp'))
    if page.locator('.loot-card').count():
        page.locator('.loot-card').first.click()
    page.get_by_role('button', name='领取并整备下一天', exact=True).click()
    # 经验持久化
    page.reload()
    page.get_by_role('button', name='继续上次冒险', exact=False).first.click()
    assert page.evaluate('window.__ff.meta.xp') == 10
    assert not page.errors, page.errors


def check_boss_clears_chapter(page):
    page.evaluate('window.__ff.resetMeta()')
    start(page)
    # 攒出足够火力，然后直达 Boss
    page.locator('#shopBtn').click()
    page.locator('#buyWood').click()
    page.locator('#buyWood').click()
    page.get_by_role('button', name='返回海面', exact=True).click()
    page.locator('#growBtn').click()
    page.locator('#growBtn').click()
    for index in [2, 6, 8, 9, 10, 12, 13, 14]:
        build(page, 'ballista', index)
    page.evaluate("""()=>{
      const r=window.__ff.run;
      r.route.push({day:1,node:'1a'},{day:2,node:'2b'},{day:3,node:'3a'},{day:4,node:'4a'});
      r.day=5; r.hp=100; window.__ff.paint();
    }""")
    page.locator('#sailBtn').click()
    assert page.locator('.sail-row').count() == 1, '只剩 Boss 航点'
    page.locator('.sail-row').first.click()
    page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
    title = page.locator('#journeyTitle').inner_text()
    assert '征服' in title and '深海巨兽' in title, title
    assert page.evaluate('window.__ff.meta.highest') == 2, '通关应解锁第二章'
    assert page.evaluate('window.__ff.meta.level') >= 2, '通关应升级到至少 Lv2'
    assert page.get_by_role('button', name='进入第 2 章', exact=True).count() == 1
    # 进入第二章：章节数更新、难度更高
    page.get_by_role('button', name='进入第 2 章', exact=True).click()
    assert page.evaluate('window.__ff.meta.chapter') == 2
    assert page.evaluate('window.__ff.run.chapter') == 2
    assert not page.errors, page.errors


if __name__ == '__main__':
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = new_page(browser)
        check_default_and_locked(page)
        print('PASS default meta + locked weapons')
        check_level_unlock(page)
        print('PASS level unlock + place')
        check_chapter_difficulty(page)
        print('PASS chapter difficulty scaling')
        check_xp_on_victory(page)
        print('PASS xp on victory + persistence')
        check_boss_clears_chapter(page)
        print('PASS boss clears chapter + next chapter')
        browser.close()
