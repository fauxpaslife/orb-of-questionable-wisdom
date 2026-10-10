// Presentation only: oracle verdicts and probabilities remain unchanged.
export const VERDICT_LABELS = {
  DEFINITELY: ['DEFINITELY', 'THE OMENS AGREE', 'SO IT SHALL BE', 'A CERTAIN YES'],
  PROBABLY: ['PROBABLY', 'THE OMENS LEAN YES', 'A LIKELY YES', 'FATE LOOKS FAVORABLE'],
  'ASK LATER': [
  'THE MISTS REFUSE',
  'NOT YET, MORTAL',
  'OMEN PENDING',
  'THE SPIRITS ABSTAIN',
  'INSUFFICIENT OMENS',
  'FATE IS UNDECIDED',
  ],
  UNLIKELY: ['UNLIKELY', 'THE OMENS LEAN NO', 'A DOUBTFUL SIGN', 'FATE LOOKS UNFAVORABLE'],
  NO: ['NO', 'THE OMENS SAY NO', 'THE WAY IS CLOSED', 'A CERTAIN NO'],
  CURSED: ['CURSED', 'AN ILL OMEN', 'DOOM APPROACHES', 'BEWARE, MORTAL'],
};

export function verdictLabel(verdict) {
  const labels = VERDICT_LABELS[verdict];
  return labels ? labels[Math.floor(Math.random() * labels.length)] : verdict;
}
