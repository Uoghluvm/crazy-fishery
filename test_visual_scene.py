from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 b=p.chromium.launch()
 for w,h in [(1440,900),(390,844)]:
  page=b.new_page(viewport={'width':w,'height':h});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.emulate_media(reduced_motion='reduce');page.goto(Path('mvp.html').resolve().as_uri());page.get_by_role('button',name='自由构筑',exact=True).click()
  page.locator('#growBtn').click();page.locator('#growBtn').click()
  page.locator('#resetBtn').click()
  ids=page.locator('.tool').evaluate_all('(es)=>es.map(e=>e.dataset.id)')
  for i,id in enumerate(ids[:25]):
   page.locator('#buildBtn').click();page.locator('.tool[data-id="'+id+'"]').click()
   cell=page.locator('.cell').nth(i);box=cell.bounding_box();page.mouse.click(box['x']+box['width']/2,box['y']+box['height']/2)
   assert cell.get_attribute('data-building')==id
  page.keyboard.press('Escape');page.mouse.move(0,0)
  page.wait_for_function("document.querySelectorAll('.float').length===0")
  assert page.locator('.hull-detail').count()==1
  assert 'undefined' not in page.locator('#grid').inner_text()
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  assert not errors,errors
  if w<600:
   boxes=page.locator('.labels .value').evaluate_all('(es)=>es.map(e=>{const r=e.getBoundingClientRect();return {l:r.left,r:r.right,t:r.top,b:r.bottom}})')
   for i,a in enumerate(boxes):
    for z in boxes[i+1:]:
     assert min(a['r'],z['r'])-max(a['l'],z['l'])<=1 or min(a['b'],z['b'])-max(a['t'],z['t'])<=1, 'Dense labels overlap'
  page.screenshot(path=f'preview-art-full-{w}.png')
  page.reload();page.get_by_role('button',name='开始五日冒险',exact=True).click();page.mouse.move(0,0);page.screenshot(path=f'preview-art-{w}.png')
  page.locator('#sailBtn').click();page.locator('.sail-row').first.click()
  assert page.locator('#journey').is_visible()
  page.close();print('PASS visual layout, all building hits, decorative hull, no overflow and battle render',w)
 b.close()
