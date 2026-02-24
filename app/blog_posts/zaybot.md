# Building ZayBot: My AlphaZero-Style Chess Engine in Python

I built **ZayBot** as a hands-on AlphaZero-style engine project to learn by implementing the full loop myself: board representation, policy/value network, Monte Carlo Tree Search (MCTS), self-play training, checkpointing, and a UCI interface for real engine tooling.

This repo is still a research codebase, but it already has a clean core package (`alpha_zero`) and practical scripts for training, evaluation, and engine integration.

## Why I Built It

I wanted to understand modern game-playing systems from first principles, not just use a finished library.  
That meant writing the components that matter:

- A ResNet-style policy/value network
- MCTS with PUCT-style selection
- Self-play data generation
- Replay buffer and supervised updates for policy + value
- UCI wiring so the model can play as an engine

## Core Architecture

The project is organized around a reusable package:

- `alpha_zero/model.py`: neural network (policy logits + scalar value)
- `alpha_zero/mcts.py`: search tree (`Node`) and MCTS runner
- `alpha_zero/self_play.py`: game generation for training
- `alpha_zero/dataset.py`: replay buffer and training dataset helpers
- `alpha_zero/game_adapter.py`: game abstraction layer
- `alpha_zero/chess_wrapper.py` and `alpha_zero/tictactoe.py`: board APIs

One design choice I like is the **adapter layer** (`ChessAdapter`, `TicTacToeAdapter`).  
It keeps MCTS and training code game-agnostic while handling move encoding, tensorization, terminal values, and board operations per game.

## Model + Search

ZayBot uses an AlphaZero-inspired network:

- Input: board tensor (`12x8x8` for chess, `2x3x3` for tic-tac-toe)
- Backbone: convolution stem + residual blocks
- Outputs: policy head over the action space and value head in `[-1, 1]`

During inference, MCTS:

1. Expands legal moves from a leaf
2. Calls the network for priors + value
3. Applies PUCT to balance exploration/exploitation
4. Backs up values through the tree
5. Picks a move by visit count at the root

## Training Loop

The training utility (`training_utils.py`) runs generation-based self-play:

1. Play `num_games_per_gen` games with current model + MCTS
2. Append examples to a bounded replay buffer
3. Sample batches from buffer
4. Train policy loss (cross-entropy over target policy)
5. Train value loss (MSE to game outcome target)
6. Save checkpoint (`az_gen_<n>_epoch_<m>.pt`)

Checkpoints are grouped into run folders like `checkpoints/ttt_run_1/`.

## Engine Integration (UCI)

I added a UCI loop in `uci_engine.py`, so the model can be used with tools like Cute Chess:

- Supports `uci`, `isready`, `ucinewgame`, `position`, `go`, `quit`
- Loads checkpoints onto CPU or CUDA
- Runs fixed-step MCTS per move
- Returns `bestmove` in UCI format

This made the project feel like a real engine instead of only a notebook experiment.

## Evaluation

`evaluate.py` includes an arena that pits:

- Challenger: MCTS + model
- Baseline: random move player

It alternates sides and reports wins/draws/losses.  
Right now this script is configured for tic-tac-toe by default with a hardcoded checkpoint path, which is useful for fast iteration.

## Current Status

What is working now:

- End-to-end self-play training pipeline
- MCTS integrated with model priors/values
- Two game backends (chess + tic-tac-toe)
- UCI engine wrapper
- Unit tests across major modules

What I want to improve next:

- Better configuration surface (CLI over hardcoded paths/modes)
- Stronger evaluation opponents and metrics
- Cleaner APIs around root-node construction and policy naming
- More training/eval automation

## How to Run It

Install:

```bash
poetry install
```

Train (current script):

```bash
python train_ttt.py
```

Evaluate:

```bash
python evaluate.py
```

Run as UCI engine:

```bash
python uci_engine.py --checkpoint <path_to_checkpoint> --mcts-steps 100
```

## Final Thoughts

ZayBot is my practical sandbox for understanding how learned evaluation and tree search work together.  
It is not trying to beat top engines yet. The goal is to build a solid, extensible foundation, then raise playing strength step by step with better data, stronger training, and tighter evaluation.
