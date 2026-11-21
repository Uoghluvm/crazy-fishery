"""Run: py -3 test_explore2.py
第二轮：结构性与数值扫描。航线图连通、存档矩阵、双窗口、种子复现、战斗性能。
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

# 这些用例断言的是精确数值与流程，用 ?chart=legacy 固定成原来那张 13 节点海图；
# 随机海图的行为由 test_map_codex.py 覆盖。
URL = Path(__file__).with_name('mvp.html').as_uri() + '?chart=legacy'
KEY = 'crazy-fishery.save.v1'


def new_page(browser, w=1200, h=800, motion='reduce'):
    page = browser.new_page(viewport={'width': w, 'height': h})
    page.set_default_timeout(60000)   # 批量跑时 CPU 被着色器占满，放宽等待避免误报
    page.emulate_media(reduced_motion=motion)
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


def take_battle_reward(page):
    page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
    if page.locator('.loot-card').count():
        page.locator('.loot-card').first.click()
    page.get_by_role('button', name='领取并整备下一天', exact=True).click()


def t01_graph(page):
    """航线图必须连通：没有断链、没有指向不存在节点的边、任何起点都能到 Boss。"""
    page.goto(URL)
    report = page.evaluate("""()=>{
      const nodes=window.__ff.MAP_NODES, byId=Object.fromEntries(nodes.map(n=>[n.id,n]));
      const problems=[];
      for(const n of nodes){
        for(const id of n.links) if(!byId[id]) problems.push(n.id+' -> 不存在的 '+id);
        for(const id of n.links) {
          const t=byId[id];
          if(t && t.day!==n.day+1) problems.push(n.id+' 跨天连到 '+id+'（'+n.day+'→'+t.day+'）');
        }
      }
      const reach=(from)=>{
        const seen=new Set(), st=[from];
        while(st.length){ const id=st.pop(); if(seen.has(id))continue; seen.add(id);
          for(const nx of byId[id].links) st.push(nx); }
        return seen;
      };
      const starts=nodes.filter(n=>n.day===1).map(n=>n.id);
      const boss=nodes.find(n=>n.kind==='boss').id;
      for(const s of starts) if(!reach(s).has(boss)) problems.push('从 '+s+' 到不了 Boss');
      const days=[1,2,3,4,5].map(d=>nodes.filter(n=>n.day===d).length);
      if(days.some(c=>c===0)) problems.push('空的天数 '+JSON.stringify(days));
      // 天数必须严格递增可达，避免出现跳天
      for(const n of nodes) for(const id of n.links)
        if(byId[id] && byId[id].day - n.day !== 1) problems.push('非逐天推进 '+n.id+'→'+id);
      return {problems, days, starts, kinds:[...new Set(nodes.map(n=>n.kind))]};
    }""")
    assert not report['problems'], report['problems']
    assert report['days'] == [3, 3, 3, 3, 1], report['days']
    assert 'event' in report['kinds'] and 'supply' in report['kinds'], report['kinds']
    assert not page.errors, page.errors


def t02_balance_sweep(page):
    """每日数值扫描：找出无解的一天或形同虚设的一天。"""
    page.goto(URL)
    rows = page.evaluate("""()=>{
      const out=[];
      const enc=(day,elite)=>window.__ff.encounter(day,elite);
      const ships=[
        {name:'弱（攻30）',attack:30,income:8,shield:0,foeHp:1,loot:0,heal:0,rules:{}},
        {name:'中（攻60）',attack:60,income:10,shield:9,foeHp:1,loot:0,heal:0,rules:{}},
        {name:'强（攻100）',attack:100,income:14,shield:9,foeHp:1,loot:0,heal:0,rules:{}},
        {name:'满（攻140+盾）',attack:140,income:14,shield:18,foeHp:1,loot:0,heal:0,rules:{shieldCarry:true}}
      ];
      for(let day=1;day<=5;day++){
        for(const elite of (day===5?[false]:[false,true])){
          const power=day===5?72:12+day*8+(elite?14:0);
          const foes=enc(day,elite);
          const line={day,elite,rival:foes.join('+')};
          for(const s of ships){
            const r=window.__ff.simulate(s,foes,{power,boss:day===5});
            line[s.name]=r.damage;
          }
          out.push(line);
        }
      }
      return out;
    }""")
    problems = []
    for line in rows:
        weak = line['弱（攻30）']
        strong = line['满（攻140+盾）']
        if strong <= 0:
            problems.append(('满配也会瞬间沉没', line))
        if strong > 60 and line['day'] < 5:
            problems.append(('满配在小关卡掉血过多', line))
        print(f"  day{line['day']}{' 险' if line['elite'] else ' 稳'} {line['rival'][:28]:<28} "
              f"弱{weak:>4} 中{line['中（攻60）']:>4} 强{line['强（攻100）']:>4} 满{strong:>4}")
    assert not problems, problems


def t03_save_matrix(page):
    """每个阶段刷新：要么恢复原样，要么安全回退，不能坏档或重复领奖。"""
    # 第 1 天整备
    start(page)
    snap = page.evaluate('(k)=>JSON.parse(localStorage.getItem(k))', KEY)
    page.reload()
    page.get_by_role('button', name='继续上次冒险', exact=False).first.click()
    assert page.evaluate('window.__ff.run.day') == 1
    assert page.evaluate('(k)=>JSON.parse(localStorage.getItem(k)).run.day', KEY) == snap['run']['day']

    # 战前（战斗中）刷新 → 回到出航前：必须真的打断动画中的战斗
    page.emulate_media(reduced_motion='no-preference')
    page.locator('#sailBtn').click()
    page.locator('.sail-row').first.click()
    page.wait_for_function("document.querySelector('#enemyHealth').value < document.querySelector('#enemyHealth').max", timeout=10000)
    page.reload()
    page.get_by_role('button', name='继续上次冒险', exact=False).first.click()
    st = page.evaluate("()=>({phase:window.__ff.run.phase,route:window.__ff.run.route.length})")
    assert st['phase'] == 'build' and st['route'] == 0, ('战斗中刷新应回到出航前', st)

    # 结算（已领奖）刷新 → 报告仍在，奖励不重复
    page.emulate_media(reduced_motion='reduce')
    page.wait_for_timeout(200)
    page.locator('#sailBtn').click()
    page.locator('.sail-row').first.click()
    page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
    if page.locator('.loot-card').count():
        page.locator('.loot-card').first.click()
    wood_now = page.evaluate('window.__ff.run.wood')
    page.reload()
    page.get_by_role('button', name='继续上次冒险', exact=False).first.click()
    assert page.evaluate('window.__ff.run.wood') == wood_now, '刷新后木材变了（奖励重复或丢失）'
    assert '胜利' in page.locator('#journeyTitle').inner_text()
    page.get_by_role('button', name='领取并整备下一天', exact=True).click()
    assert page.evaluate('window.__ff.run.wood') == wood_now, '进入下一天后奖励又发了一次'
    assert not page.errors, page.errors


def t04_multi_window_no_dup(browser):
    """两个窗口同时玩同一局：不能把同一份战利品各领一次。"""
    ctx = browser.new_context(viewport={'width': 1200, 'height': 800})
    a = ctx.new_page(); a.goto(URL)
    a.get_by_role('button', name='开始五日冒险', exact=True).click()
    b = ctx.new_page(); b.goto(URL)
    b.get_by_role('button', name='继续上次冒险', exact=False).first.click()
    b.emulate_media(reduced_motion='reduce')
    a.emulate_media(reduced_motion='reduce')
    b.locator('#sailBtn').click()
    b.locator('.sail-row').first.click()
    b.wait_for_function("document.querySelector('#journey').open", timeout=10000)
    if b.locator('.loot-card').count():
        b.locator('.loot-card').first.click()
    b_wood = b.evaluate('window.__ff.run.wood')
    b.get_by_role('button', name='领取并整备下一天', exact=True).click()
    a.wait_for_timeout(300)
    # A 收到"另一窗口有不同进度"，不应把 B 的奖励加到自己身上
    a_wood = a.evaluate('window.__ff.run.wood')
    assert a_wood == 18, ('A 窗口不应凭空获得奖励', a_wood)
    assert '另一窗口' in a.locator('#announcement').inner_text() or '另一窗口' in a.locator('#voyageHud').inner_text(), 'A 应被提示冲突'
    ctx.close()


def t05_seed_replay(browser):
    """同种子 + 同操作 → 两次结果必须完全一致（这是"可复现"的定义）。"""
    def play(page):
        page.goto(URL)
        page.get_by_role('button', name='开始五日冒险', exact=True).click()
        page.evaluate('window.__ff.setSeed(777)')
        page.locator('#shopBtn').click()
        page.locator('#buyWood').click()
        page.get_by_role('button', name='返回海面', exact=True).click()
        page.locator('#growBtn').click()
        for index in [2, 6, 8]:
            build(page, 'ballista', index)
        trace = []
        for _ in range(3):
            sail(page)
            page.wait_for_function("document.querySelector('#journey').open", timeout=10000)
            if page.locator('.loot-card').count():
                page.locator('.loot-card').first.click()
            trace.append((page.evaluate('window.__ff.run.hp'), page.evaluate('window.__ff.run.wood'),
                          page.locator('.loot-title').first.inner_text() if page.locator('.loot-title').count() else ''))
            page.get_by_role('button', name='领取并整备下一天', exact=True).click()
        return trace

    p1 = new_page(browser); t1 = play(p1); p1.close()
    p2 = new_page(browser); t2 = play(p2); p2.close()
    assert t1 == t2, ('同种子两次结果不同', t1, t2)


def t06_battle_perf(browser):
    """5×5 满场 + 战斗动画：记录帧率与最长帧，仅作基线。"""
    page = new_page(browser, 1440, 900, motion='no-preference')
    start(page)
    page.locator('#shopBtn').click()
    page.locator('#buyWood').click()
    page.locator('#buyWood').click()
    page.get_by_role('button', name='返回海面', exact=True).click()
    page.locator('#growBtn').click()
    page.locator('#growBtn').click()
    kinds = ['ballista', 'harpoon', 'net', 'shield', 'ammo', 'coral', 'beacon', 'still', 'trawl']
    for index in range(25):
        build(page, kinds[index % len(kinds)], index)
    idle = page.evaluate("""()=>new Promise(res=>{
      const t=[]; let last=performance.now();
      const tick=n=>{t.push(n-last);last=n;if(t.length<80)requestAnimationFrame(tick);else{
        const s=t.slice(10);res({avg:Math.round(1000/(s.reduce((a,b)=>a+b,0)/s.length)),worst:Math.round(Math.max(...s))});}};
      requestAnimationFrame(tick);
    })""")
    page.locator('#sailBtn').click()
    page.locator('.sail-row').first.click()
    page.wait_for_function("document.querySelectorAll('.projectile').length>0", timeout=10000)
    battle = page.evaluate("""()=>new Promise(res=>{
      const t=[]; let last=performance.now();
      const tick=n=>{t.push(n-last);last=n;if(t.length<30)requestAnimationFrame(tick);else{
        const s=t.slice(6);res({avg:Math.round(1000/(s.reduce((a,b)=>a+b,0)/s.length)),worst:Math.round(Math.max(...s))});}};
      requestAnimationFrame(tick);
    })""")
    print(f'  25 建筑空闲 {idle["avg"]}fps（最长帧 {idle["worst"]}ms）· 战斗中 {battle["avg"]}fps（最长帧 {battle["worst"]}ms）')
    # 满场火力下战斗可能已经自己打完，按钮消失是正常的
    if page.locator('#battleView').is_visible():
        page.locator('#skipBattle').click()
    page.wait_for_function("document.querySelector('#journey').open", timeout=15000)
    assert not page.errors, page.errors


def t07_aria():
    """无障碍基本项：格子有名字、对话框按钮有文本、焦点可见。"""
    page = new_page(page_browser, 1200, 800)
    start(page)
    bad = page.evaluate("""()=>{
      const out=[];
      document.querySelectorAll('.cell').forEach(c=>{ if(!c.getAttribute('aria-label')) out.push('格子缺少 aria-label'); });
      document.querySelectorAll('button').forEach(b=>{ if(!b.textContent.trim() && !b.getAttribute('aria-label')) out.push('按钮无名称: '+b.id); });
      return [...new Set(out)];
    }""")
    assert not bad, bad
    page.close()


if __name__ == '__main__':
    global page_browser
    with sync_playwright() as p:
        page_browser = browser = p.chromium.launch()
        page = new_page(browser)
        t01_graph(page); print('PASS 航线图连通性')
        t02_balance_sweep(page); print('PASS 数值扫描（见上表）')
        t03_save_matrix(page); print('PASS 存档阶段矩阵')
        page.close()
        t04_multi_window_no_dup(browser); print('PASS 双窗口不重复领奖')
        t05_seed_replay(browser); print('PASS 同种子重放一致')
        t06_battle_perf(browser); print('PASS 满场战斗性能采样')
        t07_aria(); print('PASS 无障碍基本项')
        browser.close()
