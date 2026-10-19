import { CalendarBlank } from '@phosphor-icons/react';
import { clock, normalizeTimetable } from './timetable.js';

const monthDay = (day) => `${Number(day.slice(5, 7))}月${Number(day.slice(8, 10))}日`;
const shortDate = (day) => `${Number(day.slice(5, 7))}/${Number(day.slice(8, 10))}`;

export function WeekTimetable({ detail }) {
  const table = normalizeTimetable(detail);
  if (table.error) return <p className="form-error" role="alert">{table.error}</p>;
  const { days, weekStart, weekEnd, today, startHour, endHour, loginMode, count } = table;
  const hourHeight = 56;
  const height = (endHour - startHour) * hourHeight;
  const hours = Array.from({ length: endHour - startHour }, (_, index) => startHour + index);
  const modeLabel = loginMode === 'direct' ? '校园网直连' : loginMode === 'vpn' ? 'WebVPN' : '';
  return <div className="week-timetable">
    <div className="timetable-toolbar"><div className="timetable-date"><CalendarBlank size={21} weight="regular" /><strong>{monthDay(weekStart)} — {monthDay(weekEnd)}</strong><span>共 {count} 节课</span></div>{modeLabel && <span className="timetable-mode">{modeLabel}</span>}</div>
    <div className="timetable-legend" aria-label="签到状态说明">
      <span><i className="legend-dot attended" />正常出勤</span><span><i className="legend-dot upcoming" />待上课 / 待签到</span><span><i className="legend-dot missed" />未签到</span><span><i className="legend-dot late" />迟到签到</span>
    </div>
    {!count ? <div className="timetable-empty"><CalendarBlank size={40} weight="light" /><p>本周暂无课程</p></div> : <div className="timetable-scroll" tabIndex={0} aria-label="本周课程表，可上下或左右滚动">
      <div className="timetable-grid" role="table" aria-label="本周课程表">
        <div className="timetable-grid-header" role="row"><div className="timetable-corner" role="columnheader">时间</div>{days.map((day) => <div key={day.key} role="columnheader" className={`timetable-day-heading ${day.key === today ? 'today' : ''}`}><strong>{day.label}</strong><span>{shortDate(day.key)}{day.key === today && <em>今天</em>}</span></div>)}</div>
        <div className="timetable-grid-body" role="row" style={{ height }}><div className="timetable-time-axis" role="rowheader">{hours.map((hour, index) => <span key={hour} className={`hour-label ${index === 0 ? 'first' : ''}`} style={{ top: index * hourHeight }}>{clock(hour * 60)}</span>)}</div>
          {days.map((day) => <div key={day.key} role="cell" aria-label={`${day.label} ${monthDay(day.key)}课程`} className={`timetable-day-track ${day.key === today ? 'today' : ''}`}>
            {hours.map((hour, index) => <div key={hour} className="timetable-hour-line" style={{ top: index * hourHeight }} />)}
            {day.events.map((event) => {
              const time = `${clock(event.startMinute)}–${clock(event.endMinute)}`;
              const description = `${event.name}，${day.label} ${time}，${event.label}${event.teacher ? `，${event.teacher}` : ''}`;
              return <article key={event.id} className={`timetable-course ${event.tone}`} aria-label={description} title={description}
                style={{ top: (event.startMinute - startHour * 60) / 60 * hourHeight + 3,
                  height: Math.max(26, (event.endMinute - event.startMinute) / 60 * hourHeight - 6),
                  left: `calc(${event.lane / event.lanes * 100}% + 4px)`, width: `calc(${100 / event.lanes}% - 8px)` }}>
                <h3>{event.name}</h3><time>{time}</time><span className="course-attendance">{event.label}</span>
              </article>;
            })}
          </div>)}
        </div>
      </div>
    </div>}
    <div className="timetable-footnote"><span>按北京时间显示 · 状态以学校系统为准</span><span className="timetable-scroll-hint">左右滑动查看整周</span></div>
  </div>;
}
