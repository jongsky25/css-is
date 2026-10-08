// Shared profile-photo crop editor: drag + zoom into a circular avatar, baked to a
// square JPEG data URL in the form's hidden photo_data input.
// Markup/CSS live in templates/_photo_crop.html.
//   PhotoCrop.init({ hidden, preview })   -> returns { pick(input) }
(function () {
  var V = 240, OUT = 512;                       // editor viewport px, baked output px
  var MAX_BYTES = 5000000;

  function init(opts) {
    var hidden = typeof opts.hidden === 'string' ? document.querySelector(opts.hidden) : opts.hidden;
    var preview = typeof opts.preview === 'string' ? document.querySelector(opts.preview) : opts.preview;
    var editor = document.getElementById('photoEditor');
    var stage = document.getElementById('cropStage');
    var cvs = document.getElementById('cropCanvas');
    var zoom = document.getElementById('cropZoom');
    var adjustBtn = document.getElementById('adjustBtn');
    if (!hidden || !preview || !editor || !stage || !cvs || !zoom) return null;
    var cctx = cvs.getContext('2d');
    var crop = null;                            // { img, min, scale, ox, oy }
    var drag = null;

    function existingSrc() {
      if (hidden.value) return hidden.value;
      var im = preview.querySelector('img');
      return im ? im.getAttribute('src') : '';
    }
    function syncAdjust() { if (adjustBtn) adjustBtn.hidden = !existingSrc(); }

    function clamp() {
      var w = crop.img.width * crop.scale, h = crop.img.height * crop.scale;
      crop.ox = Math.min(0, Math.max(V - w, crop.ox));
      crop.oy = Math.min(0, Math.max(V - h, crop.oy));
    }
    function bake() {
      var k = OUT / V;
      var c = document.createElement('canvas'); c.width = OUT; c.height = OUT;
      var x = c.getContext('2d');
      x.fillStyle = '#fff'; x.fillRect(0, 0, OUT, OUT);
      x.drawImage(crop.img, crop.ox * k, crop.oy * k, crop.img.width * crop.scale * k, crop.img.height * crop.scale * k);
      var d = c.toDataURL('image/jpeg', 0.85);
      hidden.value = d;
      preview.innerHTML = '<img src="' + d + '" alt="" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">';
    }
    function render() {
      if (!crop) return;
      clamp();
      cctx.clearRect(0, 0, V, V);
      cctx.drawImage(crop.img, crop.ox, crop.oy, crop.img.width * crop.scale, crop.img.height * crop.scale);
      bake();
    }
    function open(src) {
      var img = new Image();
      img.onload = function () {
        var min = Math.max(V / img.width, V / img.height);   // "cover" the circle at zoom 1
        crop = { img: img, min: min, scale: min, ox: 0, oy: 0 };
        crop.ox = (V - img.width * crop.scale) / 2;           // start centred
        crop.oy = (V - img.height * crop.scale) / 2;
        zoom.value = 1;
        editor.hidden = false;
        render();
        syncAdjust();
      };
      img.src = src;
    }

    function pick(input) {
      var f = input.files && input.files[0];
      if (!f) return;
      if (f.size > MAX_BYTES) {
        alert('That image is a bit large — please choose one under 5 MB.');
        input.value = '';
        return;
      }
      var r = new FileReader();
      r.onload = function () { open(r.result); };
      r.readAsDataURL(f);
    }

    zoom.addEventListener('input', function () {
      if (!crop) return;
      var s = crop.min * parseFloat(zoom.value);
      var cx = (V / 2 - crop.ox) / crop.scale;               // keep viewport centre fixed
      var cy = (V / 2 - crop.oy) / crop.scale;
      crop.scale = s;
      crop.ox = V / 2 - cx * s;
      crop.oy = V / 2 - cy * s;
      render();
    });
    stage.addEventListener('pointerdown', function (e) {
      if (!crop) return;
      drag = { x: e.clientX, y: e.clientY, ox: crop.ox, oy: crop.oy };
      stage.setPointerCapture(e.pointerId);
    });
    stage.addEventListener('pointermove', function (e) {
      if (!drag) return;
      crop.ox = drag.ox + (e.clientX - drag.x);
      crop.oy = drag.oy + (e.clientY - drag.y);
      render();
    });
    stage.addEventListener('pointerup', function () { drag = null; });
    stage.addEventListener('pointercancel', function () { drag = null; });
    document.getElementById('cropDone').addEventListener('click', function () { editor.hidden = true; });
    if (adjustBtn) {
      adjustBtn.addEventListener('click', function () {
        var src = existingSrc();
        if (src) open(src);
      });
    }
    syncAdjust();
    return { pick: pick };
  }

  window.PhotoCrop = { init: init };
})();
