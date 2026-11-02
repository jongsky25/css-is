"""Christmas costume compatibility, live selection and real named-companion layouts."""
import xml.etree.ElementTree as ET
from pathlib import Path

import appearance as rules
import storage as st
from tests.test_appearance import submit
from tests.test_appearance_browser import seasonal_browser, page_for, pw

STYLES = ['christmas', 'christmas_elf', 'christmas_reindeer', 'christmas_parol', 'christmas_knit']


def test_every_species_growth_style_and_personal_optout(app_mod):
    module = app_mod.templates.env.get_template('_avatars.html').module
    for species in st.AVATAR_CATALOG:
        for stage in range(1, 7):
            for style in STYLES:
                assert rules.accessory_month(style) == 12
                svg = ET.fromstring(str(module.avatar_svg(species['key'], stage, 12, style)))
                assert svg.attrib['data-avatar-outfit'] == style
                assert svg.find(f'.//g[@data-christmas-style="{style}"]') is not None
                opted_out = ET.fromstring(str(module.avatar_svg(species['key'], stage, 12, style,
                    preferences={'mode': 'none', 'items': []})))
                assert opted_out.attrib['data-avatar-outfit'] == 'default'
                assert opted_out.find('.//g[@data-christmas-style]') is None


def name_rabbit(app_mod, username):
    connection = st.connect(app_mod.DB)
    try:
        connection.execute('UPDATE admin_user SET avatar_kind=?, avatar_name=? WHERE username=?',
                           ('rabbit', 'Clover', username))
        connection.commit()
    finally:
        connection.close()


def test_named_companion_full_width_controls_and_scene(seasonal_browser, admin, viewer, app_mod, tmp_path):
    name_rabbit(app_mod, 'viewer@test.local')
    assert submit(admin, 'publish', theme='christmas', outfit='christmas_elf',
                  artwork_present='1', artwork='1').status_code == 303
    context, page = page_for(seasonal_browser, viewer, reduced_motion='reduce')
    context.add_init_script("localStorage.setItem('css_tour_optout','1')")
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    try:
        for width in (320, 390, 768, 1024, 1440):
            page.set_viewport_size({'width': width, 'height': 1000})
            for mode in ('light', 'dark'):
                page.goto('http://testserver/?view=me')
                page.evaluate('(mode)=>{document.documentElement.dataset.theme=mode;document.documentElement.dataset.textscale="lg";}',mode)
                stage = page.locator('.oc-pet-stage')
                box, parent = stage.bounding_box(), stage.locator('..').bounding_box()
                assert abs(box['width'] - parent['width']) < 2
                assert abs(box['x']-parent['x']) < 2
                art = stage.locator('.av-tiltstage').bounding_box()
                controls = stage.locator('.av-sound-controls').bounding_box()
                assert abs((art['x']+art['width']/2)-(box['x']+box['width']/2)) < 2
                assert controls['y'] >= art['y']+art['height']
                assert stage.locator('.av-play-btn').is_enabled()
                edit = stage.locator('.oc-pet-edit').bounding_box()
                assert edit['y'] >= controls['y']+controls['height']
                assert 'companion-courtyard.svg' in stage.evaluate('(el)=>getComputedStyle(el,"::before").backgroundImage')
                assert 'christmas-parols.svg' not in stage.evaluate('(el)=>getComputedStyle(el).backgroundImage')
                stage.locator('.av-sound-btn').click()
                pw.expect(stage.locator('.av-volume')).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                opened = stage.locator('.av-sound-controls').bounding_box()
                assert stage.locator('.oc-pet-edit').bounding_box()['y'] >= opened['y']+opened['height']
                stage.locator('.av-sound-btn').click()
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                if width in (390, 768, 1440):
                    page.screenshot(path=str(tmp_path/f'courtyard-{mode}-{width}.png'),full_page=True)
                    stage.screenshot(path=str(tmp_path/f'panel-{mode}-{width}.png'))
            if width in (390, 768, 1440):
                for alternative in ('sala','veranda'):
                    page.add_style_tag(content=f'.oc-pet-stage::before{{background-image:url("/static/img/seasonal/companion-{alternative}.svg")!important}}')
                    page.screenshot(path=str(tmp_path/f'{alternative}-{width}.png'),full_page=True)
        page.goto('http://testserver/?view=me')
        page.evaluate('document.documentElement.dataset.theme="contrast"')
        assert page.locator('.oc-pet-stage').evaluate('(el)=>getComputedStyle(el,"::before").display') == 'none'
        page.evaluate('document.documentElement.dataset.seasonArtwork="0"')
        assert page.locator('.oc-pet-stage').evaluate('(el)=>getComputedStyle(el,"::before").content') == 'none'
        page.goto('http://testserver/me')
        page.locator('#avatar_name').fill('Keep this name')
        svg = page.locator('svg[data-avatar-kind="rabbit"]').first
        svg.locator('.av-head').first.evaluate('(el)=>el.dataset.preserved="yes"')
        for style in ('christmas_reindeer','christmas_parol','christmas_knit'):
            assert submit(admin, 'publish', theme='christmas', outfit=style).status_code == 303
            page.evaluate("window.dispatchEvent(new Event('focus'))")
            pw.expect(svg).to_have_attribute('data-avatar-outfit',style)
            pw.expect(svg.locator('.av-head').first).to_have_attribute('data-preserved','yes')
            pw.expect(page.locator('#avatar_name')).to_have_value('Keep this name')
        assert not errors
    finally:
        context.close()


