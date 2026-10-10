// Local canvas rendering only; sharing is invoked explicitly by the user.
export function candleCount(confidence) {
  return confidence == null ? 0 : Math.round(Math.max(0, Math.min(1, confidence)) * 7);
}

export function wrap(ctx, text, width) {
  const lines = [];
  for (const paragraph of String(text).split('\n')) {
    let line = '';
    for (const word of paragraph.trim().split(/\s+/).filter(Boolean)) {
      const candidate = line ? `${line} ${word}` : word;
      if (ctx.measureText(candidate).width <= width) { line = candidate; continue; }
      if (line) { lines.push(line); line = ''; }
      if (ctx.measureText(word).width <= width) { line = word; continue; }
      // Split only a single token that cannot fit even on an empty line.
      const letters = typeof Intl.Segmenter === 'function'
        ? [...new Intl.Segmenter(undefined, {granularity: 'grapheme'}).segment(word)].map(item => item.segment)
        : Array.from(word);
      for (const letter of letters) {
        if (line && ctx.measureText(line + letter).width > width) { lines.push(line); line = ''; }
        line += letter;
      }
    }
    lines.push(line);
  }
  return lines;
}

export async function renderCard(result) {
  const canvas = document.createElement('canvas');
  canvas.width = 1200;
  const ctx = canvas.getContext('2d');
  ctx.font = '32px Georgia';
  const question = wrap(ctx, result.question, 980);
  ctx.font = 'italic 36px Georgia';
  const quip = wrap(ctx, result.quip, 950);
  canvas.height = Math.max(1000, 820 + question.length * 43 + quip.length * 47);
  const background = ctx.createRadialGradient(600, 420, 40, 600, 420, 1000);
  background.addColorStop(0, '#172e47'); background.addColorStop(1, '#070b13');
  ctx.fillStyle = background; ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.textAlign = 'center';
  ctx.fillStyle = '#8faac3'; ctx.font = '18px sans-serif';
  ctx.fillText('LOCAL SPIRITS · DUBIOUS ADVICE', 600, 72);
  ctx.fillStyle = '#e4edf5'; ctx.font = '32px Georgia';
  question.forEach((line, i) => ctx.fillText(line, 600, 125 + i * 43));
  const cy = 365 + question.length * 43;
  const sphere = ctx.createRadialGradient(535, cy - 95, 15, 600, cy, 220);
  sphere.addColorStop(0, '#36546d'); sphere.addColorStop(.6, '#11283d'); sphere.addColorStop(1, '#020711');
  ctx.fillStyle = sphere; ctx.beginPath(); ctx.arc(600, cy, 220, 0, Math.PI * 2); ctx.fill();
  ctx.shadowColor = '#80d9ff'; ctx.shadowBlur = 24;
  ctx.fillStyle = result.conflicted ? '#aba6e1' : '#8dc9ef';
  ctx.beginPath(); ctx.moveTo(600, cy - 120); ctx.lineTo(735, cy + 112); ctx.lineTo(465, cy + 112); ctx.closePath(); ctx.fill();
  ctx.shadowBlur = 0; ctx.fillStyle = '#071a2d'; ctx.font = 'bold 29px sans-serif';
  const label = result.displayVerdict || result.verdict;
  ctx.font = `bold ${label.length > 14 ? 22 : 29}px sans-serif`;
  // This rectangle fits inside the triangle even at its narrow upper edge.
  let labelSize = label.length > 14 ? 22 : 29;
  let verdictLines;
  while (true) {
    ctx.font = `bold ${labelSize}px sans-serif`;
    verdictLines = wrap(ctx, label, 155);
    if (verdictLines.length * labelSize * 1.2 <= 72 || labelSize <= 8) break;
    labelSize--;
  }
  ctx.textBaseline = 'top';
  verdictLines.forEach((line, i) => ctx.fillText(line, 600, cy + 30 + i * labelSize * 1.2));
  ctx.textBaseline = 'alphabetic';
  const count = candleCount(result.confidence);
  for (let i = 0; i < 7; i++) {
    const x = 360 + i * 80, y = cy + 290;
    ctx.fillStyle = '#b5a38e'; ctx.fillRect(x - 10, y, 20, 38);
    ctx.fillStyle = i < count ? '#ffce83' : '#374350';
    ctx.shadowColor = '#ffaf57'; ctx.shadowBlur = i < count ? 22 : 0;
    ctx.beginPath(); ctx.ellipse(x, y - 13, 7, 15, 0, 0, Math.PI * 2); ctx.fill();
  }
  ctx.shadowBlur = 0; ctx.fillStyle = '#9caec1'; ctx.font = '19px sans-serif';
  ctx.fillText(result.confidence == null ? 'Dice only · no model confidence' : `${count} of 7 confidence candles · uncalibrated`, 600, cy + 370);
  if (label !== result.verdict) {
    ctx.font = '16px sans-serif';
    ctx.fillText(`Oracle verdict: ${result.verdict}`, 600, cy + 395);
  }
  ctx.fillStyle = '#e4edf5'; ctx.font = 'italic 36px Georgia';
  quip.forEach((line, i) => ctx.fillText(line, 600, cy + 435 + i * 47));
  ctx.fillStyle = '#859ab1'; ctx.font = '22px Georgia';
  ctx.fillText('Orb of Questionable Wisdom', 600, canvas.height - 55);
  return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('The card could not materialize.')), 'image/png'));
}

export function downloadCard(blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = 'orb-prophecy.png';
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
