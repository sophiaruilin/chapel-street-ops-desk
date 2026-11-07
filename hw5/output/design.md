# Design notes: Campus Customs · Chapel Street Ops Desk

`frontend/` (React + Vite + TypeScript). Run it from `frontend/` with `npm run dev`, which opens http://localhost:5173. It talks to the FastAPI backend at http://localhost:8000 (`src/api.ts`, override with `VITE_API_URL`), and the backend's CORS allows only the Vite origin (`http://localhost:5173`).

## The idea: the back office behind Handsome Dan's Atelier

In HW 4, Campus Customs got a storefront dressed like a Yale club: navy, cream and brass, engraved toile wallpaper, Playfair Display headings, and Handsome Dan in a top hat. This desk is the **room behind that shop**: same wallpaper, same brass and navy, but now it's an old-fashioned back office where the work happens on paper. Every element is a paper object you'd find on a real desk, so the screen reads at a glance without a legend:

| Desk object | What it shows | Why |
|---|---|---|
| **Claim stubs** (left rail) | The 3 tickets, with perforated edges and a tilted rubber **status stamp** (Open, Awaiting signature, Blocked, Resolved) | Tickets *are* claim checks. A stamp says "this is the state of record" more firmly than a coloured pill |
| **The team table** (top centre) | A **navy baize table** with brass inlay: the Boss at the head, four specialists seated below | You see the whole team at once, and who is "speaking" right now |
| **The wire** (centre tab) | A live, scrolling feed of every step: slips passed between agents, tool chips, replies | Like a newsroom wire: it streams in while you watch |
| **Who did what** (centre tab) | One torn-edge **receipt** per agent, then the Boss's **memorandum** | The after-action summary is literally a stack of receipts |
| **Signature tray** (right) | Each payment the agents prepared, as a blue safety-paper **cheque** with "Pay to the order of", amount, memo and a signature line | Approving money should *feel* like signing a cheque: deliberate, personal, a little ceremonial |
| **Brass ledger** (header) | The checking balance, a gauge of what's left of the opening balance, and paid lines | Cash is the one number everyone checks first, so it lives in the header and is never scrolled away |
| **Desk calendar** (header) | A tear-off calendar tile showing `desk.date_today` (Mon · 31 · Aug 2026) | Reminds the worker the shop's "today" is the database date, not the wall clock (shop rule R1) |

## Layout

Three columns on a wide screen, stacking on narrow ones:

1. **Left, the Board:** sticky claim stubs. Click one to select it; the selected stub slides out and grows a navy **"Send to the team →"** button. While a ticket is being worked, its stub breathes with a soft blue glow, and the other stubs' buttons say "Desk busy with No. 101" because the backend runs one ticket at a time.
2. **Centre, the work:** a big serif title for the selected ticket with its run state on the right, the **team table**, then two tabs, *The wire* (live) and *Who did what* (summary). The wire scrolls inside its own panel, so the team table never leaves the screen during a run.
3. **Right, the Signature tray:** sticky, so a cheque that arrives mid-run is visible immediately.

## How agents read differently

Each agent has a **seat colour, a monogram crest and a typographic voice**. On the wire and in their seats, their words are set in that voice, so you know who is talking before reading a name:

| Agent | Colour | Voice on the wire |
|---|---|---|
| **The Boss** | Yale navy | A crisp **memo**: Playfair serif on ivory with a double navy rule. Authoritative, final |
| **Inventory** | Forest green | A **manila stockroom tag** in typewriter type (Special Elite), with a punched string hole |
| **Accounting** | Brass | **Green-ruled ledger paper** with a red margin line and tabular figures, so numbers line up like a real ledger |
| **Facilities** | Burgundy | A framed **building NOTICE** with an IM Fell small-caps header, like a notice pinned in a lobby |
| **Customer Service** | Light Yale blue | A **handwritten note** (Caveat) on a lined blue index card, slightly tilted, because it writes the human, friendly drafts |

