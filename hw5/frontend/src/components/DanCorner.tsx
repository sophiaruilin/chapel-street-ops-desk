import { useEffect, useState } from 'react'
import Dan from './Dan'

// One-liners for whoever is sitting at the desk. Dan rotates them; click him for the next one.
const TIPS = [
  'Sip some water. Even Dan takes a bowl break.',
  'Agents draft, you decide. That’s real teamwork.',
  'Read the cheque twice, sign once. You’ve got this.',
  'Shoulders down, deep breath. The ledger can wait ten seconds.',
  '“Blocked” just means waiting for the right key.',
  'A kind reply turns a sold-out size into a loyal customer.',
  'You caught that number? Sharp eyes, Bulldog!',
  'Stand up and stretch those paws. Chapel Street will still be here.',
  'Every ticket closed is a promise kept. Boola Boola!',
  'Not sure? Decline is a perfectly good answer.',
  'Celebrate the small wins: one ticket at a time.',
]

export default function DanCorner({ cheer }: { cheer: { text: string; key: number } | null }) {
  const [i, setI] = useState(() => Math.floor(Math.random() * TIPS.length))
  const [jump, setJump] = useState(false)
  const [hidden, setHidden] = useState(false)
  const [showCheer, setShowCheer] = useState(false)

  useEffect(() => {
    const t = window.setInterval(() => setI((n) => (n + 1) % TIPS.length), 22000)
    return () => window.clearInterval(t)
  }, [])

  useEffect(() => {
    if (!cheer) return
    setShowCheer(true)
    setJump(true)
    setHidden(false)
    const a = window.setTimeout(() => setJump(false), 900)
    const b = window.setTimeout(() => setShowCheer(false), 7000)
    return () => { window.clearTimeout(a); window.clearTimeout(b) }
  }, [cheer])

  const text = showCheer && cheer ? cheer.text : TIPS[i]

  if (hidden) {
    return (
      <button className="dan-peek" onClick={() => setHidden(false)} aria-label="Show Handsome Dan">
        <Dan size={44} />
      </button>
    )
  }
  return (
    <aside className="dan-corner" aria-live="polite">
      <div className={`dan-bubble${showCheer ? ' cheer' : ''}`} key={text}>
        <span className="dan-eyebrow">{showCheer ? 'Dan says' : 'Desk tip'}</span>
        {text}
        <button className="dan-close" onClick={() => setHidden(true)} aria-label="Tuck Dan away">×</button>
      </div>
      <button
        className={`dan-btn${jump ? ' jump' : ''}`}
        onClick={() => { setI((n) => (n + 1) % TIPS.length); setShowCheer(false); setJump(true); window.setTimeout(() => setJump(false), 900) }}
        aria-label="Next tip from Handsome Dan"
      >
        <Dan size={92} />
      </button>
    </aside>
  )
}
