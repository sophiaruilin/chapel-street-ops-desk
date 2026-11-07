import { useId } from 'react'

const INK = '#0b2a52'
const NAVY = '#00356b'
const CREAM = '#fffdf7'
const BRASS = '#b08d57'
const POWDER = '#dbe5f1'

// Handsome Dan, the Campus Customs bulldog (original drawing from the HW 4 Atelier storefront),
// dressed for the desk: straw boater for the last day of summer, monocle on a brass chain,
// polka-dot bow tie, Yale sweater, and a pencil tucked behind one ear for desk duty.
export default function Dan({ size = 96, className }: { size?: number; className?: string }) {
  const id = useId().replace(/:/g, '')
  return (
    <svg className={className} viewBox="0 0 220 240" width={size} height={(size * 240) / 220} role="img"
      aria-label="Handsome Dan, the Campus Customs bulldog">
      <defs>
        <pattern id={`dots${id}`} width="6" height="6" patternUnits="userSpaceOnUse">
          <rect width="6" height="6" fill="#286dc0" />
          <circle cx="3" cy="3" r="1.1" fill={CREAM} />
        </pattern>
      </defs>
      <g stroke={INK} strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round">
        <ellipse cx="44" cy="222" rx="18" ry="10" fill={CREAM} />
        <ellipse cx="176" cy="222" rx="18" ry="10" fill={CREAM} />
        <path d="M60 152C46 172 42 198 50 224H170C178 198 174 172 160 152Z" fill={NAVY} />
        <path d="M56 214H164M58 219H162" stroke={CREAM} strokeOpacity="0.5" strokeWidth="1.2" />
        <text x="110" y="208" textAnchor="middle" fontFamily="'Playfair Display', Georgia, serif" fontWeight="900"
          fontSize="46" fill={CREAM} stroke="none">Y</text>
        <ellipse cx="88" cy="226" rx="15" ry="9" fill={CREAM} />
        <ellipse cx="132" cy="226" rx="15" ry="9" fill={CREAM} />
        <path d="M83 222V230M93 222V230M127 222V230M137 222V230" strokeWidth="1.2" />

        <path d="M62 72Q42 74 34 60Q46 48 70 62Z" fill={POWDER} />
        <path d="M158 72Q178 74 186 60Q174 48 150 62Z" fill={POWDER} />
        {/* pencil behind the ear */}
        <g transform="rotate(-38 176 64)">
          <rect x="150" y="60" width="44" height="7" rx="1.5" fill="#f2c14e" strokeWidth="1.6" />
          <path d="M194 60L203 63.5L194 67Z" fill="#f3e2c3" strokeWidth="1.4" />
          <rect x="146" y="60" width="5" height="7" fill="#e88a9a" strokeWidth="1.4" />
        </g>

        <path d="M110 56C158 56 182 80 182 108C182 136 162 154 136 158H84C58 154 38 136 38 108C38 80 62 56 110 56Z" fill={CREAM} />
        <path d="M60 126Q56 146 78 156M160 126Q164 146 142 156" strokeWidth="1.5" fill="none" />
        <path d="M84 72Q110 64 136 72M90 79Q110 73 130 79" strokeWidth="1.4" fill="none" />
        <circle cx="64" cy="118" r="10" fill="#f4b9c4" fillOpacity="0.6" stroke="none" />
        <circle cx="156" cy="118" r="10" fill="#f4b9c4" fillOpacity="0.6" stroke="none" />
        <path d="M76 84Q88 77 99 84M121 84Q132 77 144 84" strokeWidth="1.8" fill="none" />
        <circle className="dan-eye" cx="88" cy="95" r="6.5" fill={INK} />
        <circle className="dan-eye" cx="132" cy="95" r="6.5" fill={INK} />
        <circle cx="90.5" cy="92.5" r="2" fill={CREAM} stroke="none" />
        <circle cx="134.5" cy="92.5" r="2" fill={CREAM} stroke="none" />
        <circle cx="132" cy="95" r="13" fill={CREAM} fillOpacity="0.25" stroke={BRASS} strokeWidth="2.6" />
        <path d="M144 101Q160 124 150 152" stroke={BRASS} strokeWidth="1.2" strokeDasharray="2 2.5" fill="none" />

        <path d="M80 116C80 102 95 100 110 102C125 100 140 102 140 116C140 134 126 142 110 142C94 142 80 134 80 116Z" fill={CREAM} />
        <path d="M95 104Q110 95 125 104Q125 114 110 116Q95 114 95 104Z" fill={INK} />
        <path d="M110 115V122M88 125Q99 133 110 123Q121 133 132 125" strokeWidth="1.8" fill="none" />
        <path d="M103 131Q110 140 117 131Z" fill="#e88a9a" strokeWidth="1.4" />
        <path d="M97 129L100 121L103 129Z M117 129L120 121L123 129Z" fill={CREAM} strokeWidth="1.3" />

        <path d="M110 157L86 146V168Z" fill={`url(#dots${id})`} />
        <path d="M110 157L134 146V168Z" fill={`url(#dots${id})`} />
        <rect x="104" y="151" width="12" height="12" rx="3" fill="#286dc0" />

        <g transform="rotate(-8 110 54)">
          <ellipse cx="110" cy="54" rx="54" ry="10" fill="#ecd9a8" />
          <path d="M80 54V32Q110 26 140 32V54Z" fill="#ecd9a8" />
          <ellipse cx="110" cy="32" rx="30" ry="5" fill="#f3e6c2" />
          <path d="M80 42Q110 37 140 42V51Q110 46 80 51Z" fill={NAVY} />
          <path d="M64 57Q110 66 156 57" stroke={BRASS} strokeWidth="1" fill="none" />
        </g>
      </g>
    </svg>
  )
}
