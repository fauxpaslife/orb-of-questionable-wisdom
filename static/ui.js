import {OrbFX} from './orb-fx.js';
import {ShakeInput} from './shake.js';
import {candleCount, renderCard, downloadCard} from './share-card.js';
import {OrbSound} from './sound.js';
import {verdictLabel} from './verdict-label.js';

const $ = id => document.getElementById(id);
const fx = new OrbFX($('room'), $('orb-motion'));
const sound = new OrbSound();
export function fitVerdict() {
  const label = $('verdict');
  label.style.fontSize = '';
  let size = parseFloat(getComputedStyle(label).fontSize);
  while (size > 8 && (label.scrollWidth > label.clientWidth || label.scrollHeight > label.clientHeight)) {
    label.style.fontSize = `${--size}px`;
  }
}
new ResizeObserver(fitVerdict).observe($('triangle'));
$('orb').addEventListener('pointerdown', () => sound.unlock());
document.addEventListener('keydown', event => { if (event.code === 'Space' && !$('settings').open) sound.unlock(); });
let busy = false;
let snapshot = null;
let poll = null;
let typeTimer = null;
let statePoll = null;
let dirty = false;
let cardBlob = null;
let cardGeneration = 0;
for (let i = 0; i < 7; i++) {
  const candle = document.createElement('div');
  candle.className = `candle candle-${i}`;
  const flame = document.createElement('span'); flame.className = 'flame';
  const wax = document.createElement('span'); wax.className = 'wax';
  candle.append(flame, wax); $('candles').append(candle);
}
fx.setCandles([...$('candles').children]);
const STATES = {stirring: 'The spirits are stirring…', listening: 'The spirits are considering your question…', murmuring: 'Something questionable approaches…'};

async function api(path, options = {}) {
  const response = await fetch(path, {headers: {'Content-Type': 'application/json'}, ...options});
  const data = await response.json();
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : 'The spirits could not understand that request.';
    throw new Error(detail + (data.hint ? '\n' + data.hint : ''));
  }
  return data;
}

function lock(value) {
  busy = value;
  shake.setEnabled(!value && !$('settings').open);
  $('question').disabled = value;
}

function reset() {
  clearInterval(typeTimer);
  $('quip').setAttribute('aria-live', 'polite');
  $('quip').textContent = '';
  $('quip').removeAttribute('title');
  $('voice-source').textContent = '';
  $('verdict').textContent = '';
  $('triangle').removeAttribute('title');
  $('triangle').removeAttribute('aria-label');
  $('detail').textContent = '';
  $('confidence-note').textContent = '';
  $('share-actions').hidden = true;
  $('share-status').textContent = '';
  cardBlob = null; cardGeneration++;
  $('candles').setAttribute('aria-label', 'Confidence candles await a prediction');
}

function typeQuip(text) {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
    $('quip').textContent = text;
    return;
  }
  let index = 0;
  // Live regions receive the whole line once; incremental text is visual only.
  $('quip').setAttribute('aria-live', 'off');
  typeTimer = setInterval(() => {
    $('quip').textContent = text.slice(0, ++index);
    if (index >= text.length) {
      clearInterval(typeTimer);
      $('quip').setAttribute('aria-live', 'polite');
    }
  }, 20);
}

function finish(job) {
  clearTimeout(poll);
  if (job.state === 'error') {
    fx.setState('error');
    $('status').textContent = job.error;
    $('detail').textContent = job.hint || '';
    lock(false);
    return;
  }
  const result = job.result;
  const displayVerdict = verdictLabel(result.verdict);
  $('verdict').textContent = displayVerdict;
  $('triangle').classList.toggle('long-label', displayVerdict.length > 12);
  fitVerdict();
  const voiceSource = result.source === 'model' ? `Voice: ${result.voice_model || 'selected roleplay model'}` : 'Voice: canned fallback';
  $('quip').title = voiceSource;
  $('voice-source').textContent = voiceSource;
  $('triangle').title = `Oracle verdict: ${result.verdict}`;
  $('triangle').setAttribute('aria-label', `${displayVerdict}. Oracle verdict: ${result.verdict}`);
  const count = candleCount(result.confidence);
  fx.reveal({...result, candleCount: count, flicker: result.conflicted ? 1 : Math.max(0, Math.min(1, result.split || 0))});
  $('candles').setAttribute('aria-label', result.confidence == null ? 'Dice only: no model confidence' : `${count} of 7 confidence candles lit. Probabilities are uncalibrated.`);
  $('status').textContent = result.conflicted ? 'The spirits are conflicted.' : result.mode === 'dice-only' ? 'Dice only · the oracle is unavailable.' : 'The orb has spoken. Questionably.';
  const probability = result.confidence == null ? 'Random verdict · no model probabilities.' : `${Math.round(result.confidence * 100)}% chosen probability · uncalibrated`;
  $('confidence-note').textContent = probability;
  $('confidence-note').title = 'Candles show the probability assigned to the chosen verdict, not a calibrated chance of being right.';
  $('detail').textContent = [result.mode === 'dice-only' ? result.notice : '', result.hint, result.mutters ? `The orb mutters… ${result.mutters}` : ''].filter(Boolean).join('\n');
  const generation = ++cardGeneration;
  renderCard({...result, displayVerdict, question: result.question || $('question').value.trim()}).then(blob => {
    if (generation !== cardGeneration) return;
    cardBlob = blob; $('share-actions').hidden = false;
  }).catch(error => { if (generation === cardGeneration) $('share-status').textContent = error.message; });
  typeQuip(result.quip);
  if (navigator.vibrate) navigator.vibrate(45);
  sound.reveal();
  lock(false);
}

