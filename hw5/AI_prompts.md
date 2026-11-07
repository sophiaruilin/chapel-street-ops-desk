# HW 5 — AI prompt log

This log records the AI-assisted work for every problem in HW 5 (Campus Customs Multi-Agent Operations). Each entry has the problem number and title, at least one prompt I wrote in my own words, and a follow-up prompt when one was needed, with one sentence on what the first response was missing.

<!--
Template for each problem (copy for each new problem):

## Problem N — Title

**Prompt (my own words):**

> ...

**Follow-up prompt:**

> ...

**What was lacking before:** One sentence.
-->

## Problem 1 — Vibe Coder Prompts

**Prompt (my own words):**

> HW 5: Campus Customs Multi-Agent Operations/

**Follow-up prompt:**

> HW 5: Campus Customs Multi-Agent Operations
>
> Problem 1: Vibe Coder Prompts
>
> Create AI_prompts.md.

**What was lacking before:** The first prompt gave only the assignment title, so the assistant started exploring the repo instead of knowing to create the prompt log.

## Problem 2 — Study the Campus Customs Database

**Prompt (my own words):**

> Open data/campus_customs.db and look through every table and its fields. Copy original file to data/campus_customs_new.db.
>
> start output/harness.md
>
> for each table, list fields and one short line on why that table matters for the agents.

**Follow-up prompt:**

> @"C:\Users\sophi\Downloads\data (3)\data\campus_customs.db"
> Here is the data. Move it to where it should be. Let me know if you need anything else.

**What was lacking before:** The HW 5 database wasn't in the project yet, so the assistant could only find the old HW 4 database, which has no tickets table.

## Problem 3 — Build the MCP server

**Prompt (my own words):**

> Write an MCp server in mcp_server/ using FastMCP. it will talk to data/campus_customs_new.db. You do not need to connect or run it in this problem.every agent in this hw uses the tools in this MCP server. i will add more tools to it later. for now write 3 tools you know you will need for the tiekts in the database with names clear. never invent any data adn only use info in te database.
>
> in output/harness.md, list each of your three MCP tools. for every tool include: which table it reads, which ticket it helps unlock (101, 102, or 103) and one sentence on why that tool is the right one for that ticket. Vague lines like "reads inventory" score low - tie the tool to the ticket. Also add a short mcp_server/README.md file that explains what the MCP server is for, which database file it uses, and the three tools it has.

**Follow-up prompt:**

> @"C:\Users\sophi\Downloads\data (3)\data\campus_customs.db"
> Here is the data. Move it to where it should be. Let me know if you need anything else.

> (Screenshot of "Rules of this shop") Also incorporate these rules if not already

**What was lacking before:** Without the HW 5 database there were no tickets 101–103 to design tools around, so the tools couldn't be tied to tickets without inventing data. The first version also didn't cover the shop rules: desk date as "today", vendors with unpaid invoices not shipping, human approval for payments, no negative cash, and resetting the database before a run.

## Problem 4 — Add the MCP server to vibe coder and test each tool

**Prompt (my own words):**

> Add MCP server to this project so you can call the tools. Save the connection JSON text in .mcp.json at project root (or however your vibe coder saves local MCP server lists).
>
> with vibe coder conneted, test each of the 3 MCP tools. save evidence in output/mcp_smoke.json. For every tool include:
> -prompt you asked
> -tool name
> -tool output (must match values in data/campus_customs_new.db)

**Follow-up prompt:**

> restart the app for me

**What was lacking before:** Saving the server in .mcp.json alone did not connect it in the Claude desktop app. It also had to be registered in the user MCP config (~/.claude.json), and the app had to be fully quit and reopened before the tools showed up.

## Problem 5 — Build the agent team and grow the MCP tools

**Prompt (my own words):**

