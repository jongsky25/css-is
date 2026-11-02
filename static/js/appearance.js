/* Refresh seasonal styling without reloading pages or interrupting forms. */
(function(){
  'use strict';
  var root=document.documentElement;
  if(root.dataset.appearancePreview==='1')return;
  var timer,busy=false;
  async function refresh(){
    if(busy || document.hidden)return;
    clearTimeout(timer);timer=null;
    busy=true;
    try{
      var response=await fetch('/appearance/current',{cache:'no-store',headers:{Accept:'application/json'}});
      if(!response.ok || !response.headers.get('content-type').includes('application/json'))return;
      var active=await response.json();
      root.dataset.season=active.theme;
      root.dataset.seasonEffects=active.effects?'1':'0';
      root.dataset.seasonArtwork=active.artwork?'1':'0';
      if(window.ocNewYear)window.ocNewYear.sync(active);
      document.querySelectorAll('[data-season-banner-message], [data-celebration-message]').forEach(function(message){message.textContent=active.banner;});
      var statusFields={theme:active.theme_name,outfit:active.outfit_name,source:active.source.charAt(0).toUpperCase()+active.source.slice(1)};
      Object.keys(statusFields).forEach(function(key){
        var field=document.querySelector('[data-appearance-active-'+key+']');
        if(field)field.textContent=statusFields[key];
      });
      var detail=document.querySelector('[data-appearance-active-detail]');
      if(detail){
        detail.hidden=active.source==='default';
        detail.classList.toggle('appearance-warning',active.source==='manual');
        if(active.source==='scheduled')detail.textContent='Scheduled event: '+active.event_name;
        if(active.source==='manual'){
          var until=active.override_expires_at ? new Intl.DateTimeFormat('en-PH',{timeZone:'Asia/Manila',dateStyle:'medium',timeStyle:'short'}).format(new Date(active.override_expires_at*1000))+' Asia/Manila' : 'you turn it off';
          detail.textContent='Manual override is active. Scheduled appearances are paused until '+until+'.';
        }
      }
      var overrideNote=document.querySelector('[data-appearance-override-note]');
      if(overrideNote)overrideNote.hidden=active.source!=='manual';
      var avatars=Array.from(document.querySelectorAll('svg[data-avatar-kind]')).filter(function(svg){
        return (!svg.dataset.avatarMode || svg.dataset.avatarMode==='seasonal') && !svg.closest('[data-appearance-sample]') && (Number(svg.dataset.avatarMonth)!==active.month || svg.dataset.avatarOutfit!==active.outfit);
      });
      var pairs=new Map();
      avatars.forEach(function(svg){pairs.set(svg.dataset.avatarKind+'/'+svg.dataset.avatarStage,null);});
      await Promise.all(Array.from(pairs.keys()).map(async function(pair){
        var art=await fetch('/appearance/avatar/'+pair,{cache:'no-store'});
        if(!art.ok)return;
        var doc=new DOMParser().parseFromString(await art.text(),'text/html');
        var source=doc.querySelector('svg[data-avatar-month]');
        if(!source || Number(source.dataset.avatarMonth)!==active.month || source.dataset.avatarOutfit!==active.outfit)return;
        pairs.set(pair,doc.querySelectorAll('.av-acc,.av-costume-back,.av-costume-front'));
      }));
      avatars.forEach(function(svg){
        var art=pairs.get(svg.dataset.avatarKind+'/'+svg.dataset.avatarStage);
        var anchors=svg.querySelectorAll('.av-acc,.av-costume-back,.av-costume-front');
        if(!art || anchors.length!==art.length)return;
        anchors.forEach(function(anchor,i){anchor.replaceChildren.apply(anchor,Array.from(art[i].childNodes).map(function(node){return document.importNode(node,true);}));});
        svg.dataset.avatarMonth=String(active.month);
        svg.dataset.avatarOutfit=active.outfit;
      });
      var delay=active.next_transition ? (active.next_transition-active.server_time)*1000+250 : 60000;
      clearTimeout(timer);
      timer=setTimeout(refresh,Math.max(1000,Math.min(60000,delay)));
    }catch(error){/* A transient network failure leaves the last valid styling. */}
    finally{busy=false;if(!timer)timer=setTimeout(refresh,60000);}
  }
  document.addEventListener('visibilitychange',function(){if(!document.hidden){clearTimeout(timer);timer=null;refresh();}});
  window.addEventListener('focus',function(){clearTimeout(timer);timer=null;refresh();});
  refresh();
})();
