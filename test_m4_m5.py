"""Run: py -3 test_m4_m5.py
M4 反馈：按建筑类别区分的开火表现、Boss 预警、减少动态效果下的替代路径。
M5 工程项：诊断信息/版本入口、四档视口兼容、帧率参考采样。
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = Path(__file__).with_name('mvp.html').as_uri()


def start(page):
    page.goto(URL)
    page.get_by_role('button', name='开始五日冒险', exact=True).click()


def build(page, kind, index):
    page.locator('#buildBtn').click()
    page.locator('.tool[data-id="' + kind + '"]').click()
    page.locator('.cell').nth(index).focus()
    page.locator('.cell').nth(index).press('Enter')
    page.keyboard.press('Escape')


def check_category_feedback(page):
    """攻击建筑发射弹丸，资源建筑冒水花，技能/奇妙建筑亮一下——三类不再共用一种表现。"""
    page.emulate_media(reduced_motion='no-preference')
    start(page)
    build(page, 'net', 2)
    page.locator('#sailBtn').click()
    page.locator('.sail-row').first.click()
    page.wait_for_function("document.querySelectorAll('.projectile').length>0", timeout=8000)
    page.wait_for_timeout(120)
    seen = page.evaluate("""()=>({
      shots: document.querySelectorAll('.projectile').length,
      splashes: document.querySelectorAll('.particle.water').length
    })""")
    assert seen['shots'] > 0, '攻击建筑应发射弹丸'
    assert seen['splashes'] > 0, ('资源建筑应有产出反馈', seen)
    page.locator('#skipBattle').click()
    page.wait_for_function("document.querySelector('#journey').open", timeout=10000)


def check_boss_warning(page):
    """第五天进战斗时要有明确的巨兽预警，且战斗结束能恢复。"""
    page.emulate_media(reduced_motion='no-preference')
    start(page)
    page.evaluate("""()=>{
      const r=window.__ff.run;
      r.route.push({day:1,node:'1a'},{day:2,node:'2b'},{day:3,node:'3a'},{day:4,node:'4a'});
      r.day=5; r.hp=100; window.__ff.paint();
    }""")
    page.locator('#sailBtn').click()
    rows = page.locator('.sail-row')
    assert rows.count() == 1, '第四天后只剩 Boss 航点'
    rows.first.click()
    page.wait_for_function("document.body.classList.contains('boss-battle')", timeout=8000)
    text = page.locator('#battleRound').inner_text()
    assert '巨兽' in text, ('Boss 出场要有预警文案', text)
    page.locator('#skipBattle').click()
    page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
    assert not page.evaluate("document.body.classList.contains('boss-battle')"), '战斗结束应清掉 Boss 状态'


def check_reduced_motion_path(page):
    """减少动态效果时不应残留弹丸/水花，结算照常。"""
    page.emulate_media(reduced_motion='reduce')
    start(page)
    build(page, 'net', 2)
    page.locator('#sailBtn').click()
    page.locator('.sail-row').first.click()
    page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
    assert page.locator('[data-combat]').count() == 0
    assert page.locator('.particle').count() == 0


def check_diagnostics(page):
    page.goto(URL)
    page.get_by_role('button', name='诊断信息', exact=True).click()
    page.wait_for_selector('.diag')
    text = page.locator('.diag').inner_text()
    assert 'MVP v0.6' in text, text
    assert '布局' in text and '视口' in text, text
    assert '手绘 SVG' in page.locator('#journeyBody').inner_text(), '素材来源要写在可追溯的位置'
    page.get_by_role('button', name='返回', exact=True).click()
    assert page.get_by_role('button', name='开始五日冒险', exact=True).count() == 1


def check_seed_repro(page):
    """同一随机种子必须复现同一组战利品；种子要能随存档恢复，才谈得上复现问题。"""
    start(page)
    a = page.evaluate("()=>{window.__ff.setSeed(12345); return window.__ff.rewardOptions();}")
    b = page.evaluate("()=>{window.__ff.setSeed(12345); return window.__ff.rewardOptions();}")
    assert a == b, ('同种子应得到同一组战利品', a, b)
    page.evaluate("()=>window.__ff.setSeed(4242)")
    page.locator('#buildBtn').click()
    page.locator('.tool[data-id="harpoon"]').click()
    page.locator('.cell').nth(8).focus()
    page.locator('.cell').nth(8).press('Enter')
    page.keyboard.press('Escape')
    page.reload()
    page.get_by_role('button', name='继续上次冒险', exact=False).first.click()
    assert page.evaluate('window.__ff.seed') == 4242, '读档应恢复随机种子'


def check_viewports(browser):
    """四档常用分辨率：不出现横向滚动，关键按钮都在视口内。"""
    for width, height in [(1024, 768), (1280, 800), (1440, 900), (1920, 1080)]:
        page = browser.new_page(viewport={'width': width, 'height': height})
        page.emulate_media(reduced_motion='reduce')
        start(page)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), (width, '存在横向溢出')
        for sel in ['#sailBtn', '#buildBtn', '#moveBtn', '#undoBtn', '#growBtn']:
            box = page.locator(sel).bounding_box()
            assert box and box['x'] >= 0 and box['x'] + box['width'] <= width + 1, (width, sel, box)
        # 抽屉在 5×5 时可以滚动，不遮挡按钮
        page.locator('#growBtn').click()
        page.locator('#growBtn').click()
        page.locator('#buildBtn').click()
        drawer = page.locator('#drawer').bounding_box()
        assert drawer and drawer['y'] >= 0 and drawer['y'] + drawer['height'] <= height + 1, (width, drawer)
        page.close()
        print(f'  viewport {width}x{height} OK')


def sample_fps(page):
    """参考采样：只记录数值，不做硬断言——无头环境不代表真机。"""
    page.emulate_media(reduced_motion='no-preference')
    start(page)
    for index in [2, 6, 8]:
        build(page, 'ballista', index)
    fps = page.evaluate("""()=>new Promise(res=>{
      const times=[]; let last=performance.now();
      const tick=now=>{ times.push(now-last); last=now; if(times.length<90) requestAnimationFrame(tick); else {
        const avg=times.slice(10).reduce((a,b)=>a+b,0)/(times.length-10);
        res(Math.round(1000/avg));
      }};
      requestAnimationFrame(tick);
    })""")
    return fps


if __name__ == '__main__':
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width, height in [(1440, 900), (390, 844)]:
            page = browser.new_page(viewport={'width': width, 'height': height})
            errs = []
            page.on('pageerror', lambda e: errs.append(str(e)))
            check_category_feedback(page)
            check_boss_warning(page)
            check_reduced_motion_path(page)
            check_diagnostics(page)
            check_seed_repro(page)
            assert not errs, errs
            page.close()
            print(f'PASS category feedback / boss warning / reduced motion / diagnostics {width}x{height}')
        check_viewports(browser)
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        fps = sample_fps(page)
        page.close()
        print(f'PERF reference fps (headless, 3 buildings): {fps}')
        browser.close()
