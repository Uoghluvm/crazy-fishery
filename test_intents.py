"""Run: py -3 test_intents.py
M3 收尾：敌人意图（蓄力/重击、结壳、群袭）可预告、可结算，且两种非同质构筑都能通关。
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = Path(__file__).with_name('mvp.html').as_uri()


def hp(page):
    return page.evaluate('window.__ff.run.hp')


def wood(page):
    return page.evaluate('window.__ff.run.wood')


def attack(page):
    return int(page.locator('[data-cat="attack"] b').inner_text())


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


def take_reward(page):
    page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
    cards = page.locator('.loot-card')
    for i in range(cards.count()):
        if '木材' not in cards.nth(i).inner_text():
            cards.nth(i).click(); break
    page.get_by_role('button', name='领取并整备下一天', exact=True).click()


def check_intent_log(page):
    """三种行为必须在 log 里出现，且预告与下一轮实际发生的一致。"""
    page.goto(URL)
    result = page.evaluate("""()=>{
      const ship=(atk,sh)=>({attack:atk,income:10,shield:sh,foeHp:1,loot:0,heal:0,rules:{}});
      const run=(id,power,atk,sh=9,boss=false)=>{
        const r=window.__ff.simulate(ship(atk,sh),[id],{power,boss});
        return {damage:r.damage,log:r.log};
      };
      return {ambush:run('ambush',40,30), shell:run('shell',40,20), school:run('school',40,40)};
    }""")
    amb = result['ambush']['log']
    assert '蓄力' in amb[0]['tags'][0], ('第一轮应蓄力', amb[0])
    assert amb[0]['raw'] == 0 and amb[0]['taken'] == 0, ('蓄力轮不应造成伤害', amb[0])
    assert '重击' in amb[1]['tags'][0] and amb[1]['raw'] >= 25, ('第二轮应是三倍重击', amb[1])

    shell = result['shell']['log']
    guard_rounds = [e for e in shell if any('结壳' in t for t in e['tags'])]
    assert guard_rounds, ('铁壳蟹应在第 3 轮结壳', shell)
    normal_dealt = max(e['dealt'] for e in shell if not any('结壳' in t for t in e['tags']))
    assert guard_rounds[0]['dealt'] < normal_dealt, ('结壳轮我方伤害应下降', guard_rounds[0]['dealt'], normal_dealt)

    school = result['school']['log']
    assert all(any('群袭' in t for t in e['tags']) for e in school), ('鱼群每轮都是群袭', school)

    # 预告必须与下一轮实际一致，否则玩家会被骗
    checks = page.evaluate("""()=>{
      const ship={attack:40,income:10,shield:6,foeHp:1,loot:0,heal:0,rules:{}};
      const r=window.__ff.simulate(ship,['ambush'],{power:40,boss:false});
      return r.log.map((e,i)=>({next:(e.next||[]).map(n=>n.kind), actual:i+1<r.log.length?r.log[i+1].tags:[]}));
    }""")
    map_kind = {'charge': '蓄力', 'heavy': '重击', 'guard': '结壳', 'swarm': '群袭'}
    for row in checks:
        if not row['next'] or not row['actual']:
            continue
        want = map_kind.get(row['next'][0])
        if want:
            assert any(want in t for t in row['actual']), ('预告与实战不一致', row)


def check_intent_on_screen(page):
    page.emulate_media(reduced_motion='no-preference')
    page.goto(URL)
    page.get_by_role('button', name='开始五日冒险', exact=True).click()
    # 第二天走有潜伏者的航线太慢，这里直接在第 1 天验证播报结构：有「下轮：」提示
    page.locator('#sailBtn').click()
    # 第 1 天固定有灯影事件，挑战斗票才能进战斗界面
    page.locator('.sail-row.fight, .sail-row.elite').first.click()
    page.wait_for_function("document.querySelector('#battleDetail').textContent.includes('首轮：')")
    detail = page.locator('#battleDetail').inner_text()
    assert '首轮：' in detail, ('开场播报应给出首轮意图', detail)
    assert any(k in detail for k in ['齐射', '蓄力', '重击', '结壳', '群袭']), detail
    page.locator('#skipBattle').click()
    page.wait_for_function("document.querySelector('#journey').open", timeout=10000)


def play_run(page, build_fn, label):
    page.emulate_media(reduced_motion='reduce')
    page.goto(URL)
    page.get_by_role('button', name='开始五日冒险', exact=True).click()
    page.locator('#shopBtn').click()
    page.locator('#buyWood').click()
    page.get_by_role('button', name='返回海面', exact=True).click()
    page.locator('#growBtn').click()
    build_fn(page)
    for day in range(1, 6):
        while hp(page) < 100 and wood(page) >= 10:
            page.locator('#repairBtn').click()
        sail(page)
        page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
        title = page.locator('#journeyTitle').inner_text()
        assert '沉没' not in title, (label + ' 在第 ' + str(day) + ' 天沉没', title)
        if day == 5:
            assert title == '你征服了「深海巨兽」！', (label, title)
        else:
            take_reward(page)
        assert hp(page) > 0
    return True


def check_two_builds_win(page):
    def attack_build(p):
        for index in [2, 6, 8, 9, 10]:
            build(p, 'ballista', index)

    def shield_build(p):
        for index in [2, 6, 9]:
            build(p, 'shield', index)
        build(p, 'tidegate', 8)
        for index in [10, 12, 13]:
            build(p, 'ballista', index)

    play_run(page, attack_build, '攻击流')
    assert attack(page) >= 80
    page.reload()
    page.emulate_media(reduced_motion='reduce')
    play_run(page, shield_build, '护盾流')
    assert page.evaluate('window.__ff.fleet().rules.shieldCarry') is True


if __name__ == '__main__':
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width, height in [(1440, 900), (390, 844)]:
            page = browser.new_page(viewport={'width': width, 'height': height})
            errs = []
            page.on('pageerror', lambda e: errs.append(str(e)))
            check_intent_log(page)
            check_intent_on_screen(page)
            assert not errs, errs
            page.close()
            print(f'PASS intent log/telegraph/screen {width}x{height}')
        page = browser.new_page(viewport={'width': 1200, 'height': 800})
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        check_two_builds_win(page)
        assert not errs, errs
        print('PASS two distinct builds clear all five days')
        browser.close()
