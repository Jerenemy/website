# Zaychess: A Chess App Built to Feel Good to Play

Most chess apps optimize for ratings, puzzles, and endless analysis. Zaychess was built with a different goal: make playing chess feel tactile, social, and satisfying from the first click.

Zaychess is a Java desktop chess app with local hot-seat play, AI matches, and online matchmaking. Under the hood it has full rule support, move history, save/load, and a relay-based multiplayer stack. But what makes it special is the play experience.

## Why Zaychess exists

A lot of chess software is powerful, but cold. Zaychess aims for the opposite: a cozy, premium feel that makes you want to open it even when you are not grinding openings.

The app is local-first and low-friction:
- No account required
- Fast startup
- Designed for two players on one computer
- Built-in AI for solo sessions

## What you can do in Zaychess today

- Play local hot-seat games with automatic board flipping between turns
- Play against the Serendipity engine with side selection and difficulty levels 0-10
- Queue for online multiplayer through the relay server
- Save games to `.chesslog` and load them later
- Continue loaded games either vs human or vs AI
- Use undo/redo with full AI-aware behavior
- Offer draws, resign, and request rematches
- Track SAN move history and captured pieces with material advantage display

The game logic also handles full endgame conditions:
- Checkmate
- Stalemate
- Draw by agreement
- Threefold repetition
- Insufficient material
- 50-move rule

## AI that feels more human

Zaychess includes custom behavior at lower levels:
- Level 0: passive bias
- Level 1: aggressive bias
- Level 2: mixed passive/aggressive
- Level 3: mixed passive/normal/aggressive

This gives players more personality in games, especially for casual play. Instead of just scaling raw strength, different levels produce different styles.

## UX details that matter

Zaychess supports both click-to-move and drag-and-drop, with visual highlights for legal moves, last move, check, and checkmate. It also includes overlay dialogs for promotion, loading, draw offers, resignation, and game-over flows.

Audio is part of the experience too. Zaychess includes SFX for moves, captures, checks, castling, promotions, and game-over moments. There is also a Bluetooth keep-alive workaround to reduce missed first sounds on wireless devices.

## Technical foundation

The app uses a clean MVC-style structure in Java:
- Core chess model and move validation
- Controller orchestration for local, AI, and online modes
- Swing-based UI with custom board/panel components
- Node.js relay server for queue matchmaking

Saved games are stored in UCI move notation and replayed with move-type reconstruction (including castling, en passant, and promotion), so sessions are portable and robust.

## What is next

Zaychess is still moving quickly. Current direction includes stronger polish, broader customization, and even smoother online rematch/session handling.

If you want a chess app that feels like a real object on your desktop, not just a stats dashboard, Zaychess is worth trying.
