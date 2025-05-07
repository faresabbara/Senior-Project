
> [!IMPORTANT]  
> This repository is a early-access checkpoint for Llama 3.1 70B.
> This repo contains only Meta provided original checkpoints. Hugging Face checkpoints are available here.

```bash
You can invoke them via torchrun by doing the following:
CHECKPOINT_DIR=~/.llama/checkpoints/Llama3.1-70B-Instruct-2014-12/
pip install torch fairscale
torchrun --nproc_per_node 8 `which example_chat_completion` "$CHECKPOINT_DIR"
```