async function follow(id, failures = 0) {
  try {
    const job = await api(`/api/predictions/${encodeURIComponent(id)}`);
    if (['revealed', 'error'].includes(job.state)) return finish(job);
    fx.setState(job.state);
    $('status').textContent = STATES[job.state] || STATES.stirring;
    poll = setTimeout(() => follow(id), 250);
  } catch (error) {
    if (failures < 3) {
      $('status').textContent = 'The spirits are reconnecting…';
      poll = setTimeout(() => follow(id, failures + 1), 1000);
    } else finish({state: 'error', error: 'The spirits are unreachable.', hint: 'Start the local orb server and reload the page.'});
  }
}

async function ask() {
  if (busy || $('settings').open) return;
  const question = $('question').value.trim();
  if (!question) {
    $('status').textContent = 'Whisper a question first, mortal.';
    $('question').focus();
    return;
  }
  reset();
  lock(true);
  fx.setState('stirring');
  $('status').textContent = STATES.stirring;
  try {
    const job = await api('/api/predictions', {method: 'POST', body: JSON.stringify({question})});
    await follow(job.id);
  } catch (error) {
    finish({state: 'error', error: error.message, hint: ''});
  }
}

const shake = new ShakeInput($('orb'), {
  trigger: ask,
  weak: () => { if (!busy) $('status').textContent = 'A little more conviction. The orb barely felt that.'; },
  intensity: value => { fx.intensity(value); sound.intensity(value); },
});

function options(select, role, current, canned = false) {
  const values = snapshot.models.filter(model => model.role === role).sort((a, b) => a.name.localeCompare(b.name));
  select.replaceChildren();
  if (canned) select.add(new Option('Canned quips · no voice model', ''));
  if (current && !values.some(model => model.name === current)) select.add(new Option(`${current} · not discovered yet`, current));
  for (const model of values) select.add(new Option(model.name, model.name));
  select.value = current;
}

function renderSettings() {
  if (!snapshot) return;
  const current = dirty ? {oracle_model: $('oracle-model').value, voice_model: $('voice-model').value, let_think: $('let-think').checked, sound: $('sound').checked} : snapshot.settings;
  options($('oracle-model'), 'decision', current.oracle_model);
  options($('voice-model'), 'voice', current.voice_model, true);
  $('let-think').checked = current.let_think;
  $('sound').checked = current.sound;
  $('let-think').disabled = !$('voice-model').value;
  $('discovery-status').textContent = snapshot.discovery_error || `${snapshot.models.length} local candidates · Ollama ${snapshot.version || 'checking'}${snapshot.scanning ? ' · probing in the background' : ' · cache ready'}${snapshot.warming ? '\nThe selected oracle is warming.' : ''}`;
  $('memory-warning').textContent = snapshot.memory_warning;
}

async function refresh() {
  try {
    snapshot = await api('/api/state');
    sound.setEnabled(snapshot.settings.sound);
    if ($('settings').open) renderSettings();
    if (!busy && !$('quip').textContent && snapshot.discovery_error) {
      $('status').textContent = 'The spirits are unreachable.';
      $('detail').textContent = 'Start Ollama (ollama serve), then Rescan in settings.';
    }
  } catch (error) {
    if ($('settings').open) $('discovery-status').textContent = 'The local orb server is unreachable.';
  }
  statePoll = setTimeout(refresh, $('settings').open ? 1500 : 6000);
}

$('gear').addEventListener('click', () => {
  dirty = false;
  $('settings-error').textContent = '';
  renderSettings();
  $('settings').showModal();
  shake.setEnabled(false);
  clearTimeout(statePoll);
  refresh();
});
$('close-settings').addEventListener('click', () => $('settings').close());
$('settings').addEventListener('close', () => shake.setEnabled(!busy));
$('settings-form').addEventListener('change', () => { dirty = true; $('let-think').disabled = !$('voice-model').value; });
$('rescan').addEventListener('click', async () => {
  try {
    await api('/api/rescan', {method: 'POST'});
    $('discovery-status').textContent = 'Rescanning in the background…';
  } catch (error) { $('settings-error').textContent = error.message; }
});
$('settings-form').addEventListener('submit', async event => {
  event.preventDefault();
  sound.setEnabled($('sound').checked); sound.unlock();
  try {
    await api('/api/settings', {method: 'PATCH', body: JSON.stringify({oracle_model: $('oracle-model').value, voice_model: $('voice-model').value, let_think: $('let-think').checked && Boolean($('voice-model').value), sound: $('sound').checked})});
    dirty = false;
    $('settings').close();
    if (!busy) $('status').textContent = 'The spirits have updated their preferences.';
    clearTimeout(statePoll);
    refresh();
  } catch (error) { $('settings-error').textContent = error.message; }
});
if ('DeviceMotionEvent' in window) {
  $('enable-motion').hidden = false;
  $('enable-motion').addEventListener('click', async () => {
    try {
      await shake.enableMotion();
      $('enable-motion').textContent = 'Phone shake enabled';
      $('enable-motion').disabled = true;
    } catch (error) { $('settings-error').textContent = error.message; }
  });
}
refresh();

$('save-card').addEventListener('click', () => { if (cardBlob) downloadCard(cardBlob); });
$('share-card').addEventListener('click', async () => {
  if (!cardBlob) return;
  const file = new File([cardBlob], 'orb-prophecy.png', {type: 'image/png'});
  if (!navigator.share || !navigator.canShare?.({files: [file]})) {
    downloadCard(cardBlob); $('share-status').textContent = 'Card saved; this browser does not support file sharing.'; return;
  }
  try { await navigator.share({files: [file], title: 'Orb of Questionable Wisdom'}); }
  catch (error) { if (error.name !== 'AbortError') $('share-status').textContent = 'The spirits could not share. Save the card instead.'; }
});
