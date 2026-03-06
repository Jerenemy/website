# Attack-Target Graph Presentation Notes

## One-Sentence Pitch
This app is an interactive network view of which political sponsors are attacking which targets, with node size, party coloring, spend context, and click-based neighborhood exploration.

## Live Link
- `https://jeremyzay.com/deltalab/`

## What The Graph Shows
- Sponsors are the ad sponsors running attack content.
- Targets are the people or entities mentioned as attack targets.
- Directed edges run from `sponsor -> target`.
- Edge strength is represented by `mention_count`.
- Spend context is added through `spend_proxy`, joined on `(platform, ad_id)`.

## Core Visual Semantics
- Sponsors are squares.
- Targets are circles.
- In party color mode:
  - `REP` is red.
  - `DEM` is blue.
  - `IND` is green.
  - `OTHER` and `UNKNOWN` are gray.
- Size mode:
  - `Topology`: sponsors scale by outgoing degree; targets scale by incoming degree.
  - `Money`: sponsors scale by total attack spend; targets scale by total received attack spend.

## Data Inputs Behind The App
- `attack_target_edges`: sponsor-target edge table.
- `attack_target_nodes`: node-level metadata.
- `entity_mentions_week3_cleaned`: cleaned mention-level target records.
- `harmonized_sample_week1`: provides `spend_proxy`.

## Key Derived Fields To Explain
- `sponsor_party`: modal sponsor party from mention data.
- `target_party_inferred_mentions`: inferred target party based on the dominant incoming attacker party by summed `mention_count`, then flipped to represent the target side.
- `target_party_inferred_money`: inferred target party based on the dominant incoming attacker party by summed `spend_proxy`, then flipped to represent the target side.
- `edge_attack_spend`: spend aggregated to a sponsor-target edge after ad-level deduplication.
- `sponsor_attack_spend`: total spend across a sponsor’s visible attack ads.
- `target_received_spend`: total spend across ads targeting a given target.

## Important Methodology Note
The graph does not claim a ground-truth ideology label for targets.
It produces an operational inference from attack behavior:
- If Republican sponsors dominate attacks on a target, the inferred target party is treated as Democrat.
- If Democratic sponsors dominate attacks on a target, the inferred target party is treated as Republican.
- Ties become `UNKNOWN`.
- The user can toggle the inference basis between `Money` and `Mentions`.

## What Is New In The Current Build
- Target-party inference is togglable:
  - `Money` is the default.
  - `Mentions` is available as an alternate view.
- Layout is togglable:
  - `Force Directed` is the default.
  - `Bipartite` and `Radial` are also available.
- Search controls:
  - sponsor party search,
  - target party search,
  - visible node search.
- Click highlighting:
  - `Neighbor Highlight` for one active seed,
  - `Accumulate Highlight` for multiple seeds.
- Edge hover behavior:
  - when a node is selected, only highlighted edges are hoverable.
- Selected Ad IDs panel:
  - clicking/selecting a node lets you expand a details panel below the graph,
  - the panel shows only ad IDs from the currently visible graph.

## Recommended Live Demo Flow
1. Start with the default force-directed layout and party colors.
2. Point out role semantics:
   - squares are sponsors,
   - circles are targets,
   - arrows/edges run sponsor to target.
3. Show the target-party inference toggle:
   - switch between `Money` and `Mentions`,
   - explain that both are operational definitions, not ground truth.
4. Use a node click to highlight a local neighborhood.
5. Expand the `Selected Ad IDs` section to show the supporting ad-level records.
6. Switch size mode from `Topology` to `Money` to show how network prominence and spend prominence differ.
7. Switch layout from `Force Directed` to `Bipartite` if you want a cleaner sponsor-vs-target separation for explanation.

## Good Talking Points
- This graph connects sponsor behavior to the targets they attack.
- It supports both structural interpretation and spend-aware interpretation.
- The tool is designed for exploratory analysis, not just static visualization.
- The app lets you move from macro pattern to micro evidence:
  - macro: network structure and partisan clustering,
  - micro: selected neighborhood and the underlying ad IDs.
- Toggling inference between money and mentions can expose cases where volume and spend tell different stories.

## Things To Be Careful Not To Overclaim
- Do not say the app proves a target’s true political identity.
- Do not say spend is exact if `spend_proxy` is only a proxy measure.
- Do not treat centrality as purely substantive:
  - layout choice and current filters affect what looks central.
- Do not forget that `Top N Edges` and `Min Edge Mentions` change the visible graph.

## Likely Questions And Strong Answers

### What does an edge mean?
An edge means a sponsor attacked a target in the underlying ad/mention data. The edge carries aggregated counts like `mention_count`, `ad_count`, and `edge_attack_spend`.

### How is target party inferred?
It is inferred from the dominant attacking side, then flipped to represent the likely target side. The app allows that inference to be weighted either by mentions or by spend.

### Why is money the default?
Money can better reflect the intensity or strategic priority of an attack campaign than raw mention volume alone.

### Why keep mentions as an option?
Mentions are still useful because they reflect frequency and may highlight repeated targeting even when spend is lower.

### What does the ad ID panel show?
It shows the ad IDs associated with the currently selected sponsor or target, restricted to the ads represented in the visible graph after current filters.

### Why do some labels become `UNKNOWN`?
That happens when the dominant attacking side is tied or the available evidence is not decisive.

## Quick Demo Script
“This is an interactive sponsor-to-target attack network. Squares are sponsors, circles are targets, and edges represent attack relationships. I can size by topology or by spend, and I can infer target party either by mentions or by money. When I click a node, I isolate its local neighborhood, and if I expand the panel below, I can inspect the actual ad IDs supporting what we are seeing in the graph.”

## If You Want A One-Slide Summary
- Interactive Week 3 sponsor-to-target attack network
- Combines structure, party inference, and spend context
- Supports layout, filtering, and search-based exploration
- Moves from network overview to supporting ad IDs on selection

## If You Want A One-Minute Closing Line
The main value of this graph is that it turns a large attack-ad dataset into a navigable map of who is targeting whom, while still letting you drill back down to the underlying ad-level evidence.
