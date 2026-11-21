"""Shared Playwright helpers for the adventure flow (imported by the test_*.py scripts).

The adventure no longer offers a fixed "驶入浅海" button. Each day opens a sea chart with one
ticket per reachable node (.sail-row.<kind>), a victory asks for one of three loot cards before the
next day, and some nodes are supply stops instead of fights. These helpers wrap that flow.
"""
import re
from pathlib import Path

URL = Path(__file__).with_name('mvp.html').as_uri()
SAVE_KEY = 'crazy-fishery.save.v1'
CODEX_KEY = 'crazy-fishery.codex.v1'
NEXT_DAY = '领取并整备下一天'


def start_adventure(page, seed=None):
    """Load the page and begin a fresh adventure. A seed pins the sea chart for the first run."""
    page.goto(URL + ('?seed=%d' % seed if seed else ''))
    page.get_by_role('button', name='开始五日冒险', exact=True).click()


def hud(page):
    """Hull and wood as shown in the voyage HUD."""
    strongs = page.locator('#voyageHud strong')
    return {'hp': int(strongs.first.inner_text()), 'wood': int(strongs.last.inner_text())}


def tickets(page):
    """Read every ticket on the open chart. net/reward are None for supply stops."""
    out = []
    rows = page.locator('.sail-row')
    for i in range(rows.count()):
        row = rows.nth(i)
        nums = row.locator('.num b')
        net, reward = nums.nth(0).inner_text(), nums.nth(1).inner_text()
        out.append({
            'index': i,
            'kind': row.get_attribute('class').split()[1],
            'node': row.get_attribute('data-node'),
            'net': int(net) if re.fullmatch(r'-?\d+', net) else None,
            'reward': int(reward[1:]) if re.fullmatch(r'\+\d+', reward) else None,
            'wreck': 'wreck' in (row.locator('.go').get_attribute('class') or ''),
        })
    return out


def open_chart(page):
    page.locator('#sailBtn').click()
    page.locator('.sail-row').first.wait_for()


def sail(page, kind='fight'):
    """Open the chart and take the first ticket of this kind (fight / elite / supply / boss)."""
    open_chart(page)
    page.locator('.sail-row.%s' % kind).first.click()


def wait_for_dialog(page, timeout=15000):
    page.wait_for_function("document.querySelector('#journey').open", timeout=timeout)


def claim_loot(page, prefer=('wood', 'repair', 'relic', 'build')):
    """Pick one of the three victory cards (the next-day button stays disabled until then)."""
    for kind in prefer:
        card = page.locator('[data-loot^="%s:"]' % kind)
        if card.count():
            loot = card.first.get_attribute('data-loot')
            card.first.click()
            return loot
    card = page.locator('[data-loot]').first
    loot = card.get_attribute('data-loot')
    card.click()
    return loot


def next_day(page):
    page.get_by_role('button', name=NEXT_DAY, exact=True).click()


def settle_stop(page, loot=('wood', 'repair', 'relic', 'build'), supply='wood'):
    """After a ticket was clicked: finish whatever it led to and say what happened.

    Returns 'victory' (boss down), 'sunk', 'supply' or 'win'. For 'supply' and 'win' the game is
    already on the next day's整备 screen.
    """
    wait_for_dialog(page)
    if page.locator('[data-supply]').count():
        page.locator('[data-supply="%s"]' % supply).click()
        page.get_by_role('button', name='继续航行', exact=True).click()
        return 'supply'
    title = page.locator('#journeyTitle').inner_text()
    if title.startswith('你征服了'):
        return 'victory'
    if title == '木筏沉没了':
        return 'sunk'
    claim_loot(page, loot)
    next_day(page)
    return 'win'


def safest_ticket(page):
    """The non-sinking ticket with the lowest forecast hull loss (supply stops count as free)."""
    options = [t for t in tickets(page) if not t['wreck']]
    if not options:
        return None
    return min(options, key=lambda t: (t['net'] or 0, -(t['reward'] or 0)))


def build(page, kind, index):
    """Place a building by keyboard on the index-th deck cell (the same path real players can use)."""
    page.locator('#buildBtn').click()
    page.locator('.tool[data-id="%s"]' % kind).click()
    page.locator('.cell').nth(index).focus()
    page.locator('.cell').nth(index).press('Enter')
    page.keyboard.press('Escape')


def empty_cells(page):
    """Indices of the free deck cells, in DOM order."""
    return page.evaluate("[...document.querySelectorAll('.cell')].map((c,i)=>c.classList.contains('empty')?i:-1).filter(i=>i>=0)")


def strengthen(page, reserve=0):
    """Spend wood like a careful player: repair when low, then alternate shield / ballista, expanding when full.

    Returns the list of things it did so a test can say what happened.
    """
    done = []
    state = hud(page)
    while state['hp'] <= 75 and state['wood'] >= 10 + reserve and not page.locator('#repairBtn').is_disabled():
        page.locator('#repairBtn').click()
        done.append('repair')
        state = hud(page)
    order = ['shield', 'ballista']
    cost = {'shield': 10, 'ballista': 8}
    step = 0
    while True:
        state = hud(page)
        free = empty_cells(page)
        kind = order[step % 2]
        if not free:
            size = page.locator('.cell').count()
            price = 15 if size == 9 else 25
            if size == 25 or state['wood'] < price + cost[kind] + reserve:
                break
            page.locator('#growBtn').click()
            done.append('grow')
            continue
        if state['wood'] < cost[kind] + reserve:
            break
        build(page, kind, free[0])
        done.append(kind)
        step += 1
    return done
