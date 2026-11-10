# 2026-11-10: Legacy mode internals

## Question and method

Where does Legacy (dynasty) mode keep its calendar, teams, coaches,
recruiting, player development, conferences and prestige, and which functions
change them? Retail USA XEX (SHA-256
`71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36`).
Static reads and headless Ghidra 12.1.4 + Xenon360 decompiles; offsets named
against the PS3 roster schema (CHoops Extractor Reborn) where the layouts
match. Items marked "observed in testing" were read or written at runtime on a
test save and checked against the game's own hub screen, then saved, closed
and reloaded. All addresses are 360 guest addresses.

## Calendar and league header

- [CONFIRMED, observed in testing] League header `85C15288`: `+0` today
  (packed date), `+4..+24` six more packed dates, `+28` season index (s16;
  year = 2007 + index), `+40` four coach slots of 0x3260 bytes.
- [CONFIRMED] Packed date (`sub_8484E2D8` / `sub_8484E940`): year = 2000 +
  bits 25-31, month = bits 21-24 (0-based), day = bits 16-20.
- [CONFIRMED, observed in testing] `sub_84BD82D8` initializes a new Legacy
  (clears the coach slots, builds the league); `sub_84BD8C10` sets "today" once
  per simulated day and only moves forward; `sub_84BD4468` drives the season
  rollover (bumps the index through `sub_84BD5C68`).

## Coach slots

- [CONFIRMED] Slot `85C152B0 + 0x3260 * [85C152AC]` is the user coach.
  Slot `+0x00` = team record pointer (roster team row `+0x30`), `+4` = coach
  record (`sub_84BCF910`).
- [CONFIRMED] `+0x48` / `+0x4C`: this week's two drill slots (a slot counts as
  used when it is 0). Counter `sub_84BD2ED8` reads only these two; the hub shows
  `2 - completed` (`84C6F3E8`); the weekly reset `sub_84BD2DB0` (start of
  `sub_84BE7168`) clears exactly these two.
- [CONFIRMED] `+0x50`: 18 roster entries of 0x18C. Each holds 3 drill-id slots
  x 24 weeks (`+0x74`, `+0xD4`, `+0x134`; applied flags `+0x144`, `+0x15C`,
  `+0x174`; getters `sub_84BD26C0` / `27E0` / `2900`, flags `sub_84BD2A20` /
  `2B50` / `2C80`, setter `sub_84BD2AC0`). Week index <= 23 is checked
  everywhere. The weekly drill count is structural: counter, hub text, reset
  and save storage are all fixed-size.
- [CONFIRMED] `+7604..+8083`: 40 history entries x 12 bytes, filled by Legacy
  init `sub_84BCF120` (`li r10,40`) and indexed by season. The word after it
  (`+8084`) is read at about 202 sites; about 16 functions index the table;
  6 cap sites compare against 39. Extending past 40 seasons is structural.
- [CONFIRMED] Coach record `+12`: birth year (s16, `sub_84CEA020`).

## Team record

Team records are 704 bytes apart (team 0 = roster team table).

| Offset | Field | Evidence |
| --- | --- | --- |
| `+0x00` / `+0x08` | short name / school name (UTF-16BE string pointers) | [LIKELY] read at runtime, not checked against every team |
| `+0x14` | arena row pointer; seats u32 at arena `+0x14` (row `+0x2C`) | [CONFIRMED, observed in testing] written, hub attendance follows, reload clean |
| `+0x18` | conference pointer (PS3 schema team `+0x48`) | [CONFIRMED] `sub_84C48C98` |
| `+0x1C` / `+0x20` / `+0x24` | rival team pointers (roster row `+0x4C..+0x54`) | [LIKELY] |
| `+0x30` / `+0x34` / `+0x38` | head coach / two assistants (coach record pointers; PS3 schema `+0x60..+0x68`) | [CONFIRMED] `sub_84BCA528` reads exactly these |
| `+0xCC + 4i` | player pointers | [CONFIRMED] hub roster panel `84C6F140` |
| `+0x15A` | location compared with a recruit's hometown | [CONFIRMED] `sub_84D04160` |
| `+350` | team index (u16) | [CONFIRMED, observed in testing] |
| `+508` | W, L, conference W, conference L (bytes, this season), then last season | [CONFIRMED, observed in testing] matches the hub |
| `+596` / `+600` / `+602` | job-security terms (below) | [CONFIRMED] |
| `+604` / `+606` | recruit points (u16) / this week | [CONFIRMED, observed in testing] written, hub follows, reload clean |
| `+680` | packed scholarships: bits 31-28 offered, 27-24 total | [CONFIRMED] hub recruiting panel `84C6F220` |
| `+0x2B0` / `+0x2B4` | prestige fields (below) | [CONFIRMED] |