Other things that make the run easy to follow:
- **Hand-offs** appear as cream **slips**: "The Boss *passes a slip to* Accounting", with the request in italic serif. Deeper delegations are indented, so the conversation tree is visible (Boss → Accounting → Facilities).
- **Tool calls** are little brass **chips** with friendly names and their arguments ("check shelf · CC-TEE-WHITE · S"). Raw tool results are folded under "↳ 3 tool results back to Facilities" for anyone who wants to audit.
- **Seats come alive:** a working seat lifts and glows in its colour with a bobbing crest and typing dots. A seat that delegated says "waiting on Accounting". Finished seats get a ✓. Seats never called stay dimmed with "not called (yet)", which makes it obvious when the Boss didn't need everyone (the Problem 6 plan comparison).

## Resolved tickets

- The stub's rubber **stamp** always shows the ticket's status from the database. When a ticket becomes Resolved, a green stamp **thumps in** (it scales down from large with a little overshoot, like a real stamp hitting paper), and a large double-ruled **RESOLVED** stamp appears beside the ticket title.
- When a run finishes, the desk jumps to **Who did what**. It shows "Run complete · the Boss left it **Awaiting signature**" (or Blocked, or Resolved) with the next action:
  - if a cheque for that ticket is still in the tray: "✒ sign or decline in the tray first";
  - otherwise a green **Mark resolved ✓** button, which records the person's name and closes the ticket.
- I kept the *decision* to resolve with the agents and the human rather than auto-resolving on every finished run. A run that ends with "blocked, the vendor won't ship" shouldn't be stamped resolved just because the agents stopped talking. The board marks resolved exactly when the Boss resolves it or a person clicks Mark resolved.

## Cash

- The ledger's balance **counts down** (an eased 1.1 s roll) when a signed payment clears, and a red **"−$2,400.00 · PAID"** stamp lands on it, then fades.
- A brass-to-blue **gauge** shows what's left of the opening balance, a reminder that cash only goes out in this shop (rule R6).
- Paid lines collect under the balance ("Rent · lease 1 −$2,400.00, *signed by …*" in handwriting), so the day's outflows are always visible.
- **Signing:** the cheque's signature line is a big handwriting-font input. "Sign & pay" stays disabled until a name is written, and the name becomes `payments.approved_by`. If the server refuses (not enough cash), the cheque shows the refusal in red, so a "no negative balances" refusal is visible, not silent. Decline asks for an optional reason.
- **Reset the shop** lives in the header, confirms first, and restores the August 31 database for a fresh run.

## Handsome Dan's corner

The desk mascot from the Atelier storefront sits in the bottom-right corner: **Handsome Dan** in a straw boater (it's August 31, the last day of summer), monocle on a brass chain, polka-dot bow tie and Yale sweater, with a **yellow pencil tucked behind his ear** for desk duty. He bobs gently, and a speech bubble offers a one-line **desk tip** that rotates every ~20 seconds (click Dan for the next one):

- "Sip some water. Even Dan takes a bowl break."
- "Agents draft, you decide. That's real teamwork."
- "Read the cheque twice, sign once. You've got this."
- "'Blocked' just means waiting for the right key."
- "Not sure? Decline is a perfectly good answer."
- "Every ticket closed is a promise kept. Boola Boola!"

He also **reacts**: he jumps and cheers when you send a ticket ("Off it goes!"), when a run comes back, and when a cheque clears ("Signed and cleared: $2,400.00. Beautiful penmanship!"). Declining gets a kind word too ("Saying no is part of the job, too."). The × tucks him away into a small peeking head for anyone who wants a quieter desk.

## Small touches

- A live red dot on *The wire* tab while a run streams in, and "the team is working…" typing dots at the bottom of the feed.
- The board polls every 4 s (tickets, cash, cheques) and a running ticket every 1.5 s (new events only, via `since=`), so a second person signing on another screen shows up quickly.
- Run cost is visible on the Boss's memo ("8 hand-offs · 30 model calls · 79,636 tokens"), which keeps the token budget honest.
- `prefers-reduced-motion` turns off every animation. Ticket stubs are keyboard-focusable buttons, live areas use `aria-live`, and colours meet contrast on cream.
- If the backend isn't running, a red banner says exactly which command starts it.
