# Reading list

Annotated, in our words. Links were opened or returned by a search that showed the title, authors, and abstract. Quotes are short. This list does not change `config/`. None of these papers is a Thai flood-call corpus.

## Emergency call triage

**InTriage: Intelligent Telephone Triage in Pre-Hospital Emergency Care.** He, Lin, Fei, Chng, Hong, Ong, and Feng, EMNLP 2025 system demo. A multilingual telephone-triage demo: transcribe the call, pull out the clinical facts, prompt for what is missing, and show a triage suggestion. On about 40 hours of real calls they report a word-error rate of 14.57% and an F1 of 73.34% for key-information extraction. The abstract does not point at a public audio download. Useful as a picture of the pipeline, not as training data.

https://aclanthology.org/2025.emnlp-demos.67/

**Machine learning on ambulance-dispatch records (Singapore).** A Random Forest on structured call-centre fields, not on audio. The authors report about 15 percentage points less over-triage than the call-centre protocol, with under-triage held similar, and they say the protocol and the data are not public by default. The transfer lesson is the split of over-triage and under-triage, which our Priority labels do not yet measure.

https://pmc.ncbi.nlm.nih.gov/articles/PMC10880163/

**Text mining of road-accident calls in Taipei.** Wang and colleagues, 2022. Mandarin audio from 2018, transcribed, then TF-IDF plus a Bernoulli naive Bayes model (their PAMT model) to flag severely injured patients. Dispatchers were more accurate when they were sure; the model helped more when the dispatchers were not. The paper is a reminder that a fast text classifier is a second opinion, not a replacement. The audio is not a dataset we can pull.

https://pmc.ncbi.nlm.nih.gov/articles/PMC9233260/

**DispatchMAS.** Li and colleagues, 2025. A simulated emergency-medical-dispatch drill: a taxonomy of complaints, a caller agent, and a dispatcher agent, scored by physicians on guidance and on whether the right resource was contacted. It is a way to rehearse a demo without real calls. It is not evidence about Thai floods.

https://arxiv.org/abs/2510.21228

## Crisis informatics

**HumAID.** Alam, Sajjad, Imran, and Ofli, ICWSM 2021. English tweets from 19 disasters in 2016–2019, labelled into humanitarian classes (rescue, infrastructure, injured, and so on). The Hugging Face card puts the combined set at about 76,500 tweets. This is the closest public labelled set to "what kind of need is this", and it is tweets, not phone calls, and not Thai.

Paper: https://ojs.aaai.org/index.php/ICWSM/article/view/18116
Data notes: https://crisisnlp.qcri.org/humaid_dataset
Terms: https://crisisnlp.qcri.org/terms-of-use.html

**CrisisLex.** Olteanu, Castillo, Diaz, and Vieweg, ICWSM 2014, and the 2015 CSCW follow-up with Vieweg and Castillo. CrisisLexT6 labels about 60,000 tweets as on-topic or off-topic across six crises, including the 2013 Alberta and Queensland floods. CrisisLexT26 labels about 1,000 tweets per event for 26 crises, for informativeness, information type, and source. The collection page describes the labels. It does not state a dataset licence in the text we read. The GitHub repository that holds the files is MIT, which covers the repo, not a promise about the tweets.

Lexicon paper context and files: https://github.com/sajao/CrisisLex
Download notes: https://crisislex.org/tweet-collections.html
T26 citation: Olteanu, Vieweg, and Castillo, CSCW 2015, "What to Expect When the Unexpected Happens".

**Interactive labelling during an event.** Snyder, Lin, Karimzadeh, Goldwasser, and Ebert, 2019. A responder corrects "relevant / not relevant" on a live tweet stream and the classifier retrains at interactive speed. They tried it with first responders inside the SMART toolkit. This is the crisis-informatics version of our correction loop, on tweets, and without a fine-tune of a large model.

https://arxiv.org/abs/1908.02588

**Active learning on disaster tweets.** Hanny, Schmidt, and Resch, 2024. Keyword filter versus a RoBERTa model fine-tuned on CrisisLex versus the same model plus a few rounds of active learning, tested on CrisisLex and on labelled posts from the 2021 German floods and the 2023 Chile fires. Generic fine-tuning plus ten rounds of active learning beat the other setups. Small labelled sets moved the model. That is the "fast refresh" track in miniature.

