/* Server-synchronized countdown. No remote audio, particles or per-second requests. */
(function(){
  'use strict';
  var clock=document.querySelector('[data-newyear-clock]');
  if(!clock)return;
  var root=document.documentElement, timer=clock.querySelector('[data-countdown]'),
      greeting=clock.querySelector('[data-newyear-greeting]'), target=null, stamp=null,
      base=null, previous=null, active=false, handle=null, confettiTimer=null;
  function stop(){clearTimeout(handle);handle=null;}
  function tick(){
    stop();
    if(!active || document.hidden || target===null || stamp===null)return;
    var remaining=Math.max(0,Math.ceil(target-(stamp+(performance.now()-base)/1000)));
    timer.hidden=remaining===0;greeting.hidden=remaining!==0;
    var values=[Math.floor(remaining/86400),Math.floor(remaining%86400/3600),Math.floor(remaining%3600/60),remaining%60];
    clock.querySelectorAll('[data-countdown-unit]').forEach(function(el,i){el.textContent=String(values[i]).padStart(2,'0');});
    if(previous!==null && previous>0 && remaining===0){
      clock.querySelector('[data-newyear-announcement]').textContent='Happy New Year, Office Connect!';
      var key='oc-newyear-celebrated-'+target, seen=true;
      try{seen=sessionStorage.getItem(key)==='1';sessionStorage.setItem(key,'1');}catch(error){/* No replay if storage is unavailable. */}
      if(!seen && root.dataset.seasonEffects==='1' && root.dataset.seasonArtwork==='1' && !matchMedia('(prefers-reduced-motion: reduce)').matches){
        clock.classList.add('celebrating');clearTimeout(confettiTimer);
        confettiTimer=setTimeout(function(){clock.classList.remove('celebrating');},4000);
      }
    }
    previous=remaining;
    if(remaining>0)handle=setTimeout(tick,250);
  }
  function sync(data){
    var next=Number(data.newyear_target), server=Number(data.server_time);
    if(!Number.isFinite(next)||!Number.isFinite(server)||next<=0)return;
    var wasActive=active;
    active=data.theme==='newyear';
    if(next!==target || !wasActive || !active)previous=null;
    target=next;stamp=server;base=performance.now();
    document.querySelectorAll('[data-newyear-year]').forEach(function(el){el.textContent=String(data.target_year);});
    if(!active){clock.classList.remove('celebrating');stop();return;}
    tick();
  }
  window.ocNewYear={sync:sync};
  sync({theme:root.dataset.season,newyear_target:clock.dataset.target,server_time:clock.dataset.serverTime,target_year:clock.dataset.year});
  document.addEventListener('visibilitychange',function(){previous=null;if(document.hidden)stop();else tick();});
  window.addEventListener('focus',function(){previous=null;tick();});
})();
