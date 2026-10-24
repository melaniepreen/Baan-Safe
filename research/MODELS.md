# Candidate models

Options for a human, plus one verifier the humans have already selected. `system2.orchestrator_model`, `system1.extraction_model`, `system2.hosting`, and `speech_to_text.provider` stay `TODO_HUMAN`. Sizes and licences move; read the card on the day you pick.

## Banyan Sapling, selected for verification

`system2.use_banyan_sapling` is true, scoped to aid eligibility and denials. The checkpoint is [`MubitLabs/banyan-sapling`](https://huggingface.co/MubitLabs/banyan-sapling) (Apache-2.0, research preview, card read 24 October 2026). It is a pruned Qwen3-30B-A3B with a verification head: 23,042,164,740 stored parameters, BF16 weights of about 46 GB, input limit 16,384 tokens, evaluated language English. It classifies a policy, evidence, and a claim. The checkpoint labels are `supported`, `violation`, `insufficient_information`, and `inconsistent_context`. Calibrated `status` may be `unsure`. BaanSafe calls the middle two `missing` and `contradicted`.

`sapling.model_id` is still `TODO_HUMAN` in git so the Modal app refuses to start. The id to export is the repo above. `sapling.hosting`, `sapling.gpu`, and `sapling.thai_handling` are `TODO_HUMAN` on purpose: every model call has to go through Mubit, and it is unconfirmed that Mubit can route to a self-hosted endpoint; the GPU is an L40S on Modal or an A6000 when self-hosting; the card does not say to translate Thai, and this note does not decide that. The committed client is the stub. See `infra/HARDWARE.md`.

Every LLM call in this repo has to be able to go through Mubit (`research/MUBIT.md`). Self-hosting and a vendor endpoint are hosting options only if Mubit is still the hop the hackathon rule requires. That is a constraint, not a choice of model.

## Nemotron, for System 2 orchestration

The architecture names Nemotron as the System 2 orchestrator. It is not inside Mubit. The family is covered by the NVIDIA Nemotron Open Model License: https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-nemotron-open-model-license/

Two public checkpoints, as options:

| Checkpoint | Shape | Thai | Released | Card |
|---|---|---|---|---|
| `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16` | About 30B total, about 3B active | The card's language list does not feature Thai | 15 Dec 2025 | https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16 |
| `nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-Base-BF16` | About 120B total, about 12B active. This card is a base model | The README lists Thai among supported languages | 4 Mar 2026 | https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-Base-BF16 |

Trade-off, not a recommendation. Nano is the one you can realistically serve on a single large GPU, and it is a weak bet for Thai calls. Super is the one whose card claims Thai, and it is a base checkpoint at a size that needs serious hardware or a hosted endpoint. Other Nemotron sizes exist. A human should open the current NVIDIA and Hugging Face lists before locking `system2.orchestrator_model`. Hosting (`system2.hosting`) is a separate decision: through Mubit, self-hosted, or another provider, still with Mubit as the application hop.

## Small models for System 1 extraction

System 1 is supposed to stay fast and deterministic. A small model is only relevant if `system1.extraction_method` is "small model" or "hybrid". Rules-only is still on the table.

Thai-capable families a human can compare. Licences are per checkpoint. I am not asserting a licence I did not read on that card.

| Family | What was checked | Licence as checked | Where |
|---|---|---|---|
| Typhoon 2 | Announcement lists 1B, 3B, 7B, 8B, and 70B text models aimed at Thai | Mixed. See the two rows below | https://medium.com/scb10x/introducing-typhoon-2-0806fb040c45 |
| `typhoon-ai/typhoon2-qwen2.5-7b` | 7B, Qwen 2.5 base | Apache-2.0 on the card | https://huggingface.co/typhoon-ai/typhoon2-qwen2.5-7b |
| Llama Typhoon 2 (`llama3.2-typhoon2-1b`, `llama3.1-typhoon2-8b`, `llama3.1-typhoon2-70b-instruct`) | Same family, Llama bases | Llama community licence, not Apache. Confirm the exact card | Hugging Face under `typhoon-ai` and `scb10x`. The org has drifted; do not guess which repo is canonical |
| SeaLLM | `SeaLLMs/SeaLLM-7B-v2`, Southeast Asian languages including Thai, about 7B | The card's licence field is `seallms`, not Apache-2.0. Read their terms | https://huggingface.co/SeaLLMs/SeaLLM-7B-v2 |
| OpenThaiGPT | Project licence page, not one checkpoint | Models and code: Apache-2.0. Their datasets: CC BY-SA. A mirror checkpoint can differ | https://openthai.ai/en/license |
| Qwen, Llama, Gemma | General small checkpoints (roughly 1B–8B) that sometimes list Thai | Per card. Llama and Gemma community licences are not the same as Apache | Open the card. Do not copy a licence from the family name |

Trade-off. A 1B–3B model is the only size that keeps a System 1 budget honest on a laptop. Thai quality at that size is uneven, and a rules extractor may beat it on the seven clear fixtures. A 7B–8B Thai model is a better extraction candidate and starts to look like a second reasoner, which System 1 is not supposed to be. 70B belongs in the System 2 column if it belongs anywhere.

A NER or classifier (word-level location, number of people, danger words) is a third option under `system1.extraction_method`. LST20 is the labelled Thai set to look at first (`research/DATASETS.md`). A classifier does not satisfy the hackathon's "model update" demo by itself.

## Thai speech-to-text

`speech_to_text.provider` may also be "scripted only" for the demo. The fixtures are already scripted English text.

| Option | What was checked | Licence | Where |
|---|---|---|---|
| Thonburian Whisper | Fine-tunes of Whisper for Thai. The README gives a Common Voice 13 word-error of 7.42 for the medium combined model and 6.59 for large-v3, measured with their own normaliser | The GitHub repo is MIT. The weights are Whisper fine-tunes, so read the model card and the Whisper terms as well | https://github.com/biodatlab/thonburian-whisper |
| Typhoon2-Audio | Speech in, text and speech out, Thai and English. Paper: https://arxiv.org/abs/2412.13702 | The Hugging Face card says Llama 3.1 Community License for speech input and the LLM, and CC-BY-NC for speech output. The code repo is marked Apache-2.0 and tells you the checkpoints keep their own licences. Those two statements are both on the public pages; they are not the same licence | https://huggingface.co/typhoon-ai/llama3.1-typhoon2-audio-8b-instruct and https://github.com/scb-10x/typhoon2-audio |
| Whisper, unmodified | OpenAI's multilingual model, Thai in the training mix | Confirm on the card you would actually ship. Do not assume the MIT code licence covers a fine-tune | https://github.com/openai/whisper |
| A cloud speech API | Not opened in this pass | Read the current Thai terms and the data-retention clause before any real audio | Leave `speech_to_text.provider` unset until that is done |

Trade-off. Scripted audio finishes the demo with no speech risk. A local Whisper fine-tune is the open option and needs a GPU if you want it live. Typhoon2-Audio is the Thai-specific speech model, with a non-commercial restriction on the speech it generates, which matters if the demo plays audio back. A cloud API is the least work and the worst fit for "we own the update", and real caller audio must not be sent anywhere.

## Embeddings for Thai retrieval

Mubit retrieval may use its own index. If we also embed locally, the candidate families people reach for are BAAI `bge-m3` and the multilingual E5 models, because their cards advertise many languages including Thai. I did not open those licence files in this pass. Do not treat them as cleared. Read the card, check whether Thai is in the training mix or only in the language list, and try a handful of synthetic Thai queries against our district strings before depending on one.

Trade-off. A multilingual embedding is enough to retrieve similar synthetic cases. It is the wrong tool for the correction-to-model-update demo. It is the right tool if Melanie wants memory search that is not only keyword overlap.

## What not to do with this note

Do not write a model name into `config/decisions.yaml` from this file. Do not put a token price in the config. `llm.token_price_usd` stays `TODO_HUMAN`, and the correction-loop demo prints cost as null on purpose.
