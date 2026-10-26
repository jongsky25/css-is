/* Private previews and form helpers; publishing always goes through the server. */
(function(){
  'use strict';
  var editor=document.getElementById('appearance-editor');
  if(!editor)return;
  document.querySelectorAll('[data-match-outfit]').forEach(function(button){
    button.addEventListener('click',function(){
      var form=button.closest('form');
      form.elements.outfit.value=form.querySelector('[name="theme"]:checked').value;
      form.elements.outfit.dispatchEvent(new Event('change',{bubbles:true}));
    });
  });
  function updatePreview(){
    var params=new URLSearchParams({appearance_preview:'1',view:'me',
      theme:editor.querySelector('[name="theme"]:checked').value,
      outfit:editor.elements.outfit.value,effects:editor.elements.effects.checked?'1':'0',
      artwork:editor.elements.artwork.checked?'1':'0',banner:editor.elements.banner.value});
    var frame=document.getElementById('appearance-preview');
    // An edited preview must load even outside the browser's lazy-load margin.
    frame.loading='eager';
    frame.src='/?'+params.toString();
  }
  var previewTimer;
  document.getElementById('appearance-preview-button').addEventListener('click',function(){clearTimeout(previewTimer);updatePreview();});
  document.querySelectorAll('[name="theme"]').forEach(function(radio){
    radio.addEventListener('change',function(){radio.form.elements.artwork.checked=radio.value==='halloween';});
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
