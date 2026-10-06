import { health, planTrip, getMemories, savePreferences, saveFeedback, pacificTimestamp } from './api.js';

const form = document.querySelector('#trip-form');
const status = document.querySelector('#status');
const cards = document.querySelector('#cards');
const summary = document.querySelector('#memory-summary');
const submit = document.querySelector('#plan-button');
const crew = document.querySelector('#travelers');
const addButton = document.querySelector('#add-traveler');
const tags = ['nature', 'scenic', 'quiet', 'art', 'food', 'walking', 'hiking', 'social'];
let sequence = 0;
let activeRequest;
let retrieved = {};

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function tagChoices(container, name, selected = []) {
  for (const tag of tags) {
    const label = element('label');
    const checkbox = element('input');
    checkbox.type = 'checkbox'; checkbox.name = name; checkbox.value = tag; checkbox.checked = selected.includes(tag);
    label.append(checkbox, element('span', tag)); container.append(label);
  }
}
function selectedTags(container, name) {
  return [...container.querySelectorAll(`input[name="${name}"]:checked`)].map(input => input.value);
}
function syncCrew() {
  const editors = [...crew.querySelectorAll('.traveler-editor')];
  editors.forEach((editor, index) => {
    editor.querySelector('legend').textContent = `Traveler ${index + 1}`;
    editor.querySelector('.remove-traveler').disabled = editors.length === 1;
  });
  addButton.disabled = editors.length >= 8;
}
function addTraveler(id = '', name = '', interests = []) {
  const editor = document.querySelector('#traveler-template').content.firstElementChild.cloneNode(true);
  const prefix = `traveler-${++sequence}`;
  editor.querySelectorAll('[data-field]').forEach(input => { input.id = `${prefix}-${input.dataset.field}`; });
  editor.querySelectorAll('[data-for]').forEach(label => { label.htmlFor = `${prefix}-${label.dataset.for}`; });
  editor.querySelector('[data-field=id]').value = id;
  editor.querySelector('[data-field=name]').value = name;
  tagChoices(editor.querySelector('.traveler-interests'), 'interests', interests);
  editor.querySelector('.remove-traveler').addEventListener('click', () => { editor.remove(); syncCrew(); });
  const remember = editor.querySelector('.remember-button');
  const message = editor.querySelector('.traveler-status');
  remember.addEventListener('click', async () => {
    const idInput = editor.querySelector('[data-field=id]');
    const travelerId = idInput.value.trim();
    const interests = selectedTags(editor, 'interests');
    if (!travelerId || !idInput.reportValidity()) { message.textContent = 'Enter your traveler ID first.'; return; }
    if (!interests.length) { message.textContent = 'Select the interests you want to remember.'; return; }
    remember.disabled = true;
    message.textContent = 'Saving your stated interests to Mem0…';
    try {
      const result = await savePreferences({ traveler_id: travelerId, text: `I enjoy ${interests.join(', ')}.`, signals: { liked_tags: interests } });
      if (!['saved', 'pending'].includes(result.status)) throw new Error('Mem0 did not confirm the save.');
      message.textContent = result.status === 'pending' ? 'Processing memory. It may not be available for the next plan yet.' : 'Interests saved to Mem0. New plans will retrieve them.';
    } catch (error) { message.textContent = error.message; }
    finally { remember.disabled = false; }
  });
  crew.append(editor); syncCrew();
}
addButton.addEventListener('click', () => addTraveler());
addTraveler('demo-jamie', 'Jamie', ['nature', 'scenic']);