- [CONFIRMED] Player `+0x70` is shown in the hub's roster panel. Live pointers
  sit at the PS3 schema's logical origin (raw `+0x10`), so `+0x70` = raw `+0x80`.
  [LIKELY] This is the schema's Confidence field (offset 128; Potential is 127).
- [CONFIRMED] The hub's injuries panel (`84C6FB50`) shows days out per injured
  player from `sub_84759D70(team, i)`.
- [CONFIRMED] Schedule rows (roster table at `[R+0x34]`, count `[R+0x30]`,
  where `R+0x2C` holds the team table pointer): 20 bytes, `[date u32][home u16]
  [away u16] ...`, `+12` event id (`0xFFFF` = regular game; others are
  tournament events played at a neutral site even when a row lists a home team).

## Coaches and the carousel

- [CONFIRMED] Per-team carousel step `sub_84BCA528`: for the head coach and each
  assistant, a rating (`sub_84CE9B88`) against a threshold leads to
  `sub_84BCA2E0` (a move/raise roll scaled by a 0-10 value from
  `sub_84CE9010`); age (`sub_84CEA020`) over 50 plus a random roll decrements
  that value; then the firing roll on `(+596 - +602)`.
- [CONFIRMED] Season-end job security `sub_84BCA880`: `+600 = min(80, +600 +
  +596 - +602)`. New hire `sub_84BC9EF0`: `+600 = max(+600, 40)`.
- [LIKELY] Coach name: coach record `+0` (roster coach row `+0x14`; schema
  `coach_name`), same pointer bias as team names.

## Recruiting

- [CONFIRMED] Recruiting code is `84BF0000-84BF4000` (most of the 43
  `cmpwi 16000` sites) and corresponds one for one to the PS3 schema's map:
  size getter `sub_84BF28A8` (returns `0x415A4`, the save component),
  serializer `sub_84BF28B8` (copies the globals below, rebasing pointer pools),
  node init `sub_84BF0648` (builds both 16,000-node free lists, clears school
  `+0x260` heads), insert-by-score `sub_84BF0580(school, recruit, points)`.
- [CONFIRMED] Live state is static `.data` (component offset in brackets):

| Global | Size | Meaning |
| --- | --- | --- |
| `85C8C304` / `85C8C300` | 4 / 4 | free heads, pool 1 / pool 2 (`+0` / `+4`) |
| `85C8C2F0` | 0x10 | four queue counts (`+0x8`) |
| `85CAB708` | 0x10 | four raw counters (`+0x18`) |
| `85C8C308` | 0x1F400 | interest pool 1: 16,000 x {school s16, next s16, score s16, 2 bytes} (`+0x28`) |
| `85CABC90` | 0x1F400 | pool 2: lists headed at `+0x260` of a record; node {pointer, next s16 `+4`, task count = high byte of `+6`, capped 255} (`+0x1F428`) |
| `85CCB090` | 0x2800 | four 0xA00 queue blocks of 20-byte records (`+0x3E828`) |
| `85CCD898` | 4 | raw word (`+0x41028`) |
| `85CAB718` | 0x578 | tail (`+0x4102C`) |

- [GUESS] In pool 2, which of school and recruit is the list head was not
  confirmed at runtime.
- [CONFIRMED] Task application `sub_84BF0B50(school, recruit, coach, task,
  flag)`: base points from `.rdata:8212EA64[task]`; types 0/1/3 scale by the
  coach's rating (`sub_84CE8F30`), type 5 by the sum of the team's three
  coaches; adds through `sub_84BF0580`; bumps the per-node task counter via
  `sub_84BF0400(task, coach)`; types 6/7 set/clear byte `+7` of a pool-1 node
  (index from `sub_84BEFB00`). `sub_84BF04D0` is the counter-only variant.
- [CONFIRMED] Task types (screen `CoachMenu_AssignRecruitingTaskMenu`; filter
  `sub_84BF3428`; labels `.data:8553DE38[type]`; scheduling `sub_84BF4EA0`):

| Type | Task | Base points | Effect |
| --- | --- | --- | --- |
| 0 | Email | 1 | immediate, x coach rating |
| 1 | Phone | 5 | immediate, x coach rating |
| 2 | Request game tape | 5 | immediate |
| 3 | Home visit | 30 | x coach rating; ties up that coach (team `+0x262` status 4/5/6 by staff slot) |
| 4 | Scout game | 15 | ties up that coach |
| 5 | Campus visit | 40 | x sum of the three coaches; ties up the staff |
| 6 | Offer scholarship | 40 | immediate; sets pool-1 node byte `+7` |
| 7 | Rescind scholarship | -60 | immediate; clears it |

  All tasks are also queued on the calendar (20-byte records, event `0xE`),
  where deferred visits resolve.

## Recruit records

