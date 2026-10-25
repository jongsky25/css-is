/* Optional read-only hour grid. The authorized native weekly list is the fallback. */
(function () {
  'use strict';
  var root = document.querySelector('[data-calendar-schedule]');
  var data = document.getElementById('cal-schedule-data');
  if (!root || !data) return;
  var grid = document.getElementById('cal-schedule-grid');
  var list = document.getElementById('cal-schedule-list');
  var status = root.querySelector('[data-schedule-status]');
  var tools = root.querySelector('[data-schedule-tools]');
  var toggle = root.querySelector('[data-schedule-toggle]');
  var day = document.getElementById('cal-schedule-day');
  var calendar;
  try {
    var snapshot = JSON.parse(data.textContent);
    if (!window.FullCalendar || !window.luxon || !window.FullCalendar.Luxon3) throw new Error('unavailable');
    var narrow = window.matchMedia('(max-width: 759px)');
    grid.hidden = false; // Measure a visible container; keep the list until render succeeds.
    calendar = new FullCalendar.Calendar(grid, {
      initialView: narrow.matches ? 'timeGridDay' : 'timeGridWeek',
      initialDate: snapshot.selected, now: snapshot.today, firstDay: 1,
      timeZone: snapshot.zone, validRange: { start: snapshot.start, end: snapshot.end },
      headerToolbar: false, height: 620, scrollTime: '07:00:00',
      slotDuration: '00:30:00', allDayText: 'All-day / time not set', dayMaxEventRows: 4,
      eventTimeFormat: { hour: '2-digit', minute: '2-digit', hour12: false },
      slotLabelFormat: { hour: '2-digit', minute: '2-digit', hour12: false },
      editable: false, selectable: false, droppable: false, eventInteractive: false,
      nowIndicator: false, eventMinHeight: 30, events: snapshot.events,
      eventClassNames: function () { return ['cal-schedule-event']; },
      eventDidMount: function (info) { info.el.setAttribute('data-tone', info.event.extendedProps.tone); },
      eventContent: function (info) {
        var props = info.event.extendedProps;
        // No event.url: the library must not navigate before calendar.js opens
        // the existing item sheet. This inner native anchor owns navigation.
        var node = document.createElement(props.href ? 'a' : 'span');
        if (props.href) node.setAttribute('href', props.href);
        node.className = 'cal-schedule-link';
        var time = document.createElement('span');
        time.className = 'cal-schedule-clock';
        time.textContent = info.timeText || props.timeLabel;
        var title = document.createElement('strong');
        title.textContent = info.event.title;
        var meta = document.createElement('span');
        meta.textContent = [props.owner, props.status].filter(Boolean).join(' · ');
        node.appendChild(time); node.appendChild(title); node.appendChild(meta);
        node.setAttribute('aria-label', [time.textContent, info.event.title, meta.textContent].join(' · '));
        node.title = node.getAttribute('aria-label');
        return { domNodes: [node] };
      }
    });
    calendar.render();
    list.hidden = true;
    tools.hidden = false;
    status.textContent = 'Hour grid ready.';
    toggle.addEventListener('click', function () {
      list.hidden = !list.hidden;
      toggle.setAttribute('aria-expanded', String(!list.hidden));
      toggle.textContent = list.hidden ? 'Show weekly list' : 'Hide weekly list';
      if (!list.hidden) list.querySelector('h3').focus();
    });
    day.addEventListener('change', function () {
      calendar.changeView(narrow.matches ? 'timeGridDay' : 'timeGridWeek', day.value);
    });
    var resize = function () {
      var focused = grid.contains(document.activeElement);
      calendar.changeView(narrow.matches ? 'timeGridDay' : 'timeGridWeek', day.value);
      if (focused) grid.focus();
    };
    if (narrow.addEventListener) narrow.addEventListener('change', resize);
    else narrow.addListener(resize);
  } catch (error) {
    if (calendar) { try { calendar.destroy(); } catch (ignored) {} }
    grid.hidden = true; tools.hidden = true; list.hidden = false;
    status.textContent = 'The hour grid is unavailable. Use the complete weekly list below.';
  }
})();
