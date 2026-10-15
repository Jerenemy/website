# Building ZayBot: My AlphaZero-Style Chess Engine in Python

ZayBot is an AlphaZero-style engine I wrote to learn how the whole loop works by building it myself: board representation, a policy/value network, Monte Carlo Tree Search (MCTS), self-play training, checkpointing, and a UCI interface so real chess tools can run it.

It's still a research codebase, but the core package (`alpha_zero`) is in good shape, and there are scripts for training, evaluation and engine integration.

## Why I built it

I wanted to understand how modern game-playing systems work from first principles instead of calling a finished library. So I wrote the parts myself:

- a ResNet-style policy/value network
- MCTS with PUCT-style selection
- self-play data generation
- a replay buffer and supervised updates for policy and value
- UCI wiring so the model can play as an engine

## Core architecture

The project is organized around one reusable package:

- `alpha_zero/model.py`: neural network (policy logits + scalar value)
- `alpha_zero/mcts.py`: search tree (`Node`) and MCTS runner
- `alpha_zero/self_play.py`: game generation for training
- `alpha_zero/dataset.py`: replay buffer and training dataset helpers
- `alpha_zero/game_adapter.py`: game abstraction layer
- `alpha_zero/chess_wrapper.py` and `alpha_zero/tictactoe.py`: board APIs

My favorite design choice is the adapter layer (`ChessAdapter`, `TicTacToeAdapter`). Each adapter handles move encoding, tensorization, terminal values and board operations for its game, so the MCTS and training code never has to know which game it's playing.

## Model and search

The network follows AlphaZero:

- Input: board tensor (`12x8x8` for chess, `2x3x3` for tic-tac-toe)
- Backbone: convolution stem + residual blocks
- Outputs: a policy head over the action space and a value head in `[-1, 1]`

During inference, MCTS:

1. Expands legal moves from a leaf
2. Calls the network for priors and a value
3. Uses PUCT to trade off exploration and exploitation
4. Backs values up through the tree
5. Picks the move with the most visits at the root

## Training loop

The training utility (`training_utils.py`) runs self-play in generations:

1. Play `num_games_per_gen` games with the current model + MCTS
2. Append the examples to a bounded replay buffer
3. Sample batches from the buffer
4. Train the policy loss (cross-entropy against the target policy)
5. Train the value loss (MSE against the game outcome)
6. Save a checkpoint (`az_gen_<n>_epoch_<m>.pt`)

Checkpoints go into run folders like `checkpoints/ttt_run_1/`.

## Engine integration (UCI)

`uci_engine.py` runs a UCI loop, so the model works with tools like Cute Chess:

- Supports `uci`, `isready`, `ucinewgame`, `position`, `go`, `quit`
- Loads checkpoints onto CPU or CUDA
- Runs a fixed number of MCTS steps per move
- Returns `bestmove` in UCI format

Once this worked, ZayBot started to feel like an actual engine I could play against in other programs, instead of a notebook experiment.

## Evaluation

`evaluate.py` has an arena that plays the challenger (MCTS + model) against a baseline that picks random moves. It alternates sides and reports wins, draws and losses. For now the script defaults to tic-tac-toe with a hardcoded checkpoint path, which keeps iteration fast.

## Current status

Working now:

- the self-play training pipeline, end to end
- MCTS using the model's priors and values
- two game backends (chess and tic-tac-toe)
- the UCI engine wrapper
- unit tests across the major modules

Next on the list:

- a proper CLI instead of hardcoded paths and modes
- stronger evaluation opponents and better metrics
- cleaner APIs around building the root node and naming policies
- more automation for training and evaluation

## How to run it

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

Run as a UCI engine:

```bash
python uci_engine.py --checkpoint <path_to_checkpoint> --mcts-steps 100
```

## Where it stands

ZayBot is my sandbox for learning how a learned evaluation and tree search work together. It won't beat top engines anytime soon. The plan is to get the foundation right first and then make it stronger with better data, more training and tighter evaluation.