https://arxiv.org/abs/2408.09914

**FloodDeepSeek.** A 2026 paper on classifying flood posts with a distilled Llama and LoRA, then mapping them in time and space for the July 2021 Henan rains. They report about 2.5 F1 points over a BERT baseline. Social posts, Chinese event, not a call centre. The useful bit is LoRA on a small labelled flood set inside a low-latency pipeline.

https://doi.org/10.1016/j.infgeo.2026.100052

## Fast and slow systems

**Thinking Fast and Slow in AI.** Booch, Fabiano, Horesh, Kate, Lenchner, Linck, Loreggia, Murugesan, Mattei, Rossi, and Srivastava, AAAI 2021. A research agenda: treat Kahneman's System 1 as the fast learned response and System 2 as the slower deliberative one, and study how a system switches. They do not give an architecture you can copy. It is the citation for why BaanSafe has two systems and a router instead of one model.

https://arxiv.org/abs/2010.06002
Journal: https://doi.org/10.1609/aaai.v35i17.17765

**Thinking Fast and Slow in AI: the Role of Metacognition.** A follow-up that puts a metacognitive agent between a fast solver and a slow solver (they call the pattern SOFAI). Worth fifteen minutes if the route chooser is being designed. It is not a reason to set `gateway.route_chooser` from the paper.

https://arxiv.org/abs/2110.01834

## Routing and cascades

**FrugalGPT.** Chen, Zaharia, and Zou, 2023 (later a TMLR version). Three ways to spend less on model APIs: shorten the prompt, approximate the model, or cascade. Their cascade learns an order and a stop threshold. They report matching a strong model's quality at a much lower cost on the tasks they tried. The lesson for us is the shape of the decision, not the number: a cheap system handles the clear calls, and a dear one is reserved. Our gateway already refuses to run both by default. A cascade would be a human change to `config/routing.yaml`, which the stub does not implement.

https://arxiv.org/abs/2305.05176

**RouteLLM.** Ong, Almahairi, Wu, Chiang, Wu, Gonzalez, Kadous, and Stoica, 2024. Train a router on preference data to send a query to a strong model or a weak one. They report more than a 2× cost cut on some benchmarks without dropping quality, and the router still worked when the model pair changed. Relevant if System 1 becomes a small model and System 2 stays Nemotron. Not relevant while System 1 is rules.

https://arxiv.org/abs/2406.18665

## Learning from corrections

**LoRA.** Hu, Shen, Wallis, Allen-Zhu, Li, Wang, Wang, and Chen, 2021. Freeze the model, train a low-rank update. This is the usual way a Saturday fine-tune actually fits on one GPU. The correction loop writes a messages JSONL file because that is the row shape most LoRA trainers consume. The paper does not say how many corrections you need. `correction_loop.graduation_threshold` stays unset.

https://arxiv.org/abs/2106.09685

**Continual learning with LoRA (CoLoR).** Wistuba, S, Balles, and Zappella, 2023. LoRA adapters as the thing you add when the data distribution shifts, instead of prompt-tuning. They report strong domain-incremental results while staying parameter-efficient. Read this if the "fast refresh" track wins: a new flood day is a domain shift, and a full retrain is the wrong reflex.

https://arxiv.org/abs/2311.17601

**Reinforced interactive continual learning (RiCL).** Yang and colleagues, 2025. The awkward case our demo will be asked about: the human correction is streaming, and it can be wrong. They filter noisy feedback and try not to wipe earlier skills. We do not implement it. It is the objection to "every operator click becomes a training row".

https://arxiv.org/abs/2505.09925

## Human-in-the-loop safety

The Snyder paper above is the one that actually sat with responders. RiCL is the one that treats the human as noisy. InTriage and the Taipei study both keep the dispatcher as the person who is right when the model is unsure. None of them is a safeguarding policy. Humans still own denials, safeguarding exceptions, and irreversible actions, which is already the architecture line. `research/triage-philosophy.md` is the local note for how that meets our Priority and Route names, and it is suggestions only.
