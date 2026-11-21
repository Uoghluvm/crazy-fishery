"""Run: py -3 test_explore.py
对抗性测试：故意做"不合规矩"的操作，检查状态机、经济、存档与 DOM 是否仍然自洽。
任何一条 assertion 失败都代表一个真实缺陷，不是测试写法问题。
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

# 这些用例断言的是精确数值与流程，用 ?chart=legacy 固定成原来那张 13 节点海图；
# 随机海图的行为由 test_map_codex.py 覆盖。
URL = Path(__file__).with_name('mvp.html').as_uri() + '?chart=legacy'
KEY = 'crazy-fishery.save.v1'


# ---------- 通用工具 ----------
def new_page(browser, w=1200, h=800):
    page = browser.new_page(viewport={'width': w, 'height': h})
    page.emulate_media(reduced_motion='reduce')
    page.errors = []
    page.on('pageerror', lambda e: page.errors.append(str(e)))
    return page


def cells(page):
    return page.evaluate("[...document.querySelectorAll('.cell')].map(c=>c.dataset.building||'.')")


def state(page):
    return page.evaluate("""()=>{
      const r=window.__ff.run;
      return r?{day:r.day,hp:r.hp,wood:r.wood,phase:r.phase,route:r.route.length,
                result:r.result?{kind:r.result.kind||'battle',before:r.result.before,picked:r.result.picked||null}:null}:null;
    }""")


def assert_invariants(page, label):
    st = state(page)
    if st:
        assert 0 <= st['wood'] <= 1e9, (label, '木材越界', st)
        assert 0 <= st['hp'] <= 100, (label, '船体越界', st)
        assert st['phase'] in ('build', 'result', 'battle'), (label, '阶段非法', st)
        assert st['route'] <= st['day'] + 1, (label, '航线长度超过天数', st)
    lay = cells(page)
    n = len(lay)
    assert n in (9, 16, 25), (label, '甲板格数异常', n)
    used = sum(1 for c in lay if c != '.')
    assert used <= n, (label, '建筑数量超过格子', used, n)
    raw = page.evaluate('(k)=>localStorage.getItem(k)', KEY)
    if raw:
        d = json.loads(raw)
        assert page.evaluate('(x)=>window.__ff.validSave(x)', d) is True, (label, '存档自身校验不过', d.get('version'))
    assert not page.errors, (label, '页面报错', page.errors)


def start(page, w=1200, h=800):
    page.goto(URL)
    page.get_by_role('button', name='开始五日冒险', exact=True).click()


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


def sail(page, want='fight'):
    page.locator('#sailBtn').click()
    rows = page.locator('.sail-row')
    for i in range(rows.count()):
        cls = rows.nth(i).get_attribute('class') or ''
        if want == 'supply' and 'supply' in cls:
            rows.nth(i).click(); return
        if want == 'event' and 'event' in cls:
            rows.nth(i).click(); return
        if want == 'fight' and 'supply' not in cls and 'event' not in cls:
            rows.nth(i).click(); return
    raise AssertionError('没有匹配的航道')


# ---------- 场景 ----------
def s01_double_click_route(page):
    """连点航线图与船票：不能连开两场战斗，也不能重复推航线。"""
    start(page)
    before = state(page)
    page.locator('#sailBtn').click()
    row = page.locator('.sail-row').first
    row.click()
    assert page.locator('#sailBtn').is_disabled(), '战斗开始后航线按钮必须禁用，防止连开两场'
    page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
    after = state(page)
    assert after['route'] == 1, ('航线只应记录一次', after)
    assert after['phase'] == 'result'
    assert_invariants(page, 's01')


def s02_spam_clicks_empty(page):
    """空甲板狂点、右键、Delete：不能凭空造建筑，也不能报错。"""
    start(page)
    before = cells(page)
    for index in [5, 6, 7, 8]:
        x, y = box(page, index)
        page.mouse.click(x, y)
        page.mouse.click(x, y, button='right')
        page.locator('.cell').nth(index).focus()
        page.locator('.cell').nth(index).press('Delete')
    assert cells(page) == before, ('空操作改动了甲板', cells(page), before)
    assert_invariants(page, 's02')


def s03_drag_outside(page):
    """把建筑拖到甲板外：应放回，建筑不能丢。"""
    start(page)
    before = cells(page)
    x, y = box(page, 1)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 40, y + 30, steps=4)
    page.mouse.move(4, 4, steps=6)
    page.mouse.up()
    assert cells(page) == before, ('拖出界后建筑丢了', cells(page), before)
    assert_invariants(page, 's03')


def s04_drag_in_remove_mode(page):
    """拆除模式下拖拽：不应触发移动，只按点击拆除处理。"""
    start(page)
    before = cells(page)
    page.locator('#removeBtn').click()
    x, y = box(page, 1)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 50, y + 30, steps=5)
    page.mouse.move(x + 60, y + 40, steps=3)
    page.mouse.up()
    page.keyboard.press('Escape')
    after = cells(page)
    removed = sum(1 for a, b in zip(before, after) if a != b and b == '.')
    assert removed <= 1, ('拆除模式拖拽拆了多座', before, after)
    assert_invariants(page, 's04')


def s05_undo_during_dialog(page):
    """结算对话框打开时按 Ctrl+Z：不得倒退已领奖励，也不得把界面卡死。"""
    start(page)
    sail(page)
    page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
    st = state(page)
    page.keyboard.press('Control+z')
    page.keyboard.press('Control+z')
    assert state(page)['hp'] == st['hp'], '对话框打开时撤销改动了船体'
    page.locator('.loot-card').first.click()
    page.get_by_role('button', name='领取并整备下一天', exact=True).click()
    assert state(page)['day'] == 2
    assert_invariants(page, 's05')


def s06_resize_mid_battle(page):
    """战斗中改窗口尺寸：格子重建后战斗仍要继续，不能白屏或报错。"""
    page.emulate_media(reduced_motion='no-preference')
    start(page)
    build(page, 'shield', 2)
    page.locator('#sailBtn').click()
    page.locator('.sail-row').first.click()
    page.wait_for_function("document.querySelectorAll('.projectile').length>0", timeout=8000)
    page.set_viewport_size({'width': 900, 'height': 700})
    page.set_viewport_size({'width': 390, 'height': 844})
    page.locator('#skipBattle').click()
    page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
    assert page.locator('.cell').count() == 9
    assert_invariants(page, 's06')


def s07_expand_undo_roundtrip(page):
    """扩建→在新增格放建筑→撤销扩建：不能留下越界建筑。"""
    start(page)
    page.locator('#shopBtn').click()
    page.locator('#buyWood').click()
    page.get_by_role('button', name='返回海面', exact=True).click()
    page.locator('#growBtn').click()
    assert page.locator('.cell').count() == 16
    build(page, 'ballista', 15)      # 只有 4×4 才有的角落
    assert cells(page)[15] == 'ballista'
    page.locator('#undoBtn').click()  # 撤销的是"放置"
    assert cells(page)[15] == '.'
    page.locator('#undoBtn').click()  # 撤销扩建
    assert page.locator('.cell').count() == 9, '撤销扩建后应回到 3×3'
    assert_invariants(page, 's07')


def s08_zero_wood(page):
    """把木材花到 0：扩建/修船/建造都应被拦住，不能出现负木材。"""
    start(page)
    # 18 木材：买两座弩炮花 16，剩 2
    build(page, 'ballista', 5)
    build(page, 'ballista', 7)
    assert state(page)['wood'] == 2
    build(page, 'beacon', 8)          # 14 木材，买不起
    assert cells(page)[8] == '.', '木材不足却放下了建筑'
    page.locator('#growBtn').click()  # 15 木材，买不起
    assert page.locator('.cell').count() == 9
    assert page.locator('#repairBtn').is_disabled(), '木材不足时修船按钮必须禁用'
    assert state(page)['wood'] == 2, '木材不足却扣了钱'
    assert state(page)['wood'] >= 0
    assert_invariants(page, 's08')


def s09_full_board(page):
    """铺满 5×5 再操作：不应崩溃，扩建按钮应禁用。"""
    start(page)
    page.locator('#shopBtn').click()
    page.locator('#buyWood').click()
    page.locator('#buyWood').click()          # 铺满 25 座需要更多木材
    page.get_by_role('button', name='返回海面', exact=True).click()
    page.locator('#growBtn').click()
    page.locator('#growBtn').click()
    assert page.locator('.cell').count() == 25
    assert page.locator('#growBtn').is_disabled(), '满级后扩建应禁用'
    for index in range(25):
        page.locator('#buildBtn').click()
        page.locator('.tool[data-id="harpoon"]').click()
        page.locator('.cell').nth(index).focus()
        page.locator('.cell').nth(index).press('Enter')
        page.keyboard.press('Escape')
    assert sum(1 for c in cells(page) if c != '.') == 25, '应铺满 25 格'
    assert_invariants(page, 's09')
    page.locator('#sailBtn').click()
    page.locator('.sail-row').first.click()
    page.wait_for_function("document.querySelector('#journey').open", timeout=15000)
    assert_invariants(page, 's09-sail')


def s10_save_quota_and_reload(page):
    """存档被写坏后重载：必须保留原数据、给出提示，而不是白屏。"""
    start(page)
    page.evaluate("(k)=>localStorage.setItem(k,'{\"version\":2,\"run\":null}')", KEY)
    page.reload()
    assert '存档不可读取' in page.locator('#journeyBody').inner_text()
    assert page.evaluate('(k)=>localStorage.getItem(k)', KEY) == '{"version":2,"run":null}'
    assert not page.errors


def s11_keyboard_only(page):
    """纯键盘：Tab 到格子、Enter 放置、Delete 拆除、Ctrl+Z 撤销。"""
    start(page)
    page.locator('#buildBtn').click()
    page.locator('.tool[data-id="harpoon"]').click()
    page.locator('.cell').nth(8).focus()
    page.locator('.cell').nth(8).press('Enter')
    assert cells(page)[8] == 'harpoon'
    page.keyboard.press('Escape')
    page.locator('.cell').nth(8).focus()
    page.locator('.cell').nth(8).press('Delete')
    assert cells(page)[8] == '.'
    page.locator('body').click(position={'x': 5, 'y': 5})
    page.keyboard.press('Control+z')
    assert cells(page)[8] == 'harpoon', '键盘撤销没恢复'
    assert_invariants(page, 's11')


def s12_no_dom_leak(page):
    """连续三场战斗后，战斗临时节点必须清干净（防止长局越来越卡）。"""
    page.emulate_media(reduced_motion='no-preference')
    start(page)
    base = page.evaluate('document.querySelectorAll("*").length')
    for _ in range(3):
        sail(page)      # 只走战斗航点，补给/事件不产生弹丸
        page.wait_for_function("document.querySelectorAll('.projectile').length>0", timeout=8000)
        page.locator('#skipBattle').click()
        page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
        if page.locator('.loot-card').count():
            page.locator('.loot-card').first.click()
        page.get_by_role('button', name='领取并整备下一天', exact=True).click()
        page.wait_for_timeout(400)
    page.wait_for_timeout(600)
    left = page.evaluate("""()=>({
      combat: document.querySelectorAll('[data-combat]').length,
      particles: document.querySelectorAll('.particle').length,
      floats: document.querySelectorAll('.float').length,
      nodes: document.querySelectorAll('*').length
    })""")
    assert left['combat'] == 0 and left['particles'] == 0 and left['floats'] == 0, ('战斗残留节点', left)
    assert left['nodes'] < base * 3, ('DOM 节点增长过多，可能泄漏', base, left['nodes'])


def s13_narrow_screen(page):
    """320px 极窄屏：不能横向溢出，底部按钮必须可点。"""
    page.set_viewport_size({'width': 320, 'height': 640})
    start(page)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), '320px 出现横向滚动'
    for sel in ['#sailBtn', '#buildBtn', '#moveBtn', '#undoBtn', '#growBtn', '#shopBtn']:
        b = page.locator(sel).bounding_box()
        assert b and b['x'] >= 0 and b['x'] + b['width'] <= 321, (sel, b)
    page.locator('#buildBtn').click()
    drawer = page.locator('#drawer').bounding_box()
    assert drawer and drawer['y'] >= 0 and drawer['y'] + drawer['height'] <= 641, drawer
    assert_invariants(page, 's13')


def s14_repeated_restart(page):
    """连开五局：状态必须完全重置，不能把上一局的遗物/仓库带过来。"""
    for i in range(5):
        start(page)
        if i:
            page.get_by_role('button', name='再来一局', exact=True).count() or None
        st = state(page)
        assert st['day'] == 1 and st['hp'] == 100 and st['wood'] == 18, ('重开状态没重置', i, st)
        assert page.evaluate('Object.keys(window.__ff.stock).length') == 0, ('仓库没有清空', i)
        assert page.evaluate('window.__ff.relicBonus().atk') == 0, ('遗物带到了新局', i)
        assert_invariants(page, 's14-' + str(i))


def s15_event_then_supply(page):
    """事件与补给连续走：奖励不能串味（事件的建筑不该变成补给的收获）。"""
    start(page)
    page.locator('#shopBtn').click()
    page.locator('#buyWood').click()
    page.get_by_role('button', name='返回海面', exact=True).click()
    sail(page, want='event')
    page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
    page.locator('[data-event="avoid"]').click()
    page.get_by_role('button', name='继续航行', exact=True).click()
    assert state(page)['day'] == 2
    page.locator('#sailBtn').click()
    if page.locator('.sail-row.supply').count():
        page.locator('.sail-row.supply').first.click()
        page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
        assert page.locator('[data-supply]').count() == 3, '补给应给三个选项'
        page.locator('[data-supply]').first.click()
        page.get_by_role('button', name='继续航行', exact=True).click()
        assert state(page)['day'] == 3
    assert_invariants(page, 's15')


def s16_double_click_event_continue(page):
    """连点「继续航行」：天数只能 +1，航线必须同步，存档必须仍然合法。"""
    start(page)
    sail(page, want='event')
    page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
    page.locator('[data-event="avoid"]').click()
    page.evaluate("()=>{const b=document.querySelector('#journeyActions button'); b.click(); b.click(); b.click();}")
    page.wait_for_timeout(120)
    st = state(page)
    assert st['day'] == 2, ('连点把天数推多了', st)
    assert st['route'] == 1, ('天数与航线脱节', st)
    assert_invariants(page, 's16')


def s17_double_click_reward_continue(page):
    """连点「领取并整备下一天」：奖励只能记一次，天数只能 +1。"""
    start(page)
    sail(page)
    page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
    if page.locator('.loot-card').count():
        page.locator('.loot-card').first.click()
    wood = state(page)['wood']
    route = state(page)['route']
    page.evaluate("()=>{const b=document.querySelector('#journeyActions button'); b.click(); b.click();}")
    page.wait_for_timeout(120)
    st = state(page)
    assert st['day'] == 2 and st['route'] == route, ('连点推进了两天或航线错位', st)
    assert st['wood'] == wood, ('奖励被重复计入', st)
    assert_invariants(page, 's17')


def s18_double_click_start(page):
    """连点「开始五日冒险」：只能开一局，状态不能叠加。"""
    page.goto(URL)
    page.evaluate("()=>{const b=[...document.querySelectorAll('#journeyActions button')].find(x=>x.textContent.includes('开始五日')); b.click(); b.click();}")
    page.wait_for_timeout(150)
    st = state(page)
    assert st['day'] == 1 and st['wood'] == 18 and st['hp'] == 100, ('连点开局状态异常', st)
    assert sum(1 for c in cells(page) if c != '.') == 4, '开局建筑数量不对'
    assert_invariants(page, 's18')


SCENARIOS = [
    ('01 连点航线', s01_double_click_route),
    ('02 空板狂点', s02_spam_clicks_empty),
    ('03 拖出甲板', s03_drag_outside),
    ('04 拆除模式拖拽', s04_drag_in_remove_mode),
    ('05 对话中撤销', s05_undo_during_dialog),
    ('06 战斗中改窗口', s06_resize_mid_battle),
    ('07 扩建撤销往返', s07_expand_undo_roundtrip),
    ('08 零木材', s08_zero_wood),
    ('09 铺满 5×5', s09_full_board),
    ('10 坏档重载', s10_save_quota_and_reload),
    ('11 纯键盘', s11_keyboard_only),
    ('12 DOM 泄漏', s12_no_dom_leak),
    ('13 320px 窄屏', s13_narrow_screen),
    ('14 连开五局', s14_repeated_restart),
    ('15 事件接补给', s15_event_then_supply),
    ('16 连点继续航行', s16_double_click_event_continue),
    ('17 连点领取奖励', s17_double_click_reward_continue),
    ('18 连点开局', s18_double_click_start),
]

if __name__ == '__main__':
    with sync_playwright() as p:
        browser = p.chromium.launch()
        failed = []
        for name, fn in SCENARIOS:
            page = new_page(browser)
            try:
                fn(page)
                print('PASS', name)
            except Exception as exc:
                failed.append((name, str(exc)[:300]))
                print('FAIL', name, '->', str(exc)[:200])
            finally:
                page.close()
        browser.close()
        if failed:
            print('\n失败场景：')
            for name, msg in failed:
                print('-', name, ':', msg)
            raise SystemExit(1)
        print('\nALL EXPLORE SCENARIOS PASS')
