# Hugging Face

The Hugging Face connector tracks your models, datasets and Spaces on the Hub, and the papers linked from them.

## Add your account or a repo

Paste any of these on the **Sources** page, or pass it to `areao1 import`:

| Input | What it tracks |
|---|---|
| `https://huggingface.co/mayachen` or `hf:mayachen` | Every model, dataset and Space the account (or organization) publishes |
| `https://huggingface.co/mayachen/tidy-bert` | One model |
| `https://huggingface.co/datasets/mayachen/tidy-corpus` | One dataset |
| `https://huggingface.co/spaces/mayachen/tidy-demo` | One Space |

`hf.co` links work too.

## Private or gated repos

Public repos need no token. For private or gated repos, create a **read** token:

1. Open [huggingface.co/settings/tokens/new?tokenType=read](https://huggingface.co/settings/tokens/new?tokenType=read)
   (the Sources page links there as **Create one with minimum scopes**).
2. Name it, keep the type **Read**, and create it.
3. Add it on the **Sources** page (**Private repos? Add a read-only token**) or with
   `areao1 import https://huggingface.co/mayachen --private`.

The token goes to your OS keychain; `sources.json` stores only the entry's name.

## What it reads

| Metric | For | Notes |
|---|---|---|
| `downloads` | Models, datasets | Hugging Face's rolling 30-day count |
| `downloads_all_time` | Models, datasets | |
| `likes` | Models, datasets, Spaces | |
| `upvotes` | Linked papers | From the Hub's Papers page, when the paper is there |

Each snapshot is an observation, with claims quoting the exact fields the Hub returned.

### What it proposes

- **The model, dataset or Space**, for *original contributions*, when it has at least 100 all-time downloads
  (`connectors.min_downloads_for_candidate`) or 10 likes. A Space needs 10 likes. The candidate is marked
  *widely adopted* at 10,000 all-time downloads, 1,000 in the last 30 days, or 100 likes. For a model, it also
  counts **derivative models** (models that name it as their base model) and marks it *used by others* when
  there are any.
- **A paper**, for each arXiv paper the repo is tagged with. The same paper found elsewhere (a scholarly
  connector, a GitHub README) is proposed only once.

Every proposal waits in your [Inbox](../tour/inbox.md) until you accept it.
