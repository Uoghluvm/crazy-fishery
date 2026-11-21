"""Run: py -3 test_rule_building.py
规则型奇妙建筑「潮汐闸」：规则只写在 simulate() 一处，预测 / 动画 / 结算必须同源。
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


def start_rich(page):
    """开局 + 测试金币换木材，保证够买规则建筑。"""
    page.goto(URL)
    page.get_by_role('button', name='开始五日冒险', exact=True).click()
    page.locator('#shopBtn').click()
    page.locator('#buyWood').click()
    page.get_by_role('button', name='返回海面', exact=True).click()


def check_rule_visible(page):
    page.emulate_media(reduced_motion='reduce')
    start_rich(page)
    page.locator('#growBtn').click()
    for index in [2, 6]:
        build(page, 'shield', index)
    build(page, 'tidegate', 8)
    cell = page.locator('.cell').nth(8)
    assert cell.get_attribute('data-building') == 'tidegate'
    assert cell.locator('.val').inner_text() == '盾续', '规则建筑应显示规则缩写，而不是无意义的 0'
    assert page.evaluate('window.__ff.fleet().rules.shieldCarry') is True
    page.screenshot(path=str(Path(__file__).with_name('preview-tidegate-' + str(page.viewport_size['width']) + '.png')))
    # 拆除后规则立即消失，不残留
    page.locator('#removeBtn').click()
    tap(page, 8)
    page.keyboard.press('Escape')
    assert page.evaluate('window.__ff.fleet().rules.shieldCarry') is not True
    page.locator('#undoBtn').click()
    assert page.evaluate('window.__ff.fleet().rules.shieldCarry') is True, '撤销应把规则一起恢复'


def check_prediction_matches_settlement(page):
    """预测的伤害、逐轮动画的累计、实际扣血必须是同一个数。"""
    page.emulate_media(reduced_motion='reduce')
    start_rich(page)
    page.locator('#growBtn').click()
    for index in [2, 6, 9]:
        build(page, 'shield', index)
    build(page, 'tidegate', 8)
    build(page, 'ballista', 12)
    before = hp(page)
    f = page.evaluate("""()=>{
      const f=window.__ff.forecast(true);
      return {damage:f.damage, rounds:f.rounds, sum:f.log.reduce((s,e)=>s+e.taken,0), absorb:f.log.map(e=>e.absorb), tags:f.log.map(e=>e.tags)};
    }""")
    assert f['damage'] == f['sum'], ('log 累计与被扣总量必须一致', f)
    page.locator('#sailBtn').click()
    page.locator('.sail-row.elite').first.click()
    page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
    assert hp(page) == before - f['damage'], ('实际扣血应与预测一致', hp(page), f['damage'])
    # 战斗中护盾标签应体现"盾续"，方便玩家看懂规则生效了
    assert any('盾续' in t for tags in f['tags'] for t in tags), f['tags']


def check_rule_changes_outcome(page):
    page.emulate_media(reduced_motion='reduce')
    start_rich(page)
    page.locator('#growBtn').click()
    for index in [2, 6, 9]:
        build(page, 'shield', index)
    build(page, 'tidegate', 8)
    with_rule = page.evaluate('window.__ff.forecast(true)')
    page.locator('#removeBtn').click()
    tap(page, 8)
    page.keyboard.press('Escape')
    without = page.evaluate('window.__ff.forecast(true)')
    assert with_rule['shield'] == without['shield'], '规则建筑本身不提供护盾数值'
    assert with_rule['damage'] < without['damage'], ('规则应降低真实伤害', with_rule['damage'], without['damage'])
    assert with_rule['damage'] > 0, '不能变成零伤'
    # 同一局内三个海怪：穿影无视护盾，规则不应影响它
    base = page.evaluate("""()=>{
      const ship=r=>({attack:55,income:10,shield:r,foeHp:1,loot:0,heal:0,rules:{}});
      const gate=r=>({...ship(r),rules:{shieldCarry:true}});
      return {
        wraith:[window.__ff.simulate(ship(12),['wraith'],{power:40,boss:false}).damage,
                window.__ff.simulate(gate(12),['wraith'],{power:40,boss:false}).damage],
        boss:[window.__ff.simulate(ship(18),['leviathan'],{power:72,boss:true}).damage,
              window.__ff.simulate(gate(18),['leviathan'],{power:72,boss:true}).damage]
      };
    }""")
    assert base['wraith'][0] == base['wraith'][1], '穿影必须继续无视护盾'
    assert base['boss'][1] < base['boss'][0], ('对 Boss 应有明显收益', base['boss'])
    assert base['boss'][1] >= 5 * 4, ('每轮最多挡 3/4，不能退化成每轮 1 点', base['boss'][1])


def check_mode_parity_with_rule(browser):
    """观看 / 跳过 / 中途减少动态 三条路径，规则在场时结果仍必须一致。"""
    results = []
    for mode in ['watch', 'skip', 'reduce_midway']:
        page = browser.new_page(viewport={'width': 1200, 'height': 800})
        page.emulate_media(reduced_motion='no-preference')
        start_rich(page)
        page.locator('#growBtn').click()
        for index in [2, 6, 9]:
            build(page, 'shield', index)
        build(page, 'tidegate', 8)
        build(page, 'ballista', 12)
        page.locator('#sailBtn').click()
        page.locator('.sail-row.elite').first.click()
        if mode == 'watch':
            page.wait_for_function("document.querySelectorAll('.projectile').length>0")
            page.wait_for_function("document.querySelector('#journey').open", timeout=15000)
        elif mode == 'skip':
            page.wait_for_function("document.querySelectorAll('.projectile').length>0")
            page.locator('#skipBattle').click()
        else:
            page.wait_for_function("document.querySelectorAll('.projectile').length>0")
            page.emulate_media(reduced_motion='reduce')
            page.wait_for_function("document.querySelector('#journey').open", timeout=15000)
        results.append((hp(page), wood(page)))
        page.close()
    assert len(set(results)) == 1, ('三条观看路径结果必须一致', results)


def check_save_roundtrip(page):
    """新建筑要能存档、读档、并通过校验。"""
    page.emulate_media(reduced_motion='reduce')
    start_rich(page)
    build(page, 'tidegate', 8)
    raw = page.evaluate('(k)=>localStorage.getItem(k)', KEY)
    data = json.loads(raw)
    assert data['version'] == 2
    assert ['8,2', 'tidegate'] in data['cells'] or any(c[1] == 'tidegate' for c in data['cells'])
    assert page.evaluate('(d)=>window.__ff.validSave(d)', data) is True
    page.reload()
    page.get_by_role('button', name='继续上次冒险', exact=False).first.click()
    assert any(c.get_attribute('data-building') == 'tidegate' for c in [page.locator('.cell').nth(i) for i in range(9)])
    assert page.evaluate('window.__ff.fleet().rules.shieldCarry') is True


if __name__ == '__main__':
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width, height in [(1440, 900), (390, 844)]:
            page = browser.new_page(viewport={'width': width, 'height': height})
            errs = []
            page.on('pageerror', lambda e: errs.append(str(e)))
            check_rule_visible(page)
            check_prediction_matches_settlement(page)
            check_rule_changes_outcome(page)
            assert not errs, errs
            page.close()
            print(f'PASS rule building visible/predicted/effective {width}x{height}')
        page = browser.new_page(viewport={'width': 1200, 'height': 800})
        check_save_roundtrip(page)
        page.close()
        check_mode_parity_with_rule(browser)
        print('PASS save roundtrip and three-mode parity with rule active')
        browser.close()
