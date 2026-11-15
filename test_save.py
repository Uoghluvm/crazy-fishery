"""Run: python test_save.py. Persistence boundaries and reference-inspired HUD."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from ui_helpers import *

KEY=SAVE_KEY

def snapshot(page):
    return page.evaluate('(key)=>JSON.parse(localStorage.getItem(key))',KEY)

def resume(page):
    page.reload()
    page.get_by_role('button',name='继续上次冒险 · 第 1 天',exact=True).click()

with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={'width':390,'height':844})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    start_adventure(page,4242)
    page.evaluate('Math.random=()=>0')
    page.locator('#shopBtn').click()
    page.get_by_role('button',name='十连',exact=True).click()
    page.locator('#buyWood').click()
    page.get_by_role('button',name='返回海面',exact=True).click()
    page.locator('#growBtn').click()
    page.locator('#buildBtn').click()
    page.locator('#soundBtn').click()
    page.locator('.tool[data-id="ballista"]').click()
    page.locator('.cell').nth(3).focus()
    page.locator('.cell').nth(3).press('Enter')
    page.keyboard.press('Escape')
    page.locator('#coachClose').click()
    before=snapshot(page)
    assert before['stock']['ballista']==9 and before['pity']==10
    assert before['run']['wood']==103 and before['sizeIdx']==1 and before['run']['seed']==4242
    resume(page)
    assert snapshot(page)==before
    assert page.locator('.cell').count()==16
    assert not page.locator('#coach').is_visible()
    assert page.locator('#soundBtn').get_attribute('aria-pressed')=='false'
    # Hover previews are not real buildings and must not enter the save.
    page.locator('#buildBtn').click()
    page.locator('.tool[data-id="ballista"]').click()
    page.locator('.cell').nth(15).focus()
    assert page.locator('.cell.ghost').count()==1
    assert snapshot(page)['cells']==before['cells']
    page.keyboard.press('Escape')
    # An interrupted animation restores the pre-departure transaction.
    open_chart(page)
    page.locator('.sail-row.fight').first.click()
    page.wait_for_function("document.querySelector('#enemyHealth').value < document.querySelector('#enemyHealth').max")
    assert snapshot(page)==before
    resume(page)
    assert snapshot(page)==before
    assert not page.locator('#journey').is_visible()
    # Once resolved, the report and reward survive reload without duplicate credit.
    page.emulate_media(reduced_motion='reduce')
    open_chart(page)
    page.locator('.sail-row.fight').first.click()
    result=snapshot(page)
    assert result['run']['phase']=='result'
    assert result['run']['wood']==116  # 103 + 13 from the day-1 patrol on chart #4242
    assert result['run']['seed']==4242 and len(result['run']['route'])==1
    chosen=result['run']['route'][0]['node']
    resume(page)
    assert page.locator('#journeyTitle').inner_text()=='第 1 天 · 遭遇胜利'
    assert snapshot(page)==result
    resume(page)
    assert snapshot(page)==result
    # The three-way loot choice is part of the report: it must not be claimable twice across reloads.
    assert page.locator('[data-loot]').count()==3
    loot=claim_loot(page,('relic',))
    picked=snapshot(page)
    assert picked['run']['result']['picked']==loot and picked['run']['relics']==[loot.split(':')[1]]
    resume(page)
    assert snapshot(page)==picked
    assert page.locator('[data-loot]').count()==3 and page.locator('[data-loot]:not([disabled])').count()==0
    next_day(page)
    after=snapshot(page)
    assert after['run']['day']==2
    assert after['run']['wood']==116
    assert after['run']['relics']==picked['run']['relics']
    assert len(after['run']['route'])==1 and after['run']['route'][0]['node']==chosen
    page.locator('#helpBtn').click()
    page.get_by_role('button',name='继续当前航程',exact=True).click()
    page.mouse.move(0,0)
    page.screenshot(path=str(Path(__file__).with_name('preview-tidewater-390.png')))
    page.set_viewport_size({'width':1440,'height':900})
    page.screenshot(path=str(Path(__file__).with_name('preview-tidewater-1440.png')))
    assert not errors,errors
    # Invalid/unknown save data must stay untouched until a player explicitly starts anew.
    invalids=['{broken',json.dumps({**before,'version':999}),json.dumps({**before,'pity':-1}),json.dumps({**before,'cells':[['9,9','ballista']]}),json.dumps({**before,'run':{**before['run'],'wood':-1}})]
    for raw in invalids:
        page.evaluate('([key,raw])=>localStorage.setItem(key,raw)',[KEY,raw])
        page.reload()
        assert page.get_by_role('button',name='继续上次冒险',exact=False).count()==0
        assert page.evaluate('(key)=>localStorage.getItem(key)',KEY)==raw
        assert '存档不可读取' in page.locator('#journeyBody').inner_text()
    page.get_by_role('button',name='开始五日冒险',exact=True).click()
    assert snapshot(page)['run']['wood']==18
    # Browser policies / quota errors must not crash gameplay or claim success.
    blocked=browser.new_page()
    blocked.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new Error('blocked')}})")
    blocked.goto(URL)
    blocked.get_by_role('button',name='开始五日冒险',exact=True).click()
    assert '无法保存' in blocked.locator('#voyageHud').inner_text()
    blocked.locator('#buildBtn').click()
    assert blocked.locator('#drawer').is_visible()
    print('PASS persistence: state/stock/pity/settings restore, preview exclusion, battle rollback, report exactly once, invalid save preservation, blocked storage fallback')
    browser.close()
