# RL loop run

s2=live model=nvidia/nemotron-3-nano-30b-a3b via=api.mubit.ai seed=17 episodes/epoch=48
mubit_chat: live_ok=187 cache_hits=238 errors=3 avg_latency_ms=822.6

- epoch 1: mean_reward=-0.125 correct=22/48 under=7 critical_under=2 s1=0.271 cascade=0.25 s2=0.479 fallbacks=0
- epoch 2: mean_reward=0.01 correct=18/48 under=7 critical_under=3 s1=0.25 cascade=0.25 s2=0.5 fallbacks=0
- epoch 3: mean_reward=0.189 correct=21/48 under=6 critical_under=2 s1=0.25 cascade=0.25 s2=0.5 fallbacks=1

## Events
- demote epoch=1 case=RL-WEAK-1 sig=needs=water|vuln=elderly|danger=none|medical=0|loc=ok|people
- recommend epoch=1 case=RL-UP-2 sig=needs=none|vuln=none|danger=none|medical=0|loc=ok|people=kno
- recommend epoch=3 case=RL-COLD-2 sig=needs=none|vuln=none|danger=none|medical=0|loc=ok|people=kno