def test_editor_christmas_choices_mismatch_and_private_preview(seasonal_browser, admin, viewer, app_mod):
    name_rabbit(app_mod, 'admin@test.local')
    assert submit(admin,'draft',theme='christmas',outfit='halloween_vampire').status_code == 303
    context, page = page_for(seasonal_browser,admin,viewport={'width':390,'height':844})
    try:
        page.goto('http://testserver/admin/appearance')
        pw.expect(page.locator('#appearance-editor [data-outfit-mismatch]')).to_be_visible()
        pw.expect(page.locator('[data-outfit-group=christmas]')).to_have_attribute('open','')
        assert page.locator('[data-outfit-group=christmas] [data-pick-outfit]').count()==5
        page.locator('[data-pick-outfit=christmas_parol]').click()
        pw.expect(page.locator('#editor-outfit')).to_have_value('christmas_parol')
        pw.expect(page.locator('#appearance-editor [data-outfit-mismatch]')).to_be_hidden()
        page.get_by_role('button',name='Update preview',exact=True).click()
        pw.expect(page.frame_locator('#appearance-preview').locator('html')).to_have_attribute('data-appearance-preview','1')
        assert viewer.get('/appearance/current').json()['theme']=='default'
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    finally:
        context.close()


def test_outfit_contact_sheets(seasonal_browser, admin, app_mod, tmp_path):
    module = app_mod.templates.env.get_template('_avatars.html').module
    context, page = page_for(seasonal_browser,admin,reduced_motion='reduce',viewport={'width':1400,'height':1100})
    try:
        for stage in (1,3,6):
            cards=[]
            for kind in ('rabbit','plant','fish','bird'):
                for style in STYLES:
                    cards.append(f'<article><div>{module.avatar_svg(kind,stage,12,style)}</div><b>{kind}</b><p>{rules.OUTFITS[style]["name"]}</p></article>')
            html='<html><head><base href="http://testserver/"></head><body>'+str(module.avatar_defs())+'<style>body{background:#f6f0e4;font:15px system-ui;color:#243c31;margin:24px}.sheet{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}article{border:1px solid #cdbf9e;border-radius:12px;text-align:center;background:#fffaf0;padding:12px}article>div{height:170px}article svg{width:150px;height:170px}p{margin:5px;font-size:13px}</style>'+f'<h1>Christmas companions · growth stage {stage}</h1><div class="sheet">'+''.join(cards)+'</div></body></html>'
            page.set_content(html)
            page.screenshot(path=str(tmp_path/f'outfits-stage-{stage}.png'),full_page=True)
            Path(tmp_path/f'outfits-stage-{stage}.html').write_text(html)
    finally:
        context.close()