- [CONFIRMED] Roster header `[84F993FC]`: `+0x48` count, `+0x4C` array of
  0xD8-byte records (PS3 schema: same header offsets). Accessors:
  `sub_84844820(i)`, `sub_848448B0` / `sub_84844948` (next/previous),
  `sub_8484BD48(n)` (n-th with flag bits 0 and 2), `sub_8484BE88` (first with
  bit 0 and not bit 2), `sub_84844808` (count).
- [CONFIRMED] Field accessors `84CFCFD8..84CFDF30` map `+0x00..+0x4F`:
  `+0x00`/`+0x04` words, `+0x08..+0x2C` one byte each (ratings), `+0x2D` flags
  (`sub_84CFD2B8`), `+0x2E` u16, packed fields at `+0x30`, `+0x34`, `+0x38`,
  `+0x3C`, `+0x40`, `+0x44`, `+0x4C`, u16 at `+0x48`/`+0x4A`.
  `+0x40 >> 21` (4 bits) = recruit class (HS FR .. JC SO, `sub_84CFD7D0`);
  `+0x40 >> 7` (7 bits) = preference profile index (`sub_84CFD850`; 96 valid
  rows of rank permutations); `+0x44` bits 3-12 = hometown.
- [GUESS] Flag bit 0 = in the pool, bit 2 = committed (the class loop in
  `sub_84BF5508` takes bit 2).
- [CONFIRMED] `84B13204` (`sub_84B12878`) is the user-records stats module, not
  recruits. The 0xD8 table at `[85754EF8]` (`sub_84813150` family, word at
  `+0xC8`) is a separate structure.

## Recruit school score and prestige

- [CONFIRMED] `sub_84CFDF78` scores a school for a recruit from five terms,
  each weighted by the recruit's preference ranks (weights `.rdata:8217AC54`):
  feeling wanted (`sub_84BF1040`), close to home (`sub_84D04160`: recruit
  hometown vs team `+0x15A`), coaching (staff ratings), program prestige, and
  playing time (`sub_84D0B0E8`, depth chart).
- [CONFIRMED] Prestige `sub_84D09CF0(team)` = 0.50 x (`+0x2B0` bits 3-11) +
  0.30 x (`+0x2B4` bits 23-31) + 0.15 x (`+0x2B4` bits 14-22) + 0.05 x
  (`+0x2B4` bits 5-13): four 9-bit values, a decayed four-season score. The
  school score adds `+0x2B0` again after recruiting opens.

## Player development

- [CONFIRMED] Weekly, in season: `sub_84BE7168(team)` (from `sub_84BE7980`).
  Staff strength from the three coaches (`sub_84CE8F30`, `sub_84CE8EC0`,
  `sub_84CE9080`, weighted) is clamped to 5-27 = n. For each of 18 roster
  players, `sub_84BE6DE8(..., player, n)` turns up to three drill results
  (`sub_84BD2A20/26C0`, `2B50/27E0`, `2C80/2900`) into 30 per-rating weights,
  scaled by player `+0x6F` (clamped 50-95), by `sub_84CF4750(player)` and by n,
  and adds them to the 30 ratings through `sub_84CF36D8` / `sub_84CF4090`;
  then conditioning `sub_84CF8978`. Team `+0x24E` (s16) accumulates from n.
- [CONFIRMED] Off-season: `sub_84BE73F0` (from `sub_84BE2800`) snapshots every
  user roster's 30 ratings (`sub_84BD24F0` -> coach slot `+0x50`), then runs
  `sub_84BE5C50(player)` for every player on every team. The progression screen
  shows current minus snapshot (`sub_84BD2628`).
- [CONFIRMED] `sub_84CF5220` (writes all ratings through the per-field setters)
  is referenced only from a menu record (`.rdata:82153314`, likely the roster
  editor), not from progression.

## Conferences

- [CONFIRMED] Legacy setup's Customize Conferences (toggle `8565CE14`) leads to
  `CustomizeConferencesMenu` (`.rdata:82140C40`) and
  `CustomizeConference_SelectAlternateTeamMenu` (`.rdata:82140D80`).
- [CONFIRMED] `sub_84C48C98` swaps two teams: exchanges their conference
  pointers (team `+0x18`), patches both member lists (conference `+0x6E0`
  pointers, u16 count `+0x870`), adjusts team `+0x15E`, clears bits 15-17 of
  team `+0x2BC`, calls `sub_84CEE808(0)` and `sub_84BD68F0(team)`, and posts a
  confirmation pop-up. Conference table: 39 x 0xB94 (PS3 schema). Membership
  changes are swaps; conference sizes are fixed.

## Limits

Static except where marked. Recruit record `+0x50..+0xD7`, the two trailing
pool-node bytes, and which side of pool 2 is the list head are unmapped.
Nothing here changes game data; the runtime checks above used a test save.
