# Zaychess: A Chess App Built to Feel Good to Play

Most chess apps are built around ratings, puzzles and analysis. I built Zaychess for the part where you sit down and play a game, and I wanted that to feel tactile and fun from the first click.

Zaychess is a Java desktop chess app with local hot-seat play, games against an AI, and online matchmaking. It implements the full rules, keeps a move history, saves and loads games, and runs multiplayer through a relay server.

## Why I made it

A lot of chess software is powerful and a bit cold. I wanted something cozy that you'd open for a casual game even when you aren't studying openings. It's local-first and quick to get into:

- no account required
- fast startup
- designed for two players on one computer
- a built-in AI for playing alone

## What it does today

- Local hot-seat games, with the board flipping automatically between turns
- Games against the Serendipity engine, with side selection and difficulty levels 0 to 10
- Online multiplayer through a queue on the relay server
- Saving games to `.chesslog` files and loading them later
- Continuing a loaded game against a person or the AI
- Undo and redo that account for the AI's moves
- Draw offers, resignation and rematch requests
- SAN move history, captured pieces and a material-advantage display

It handles every way a game can end: checkmate, stalemate, draw by agreement, threefold repetition, insufficient material and the 50-move rule.

## An AI with a personality

The lower difficulty levels play with a bias instead of just playing weaker:

- Level 0: passive
- Level 1: aggressive
- Level 2: a mix of passive and aggressive
- Level 3: a mix of passive, normal and aggressive

Each of the easy levels has its own style as well as its own strength, which gives casual games more personality.

## Details

You can move by clicking or by dragging, and the board highlights legal moves, the last move, check and checkmate. Promotion, loading, draw offers, resignation and the end of the game each get an overlay dialog.

There are sound effects for moves, captures, checks, castling, promotions and the end of the game. Some wireless devices drop the first sound after a silence, so the app keeps the Bluetooth connection awake to avoid that.

## How it's built

The Java code is structured roughly as MVC:

- a core chess model with move validation
- controllers for local, AI and online modes
- a Swing UI with custom board and panel components
- a Node.js relay server for matchmaking

Saved games store moves in UCI notation. Loading one replays the moves and works out the special ones (castling, en passant, promotion), so saved games load back reliably and can be moved between machines.

## What's next

I'm still working on it: more polish, more customization, and smoother rematches and session handling online.