function readTraveler(editor, groupBudget) {
  const field = name => editor.querySelector(`[data-field="${name}"]`);
  return { id: field('id').value.trim(), name: field('name').value.trim(),
    interests: selectedTags(editor, 'interests'),
    budget_per_person: field('budget').value === '' ? groupBudget : Number(field('budget').value),
    max_drive_minutes: Number(field('drive').value), max_intensity: Number(field('intensity').value),
    requires_vegetarian: field('vegetarian').checked, requires_step_free: field('step-free').checked };
}
function time(value) {
  return new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', hour: 'numeric', minute: '2-digit' }).format(new Date(value));
}
function renderMemories(request, context) {
  summary.replaceChildren();
  const details = element('details', undefined, 'memory-panel');
  details.append(element('summary', 'Memories retrieved from Mem0'));
  for (const traveler of request.travelers) {
    const rows = retrieved[traveler.id] || [];
    const count = context?.find(item => item.traveler_id === traveler.id)?.retrieved_count;
    details.append(element('h3', `${traveler.name} · ${rows.length} retrieved${count === undefined ? '' : ` · ${count} planner-eligible`}`));
    if (!rows.length) details.append(element('p', 'No matching memories found. Current form preferences still apply.'));
    for (const row of rows) {
      details.append(element('p', row.text || row.memory));
      details.append(element('small', `Memory ${row.id}${row.structured ? ' · explicit preference signals' : ' · text only; no inferred ranking signals'}`));
    }
  }
  details.append(element('small', 'Only explicit structured signals affect memory-based ranking. Earlier free-text records remain visible.'));
  summary.append(details);
}
function renderFeedback(option, request) {
  const details = element('details', undefined, 'feedback-details');
  details.append(element('summary', 'After your outing · share feedback'));
  const feedback = element('form', undefined, 'feedback-form');
  const travelerLabel = element('label', 'Whose experience is this?');
  const travelerSelect = element('select');
  for (const traveler of request.travelers) {
    const choice = element('option', traveler.name); choice.value = traveler.id; travelerSelect.append(choice);
  }
  travelerLabel.append(travelerSelect);
  const textLabel = element('label', 'What did you enjoy or want to change?');
  const text = element('textarea'); text.rows = 3; text.required = true; text.maxLength = 200;
  text.placeholder = 'Your own experience, in your own words'; textLabel.append(text);
  const likes = element('fieldset'); likes.append(element('legend', 'Interests I enjoyed'));
  const likeChoices = element('div', undefined, 'interests'); tagChoices(likeChoices, 'liked_tags'); likes.append(likeChoices);
  const avoids = element('fieldset'); avoids.append(element('legend', 'Interests I would avoid next time'));
  const avoidChoices = element('div', undefined, 'interests'); tagChoices(avoidChoices, 'avoided_tags'); avoids.append(avoidChoices);
  function checkbox(label) {
    const wrapper = element('label', undefined, 'checkline'); const input = element('input'); input.type = 'checkbox';
    wrapper.append(input, document.createTextNode(label)); return { wrapper, input };
  }
  const slower = checkbox('I prefer a slower pace next time');
  const shorter = checkbox('I prefer shorter drives next time');
  const completed = checkbox('I actually completed this outing'); completed.input.required = true;
  const save = element('button', 'Save my feedback to Mem0', 'secondary'); save.type = 'submit';
  const message = element('p', '', 'feedback-status'); message.setAttribute('role', 'status');
  feedback.append(travelerLabel, textLabel, likes, avoids, slower.wrapper, shorter.wrapper, completed.wrapper, save, message);
  feedback.addEventListener('submit', async event => {
    event.preventDefault();
    const liked = selectedTags(likes, 'liked_tags'); const avoided = selectedTags(avoids, 'avoided_tags');
    if (liked.some(tag => avoided.includes(tag))) { message.textContent = 'Choose each interest as either enjoyed or avoided.'; return; }
    if (!completed.input.checked || !text.value.trim()) { message.textContent = 'Describe your experience and confirm that you completed the outing.'; return; }
    save.disabled = true; message.textContent = 'Saving feedback…';
    const travelerId = travelerSelect.value;
    let confirmed = false;
    try {
      const result = await saveFeedback({ traveler_id: travelerId, text: text.value.trim(), completed: true,
        place_id: option.place_id, trip_id: `${request.start.slice(0, 10)}:${option.place_id}`,
        signals: { liked_tags: liked, avoided_tags: avoided, slower_pace: slower.input.checked, short_drives: shorter.input.checked } });
      if (!['saved', 'pending'].includes(result.status)) throw new Error('Mem0 did not confirm the save.');
      confirmed = true;
      feedback.querySelectorAll('input, textarea, select').forEach(input => { input.disabled = true; });
      if (result.status === 'pending') { message.textContent = 'Processing memory. This feedback is not confirmed searchable yet.'; return; }
      message.textContent = 'Saved to Mem0. Generate a new plan to use your feedback.';
      try {
        const fresh = await getMemories(travelerId, `Outing from ${request.origin}. Travel interests, pace and completed outings.`);
        if (activeRequest === request) {
          retrieved[travelerId] = fresh.memories;
          renderMemories(request);
        }
      } catch (error) { message.textContent += ` Memory refresh failed: ${error.message}`; }
    } catch (error) { message.textContent = error.message; }
    finally { save.disabled = confirmed; }
  });
  details.append(feedback); return details;
}
function renderCard(option, request) {
  const card = element('article', undefined, 'card'); card.dataset.category = 'nature';
  const top = element('div', undefined, 'card-top'); const heading = element('div');
  heading.append(element('span', `${option.activity_count} ${option.activity_count === 1 ? 'activity' : 'activities'} · ${option.buffer_minutes} min return margin`, 'tag'), element('h3', option.title));
  top.append(heading, element('span', `$${option.estimated_cost_per_person.toFixed(2)} / person`, 'price'));
  card.append(top, element('p', option.description));
  card.append(element('p', `Home by ${time(option.estimated_return)} PT · ${option.spare_minutes} min before your deadline · $${option.estimated_group_cost.toFixed(2)} for the group`, 'return-info'));
  const reasons = element('div', undefined, 'reasons'); reasons.append(element('h4', 'Why this fits your crew'));
  for (const reason of option.why_this_fits_you) {
    reasons.append(element('p', `${reason.traveler_name || reason.traveler_id || 'Your crew'}: ${reason.text}`));
    if (reason.source === 'memory') reasons.append(element('small', `Memory ${reason.memory_id} · ${reason.effect}`));
  }
  card.append(reasons);
  if (option.group_tradeoffs.length) {
    const tradeoffs = element('div', undefined, 'tradeoffs'); tradeoffs.append(element('h4', 'Group tradeoffs'));
    option.group_tradeoffs.forEach(text => tradeoffs.append(element('p', text))); card.append(tradeoffs);
  }
  const itinerary = element('details', undefined, 'itinerary'); itinerary.append(element('summary', 'Your timeline & sources'));
  const timeline = element('ol', undefined, 'timeline');
  option.timeline.forEach(item => timeline.append(element('li', `${time(item.start)} – ${time(item.end)} · ${item.label}`)));
  itinerary.append(timeline);
  for (const direction of ['outbound_travel', 'return_travel']) {
    const source = option.sources[direction];
    itinerary.append(element('p', `${direction === 'outbound_travel' ? 'Outbound' : 'Return'}: ${source.minutes} min · ${source.source} · ${source.data_status}${source.checked_at ? ` · checked ${source.checked_at}` : ''}`));
  }
  itinerary.append(element('p', `Hours: ${option.sources.hours}. Accessibility: ${option.sources.accessibility}.`));
  itinerary.append(element('p', `Constraint checks: ${option.constraint_checks.basis}.`));
  const link = element('a', 'Check the official venue information ↗');
  try { const url = new URL(option.sources.venue); if (url.protocol === 'https:') { link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; itinerary.append(link); } } catch { /* An invalid source is never made clickable. */ }
  card.append(itinerary, renderFeedback(option, request)); return card;
}
form.addEventListener('submit', async event => {
  event.preventDefault();
  let request;
  try {
    const values = new FormData(form); const budget = Number(values.get('budget'));
    request = { origin: values.get('origin').trim(), start: pacificTimestamp(values.get('date'), values.get('start')),
      end: pacificTimestamp(values.get('date'), values.get('end')), budget_per_person: budget, energy: values.get('energy'),
      allow_repeats: values.has('allow_repeats'), transport: 'car',
      travelers: [...crew.querySelectorAll('.traveler-editor')].map(editor => readTraveler(editor, budget)) };
    if (!request.origin || request.travelers.some(t => !t.id || !t.name)) throw new Error('Enter an origin, traveler IDs and names.');
    if (new Set(request.travelers.map(t => t.id)).size !== request.travelers.length) throw new Error('Each traveler needs a unique ID.');
    if (Date.parse(request.end) <= Date.parse(request.start)) throw new Error('Your return deadline must be after your departure.');
  } catch (error) { status.textContent = error.message; return; }
  activeRequest = request; retrieved = {}; cards.replaceChildren(); summary.replaceChildren();
  submit.disabled = true; status.textContent = 'Retrieving each traveler’s memories and checking your constraints…';
  try {
    const result = await planTrip(request);
    status.textContent = `${result.message} ${request.travelers.map(t => t.name).join(' + ')} · from ${request.origin} · ${request.start.slice(0, 10)}.`;
    const warnings = element('div', undefined, 'data-notice');
    warnings.append(element('strong', 'Planner data sources'));
    warnings.append(element('p', `Catalog status: ${result.data_status}`));
    result.warnings.forEach(warning => warnings.append(element('p', warning))); cards.append(warnings);
    retrieved = result.retrieved_memories; renderMemories(request, result.memory_context);
    if (!result.options.length) cards.append(element('p', 'No outings meet all your requirements. Review the exclusions before changing your constraints.', 'empty-result'));
    else cards.append(...result.options.map(option => renderCard(option, request)));
    if (result.excluded.length) {
      const exclusions = element('details', undefined, 'exclusions'); exclusions.append(element('summary', `${result.excluded.length} outings excluded · see why`));
      result.excluded.forEach(item => exclusions.append(element('p', `${item.place_id}: ${item.reasons.join(' ')}`))); cards.append(exclusions);
    }
  } catch (error) { status.textContent = error.message; }
  finally { submit.disabled = false; }
});

async function initialize() {
  const badge = document.querySelector('#service-status');
  try {
    const service = await health();
    badge.textContent = 'PLANNER + MEM0';
    document.querySelector('#trip-date').value = service.pacific_date;
    document.querySelector('#travel-source').textContent = service.travel === 'google_routes' ? 'Live Google Routes estimates. Venue facts still use the planner’s sample catalog.' : 'Sample drive estimates support Mountain View, Palo Alto and Sunnyvale. Venue facts use the planner’s sample catalog.';
  } catch (error) { badge.textContent = 'SERVICE OFFLINE'; status.textContent = error.message; }
}
initialize();