> build agentic team for Cmpus Customs using PydanticAI: Boss, Inventory, Acounting, Facilities, Customer Service.
>
> Include prompts, models, agent loops so they can delegate work to each other with full connectivity.
>
> Put agent prompts in backend/prompts/ - one file per agent. Put data types in backend/models.py and agent files under backend/ (layout can vary as long as the five roles rae clear). use your potkey_api_key and only Ops 5.5 Medium for every agent.
>
> give me suggested prompts with shop rules that agent needs and let me check before moving forward.
>
> add any tools agents need to MCP server so they can work on the open tickets. shop facts come from the MCP server over data/campus_customers_new.db - do not invent a second shop-tools layer that bypasses MCP. wire agents so they append to output/audit_trail.json as they run: for each agent-loop step, record enoguh to audit later. append to this file - do not wipe it each run.
>
> in output/harness.md, list each agent and each MCP tool (including ones you add in this problem) along with which table the tool uses. also add a short safety section: the guardrails a real business would want when agents touch real customers and real money, plus limits that keep token use in check. update mcp_server/README. md so tool list matches what you hvae now.

**Follow-up prompt:**

> human approval is required for any paymnets. if not enough cash, pay tool must refuse, no negative balances. etc. rules i had shared in images - did you retain these?

**What was lacking before:** The first test run didn't show where each shop rule was enforced, so I couldn't tell whether the payment rules (human approval, no negative balances) had carried over from the screenshot into the code.

## Problem 6 — Plan the 3 tickets

**Prompt (my own words):**

> before you wire the backend, write down what you expect team to do on each open ticket. build output/desk_tickets.html - a page you can double-click with one tab per ticket (101, 102, 103) also add empty Cash and Reflection tabs for later problems (leave them blank). on each ticket tab fill Expeted section only (leave room for Actual section i will fill after i run the agents)
>
> for expected section, write sample responses to: who boss should call first, and why; all agent delegations you expect - not boss calls everyone; which MCP tools you expect that run to use. plans that send every specialist on evrey ticket score low. we will comprae this plan to what actually happens when my agents reoslve the three tickets. ask me first.

**Follow-up prompt:**

> Use this plan

**What was lacking before:** The first answer was only a draft plan in chat for me to check, because I asked to approve the expected delegations before the page was built.

## Problem 7 — Backend routes

**Prompt (my own words):**

> Your React frontend dashboard (next problem) eneds a backend it can call. In backend/main.py, use FastAPI and add routes that do the following.
>
> return the 3 tickets and whether each is open or resolved.
> take a ticket id and run your agent team on that ticket.
> return recent agent events - what each agent said and which tols they used - so board can refresh.
> approve payment or purchase after human clicks approve (agents only prepare the pay; this orute is what acutally chagnes cash)
> return current chaecking balance from cash_accounts
> reset database to original values when you want to try a fresh run
>
> from backend/ folder, start server with uvicorn main:app --reload --port 8000
>
> In output/harness.md, list each route in one line (what URL / what it does).

**What was lacking before:** The agents' terminal approval prompt can't be used from a web page, so dashboard runs now queue each payment as "prepared, not paid", and only the approve route pays it.

## Problem 8 — Agent dashboard

**Prompt (my own words):**

> build frontend dashboard in frontend/ with React + Vite + Typescript. page should call routes you build in Problem 7. at minimum board should:
>
> list all 3 tickets
> let you pick one ticket and start agent team on it
> show each agent and what they are saying / doing while ticket runs
> mark a ticket resolved when the run finishes
> show short summary of what each agent did on that ticket
> let human approve a pay or purchase when asked
> show checking balance (it should drop after an approved pay)
>
> make dashboard look good. be creative with layout and feel - this is real desk people would want ot sit at, so put thought into how it looks. you can use inspiraiton for previous custom handsom dan's atelier website aeshetic from prior homework.
>
> tell front end to talk to backend at http://localhost:8000 and on backend allow Vite page origin (usualy http://localhost:5173 so brsower is alloewd to call those routes. start board with npm run dev
>
> this opens react desk in browser so you can pick tickets and watch agents. write output/design.md with whta you chose for dashboard look (layout, how agents read differently, how resolve dtickets and cash show up) and why - including creative choices that make it feel speciail and something humans would actually enjoy using. include a little reminder in corner for the worker with positive tips you think they'd enjoy in one liner with cute handsom dan cartoon figure.

