# Datasets that could train or score a model

Public, labelled sets only. Licences are whatever the page we opened actually said. A tweet corpus is not an emergency-call corpus. None of these are loaded into `data/processed/`. Synthetic fixtures stay the eval set until a human says otherwise.

## Crisis text classification

| Set | What it is | Labels | Licence we could verify | Where |
|---|---|---|---|---|
| HumAID | About 76,500 English tweets, 19 disasters, 2016–2019 | Humanitarian classes (infrastructure damage, rescue, injured people, and similar) | Not copied here. Read the terms page before download. The ZIP is linked from the dataset homepage | Paper https://ojs.aaai.org/index.php/ICWSM/article/view/18116 — home https://crisisnlp.qcri.org/humaid_dataset — terms https://crisisnlp.qcri.org/terms-of-use.html — card https://huggingface.co/datasets/QCRI/HumAID-all — zip https://crisisnlp.qcri.org/data/humaid/humaid_data_all.zip |
| CrisisLexT6 | About 60,000 tweets, six crises in 2012–2013, including two floods (Alberta, Queensland) | On-topic or off-topic, majority of at least three workers | The download page does not state a dataset licence. The GitHub repo is MIT. Do not treat the repo licence as the tweet licence | https://crisislex.org/tweet-collections.html and https://github.com/sajao/CrisisLex/tree/master/data/CrisisLexT6 |
| CrisisLexT26 | About 250,000 tweets from 26 crises, of which about 28,000 are labelled (about 1,000 per event) | Informative or not, information type, source | Same caveat. Cite Olteanu, Vieweg, and Castillo, CSCW 2015, if you use it | https://crisislex.org/tweet-collections.html |

HumAID is the one that lines up with `Need` and `Route` names. CrisisLex is the one that lines up with "is this even a flood call". Both are English, both are public social posts, and both will teach a model the wrong channel if you fine-tune on them and then expect a phone transcript.

## Thai NER and word segmentation

**LST20** (NECTEC). News text, not emergency calls. The card's own counts: 3,164,002 words, 288,020 named entities, 248,181 clauses, 74,180 sentences, 3,745 documents, 15 news genres. Layers include word boundaries, part of speech, named entities, clauses, and sentences. That is the practical set for a Thai location and person-count extractor.

Licence, from the Hugging Face dataset card and the NECTEC catalogue, paraphrased:

- Non-commercial research and open-source use is free if you cite their technical report.
- You may not modify or redistribute the corpus unless the authors allow it.
- Commercial use is either a 50,000-word annotated contribution or a paid lifetime licence. Contact is on the card (thepchai@nectec.or.th).

https://huggingface.co/datasets/lst-nectec/lst20
https://aiforthai.in.th/corpus.php
Catalogue: https://opend-portal.nectec.or.th/en/dataset/lst20-corpus

A hackathon demo can cite LST20. Training a weight you then ship is the commercial question, and it is a human question. Do not drop the files into this repo.

## Emergency call corpora

I did not find a public, downloadable, labelled corpus of emergency calls that we could point at and use.

- InTriage reports about 40 hours of real telephone audio and does not, in the abstract, link a download. https://aclanthology.org/2025.emnlp-demos.67/
- The Taipei road-accident study used 2018 audio from the city dispatch centre. The paper does not publish it. https://pmc.ncbi.nlm.nih.gov/articles/PMC9233260/
- The Singapore ambulance-dispatch model was trained on call-centre records. The authors say sharing needs the service's approval. https://pmc.ncbi.nlm.nih.gov/articles/PMC10880163/

So the honest eval set for Saturday is still `fixtures/`. Forty-odd synthetic transcripts will not train a Thai model. They will show a before/after on a correction, which is what `make demo-correction-loop` does. If someone offers real Thai call audio during the weekend, it does not go in git, and it does not go to a cloud speech API until `speech_to_text.provider` is a human decision.

## What we already hold

`data/SOURCES.md` is the flood-map and gauge inventory (GISTDA, GDACS, GLIDE, IDMC, EOS-RS, UNOSAT, ThaiWater, Open-Meteo, Overpass). Those rows are polygons, reports, and weather. They are not labelled calls. They can be context features. They are not a training set for extraction.
