/* Private previews and form helpers; publishing always goes through the server. */
(function(){
  'use strict';
  var editor=document.getElementById('appearance-editor');
  if(!editor)return;
  document.querySelectorAll('[data-match-outfit]').forEach(function(button){
    button.addEventListener('click',function(){
      var form=button.closest('form');
      var theme=form.querySelector('[name="theme"]:checked').value;
      form.elements.outfit.value=theme==='newyear'?'default':theme;
      form.elements.outfit.dispatchEvent(new Event('change',{bubbles:true}));
    });
  });
  function showOutfits(form){
    var theme=form.querySelector('[name="theme"]:checked').value;
    var outfit=form.elements.outfit.value;
    var mismatch=form.querySelector('[data-outfit-mismatch]');
    if(mismatch)mismatch.hidden=!((theme==='christmas' && outfit.startsWith('halloween')) || (theme==='halloween' && outfit.startsWith('christmas')));
    if(form===editor){
      document.querySelectorAll('[data-outfit-group]').forEach(function(group){
        group.open=group.dataset.outfitGroup===theme || group.dataset.outfitGroup==='default';
        group.style.order=group.dataset.outfitGroup===theme?'0':'1';
      });
    }
  }
  document.querySelectorAll('[data-pick-outfit]').forEach(function(button){
    button.addEventListener('click',function(){editor.elements.outfit.value=button.dataset.pickOutfit;editor.elements.outfit.dispatchEvent(new Event('change',{bubbles:true}));});
  });
  document.querySelectorAll('form:has([data-match-outfit])').forEach(function(form){
    showOutfits(form);form.addEventListener('change',function(event){if(event.target.name==='theme'||event.target.name==='outfit')showOutfits(form);});
  });
  function updatePreview(){
    var params=new URLSearchParams({appearance_preview:'1',view:'me',
      theme:editor.querySelector('[name="theme"]:checked').value,
      outfit:editor.elements.outfit.value,effects:editor.elements.effects.checked?'1':'0',
      artwork:editor.elements.artwork.checked?'1':'0',banner:editor.elements.banner.value,target_year:editor.elements.target_year.value});
    document.getElementById('appearance-preview').src='/?'+params.toString();
  }
  var previewTimer;
  document.getElementById('appearance-preview-button').addEventListener('click',function(){clearTimeout(previewTimer);updatePreview();});
  document.querySelectorAll('[name="theme"]').forEach(function(radio){
    radio.addEventListener('change',function(){radio.form.elements.artwork.checked=radio.value!=='default';
      var message=radio.form.elements.banner;
      if(['','A little spooky. Still productive.','A season of gratitude. A little brighter together.','A brighter year, together.'].includes(message.value))message.value='';});
  });
  editor.addEventListener('change',function(event){
    if(event.target.name==='expires')return;
    clearTimeout(previewTimer);previewTimer=setTimeout(updatePreview,250);
  });
  editor.elements.banner.addEventListener('input',function(){clearTimeout(previewTimer);previewTimer=setTimeout(updatePreview,500);});
  document.querySelectorAll('[data-preview-width]').forEach(function(button){
    button.addEventListener('click',function(){
      document.getElementById('appearance-preview').style.width=button.dataset.previewWidth;
      document.querySelectorAll('[data-preview-width]').forEach(function(other){other.setAttribute('aria-pressed',String(other===button));});
    });
  });
  var dirtyForms=new Set();
  document.querySelectorAll('[data-dirty-track]').forEach(function(form){
    form.addEventListener('input',function(){dirtyForms.add(form);});
    form.addEventListener('change',function(){dirtyForms.add(form);});
  });
  document.addEventListener('submit',function(event){
    if(event.defaultPrevented)return;
    if(dirtyForms.size && (dirtyForms.size>1 || !dirtyForms.has(event.target)) &&
       !window.confirm('Continue and discard your other unsaved appearance edits?')){
      event.preventDefault();return;
    }
    dirtyForms.clear();
  });
  window.addEventListener('beforeunload',function(event){if(dirtyForms.size){event.preventDefault();event.returnValue='';}});
})();
