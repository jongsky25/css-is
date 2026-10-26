import pytest
from scripts.avatar_baseline.analyze_native_ownership import BUILD_ID,normalize,summarize


def profile():
    return {'modules':[{'uuid':BUILD_ID.upper()+'0','baseAddress':'0x1000','size':256}],
        'samples':[{'size':16,'total':32768,'stack':['0x1010 unknown','0x1010 unknown','0x2000 external']} ]}


def test_module_relative_addresses_and_external_frames():
    samples=normalize(profile())
    assert samples[0]['frames']==[{'offset':'0x10'},{'offset':'0x10'},{'external_frame':'0x2000 external'}]


def test_wrong_build_rejected():
    p=profile();p['modules'][0]['uuid']='deadbeef'
    with pytest.raises(ValueError):normalize(p)


def test_duplicate_module_rejected():
    p=profile();p['modules']*=2
    with pytest.raises(ValueError):normalize(p)


@pytest.mark.parametrize('field,value',[('size',0),('size',-1),('total',float('nan')),('total',0)])
def test_bad_sizes_rejected(field,value):
    p=profile();p['samples'][0][field]=value
    with pytest.raises(ValueError):normalize(p)


def test_inclusive_frames_not_double_counted_or_confused_with_object_size():
    result=summarize([{'samples':normalize(profile())}],{'0x10':{'function':'Document::Create'}})[0]
    assert result['sampled_object_bytes']==16
    assert result['estimated_native_sample_bytes']==32768
    assert result['inclusive_functions']['Document::Create']=={'sample_count':1,'estimated_bytes':32768}
    assert result['inclusive_functions']['0x2000 external']['estimated_bytes']==32768
