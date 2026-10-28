"""Wardrobe boundaries, additive persistence and actual cross-surface rendering."""
import json
import re
import pytest
import storage as st
import companion_wardrobe as wardrobe


@pytest.mark.parametrize('kind,items', [('cat',['small_cap','bandana']), ('fern',['ceramic','plant_label']), ('bonsai',['pot_wrap','small_trellis'])])
def test_catalog_accepts_two_compatible_slots(kind, items):
    assert set(wardrobe.validate(kind,'personal',items)['items']) == set(items)


@pytest.mark.parametrize('kind,mode,items', [
    ('cat','personal',['small_cap','flower_crown']), ('cat','personal',['bandana','bow_tie']), ('cat','personal',['scarf','bandana']),
    ('fern','personal',['small_cap']), ('cactus','personal',['small_trellis']),
    ('cat','personal',['https://example.com/a.svg']), ('cat','personal',['<svg/>']),
    ('cat','arbitrary',[]), ('cat','personal',['small_cap','bandana','scarf']),
])
def test_invalid_equipment_rejected(kind, mode, items):
    with pytest.raises(ValueError): wardrobe.validate(kind,mode,items)


def account(app_mod):
    conn=st.connect(app_mod.DB)
    user=st.get_admin_user(conn,'admin@test.local')
    return conn,user['id']


def test_migration_preferences_and_care_survive(app_mod):
    conn,uid=account(app_mod)
    st.set_user_avatar(conn,uid,'cat','Miso')
    st.record_avatar_care(conn,uid)
    before=st.get_user_profile(conn,uid)
    st.set_avatar_wardrobe(conn,uid,'cat','personal',['small_cap','bandana'])
    st.init_db(conn);st.init_db(conn)
    after=st.get_user_profile(conn,uid)
    assert after['avatar_wardrobe']['mode']=='personal'
    assert set(after['avatar_wardrobe']['items'])=={'small_cap','bandana'}
    assert after['avatar_name']=='Miso' and after['avatar_last_care_at']==before['avatar_last_care_at']
    st.set_user_avatar(conn,uid,'fern','Miso')
    assert st.get_user_profile(conn,uid)['avatar_wardrobe']=={'mode':'personal','items':[]}
    conn.execute("UPDATE admin_user SET avatar_equipment=? WHERE id=?",('["retired", {"x":1}]',uid));conn.commit()
    assert st.get_user_profile(conn,uid)['avatar_wardrobe']['items']==[]
    conn.close()


def test_preview_is_read_only_and_save_cross_surface(admin, app_mod):
    conn,uid=account(app_mod);st.set_user_avatar(conn,uid,'cat','Miso');conn.close()
    preview=admin.get('/me/companion-preview',params={'kind':'cat','stage':3,'mode':'personal','primary':'small_cap','secondary':'bandana'})
    assert preview.status_code==200 and 'data-equipment="small_cap"' in preview.text
    conn,uid=account(app_mod);assert st.get_user_profile(conn,uid)['avatar_wardrobe']['mode']=='seasonal';conn.close()
    saved=admin.post('/me',data={'avatar_kind':'cat','avatar_name':'Miso','avatar_appearance_mode':'personal','avatar_primary':'small_cap','avatar_secondary':'bandana'},follow_redirects=False)
    assert saved.status_code==303
    for path in ['/?view=me','/wellness','/me']:
        response=admin.get(path)
        assert response.status_code==200, response.text[:300]
        assert 'data-avatar-mode="personal"' in response.text
        assert 'data-equipment="small_cap"' in response.text and 'data-equipment="bandana"' in response.text
    global_art=admin.get("/appearance/avatar/cat/3").text
    assert 'data-avatar-mode="seasonal"' in global_art and 'data-equipment=' not in global_art
    # Explicit administrator samples ignore personal preferences.
    response=admin.get('/admin/appearance')
    assert 'data-equipment=' not in response.text


def test_invalid_save_is_atomic_and_cross_origin_denied(admin, app_mod):
    conn,uid=account(app_mod);st.set_user_avatar(conn,uid,'cat','Original');conn.close()
    data={'avatar_kind':'cat','avatar_name':'Forged','avatar_appearance_mode':'personal','avatar_primary':'ceramic'}
    response=admin.post('/me',data=data)
    assert response.status_code==200 and 'compatible' in response.text
    conn,uid=account(app_mod);assert st.get_user_profile(conn,uid)['avatar_name']=='Original';conn.close()
    assert admin.post('/me',data=data,headers={'Origin':'https://attacker.invalid'}).status_code==403
    assert admin.get('/me/companion-preview?kind=cat&mode=personal&primary=bogus').status_code==400


def test_preferences_are_actor_scoped(admin, viewer, client, app_mod):
    conn,uid=account(app_mod);st.set_user_avatar(conn,uid,'cat','Miso');st.set_avatar_wardrobe(conn,uid,'cat','personal',['small_cap']);conn.close()
    assert 'data-equipment="small_cap"' in admin.get('/?view=me').text
    assert 'data-equipment="small_cap"' not in viewer.get('/?view=me').text
    assert client.get('/me/companion-preview?kind=cat',follow_redirects=False).status_code in (302,303,401,403)


def test_modes_suppress_outfits_but_keep_equipment_saved(admin, app_mod):
    conn,uid=account(app_mod);st.set_user_avatar(conn,uid,'cat','Miso');conn.close()
    for mode in ['personal','none','seasonal']:
        response=admin.post('/me',data={'avatar_kind':'cat','avatar_name':'Miso','avatar_appearance_mode':mode,'avatar_primary':'small_cap'},follow_redirects=False)
        assert response.status_code==303
        page=admin.get('/?view=me').text
        if mode=='personal': assert 'data-equipment="small_cap"' in page
        else: assert 'data-equipment="small_cap"' not in page
        conn,uid=account(app_mod);assert st.get_user_profile(conn,uid)['avatar_wardrobe']['items']==['small_cap'];conn.close()


def test_all_stage_item_and_seasonal_combinations_render(app_mod):
    from lxml import etree
    macros=app_mod.templates.env.get_template('_avatars.html').module
    count=0
    for kind in st.AVATAR_KEYS:
        primary=[key for key,entry in wardrobe.CATALOG.items() if kind in entry['species'] and entry['slot']=='primary']
        secondary=[key for key,entry in wardrobe.CATALOG.items() if kind in entry['species'] and entry['slot']=='secondary']
        for stage in range(1,7):
            for first in [None]+primary:
                for second in [None]+secondary:
                    keys=[key for key in [first,second] if key]
                    art=str(macros.avatar_svg(kind,stage,preferences=wardrobe.validate(kind,'personal',keys)))
                    tree=etree.fromstring(art.encode())
                    items=tree.xpath('.//*[@data-equipment]')
                    assert sorted(item.get('data-equipment') for item in items)==sorted(keys), (kind,stage,keys)
                    assert len(items)<=2 and not tree.xpath('.//script | .//foreignObject')
                    count+=1
            for costume,month in [('default',m) for m in range(13)]+[(o,m) for o,m in [('halloween',10),('halloween_vampire',10),('halloween_pumpkin',10),('christmas',12)]]:
                tree=etree.fromstring(str(macros.avatar_svg(kind,stage,month,costume)).encode())
                assert not tree.xpath('.//*[@data-equipment]')
    assert count==1584
