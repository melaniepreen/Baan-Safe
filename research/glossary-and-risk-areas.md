# Glossary and places that flood

For fixtures and for speech-to-text. Thai here is everyday usage, not a legal glossary. Romanisation follows the words as callers say them, not a strict Royal Institute transcription.

## Words

| Thai | Roughly | Use |
|---|---|---|
| น้ำท่วม | nam thuam | flood, the general word |
| น้ำท่วมขัง | nam thuam khang | water sitting in the street, not necessarily a rescue |
| น้ำป่าไหลหลาก | nam pa lai lak | flash flood off the hills |
| น้ำหลาก | nam lak | a flood pulse coming down a river |
| น้ำล้นตลิ่ง | nam lon taling | water over the bank. This is level 5 on the ThaiWater gauge scale in our snapshot |
| โคลนถล่ม / ดินถล่ม | khlon thalom / din thalom | mudslide / landslide |
| อพยพ | aphayop | evacuate |
| จุดอพยพ / ศูนย์อพยพ | chut aphayop | an evacuation point or shelter |
| ติดอยู่ | tit yu | stuck, cannot leave |
| ชั้นสอง | chan song | the second storey, often the place people retreat to |
| หลังคา | langkha | the roof |
| เรือ | ruea | a boat |
| เชือก | chueak | a rope |
| ผู้สูงอายุ | phu sung ayu | an older person |
| เด็ก | dek | a child |
| เด็กอยู่คนเดียว | dek yu khon diao | a child who is alone. Safeguarding. Do not ask for a graphic account |
| เดินไม่ได้ / ติดเตียง | doen mai dai / tit tiang | cannot walk / bed-bound |
| ออกซิเจน | oxygen | home or hospital oxygen |
| ไฟดับ | fai dap | power cut |
| น้ำดื่ม | nam duem | drinking water |
| อาหาร | ahan | food |
| ยา | ya | medicine |
| บ้านเลขที่ | ban lek thi | a house number. Do not store a real one |
| ซอย | soi | a lane. Useful and often the only location people have |
| หมู่บ้าน | mu ban | a village |
| เทศบาล | thetsaban | a municipality |
| กำนัน / ผู้ใหญ่บ้าน | kamnan / phu yai ban | subdistrict head / village head |
| ปภ. | po bo | DDPM, as people say it |
| สายด่วน 1784 | sai duan | the DDPM hotline |

## Phrases that change the priority

These are the kind of sentences fixtures and a speech model should survive. They are written for this list, not transcribed from a real call.

| Phrase | Do not hear it as |
|---|---|
| น้ำถึงอกแล้ว (the water is at my chest) | a welfare request |
| ขึ้นชั้นบนไม่ได้ (we cannot get upstairs) | a shelter booking |
| ยายเดินไม่ได้ (grandmother cannot walk) | a low priority because the speaker is calm |
| ถังออกซิเจนใกล้หมด (the oxygen is nearly gone) | an information call about a power cut |
| เด็กอยู่คนเดียวในบ้าน (a child is alone in the house) | an ordinary missing-person query. Human, non-graphic |
| ไม่รู้ว่าอยู่ซอยอะไร (I don't know which soi) | a reason to drop the call. Ask for a temple, a shop, a road |
| เมื่อกี้โทรไปแล้ว (I already called) | automatically a duplicate. Confirm the household |
| เขาบอกว่าไม่ต้องหนี (they said we don't have to leave) | the end of the assessment. It may be a conflict between two messages |
| โทรกลับไม่ได้ เน็ตก็หมด (you can't call back, the data is gone) | a normal close. Get a second channel now |

English fixtures can keep saying "chest deep", "can't climb", "oxygen", "the blue temple", "we already called". A Thai speech-to-text test set should include the lines above, with synthetic `caller_id_hash` values only.

## Places that keep appearing

This is not an official risk ranking and it is not a choice of `data.demo_event` (still `TODO_HUMAN`). It is where public records we ingested, or the 2011 assessment, actually point.

**Lower Chao Phraya, 2011 pattern.** Ayutthaya, Pathum Thani, Nonthaburi, Bangkok, and the provinces upstream that feed the Chao Phraya barrage (Nakhon Sawan and the neighbours RID writes to when a release is coming). Slow, multi-week, release-driven. See `research/lessons-thai-floods.md`.

**South, November 2025 and earlier southern seasons.** Songkhla, especially Hat Yai; GLIDE also names Satun, Surat Thani, Nakhon Si Thammarat, Pattani, Yala, Narathiwat, Phatthalung, and Trang in recent southern flood records. Hat Yai is the city in the EOS-RS map of 23 November 2025.

**North, 2024 satellite extents and the fixture districts.** UNOSAT published water extents for Phayao, Doi Tao in Chiang Mai, and (larger files we did not download) Chiang Mai–Lamphun and Chiang Rai. The fixtures use Lampang (Mae Mo, Mae Tha, Sop Prap), Phrae (Den Chai, Long, Mueang Phrae, Wang Chin, Song, Sung Men, Rong Kwang, Nong Muang Khai), Nan (Ban Luang, Wiang Sa), and Phayao (Chiang Muan). Those names were chosen because their centres fell near the GISTDA risk polygons, not because a human picked a demo event.

**August 2026, from the GLIDE comment on `FL-2026-000158-THA`.** Phayao, Nan, Mae Hong Son, Sukhothai, Phitsanulok, Phetchabun, Sakon Nakhon, Nakhon Phanom, and Ubon Ratchathani. That is a rain-flood list for those days, not a standing ranking.

**Where the 7-day satellite layer had water on 24 October 2026.** A count-only scan of the GISTDA 7-day feature API (province codes 10–96, `numberMatched`, nothing stored from that scan) put the water in the lower Chao Phraya and its neighbours, not in the fixture provinces. The largest counts were Suphan Buri, Ayutthaya, and Nakhon Sawan, each above 10,000 cells, with more water through Ang Thong, Pathum Thani, Lopburi, Chai Nat, Sing Buri, Saraburi, Chachoengsao, Prachin Buri, Nakhon Nayok, Sukhothai, Phitsanulok, Phichit, Nakhon Pathom, and Bangkok's neighbours. Songkhla had 120 cells and Pattani 404. Lampang, Phrae, Nan, and Phayao had none that day. The full code-by-code list is in the GISTDA row of `data/SOURCES.md`. Polygons were stored for Songkhla only (the whole 7-day and 30-day pages). A first page of an Ayutthaya layer that has ten thousand cells would have looked like a complete flood and was not stored.

**Mekong and Chi-Mun towns.** Nakhon Phanom and Ubon Ratchathani recur in both GLIDE and the gauge network. A Mekong backwater flood and a flash flood in a northern valley should not share a script: one rises for days, the other arrives in an hour.

Districts in the database are whichever `admin_level=6` centres fell within 25 km of a flood cluster we were willing to query (cap 50). Check `data/SOURCES.md` for the list from this run. Matching is still nearest centre, not "the polygon contains the district".