**What was lacking before:** The approval route only knew invoice and lease ids, so the backend now adds a payee, amount and memo preview to each pending payment, so the person signing the cheque can see exactly what they are paying.

## Problem 9 — Resolve the tickets

**Prompt (my own words):**

> before testing the agents on afull run over the 3 tickets, reset the working database data/campus_customs_new.db again so i can start clean. tell me the starting checking balance before you do anything, let me confirm. then run all 3 tickets on the board until each is resolved. open output/desk_tickets.html from problem 6. on each ticket tab, fill actual section from this run: which agents worked, what they delegated, and which tools they used. keep expeted section so you can comprae the two.
>
> on cash tab of same output/desk_tickets.html, itemize the money: starting checking balance (after the reset); for each ticket: how cash changed when that ticket resolved, why (whic hpay / purchase, dollar amount); ending checking balance - it must match cash_accounts in workin gdatabase
>
> wrong cash math loses points even if borad shows every ticket resolved, so make sure and do check sot prevent from happenigns
>
> also save: output/resolved_tickets.json - for ecah ticket: id, final status, short outcome, what each agent contributed, and any human approvals; output/resolved_board.html - a page you can double-click with screensoht of React board for each resolved ticket (101, 102, and 103)
>
> append real runs to output/audit_trail.json
>
> finish output/harness.md so it covers tables, MCP tools, five agents, API routes, dashboard, and safety rules

**Follow-up prompt:**

> don't send any money but just let it sit.

**What was lacking before:** The plan assumed I would sign both cheques. Leaving them unsigned meant tickets 101 and 102 honestly stay "waiting_approval", and cash stays at $3,400 instead of dropping to $160.

## Problem 10 — Reflection

**Prompt (my own words):**

> open output/desk_tickets.html and fill reflection tab.
>
> how would you evaluate performance of agents on each and why?
> for each ticket how did actual comprae to expected plan written earlier?
> what would have been simpler as one agent with tools and why?
> describe 3 new problems Campus Customs might face that this agent team could solve with tools I built
> describe 3 new problems Campus Customs might face that this agent team could not solve with tools I built and explain the tools and agents you woudl need to solve them.
>
> feel free to give multiple optiosn adn most reocmmended and why for each if multiple responses you think shoudl be considered and we can choose ultimate best after i confirm

**What was lacking before:** My first Problem 10 message was cut off before it listed the questions, so the reflection waited for the full run to finish and for this complete list.

## Problem 11 — Submit to GitHub

**Prompt (my own words):**

> keep all the recommendations for the reflection.
>
> Problem 11: submit to GitHub.
>
> push your code to public GitHub repository so graders can clone it. submit the repo URL to canvas and also put it in output/github_url.txt
>
> do not push your real .env to github repo. Do include both database files under data/ (the original and yoru working copy) so graders can run yoru app easily.
>
> should follow this layout, and the additional rule at the bottom:
>
> *(screenshot: expected hw5/ layout — AI_prompts.md, requirements.txt, .env.example, .gitignore, .mcp.json, README.md, data/ with both .db files, mcp_server/server.py + README.md, frontend/, backend/ main.py, models.py, prompts/ with the five agent files, output/ with harness.md, mcp_smoke.json, desk_tickets.html, design.md, resolved_tickets.json, resolved_board.html, audit_trail.json, github_url.txt; "README should explain: copy original DB to the working copy when you need a clean run, start MCP server, start FastAPI backend, start the React board, reset the DB before a full three-ticket run.")*

**Follow-up prompt:**

> chapel-street-ops-desk (repo name)
>
> where on public url can i see the pretty user front
>
> yes please (turn on GitHub Pages)

**What was lacking before:** hw5 didn't match the required layout (the MCP server was mcp_server.py, there was one venv and requirements file per folder, no top-level README, .env.example or .mcp.json, and the screenshots sat in a separate folder). So I restructured it to one root environment and server.py, embedded the screenshots in resolved_board.html, and checked that no secret was in the files before pushing to a new public repo. GitHub only showed the HTML pages as source code, so GitHub Pages now serves a landing page, the board gallery and the plan-vs-actual desk at https://sophiaruilin.github.io/chapel-street-ops-desk/.
