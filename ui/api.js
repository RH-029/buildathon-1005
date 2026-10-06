async function request(path, body) {
  let response;
  try {
    response = await fetch(path, { method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body), cache: 'no-store' });
  } catch {
    throw new Error('Cannot reach TravelMind. Start ui_server.py and try again.');
  }
  let result;
  try { result = await response.json(); }
  catch { throw new Error('The TravelMind API is unavailable. Open the page through ui_server.py.'); }
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status}).`);
  return result;
}

export const health = () => request('/api/health');
export const planTrip = data => request('/api/plan', data);
export const getMemories = (travelerId, query) => request('/api/memories', { traveler_id: travelerId, query });
export const savePreferences = data => request('/api/preferences', data);
export const saveFeedback = data => request('/api/feedback', data);

// Interpret wall-clock inputs in Pacific time, independent of the browser timezone.
// Validate again after offset calculation to reject the DST spring-forward gap.
export function pacificTimestamp(date, time) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}$/.test(time)) throw new Error('Choose an outing date and times.');
  const wall = Date.parse(`${date}T${time}:00Z`);
  if (!Number.isFinite(wall)) throw new Error('Choose a valid date and time.');
  const offsetFormatter = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', timeZoneName: 'longOffset' });
  function offsetAt(value) {
    const text = offsetFormatter.formatToParts(new Date(value)).find(part => part.type === 'timeZoneName').value;
    const match = text.match(/GMT([+-])(\d{2}):(\d{2})/);
    if (!match) throw new Error('Your browser cannot resolve Pacific time offsets.');
    return { label: `${match[1]}${match[2]}:${match[3]}`, milliseconds: (match[1] === '+' ? 1 : -1) * (Number(match[2]) * 60 + Number(match[3])) * 60000 };
  }
  let instant = wall;
  for (let index = 0; index < 4; index++) instant = wall - offsetAt(instant).milliseconds;
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(instant));
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  if (`${values.year}-${values.month}-${values.day}` !== date || `${values.hour}:${values.minute}` !== time) throw new Error('That Pacific time does not exist. Choose another time.');
  return `${date}T${time}:00${offsetAt(instant).label}`;
}
