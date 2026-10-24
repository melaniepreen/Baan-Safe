"""Deterministic synthetic flood calls. No network and no model.

Eighty groups, three languages each (English, Thai, code-switched), 240 calls.
A group shares ``group_id`` so the held-out split cannot separate translations.
"""

from __future__ import annotations

import json
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from contracts.models import (
    CaseState,
    ExtractedFields,
    MemoryItem,
    Need,
    TranscriptTurn,
)
from fixtures.synthetic_gold import (
    COLOUR_TO_LABEL,
    NOUL_LABELS,
    assert_rescue,
    derive_expected,
)
from paths import ROOT

SEED = 20261024
TRAIN_FRACTION = 0.7
SYNTHETIC = ROOT / "fixtures" / "synthetic"
LANGS = ("en", "th", "mixed")

NAMES = (
    ("Arun Jaidee", "อรุณ ใจดี"),
    ("Kwan Sainam", "ขวัญ สายน้ำ"),
    ("Chala Bansuan", "ชลา บ้านสวน"),
    ("Dao Saengthong", "ดาว แสงทอง"),
    ("Natee Thongtin", "นที ท้องถิ่น"),
    ("Malee Phueng", "มาลี ผึ้ง"),
    ("Som Ruenjai", "สม เรือนใจ"),
    ("Wila Khlong", "วิลา คลอง"),
    ("Ploy Ngam", "พลอย งาม"),
    ("Ton Mai", "ต้น ใหม่"),
)

DISTRICTS = (
    ("Mae Mo District", "แม่เมาะ", "Lampang", "ลำปาง"),
    ("Mueang Lampang District", "เมืองลำปาง", "Lampang", "ลำปาง"),
    ("Mae Tha District", "แม่ทะ", "Lampang", "ลำปาง"),
    ("Song District", "สอง", "Phrae", "แพร่"),
    ("Sung Men District", "สูงเม่น", "Phrae", "แพร่"),
    ("Mueang Phrae District", "เมืองแพร่", "Phrae", "แพร่"),
    ("Nong Muang Khai District", "หนองม่วงไข่", "Phrae", "แพร่"),
    ("Ban Luang District", "บ้านหลวง", "Nan", "น่าน"),
    ("Mueang Nan District", "เมืองน่าน", "Nan", "น่าน"),
    ("Mueang Phayao District", "เมืองพะเยา", "Phayao", "พะเยา"),
)

# (people_count, en, th, mixed) — extractor-friendly English, Thai number words.
COUNTS = (
    (2, "Two of us.", "มีสองคนค่ะ", "มีสองคน, two of us."),
    (3, "There are three of us.", "มีสามคนค่ะ", "มีสามคน, three of us."),
    (4, "Four of us.", "มีสี่คนค่ะ", "มีสี่คน, four of us."),
    (5, "There are five of us.", "มีห้าคนค่ะ", "มีห้าคน, five of us."),
)

KINSHIP_TH = ("ยาย", "ตา", "หลาน", "ลูก", "พ่อ", "แม่", "ป้า", "ลุง")
NUMBER_TH = ("สอง", "สาม", "สี่", "ห้า")

OPS = {
    "en": (
        "Is anyone hurt, or is water inside the rooms?",
        "Which district are you calling from?",
        "How many people are with you?",
    ),
    "th": (
        "มีใครบาดเจ็บไหมคะ หรือน้ำเข้าบ้านหรือยัง",
        "โทรจากอำเภออะไรคะ",
        "มีกี่คนคะ",
    ),
    "mixed": (
        "Is anyone hurt, หรือน้ำเข้าบ้าน?",
        "Which district คะ",
        "How many people, มีกี่คน?",
    ),
}

# Normal facts, four paraphrases, then the twist is separate.
FACTS: dict[str, dict[str, tuple[str, ...]]] = {
    "niems_red_critical": {
        "en": (
            "{name_en}. She is unconscious and bleeding. The ground is dry.",
            "{name_en}. She is awake and bleeding, and the water is inside the house. We are trapped.",
            "{name_en}. He uses oxygen and is unconscious. The floor is dry.",
            "{name_en}. She is unconscious and bleeding. The ground is dry.",
        ),
        "th": (
            "ดิฉัน {name_th} แม่หมดสติและเลือดออก พื้นแห้ง",
            "ดิฉัน {name_th} พ่อยังรู้สึกตัวแต่เลือดออก น้ำท่วมเข้ามาในบ้าน เราติดอยู่",
            "ดิฉัน {name_th} พ่อใช้ออกซิเจนและหมดสติ พื้นแห้ง",
            "ดิฉัน {name_th} แม่หมดสติและเลือดออก พื้นแห้ง",
        ),
        "mixed": (
            "{name_en}. แม่หมดสติ and bleeding. The ground is dry.",
            "{name_en}. เลือดออก and the water is inside the house. We are trapped. เราติดอยู่",
            "{name_en}. He uses oxygen, ออกซิเจน, and is unconscious.",
            "{name_en}. แม่หมดสติ. She is unconscious and bleeding.",
        ),
    },
    "niems_yellow_urgent": {
        "en": (
            "{name_en}. Mother has laboured breathing and is wheezing. She is conscious and talking.",
            "{name_en}. Father is wheezing and needs a doctor today. He is conscious.",
            "{name_en}. She has laboured breathing. Not life-threatening, but urgent.",
            "{name_en}. Mother is wheezing. She is conscious and can talk.",
        ),
        "th": (
            "ดิฉัน {name_th} แม่หอบ หายใจลำบาก แต่ยังรู้สึกตัวและพูดได้",
            "ดิฉัน {name_th} พ่อหอบ ต้องพบแพทย์วันนี้ ยังรู้สึกตัว",
            "ดิฉัน {name_th} แม่หอบ ไม่ถึงขั้นหมดสติ แต่เร่งด่วน",
            "ดิฉัน {name_th} แม่หอบและพูดได้ ยังรู้สึกตัว",
        ),
        "mixed": (
            "{name_en}. แม่หอบ, laboured breathing. She is conscious.",
            "{name_en}. พ่อหอบ and wheezing. He is conscious and talking.",
            "{name_en}. หอบ but conscious. Urgent, not a red call.",
            "{name_en}. Mother is wheezing. แม่ยังพูดได้",
        ),
    },
    "niems_green_not_severe": {
        "en": (
            "{name_en}. He has a small cut. It is not severe. He is conscious and breathing normally.",
            "{name_en}. A small cut on the arm. He is breathing normally and is conscious.",
            "{name_en}. Minor cut only. Conscious, breathing normally, not severe.",
            "{name_en}. Small cut. He is conscious and breathing normally.",
        ),
        "th": (
            "ดิฉัน {name_th} มีแผลเล็กน้อย ไม่รุนแรง ยังรู้สึกตัวและหายใจปกติ",
            "ดิฉัน {name_th} แผลเล็กที่แขน หายใจปกติและรู้สึกตัว",
            "ดิฉัน {name_th} แผลเล็กน้อยเท่านั้น รู้สึกตัว หายใจปกติ",
            "ดิฉัน {name_th} แผลเล็ก รู้สึกตัวและหายใจปกติ",
        ),
        "mixed": (
            "{name_en}. แผลเล็กน้อย, a small cut. He is breathing normally.",
            "{name_en}. Small cut. หายใจปกติ and conscious.",
            "{name_en}. ไม่รุนแรง. Minor cut, breathing normally.",
            "{name_en}. แผลเล็ก. Conscious and breathing normally.",
        ),
    },
    "niems_white_general": {
        "en": (
            "{name_en}. This is a general patient with a mild rash. When is the clinic open tomorrow? Nobody is hurt.",
            "{name_en}. Mild rash only. When does the clinic open? Nobody is hurt.",
            "{name_en}. A general patient. What time is the clinic open tomorrow?",
            "{name_en}. Mild rash, general patient. When is the clinic open?",
        ),
        "th": (
            "ดิฉัน {name_th} เป็นผู้ป่วยทั่วไป ผื่นเล็กน้อย พรุ่งนี้คลินิกเปิดกี่โมง ไม่มีใครบาดเจ็บ",
            "ดิฉัน {name_th} ผื่นเล็กน้อย คลินิกเปิดเมื่อไร ไม่มีใครบาดเจ็บ",
            "ดิฉัน {name_th} ผู้ป่วยทั่วไป คลินิกเปิดกี่โมงพรุ่งนี้",
            "ดิฉัน {name_th} ผื่นเล็กน้อย ผู้ป่วยทั่วไป คลินิกเปิดเมื่อไร",
        ),
        "mixed": (
            "{name_en}. ผู้ป่วยทั่วไป, a mild rash. When is the clinic open tomorrow?",
            "{name_en}. Mild rash. คลินิกเปิดเมื่อไร? Nobody is hurt.",
            "{name_en}. General patient. พรุ่งนี้คลินิกเปิดกี่โมง",
            "{name_en}. ผื่นเล็กน้อย. When is the clinic open?",
        ),
    },
    "niems_black_not_a_patient": {
        "en": (
            "{name_en}. There is no patient. When is the flood update published?",
            "{name_en}. No patient here. When does the flood update come out?",
            "{name_en}. This is not a patient. When is the public update published?",
            "{name_en}. No patient. When is the flood update published?",
        ),
        "th": (
            "ดิฉัน {name_th} ไม่มีผู้ป่วยค่ะ ประกาศน้ำท่วมจะออกเมื่อไร",
            "ดิฉัน {name_th} ไม่มีคนเจ็บ ประกาศน้ำท่วมออกเมื่อไร",
            "ดิฉัน {name_th} ไม่ใช่ผู้ป่วย อยากทราบว่าประกาศจะออกเมื่อไร",
            "ดิฉัน {name_th} ไม่มีผู้ป่วย ประกาศจะเผยแพร่เมื่อไร",
        ),
        "mixed": (
            "{name_en}. ไม่มีผู้ป่วย. When is the flood update published?",
            "{name_en}. No patient. ประกาศน้ำท่วมออกเมื่อไร",
            "{name_en}. ไม่ใช่ผู้ป่วย. When does the update come out?",
            "{name_en}. No patient here. ประกาศจะออกเมื่อไร",
        ),
    },
    "niems_not_conscious_or_breathing": {
        "en": (
            "{name_en}. Father can't breathe and is unconscious. The ground is dry.",
            "{name_en}. Mother is unconscious and is not breathing normally. Dry floor.",
            "{name_en}. He is unconscious. I am calm. The ground is dry.",
            "{name_en}. Father is unconscious and can't breathe. No flood in the house.",
        ),
        "th": (
            "ดิฉัน {name_th} พ่อหายใจไม่ออกและหมดสติ พื้นแห้ง",
            "ดิฉัน {name_th} แม่หมดสติและหายใจไม่ออก พื้นแห้ง",
            "ดิฉัน {name_th} พ่อหมดสติ ดิฉันพูดช้าๆ พื้นแห้ง",
            "ดิฉัน {name_th} พ่อหายใจไม่ออก หมดสติ น้ำไม่เข้าบ้าน",
        ),
        "mixed": (
            "{name_en}. พ่อหายใจไม่ออก and is unconscious. The ground is dry.",
            "{name_en}. Mother is unconscious. แม่หายใจไม่ออก. Dry floor.",
            "{name_en}. พ่อหมดสติ. I am calm. He is unconscious.",
            "{name_en}. Father can't breathe. พ่อหายใจไม่ออก",
        ),
    },
    "sphere_water_short": {
        "en": (
            "{name_en}. We need drinking water. The ground is dry. Nobody is hurt.",
            "{name_en}. The bottles are gone. We need water to drink. Nobody is trapped.",
            "{name_en}. My aunt is with us. She is elderly. We need drinking water. The ground is dry.",
            "{name_en}. We only need water. The floor is dry. No one is hurt.",
        ),
        "th": (
            "ดิฉัน {name_th} น้ำดื่มหมดแล้ว พื้นแห้ง ไม่มีใครบาดเจ็บ",
            "ดิฉัน {name_th} น้ำขวดหมด ขอรับน้ำดื่ม ไม่มีใครติดอยู่",
            "ดิฉัน {name_th} ป้าอยู่ด้วย ป้าเป็นคนแก่ ขอรับน้ำดื่ม พื้นแห้ง",
            "ดิฉัน {name_th} ต้องการแค่น้ำดื่ม พื้นแห้ง ไม่มีใครบาดเจ็บ",
        ),
        "mixed": (
            "{name_en}. น้ำดื่มหมดแล้ว, we need drinking water. Nobody is hurt.",
            "{name_en}. Bottles are gone. ขอรับน้ำดื่ม. Nobody is trapped.",
            "{name_en}. ป้าอยู่ด้วย, she is elderly. We need drinking water.",
            "{name_en}. We only need water. ไม่มีใครบาดเจ็บ. The floor is dry.",
        ),
    },
    "sphere_food_short": {
        "en": (
            "{name_en}. The rice is finished. We need food. The ground is dry. Nobody is hurt.",
            "{name_en}. We have no food left. The floor is dry.",
            "{name_en}. Rice is gone. We need food. Nobody is trapped.",
            "{name_en}. No rice in the house. We need food. The ground is dry.",
        ),
        "th": (
            "ดิฉัน {name_th} ข้าวสารหมด ต้องการอาหาร พื้นแห้ง ไม่มีใครบาดเจ็บ",
            "ดิฉัน {name_th} อาหารไม่เหลือแล้ว พื้นแห้ง",
            "ดิฉัน {name_th} ข้าวหมด ขอรับอาหาร ไม่มีใครติดอยู่",
            "ดิฉัน {name_th} ไม่มีข้าวในบ้าน ต้องการอาหาร พื้นแห้ง",
        ),
        "mixed": (
            "{name_en}. ข้าวสารหมด, we need food. Nobody is hurt.",
            "{name_en}. No food left. พื้นแห้ง",
            "{name_en}. Rice is gone. ขอรับอาหาร. Nobody is trapped.",
            "{name_en}. ไม่มีข้าว. We need food. The ground is dry.",
        ),
    },
    "sphere_shelter_crowded": {
        "en": (
            "{name_en}. The shelter is crowded. We need a shelter bed tonight. The floor at home is dry.",
            "{name_en}. People cannot lie down. We need a shelter. The ground is dry.",
            "{name_en}. The shelter has no space. We need shelter tonight.",
            "{name_en}. Crowded shelter. We need a shelter bed. Home is dry.",
        ),
        "th": (
            "ดิฉัน {name_th} ที่พักพิงคนแน่น ต้องการที่พักคืนนี้ พื้นบ้านแห้ง",
            "ดิฉัน {name_th} นอนไม่ลง ต้องการที่พักพิง พื้นแห้ง",
            "ดิฉัน {name_th} ที่พักไม่มีที่ว่าง ต้องการที่พักคืนนี้",
            "ดิฉัน {name_th} ที่พักคนแน่นมาก ขอที่พัก บ้านแห้ง",
        ),
        "mixed": (
            "{name_en}. ที่พักพิงคนแน่น, the shelter is crowded. We need a shelter bed.",
            "{name_en}. We need a shelter. นอนไม่ลง. The ground is dry.",
            "{name_en}. ที่พักไม่มีที่ว่าง. We need shelter tonight.",
            "{name_en}. Crowded shelter. ขอที่พักคืนนี้",
        ),
    },
    "safeguarding_child": {
        "en": (
            "{name_en}. My two kids are alone at a shelter. They are unaccompanied.",
            "{name_en}. My grandchild is alone and unaccompanied at the shelter.",
            "{name_en}. A child is alone at the shelter, without a parent.",
            "{name_en}. My two kids are unaccompanied. They are alone at the shelter.",
        ),
        "th": (
            "ดิฉัน {name_th} ลูกสองคนอยู่ที่พักพิงคนเดียว ไม่มีผู้ใหญ่",
            "ดิฉัน {name_th} หลานอยู่คนเดียวที่พักพิง ไม่มีผู้ใหญ่ไปด้วย",
            "ดิฉัน {name_th} เด็กอยู่ที่พักพิงคนเดียว ไม่มีพ่อแม่",
            "ดิฉัน {name_th} ลูกอยู่คนเดียวที่พัก ไม่มีผู้ใหญ่",
        ),
        "mixed": (
            "{name_en}. ลูกสองคน are alone at a shelter. My two kids are unaccompanied.",
            "{name_en}. หลานอยู่คนเดียว. My grandchild is unaccompanied.",
            "{name_en}. A child is alone. เด็กไม่มีพ่อแม่ at the shelter.",
            "{name_en}. My two kids are unaccompanied. ลูกอยู่คนเดียว",
        ),
    },
    "safeguarding_older_person": {
        "en": (
            "{name_en}. Grandmother is elderly and we need drinking water. The ground is dry. Nobody is hurt.",
            "{name_en}. Grandfather is elderly. We need drinking water. The floor is dry.",
            "{name_en}. My aunt is elderly. We need drinking water. Nobody is hurt.",
            "{name_en}. My uncle is elderly. We need water to drink. The ground is dry.",
        ),
        "th": (
            "ดิฉัน {name_th} ยายอยู่ด้วย ยายอายุมาก ขอรับน้ำดื่ม พื้นแห้ง ไม่มีใครบาดเจ็บ",
            "ดิฉัน {name_th} ตาเป็นคนแก่ ขอรับน้ำดื่ม พื้นแห้ง",
            "ดิฉัน {name_th} ป้าอายุมาก ขอรับน้ำดื่ม ไม่มีใครบาดเจ็บ",
            "ดิฉัน {name_th} ลุงอายุมาก ต้องการน้ำดื่ม พื้นแห้ง",
        ),
        "mixed": (
            "{name_en}. ยายอายุมาก, grandmother is elderly. We need drinking water.",
            "{name_en}. ตาเป็นคนแก่. Grandfather is elderly. We need drinking water.",
            "{name_en}. ป้าอายุมาก, my aunt is elderly. Nobody is hurt.",
            "{name_en}. ลุงอายุมาก. My uncle is elderly. We need water to drink.",
        ),
    },
    "safeguarding_disability": {
        "en": (
            "{name_en}. My brother has a disability and can walk. We need drinking water. The ground is dry.",
            "{name_en}. A person with a disability is here and can walk. We need water to drink.",
            "{name_en}. He has a disability, not a wheelchair. We need drinking water.",
            "{name_en}. Disability in the household, he can walk. We only need water.",
        ),
        "th": (
            "ดิฉัน {name_th} น้องชายพิการแต่เดินได้ ขอรับน้ำดื่ม พื้นแห้ง",
            "ดิฉัน {name_th} มีคนพิการที่เดินได้ ต้องการน้ำดื่ม",
            "ดิฉัน {name_th} เขาพิการ ไม่ได้ใช้รถเข็น ขอรับน้ำดื่ม",
            "ดิฉัน {name_th} คนในบ้านพิการและเดินได้ ต้องการแค่น้ำดื่ม",
        ),
        "mixed": (
            "{name_en}. น้องชายพิการ but he can walk. We need drinking water.",
            "{name_en}. คนพิการ, can walk. We need water to drink.",
            "{name_en}. He has a disability. ไม่ได้ใช้รถเข็น. Drinking water.",
            "{name_en}. เดินได้. Disability at home. We only need water.",
        ),
    },
    "safeguarding_serious_health": {
        "en": (
            "{name_en}. Mother is wheezing, a serious health condition. She is conscious.",
            "{name_en}. Father is on dialysis and the clinic is shut. He is conscious.",
            "{name_en}. She uses oxygen. Serious health, and she is conscious.",
            "{name_en}. Mother has a serious health condition and laboured breathing. Conscious.",
        ),
        "th": (
            "ดิฉัน {name_th} แม่หอบ เป็นปัญหาสุขภาพรุนแรง แต่ยังรู้สึกตัว",
            "ดิฉัน {name_th} พ่อล้างไต คลินิกปิด ยังรู้สึกตัว",
            "ดิฉัน {name_th} แม่ใช้ออกซิเจน สุขภาพรุนแรง ยังรู้สึกตัว",
            "ดิฉัน {name_th} แม่มีปัญหาสุขภาพรุนแรงและหอบ ยังรู้สึกตัว",
        ),
        "mixed": (
            "{name_en}. แม่หอบ, a serious health condition. She is conscious.",
            "{name_en}. พ่อล้างไต, father is on dialysis. He is conscious.",
            "{name_en}. แม่ใช้ออกซิเจน. She uses oxygen and is conscious.",
            "{name_en}. Serious health. แม่หอบ and is conscious.",
        ),
    },
    "safeguarding_protection_referral": {
        "en": (
            "{name_en}. My two kids are alone. Please refer this to a person for protection.",
            "{name_en}. A child is unaccompanied. This is a protection referral.",
            "{name_en}. My child is alone without a parent. Refer this to protection.",
            "{name_en}. Unaccompanied child. A protection worker must take this.",
        ),
        "th": (
            "ดิฉัน {name_th} ลูกสองคนอยู่คนเดียว ขอส่งต่อให้คนที่ดูแลการคุ้มครอง",
            "ดิฉัน {name_th} หลานอยู่คนเดียว ไม่มีผู้ใหญ่ ขอส่งต่อการคุ้มครอง",
            "ดิฉัน {name_th} เด็กไม่มีพ่อแม่อยู่ด้วย ช่วยส่งต่อให้ผู้ดูแลการคุ้มครอง",
            "ดิฉัน {name_th} ลูกอยู่คนเดียว ต้องให้คนรับเรื่องคุ้มครอง",
        ),
        "mixed": (
            "{name_en}. ลูกสองคนอยู่คนเดียว. My two kids are unaccompanied. Refer to protection.",
            "{name_en}. หลานอยู่คนเดียว. A protection referral, the child is alone.",
            "{name_en}. เด็กไม่มีพ่อแม่. Please refer this for protection.",
            "{name_en}. Unaccompanied. ลูกอยู่คนเดียว. Protection referral.",
        ),
    },
    "flood_water_depth": {
        "en": (
            "{name_en}. The water is at the door, about knee deep. We can still step out. Nobody is trapped.",
            "{name_en}. Water is at the step, ankle deep. We are not trapped.",
            "{name_en}. The water is inside the house at knee depth. Nobody is trapped. We can step out.",
            "{name_en}. Knee-deep water is at the door. Nobody is trapped.",
        ),
        "th": (
            "ดิฉัน {name_th} น้ำถึงประตู ลึกประมาณเข่า ยังเดินออกได้ ไม่มีใครติดอยู่",
            "ดิฉัน {name_th} น้ำถึงบันได ลึกข้อเท้า ยังไม่ติดอยู่",
            "ดิฉัน {name_th} น้ำเข้าบ้านลึกถึงเข่า ไม่มีใครติด ยังเดินออกได้",
            "ดิฉัน {name_th} น้ำลึกระดับเข่าถึงประตู ไม่มีใครติดอยู่",
        ),
        "mixed": (
            "{name_en}. น้ำถึงประตู, the water is at the door, knee deep. Nobody is trapped.",
            "{name_en}. Water is at the step. ลึกข้อเท้า. We are not trapped.",
            "{name_en}. น้ำเข้าบ้าน, knee deep. Nobody is trapped. We can step out.",
            "{name_en}. Knee-deep at the door. ไม่มีใครติดอยู่",
        ),
    },
    "flood_trapped": {
        "en": (
            "{name_en}. We are trapped on the roof and cannot get out. The water is inside the house.",
            "{name_en}. We cannot get out. Trapped upstairs. Water is inside the house.",
            "{name_en}. On the roof, trapped, cannot get out. The water is inside.",
            "{name_en}. Trapped. Cannot get out. Water is inside the house.",
        ),
        "th": (
            "ดิฉัน {name_th} เราติดอยู่บนหลังคา ออกไปไม่ได้ น้ำท่วมเข้ามาในบ้าน",
            "ดิฉัน {name_th} ออกจากบ้านไม่ได้ ติดอยู่ชั้นบน น้ำอยู่ในบ้าน",
            "ดิฉัน {name_th} อยู่บนหลังคา ติดอยู่ ออกไปไม่ได้",
            "ดิฉัน {name_th} ติดอยู่ในน้ำ ออกไปไม่ได้ น้ำเข้าบ้านแล้ว",
        ),
        "mixed": (
            "{name_en}. เราติดอยู่บนหลังคา and cannot get out. Water is inside the house.",
            "{name_en}. We cannot get out. ติดอยู่ชั้นบน",
            "{name_en}. On the roof, ออกไปไม่ได้. Trapped.",
            "{name_en}. ติดอยู่. Cannot get out. The water is inside the house.",
        ),
    },
}

DETAILS = {
    "niems_red_critical": {
        "en": "Please hurry. This is a life-threatening emergency.",
        "th": "ช่วยด้วยค่ะ ฉุกเฉินมาก",
        "mixed": "ช่วยด้วย. This is life-threatening.",
    },
    "niems_yellow_urgent": {
        "en": "Urgent, but she is not unconscious.",
        "th": "เร่งด่วน แต่ไม่หมดสติ",
        "mixed": "Urgent. ไม่หมดสติ",
    },
    "niems_green_not_severe": {
        "en": "No. It is not severe.",
        "th": "ไม่รุนแรงค่ะ",
        "mixed": "ไม่รุนแรง. Not severe.",
    },
    "niems_white_general": {
        "en": "Nobody is hurt. We only need the clinic time.",
        "th": "ไม่มีใครบาดเจ็บ อยากทราบเวลาคลินิก",
        "mixed": "Nobody is hurt. อยากทราบเวลาคลินิก",
    },
    "niems_black_not_a_patient": {
        "en": "No patient and nobody is hurt.",
        "th": "ไม่มีผู้ป่วยและไม่มีใครบาดเจ็บ",
        "mixed": "No patient. ไม่มีใครบาดเจ็บ",
    },
    "niems_not_conscious_or_breathing": {
        "en": "I am speaking slowly. He is not conscious.",
        "th": "ดิฉันพูดช้าๆ เขาไม่รู้สึกตัว",
        "mixed": "I am calm. เขาไม่รู้สึกตัว",
    },
    "sphere_water_short": {
        "en": "No. Nobody is hurt and nobody is trapped.",
        "th": "ไม่มีค่ะ ไม่มีใครบาดเจ็บ และไม่มีใครติดอยู่",
        "mixed": "No. ไม่มีใครบาดเจ็บ and nobody is trapped.",
    },
    "sphere_food_short": {
        "en": "No. The ground is dry and nobody is hurt.",
        "th": "พื้นแห้ง ไม่มีใครบาดเจ็บ",
        "mixed": "พื้นแห้ง. Nobody is hurt.",
    },
    "sphere_shelter_crowded": {
        "en": "No one is hurt. We only need shelter.",
        "th": "ไม่มีใครบาดเจ็บ ต้องการแค่ที่พัก",
        "mixed": "ไม่มีใครบาดเจ็บ. We only need shelter.",
    },
    "safeguarding_child": {
        "en": "No adult is with them. They are unaccompanied.",
        "th": "ไม่มีผู้ใหญ่อยู่ด้วย พวกเขาลำพัง",
        "mixed": "No adult with them. ไม่มีผู้ใหญ่",
    },
    "safeguarding_older_person": {
        "en": "Nobody is hurt. The older person needs drinking water.",
        "th": "ไม่มีใครบาดเจ็บ ผู้สูงอายุต้องการน้ำดื่ม",
        "mixed": "Nobody is hurt. ผู้สูงอายุต้องการน้ำดื่ม",
    },
    "safeguarding_disability": {
        "en": "He can walk today. We need drinking water.",
        "th": "วันนี้เดินได้ ขอรับน้ำดื่ม",
        "mixed": "He can walk. ขอรับน้ำดื่ม",
    },
    "safeguarding_serious_health": {
        "en": "A person must decide the medical response. She is conscious.",
        "th": "ต้องให้คนตัดสินใจเรื่องการรักษา ยังรู้สึกตัว",
        "mixed": "A person must decide. ยังรู้สึกตัว",
    },
    "safeguarding_protection_referral": {
        "en": "Please hand this to a protection worker.",
        "th": "ขอส่งต่อให้ผู้ดูแลการคุ้มครอง",
        "mixed": "Protection referral. ส่งต่อให้คนดูแล",
    },
    "flood_water_depth": {
        "en": "Nobody is trapped. We can still step out.",
        "th": "ไม่มีใครติดอยู่ ยังเดินออกได้",
        "mixed": "Nobody is trapped. ยังเดินออกได้",
    },
    "flood_trapped": {
        "en": "We cannot get out. Please send help.",
        "th": "ออกไปไม่ได้ ช่วยด้วยค่ะ",
        "mixed": "Cannot get out. ช่วยด้วย",
    },
}

# variant index 4 replacements: (fact, detail) per language, plus field overrides.
TWISTS: dict[str, dict] = {
    "niems_red_critical": {
        "tag": "calm_critical",
        "needs": ["rescue", "medical"],
        "medical": True,
        "vulnerable": ["elderly", "child"],
        "danger": ["rising_water"],
        "flags": ["safeguarding"],
        "extras": [
            "niems_not_conscious_or_breathing",
            "safeguarding_older_person",
            "safeguarding_child",
            "flood_trapped",
            "flood_water_depth",
        ],
        "hard_negatives": [],
        "count": (
            4,
            "Four of us. My grandmother, myself, and my two grandchildren.",
            "มีสี่คนค่ะ ยาย ดิฉัน และหลานสองคน",
            "มีสี่คน, four of us. หลานสองคน",
        ),
        "lines": {
            "en": (
                "{name_en}. I am speaking slowly. My grandmother can't breathe.",
                "She is unconscious. My two grandchildren are on the roof and cannot get out. The water is inside the house.",
            ),
            "th": (
                "ดิฉันพูดช้าๆ ค่ะ ยายหายใจไม่ออก",
                "ยายไม่รู้สึกตัว หลานอยู่บนหลังคา ออกมาไม่ได้ น้ำท่วมเข้ามาในบ้าน",
            ),
            "mixed": (
                "{name_en}. ยายหายใจไม่ออก. My grandmother can't breathe.",
                "หลานอยู่บนหลังคา and cannot get out. She is unconscious. The water is inside the house.",
            ),
        },
    },
    "niems_yellow_urgent": {
        "tag": "multi",
        "needs": ["medical"],
        "medical": True,
        "vulnerable": ["oxygen_dependent"],
        "danger": [],
        "flags": [],
        "extras": ["safeguarding_serious_health"],
        "hard_negatives": ["niems_not_conscious_or_breathing", "niems_red_critical"],
        "lines": {
            "en": (
                "{name_en}. Mother uses oxygen and is wheezing. She is conscious.",
                "Urgent after the life-threatening cases. She is not unconscious.",
            ),
            "th": (
                "ดิฉัน {name_th} แม่ใช้ออกซิเจนและหอบ ยังรู้สึกตัว",
                "เร่งด่วน แต่ไม่หมดสติ",
            ),
            "mixed": (
                "{name_en}. แม่ใช้ออกซิเจน and is wheezing. Conscious.",
                "Not unconscious. ยังรู้สึกตัว",
            ),
        },
    },
    "niems_green_not_severe": {
        "tag": "sarcasm",
        "needs": ["medical"],
        "medical": True,
        "vulnerable": [],
        "danger": [],
        "flags": ["conflicting_evidence"],
        "extras": [],
        "hard_negatives": ["niems_red_critical", "niems_not_conscious_or_breathing"],
        "lines": {
            "en": (
                "{name_en}. Oh it's nothing, just a scratch, she says. He has a small cut and is breathing normally.",
                "It is not severe. He is conscious. Do not mark this red.",
            ),
            "th": (
                "ดิฉัน {name_th} บอกว่าไม่มีอะไร แต่มีแผลเล็กน้อย หายใจปกติ",
                "ไม่รุนแรงและรู้สึกตัว ไม่ใช่สายวิกฤติ",
            ),
            "mixed": (
                "{name_en}. It's nothing, she says. แผลเล็กน้อย and breathing normally.",
                "Not severe. รู้สึกตัว",
            ),
        },
    },
    "niems_white_general": {
        "tag": "multi",
        "needs": ["information"],
        "medical": False,
        "vulnerable": ["child"],
        "danger": [],
        "flags": [],
        "extras": ["safeguarding_child"],
        "hard_negatives": ["niems_red_critical"],
        "count": (
            3,
            "There are three of us, my two kids and me.",
            "มีสามคน ลูกสองคนกับฉัน",
            "มีสามคน, three of us, my two kids and me.",
        ),
        "lines": {
            "en": (
                "{name_en}. My two kids have a mild rash. When is the clinic open tomorrow? Nobody is hurt.",
                "A general patient. They are with me, not alone.",
            ),
            "th": (
                "ดิฉัน {name_th} ลูกมีผื่นเล็กน้อย พรุ่งนี้คลินิกเปิดกี่โมง ไม่มีใครบาดเจ็บ",
                "ผู้ป่วยทั่วไป ลูกอยู่กับฉัน ไม่ได้ลำพัง",
            ),
            "mixed": (
                "{name_en}. ลูกมีผื่นเล็กน้อย. My two kids. When is the clinic open?",
                "They are with me. ไม่ได้ลำพัง. Nobody is hurt.",
            ),
        },
    },
    "niems_black_not_a_patient": {
        "tag": "missing_location",
        "gap": "location",
        "needs": ["information"],
        "medical": False,
        "vulnerable": [],
        "danger": [],
        "flags": [],
        "extras": [],
        "hard_negatives": ["niems_red_critical", "niems_not_conscious_or_breathing"],
        "lines": {
            "en": (
                "{name_en}. No patient. When is the flood update published? Nobody is hurt.",
                "I cannot name the district.",
            ),
            "th": (
                "ดิฉัน {name_th} ไม่มีผู้ป่วย ประกาศน้ำท่วมจะออกเมื่อไร ไม่มีใครบาดเจ็บ",
                "ไม่ทราบอำเภอค่ะ",
            ),
            "mixed": (
                "{name_en}. ไม่มีผู้ป่วย. When is the flood update published?",
                "I do not know the district. ไม่ทราบอำเภอ",
            ),
        },
    },
    "niems_not_conscious_or_breathing": {
        "tag": "calm_critical",
        "needs": ["medical"],
        "medical": True,
        "vulnerable": [],
        "danger": [],
        "flags": [],
        "extras": ["safeguarding_serious_health"],
        "hard_negatives": [],
        "lines": {
            "en": (
                "{name_en}. I am calm. Father can't breathe and is unconscious. The ground is dry.",
                "There is no shouting. He is not conscious.",
            ),
            "th": (
                "ดิฉัน {name_th} พูดช้าๆ พ่อหายใจไม่ออกและหมดสติ พื้นแห้ง",
                "ไม่มีเสียงตะโกน เขาไม่รู้สึกตัว",
            ),
            "mixed": (
                "{name_en}. I am calm. พ่อหายใจไม่ออก and unconscious.",
                "No shouting. เขาไม่รู้สึกตัว",
            ),
        },
    },
    "sphere_water_short": {
        "tag": "duplicate",
        "duplicate_of_variant": 0,
        "needs": ["water"],
        "medical": False,
        "vulnerable": [],
        "danger": [],
        "flags": [],
        "extras": [],
        "hard_negatives": [
            "niems_red_critical",
            "niems_not_conscious_or_breathing",
            "flood_trapped",
        ],
        "lines": {
            "en": (
                "{name_en}. I called earlier about drinking water for this same household. Nobody is hurt.",
                "Please do not open a second case. The ground is dry. Nobody is trapped.",
            ),
            "th": (
                "ดิฉัน {name_th} เมื่อกี้โทรเรื่องน้ำดื่มของบ้านเดิม ไม่มีใครบาดเจ็บ",
                "อย่าเปิดเคสใหม่ พื้นแห้ง ไม่มีใครติดอยู่",
            ),
            "mixed": (
                "{name_en}. I called earlier. น้ำดื่มของบ้านเดิม. Nobody is hurt.",
                "Do not open a second case. ไม่มีใครติดอยู่",
            ),
        },
    },
    "sphere_food_short": {
        "tag": "sarcasm",
        "needs": ["food"],
        "medical": False,
        "vulnerable": [],
        "danger": [],
        "flags": [],
        "extras": [],
        "hard_negatives": ["flood_trapped", "niems_red_critical", "flood_water_depth"],
        "lines": {
            "en": (
                "{name_en}. Ha, I was only joking about drowning. We are not trapped. We need food. The rice is finished.",
                "The ground is dry. Nobody is hurt. That drowning line was sarcasm.",
            ),
            "th": (
                "ดิฉัน {name_th} เมื่อกี้ล้อเล่นเรื่องจมน้ำ เราไม่ได้ติดอยู่ในน้ำ ข้าวสารหมด ต้องการอาหาร",
                "พื้นแห้ง ไม่มีใครบาดเจ็บ ประโยคเมื่อกี้เป็นประชด",
            ),
            "mixed": (
                "{name_en}. Just kidding about drowning. ไม่ได้ติดอยู่. We need food. ข้าวสารหมด",
                "The ground is dry. ประชดเท่านั้น. Nobody is hurt.",
            ),
        },
    },
    "sphere_shelter_crowded": {
        "tag": "sarcasm",
        "needs": ["shelter"],
        "medical": False,
        "vulnerable": [],
        "danger": [],
        "flags": [],
        "extras": [],
        "hard_negatives": [],
        "lines": {
            "en": (
                "{name_en}. Oh the shelter is wonderfully spacious, she says, sarcastic. We are packed in and need a shelter bed.",
                "That was sarcasm. The shelter is crowded. Home is dry.",
            ),
            "th": (
                "ดิฉัน {name_th} ที่พักกว้างขวางจังเลย พูดประชด คนแน่นมาก ต้องการที่พักพิง",
                "ประชดค่ะ ที่พักคนแน่น บ้านแห้ง",
            ),
            "mixed": (
                "{name_en}. So spacious, sure. ที่พักคนแน่น. We need a shelter bed.",
                "Sarcasm. The shelter is crowded. บ้านแห้ง",
            ),
        },
    },
    "safeguarding_child": {
        "tag": "hard_kinship",
        "needs": ["shelter"],
        "medical": False,
        "vulnerable": ["child"],
        "danger": [],
        "flags": ["safeguarding"],
        "extras": ["safeguarding_protection_referral"],
        "hard_negatives": [],
        "count": (
            3,
            "There are three of us, my two kids and me, but the grandchild is alone at the shelter.",
            "มีสามคน แต่หลานอยู่ที่พักคนเดียว",
            "มีสามคน, three of us, but หลาน is alone.",
        ),
        "lines": {
            "en": (
                "{name_en}. My grandchild is alone at the shelter, unaccompanied. My two kids are usually with me.",
                "No parent is with the grandchild. Please treat this as protection.",
            ),
            "th": (
                "ดิฉัน {name_th} หลานอยู่ที่พักพิงคนเดียว ไม่มีผู้ใหญ่",
                "ไม่มีพ่อแม่อยู่กับหลาน ขอให้คนดูแลการคุ้มครอง",
            ),
            "mixed": (
                "{name_en}. หลานอยู่คนเดียว at the shelter, unaccompanied.",
                "No parent with หลาน. Protection, please.",
            ),
        },
    },
    "safeguarding_older_person": {
        "tag": "duplicate",
        "duplicate_of_variant": 0,
        "needs": ["water"],
        "medical": False,
        "vulnerable": ["elderly"],
        "danger": [],
        "flags": [],
        "extras": [],
        "hard_negatives": ["niems_red_critical", "flood_trapped"],
        "lines": {
            "en": (
                "{name_en}. I called earlier. Grandmother is elderly and we still need drinking water.",
                "Same household. Nobody is hurt. Please do not open a second case.",
            ),
            "th": (
                "ดิฉัน {name_th} เมื่อกี้โทรแล้ว ยายยังต้องการน้ำดื่ม",
                "บ้านเดิม ไม่มีใครบาดเจ็บ อย่าเปิดเคสใหม่",
            ),
            "mixed": (
                "{name_en}. I called earlier. ยายยังต้องการน้ำดื่ม",
                "Same household. ไม่มีใครบาดเจ็บ",
            ),
        },
    },
    "safeguarding_disability": {
        "tag": "immobile",
        "colour": "yellow",
        "needs": ["water"],
        "medical": False,
        "vulnerable": ["disability", "immobile"],
        "danger": [],
        "flags": [],
        "extras": [],
        "hard_negatives": ["flood_trapped"],
        "lines": {
            "en": (
                "{name_en}. My brother uses a wheelchair and cannot walk. We need drinking water. The ground is dry.",
                "He is immobile. Nobody is trapped.",
            ),
            "th": (
                "ดิฉัน {name_th} น้องชายนั่งรถเข็น เดินไม่ได้ ขอรับน้ำดื่ม พื้นแห้ง",
                "เขาขยับเองไม่ได้ ไม่มีใครติดอยู่",
            ),
            "mixed": (
                "{name_en}. นั่งรถเข็น and cannot walk. We need drinking water.",
                "Immobile. ไม่มีใครติดอยู่. The ground is dry.",
            ),
        },
    },
    "safeguarding_serious_health": {
        "tag": "calm_critical",
        "needs": ["medical"],
        "medical": True,
        "vulnerable": ["oxygen_dependent"],
        "danger": [],
        "flags": [],
        "extras": [],
        "hard_negatives": ["flood_trapped"],
        "lines": {
            "en": (
                "{name_en}. I am calm. Mother uses oxygen and has laboured breathing. She is conscious.",
                "A serious health condition. A person must decide.",
            ),
            "th": (
                "ดิฉัน {name_th} พูดช้าๆ แม่ใช้ออกซิเจนและหอบ ยังรู้สึกตัว",
                "สุขภาพรุนแรง ต้องให้คนตัดสินใจ",
            ),
            "mixed": (
                "{name_en}. I am calm. แม่ใช้ออกซิเจน and laboured breathing.",
                "Serious health. ยังรู้สึกตัว",
            ),
        },
    },
    "safeguarding_protection_referral": {
        "tag": "multi",
        "needs": ["shelter"],
        "medical": False,
        "vulnerable": ["child", "elderly"],
        "danger": [],
        "flags": ["safeguarding"],
        "extras": ["safeguarding_child", "safeguarding_older_person"],
        "hard_negatives": [],
        "lines": {
            "en": (
                "{name_en}. Grandmother is elderly and my child is alone at the shelter. Refer this for protection.",
                "The child is unaccompanied. An older person is in the household too.",
            ),
            "th": (
                "ดิฉัน {name_th} ยายอยู่ที่บ้านและลูกอยู่ที่พักคนเดียว ขอส่งต่อการคุ้มครอง",
                "ลูกไม่มีผู้ใหญ่ไปด้วย ยายอายุมาก",
            ),
            "mixed": (
                "{name_en}. ยายอยู่ที่บ้าน and my child is alone. Protection referral.",
                "ลูกอยู่คนเดียว. Grandmother is elderly.",
            ),
        },
    },
    "flood_water_depth": {
        "tag": "multi",
        "needs": ["rescue"],
        "medical": False,
        "vulnerable": ["elderly"],
        "danger": ["rising_water"],
        "flags": [],
        "extras": ["safeguarding_older_person"],
        "hard_negatives": ["flood_trapped"],
        "lines": {
            "en": (
                "{name_en}. Grandmother is elderly. The water is at the door, knee deep. We can still step out. Nobody is trapped.",
                "Please log the depth. We are not trapped.",
            ),
            "th": (
                "ดิฉัน {name_th} ยายอยู่ด้วย น้ำถึงประตูลึกระดับเข่า ยังเดินออกได้ ไม่มีใครติดอยู่",
                "ขอให้บันทึกความลึก ยังไม่ติด",
            ),
            "mixed": (
                "{name_en}. ยายอยู่ด้วย. Water is at the door, knee deep. Nobody is trapped.",
                "We can step out. ไม่มีใครติดอยู่",
            ),
        },
    },
    "flood_trapped": {
        "tag": "calm_critical",
        "needs": ["rescue"],
        "medical": False,
        "vulnerable": [],
        "danger": ["rising_water"],
        "flags": [],
        "extras": ["flood_water_depth"],
        "hard_negatives": [],
        "lines": {
            "en": (
                "{name_en}. I am calm. We are on the roof and cannot get out. The water is inside the house.",
                "No shouting. We are trapped.",
            ),
            "th": (
                "ดิฉัน {name_th} พูดช้าๆ เราอยู่บนหลังคา ออกไปไม่ได้ น้ำท่วมเข้ามาในบ้าน",
                "ไม่มีเสียงตะโกน เราติดอยู่",
            ),
            "mixed": (
                "{name_en}. I am calm. อยู่บนหลังคา and cannot get out.",
                "No shouting. เราติดอยู่. Water is inside the house.",
            ),
        },
    },
}


# Static fields for variants 0-3. Variant 3 may apply a gap. Variant 4 uses TWISTS.
BASE = {
    "niems_red_critical": [
        dict(needs=["medical"], medical=True, vulnerable=[], danger=[], flags=[],
             extras=["niems_not_conscious_or_breathing", "safeguarding_serious_health"],
             hard=["flood_trapped"]),
        dict(needs=["rescue", "medical"], medical=True, vulnerable=[], danger=["rising_water"], flags=[],
             extras=["flood_trapped", "flood_water_depth", "safeguarding_serious_health"],
             hard=[]),
        dict(needs=["medical"], medical=True, vulnerable=["oxygen_dependent"], danger=[], flags=[],
             extras=["niems_not_conscious_or_breathing", "safeguarding_serious_health"],
             hard=["flood_trapped"]),
        dict(needs=["medical"], medical=True, vulnerable=[], danger=[], flags=[],
             extras=["niems_not_conscious_or_breathing", "safeguarding_serious_health"],
             hard=["flood_trapped"], gap="location"),
    ],
    "niems_yellow_urgent": [
        dict(needs=["medical"], medical=True, vulnerable=[], danger=[], flags=[],
             extras=["safeguarding_serious_health"],
             hard=["niems_red_critical", "niems_not_conscious_or_breathing"]),
        dict(needs=["medical"], medical=True, vulnerable=[], danger=[], flags=[],
             extras=["safeguarding_serious_health"],
             hard=["niems_red_critical", "niems_not_conscious_or_breathing"]),
        dict(needs=["medical"], medical=True, vulnerable=[], danger=[], flags=[],
             extras=["safeguarding_serious_health"],
             hard=["niems_red_critical", "niems_not_conscious_or_breathing"]),
        dict(needs=["medical"], medical=True, vulnerable=[], danger=[], flags=[],
             extras=["safeguarding_serious_health"],
             hard=["niems_red_critical", "niems_not_conscious_or_breathing"]),
    ],
    "niems_green_not_severe": [
        dict(needs=["medical"], medical=True, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["niems_red_critical", "niems_not_conscious_or_breathing"]),
        dict(needs=["medical"], medical=True, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["niems_red_critical", "niems_not_conscious_or_breathing"]),
        dict(needs=["medical"], medical=True, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["niems_red_critical", "niems_not_conscious_or_breathing"]),
        dict(needs=["medical"], medical=True, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["niems_red_critical", "niems_not_conscious_or_breathing"], gap="location"),
    ],
    "niems_white_general": [
        dict(needs=["information"], medical=False, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["niems_red_critical", "sphere_water_short"]),
        dict(needs=["information"], medical=False, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["niems_red_critical"]),
        dict(needs=["information"], medical=False, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["niems_red_critical"]),
        dict(needs=["information"], medical=False, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["niems_red_critical"], gap="people"),
    ],
    "niems_black_not_a_patient": [
        dict(needs=["information"], medical=False, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["niems_red_critical", "sphere_water_short"]),
        dict(needs=["information"], medical=False, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["niems_red_critical"]),
        dict(needs=["information"], medical=False, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["niems_red_critical"]),
        dict(needs=["information"], medical=False, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["niems_red_critical"], gap="location"),
    ],
    "niems_not_conscious_or_breathing": [
        dict(needs=["medical"], medical=True, vulnerable=[], danger=[], flags=[],
             extras=["safeguarding_serious_health"], hard=["flood_trapped"]),
        dict(needs=["medical"], medical=True, vulnerable=[], danger=[], flags=[],
             extras=["safeguarding_serious_health"], hard=["flood_trapped"]),
        dict(needs=["medical"], medical=True, vulnerable=[], danger=[], flags=[],
             extras=["safeguarding_serious_health"], hard=["flood_trapped"]),
        dict(needs=["medical"], medical=True, vulnerable=[], danger=[], flags=[],
             extras=["safeguarding_serious_health"], hard=["flood_trapped"]),
    ],
    "sphere_water_short": [
        dict(needs=["water"], medical=False, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["niems_red_critical", "niems_not_conscious_or_breathing", "flood_trapped"]),
        dict(needs=["water"], medical=False, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["niems_red_critical", "flood_trapped"]),
        dict(needs=["water"], medical=False, vulnerable=["elderly"], danger=[], flags=[],
             extras=["safeguarding_older_person"],
             hard=["niems_red_critical", "flood_trapped"]),
        dict(needs=["water"], medical=False, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["niems_red_critical", "flood_trapped"], gap="people"),
    ],
    "sphere_food_short": [
        dict(needs=["food"], medical=False, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["flood_trapped", "niems_red_critical"]),
        dict(needs=["food"], medical=False, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["flood_trapped"]),
        dict(needs=["food"], medical=False, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["flood_trapped", "niems_red_critical"]),
        dict(needs=["food"], medical=False, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["flood_trapped"], gap="people"),
    ],
    "sphere_shelter_crowded": [
        dict(needs=["shelter"], medical=False, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["flood_trapped"]),
        dict(needs=["shelter"], medical=False, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["niems_red_critical"]),
        dict(needs=["shelter"], medical=False, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["flood_trapped"]),
        dict(needs=["shelter"], medical=False, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["flood_trapped"], gap="people"),
    ],
    "safeguarding_child": [
        dict(needs=["shelter"], medical=False, vulnerable=["child"], danger=[], flags=["safeguarding"],
             extras=["safeguarding_protection_referral"], hard=[]),
        dict(needs=["shelter"], medical=False, vulnerable=["child"], danger=[], flags=["safeguarding"],
             extras=["safeguarding_protection_referral"], hard=[]),
        dict(needs=["shelter"], medical=False, vulnerable=["child"], danger=[], flags=["safeguarding"],
             extras=["safeguarding_protection_referral"], hard=[]),
        dict(needs=["shelter"], medical=False, vulnerable=["child"], danger=[], flags=["safeguarding"],
             extras=["safeguarding_protection_referral"], hard=[]),
    ],
    "safeguarding_older_person": [
        dict(needs=["water"], medical=False, vulnerable=["elderly"], danger=[], flags=[], extras=[],
             hard=["niems_red_critical", "flood_trapped"]),
        dict(needs=["water"], medical=False, vulnerable=["elderly"], danger=[], flags=[], extras=[],
             hard=["flood_trapped"]),
        dict(needs=["water"], medical=False, vulnerable=["elderly"], danger=[], flags=[], extras=[],
             hard=["niems_red_critical"]),
        dict(needs=["water"], medical=False, vulnerable=["elderly"], danger=[], flags=[], extras=[],
             hard=["flood_trapped"], gap="people"),
    ],
    "safeguarding_disability": [
        dict(needs=["water"], medical=False, vulnerable=["disability"], danger=[], flags=[], extras=[],
             hard=["flood_trapped"]),
        dict(needs=["water"], medical=False, vulnerable=["disability"], danger=[], flags=[], extras=[],
             hard=["niems_red_critical"]),
        dict(needs=["water"], medical=False, vulnerable=["disability"], danger=[], flags=[], extras=[],
             hard=["flood_trapped"]),
        dict(needs=["water"], medical=False, vulnerable=["disability"], danger=[], flags=[], extras=[],
             hard=["flood_trapped"], gap="people"),
    ],
    "safeguarding_serious_health": [
        dict(needs=["medical"], medical=True, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["flood_trapped", "niems_red_critical"]),
        dict(needs=["medical"], medical=True, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["flood_trapped", "niems_not_conscious_or_breathing"]),
        dict(needs=["medical"], medical=True, vulnerable=["oxygen_dependent"], danger=[], flags=[], extras=[],
             hard=["flood_trapped"]),
        dict(needs=["medical"], medical=True, vulnerable=[], danger=[], flags=[], extras=[],
             hard=["flood_trapped"]),
    ],
    "safeguarding_protection_referral": [
        dict(needs=["shelter"], medical=False, vulnerable=["child"], danger=[], flags=["safeguarding"],
             extras=["safeguarding_child"], hard=[]),
        dict(needs=["shelter"], medical=False, vulnerable=["child"], danger=[], flags=["safeguarding"],
             extras=["safeguarding_child"], hard=[]),
        dict(needs=["shelter"], medical=False, vulnerable=["child"], danger=[], flags=["safeguarding"],
             extras=["safeguarding_child"], hard=[]),
        dict(needs=["shelter"], medical=False, vulnerable=["child"], danger=[], flags=["safeguarding"],
             extras=["safeguarding_child"], hard=[]),
    ],
    "flood_water_depth": [
        dict(needs=["rescue"], medical=False, vulnerable=[], danger=["rising_water"], flags=[], extras=[],
             hard=["flood_trapped"]),
        dict(needs=["rescue"], medical=False, vulnerable=[], danger=["rising_water"], flags=[], extras=[],
             hard=["flood_trapped", "niems_red_critical"]),
        dict(needs=["rescue"], medical=False, vulnerable=[], danger=["rising_water"], flags=[], extras=[],
             hard=["flood_trapped"]),
        dict(needs=["rescue"], medical=False, vulnerable=[], danger=["rising_water"], flags=[], extras=[],
             hard=["flood_trapped"]),
    ],
    "flood_trapped": [
        dict(needs=["rescue"], medical=False, vulnerable=[], danger=["rising_water"], flags=[],
             extras=["flood_water_depth"], hard=[]),
        dict(needs=["rescue"], medical=False, vulnerable=[], danger=["rising_water"], flags=[],
             extras=["flood_water_depth"], hard=[]),
        dict(needs=["rescue"], medical=False, vulnerable=[], danger=["rising_water"], flags=[],
             extras=["flood_water_depth"], hard=[]),
        dict(needs=["rescue"], medical=False, vulnerable=[], danger=["rising_water"], flags=[],
             extras=["flood_water_depth"], hard=[]),
    ],
}

COLOUR = {
    "niems_red_critical": "red",
    "niems_yellow_urgent": "yellow",
    "niems_green_not_severe": "green",
    "niems_white_general": "white",
    "niems_black_not_a_patient": "black",
    "niems_not_conscious_or_breathing": "red",
    "sphere_water_short": "black",
    "sphere_food_short": "black",
    "sphere_shelter_crowded": "black",
    "safeguarding_child": "yellow",
    "safeguarding_older_person": "black",
    "safeguarding_disability": "black",
    "safeguarding_serious_health": "yellow",
    "safeguarding_protection_referral": "yellow",
    "flood_water_depth": "yellow",
    "flood_trapped": "red",
}

PRIMARIES = tuple(COLOUR)

CHILD_PRIMARIES = {"safeguarding_child", "safeguarding_protection_referral"}
GAPS = {
    "niems_red_critical": "location",
    "niems_green_not_severe": "location",
    "niems_white_general": "people",
    "niems_black_not_a_patient": "location",
    "sphere_water_short": "people",
    "sphere_food_short": "people",
    "sphere_shelter_crowded": "people",
    "safeguarding_older_person": "people",
    "safeguarding_disability": "people",
}

DEMO_IDS = (
    "syn-niems-red-critical-05-th",
    "syn-flood-trapped-05-en",
    "syn-sphere-water-short-01-th",
    "syn-safeguarding-child-05-mixed",
    "syn-sphere-shelter-crowded-05-en",
    "syn-sphere-water-short-05-th",
    "syn-sphere-food-short-05-en",
    "syn-niems-not-conscious-or-breathing-05-mixed",
)


def _pack(primary_index: int, variant: int, *, like_variant: int | None = None) -> dict:
    slot = variant if like_variant is None else like_variant
    name_en, name_th = NAMES[(primary_index * 3 + slot) % len(NAMES)]
    district = DISTRICTS[(primary_index + slot) % len(DISTRICTS)]
    street_n = (primary_index + slot) % 9 + 3
    return {
        "name_en": name_en,
        "name_th": name_th,
        "district_en": district[0],
        "district_th": district[1],
        "province_en": district[2],
        "province_th": district[3],
        "street_n": street_n,
    }


def _count(primary: str, variant: int, primary_index: int):
    if primary in CHILD_PRIMARIES:
        return (
            3,
            "There are three of us, my two kids and me.",
            "มีสามคน ลูกสองคนกับฉัน" if primary == "safeguarding_child" else "มีสามคน ลูกสองคน",
            "มีสามคน, three of us, my two kids and me.",
        )
    return COUNTS[(primary_index + variant) % len(COUNTS)]


def _location_line(lang: str, pack: dict, missing: bool) -> str:
    if missing:
        return {
            "en": "I am near the invented blue temple. I do not know the district.",
            "th": "อยู่ใกล้ศาลาน้ำเงินที่สมมติขึ้น ไม่ทราบอำเภอค่ะ",
            "mixed": "ใกล้ศาลาน้ำเงิน, the invented blue temple. I do not know the district.",
        }[lang]
    if lang == "en":
        return (
            f"We are in {pack['district_en']}, {pack['province_en']}, "
            f"near Placeholder Soi {pack['street_n']}."
        )
    if lang == "th":
        return (
            f"อยู่ที่อำเภอ{pack['district_th']} จังหวัด{pack['province_th']} "
            f"ใกล้ซอยตัวอย่าง {pack['street_n']} ค่ะ"
        )
    return (
        f"อยู่ที่อำเภอ{pack['district_th']}, {pack['district_en']}, {pack['province_en']}, "
        f"near Placeholder Soi {pack['street_n']}."
    )


def _count_line(lang: str, count, missing: bool) -> str:
    if missing:
        return {
            "en": "I have not counted the household yet.",
            "th": "ยังไม่ได้นับจำนวนคนค่ะ",
            "mixed": "ยังไม่ได้นับ, I have not counted yet.",
        }[lang]
    return {"en": count[1], "th": count[2], "mixed": count[3]}[lang]


def _fill(template: str, pack: dict) -> str:
    return template.format(**pack)


def _positive_labels(primary: str, colour: str, extras: list[str]) -> list[str]:
    ordered = []
    for label in (COLOUR_TO_LABEL[colour], primary, *extras):
        if label not in ordered:
            ordered.append(label)
    return ordered


def _scenario(primary: str, variant: int) -> dict:
    colour = COLOUR[primary]
    if variant == 4:
        twist = TWISTS[primary]
        row = {
            "colour": twist.get("colour", colour),
            "needs": list(twist["needs"]),
            "medical": twist["medical"],
            "vulnerable": list(twist["vulnerable"]),
            "danger": list(twist["danger"]),
            "flags": list(twist["flags"]),
            "extras": list(twist["extras"]),
            "hard_negatives": list(twist["hard_negatives"]),
            "gap": twist.get("gap"),
            "tag": twist["tag"],
            "duplicate_of_variant": twist.get("duplicate_of_variant"),
            "count_override": twist.get("count"),
        }
    else:
        base = BASE[primary][variant]
        row = {
            "colour": colour,
            "needs": list(base["needs"]),
            "medical": base["medical"],
            "vulnerable": list(base["vulnerable"]),
            "danger": list(base["danger"]),
            "flags": list(base["flags"]),
            "extras": list(base["extras"]),
            "hard_negatives": list(base["hard"]),
            "gap": base.get("gap"),
            "tag": None,
            "duplicate_of_variant": None,
            "count_override": None,
        }
    row["labels"] = _positive_labels(primary, row["colour"], row["extras"])
    overlap = set(row["labels"]) & set(row["hard_negatives"])
    if overlap:
        raise RuntimeError(f"{primary} v{variant} hard negative overlaps {overlap}")
    return row


def _turns(primary: str, variant: int, lang: str, pack: dict, scenario: dict, count) -> list[dict]:
    if variant == 4:
        fact, detail = TWISTS[primary]["lines"][lang]
        fact, detail = _fill(fact, pack), _fill(detail, pack)
    else:
        fact = _fill(FACTS[primary][lang][variant], pack)
        detail = DETAILS[primary][lang]
    missing_people = scenario["gap"] == "people"
    missing_location = scenario["gap"] == "location"
    caller = (
        fact,
        detail,
        _location_line(lang, pack, missing_location),
        _count_line(lang, count, missing_people),
    )
    ops = OPS[lang]
    texts = []
    for index, text in enumerate(caller):
        texts.append(("caller", text))
        if index < 3:
            texts.append(("operator", ops[index]))
    turns = []
    for index, (speaker, text) in enumerate(texts):
        turns.append({"t_ms": index * 4200, "speaker": speaker, "text": text})
    return turns


def _fields(scenario: dict, pack: dict, count) -> dict:
    if scenario["gap"] == "location":
        location, confidence = None, None
    else:
        location = f"{pack['district_en']}, {pack['province_en']}"
        confidence = 0.92
    people = None if scenario["gap"] == "people" else count[0]
    return {
        "location": location,
        "location_confidence": confidence,
        "people_count": people,
        "vulnerable": list(scenario["vulnerable"]),
        "medical": scenario["medical"],
        "danger": list(scenario["danger"]),
        "needs": list(scenario["needs"]),
    }


def stratified_split(group_ids_by_primary: dict[str, list[str]], seed: int = SEED) -> tuple[list[str], list[str]]:
    """About 70/30 by group. Each primary label keeps at least one held-out group."""

    rng = random.Random(seed)
    labels = sorted(group_ids_by_primary)
    order = labels[:]
    rng.shuffle(order)
    hold_two = set(order[:8])
    train: list[str] = []
    held: list[str] = []
    for label in labels:
        ids = sorted(group_ids_by_primary[label])
        local = random.Random(f"{seed}:{label}")
        local.shuffle(ids)
        n_held = 2 if label in hold_two else 1
        held.extend(ids[:n_held])
        train.extend(ids[n_held:])
    return sorted(train), sorted(held)


def build_catalog() -> dict:
    """Return calls, the group split, and the demo ids. Does not touch disk."""

    primaries = list(PRIMARIES)
    if len(primaries) != 16:
        raise RuntimeError("expected 16 primaries")
    calls: list[dict] = []
    groups: dict[str, list[str]] = {primary: [] for primary in primaries}
    ordinal = 0
    base_time = datetime(2026, 10, 24, 8, 0, tzinfo=timezone.utc)

    for primary_index, primary in enumerate(primaries):
        for variant in range(5):
            group_id = f"syn-{primary.replace('_', '-')}-{variant + 1:02d}"
            groups[primary].append(group_id)
            scenario = _scenario(primary, variant)
            like = scenario["duplicate_of_variant"]
            pack = _pack(primary_index, variant, like_variant=like)
            count = scenario["count_override"] or _count(primary, variant, primary_index)
            source_group = None
            if scenario["duplicate_of_variant"] is not None:
                source_group = (
                    f"syn-{primary.replace('_', '-')}-"
                    f"{scenario['duplicate_of_variant'] + 1:02d}"
                )
            for lang in LANGS:
                case_id = f"{group_id}-{lang}"
                turns = _turns(primary, variant, lang, pack, scenario, count)
                fields = _fields(scenario, pack, count)
                memory: list[dict] = []
                if source_group:
                    source_id = f"{source_group}-en"
                    memory.append(
                        {
                            "memory_id": f"mem-{case_id}",
                            "kind": "similar_case",
                            "summary": (
                                f"Open case {source_id} from the same synthetic household. "
                                "Not yet delivered."
                            ),
                            "relevance": 0.95,
                            "source_case_id": source_id,
                        }
                    )
                case = CaseState(
                    case_id=case_id,
                    caller_id_hash=f"synthetic:{source_group or group_id}",
                    transcript=[TranscriptTurn.model_validate(turn) for turn in turns],
                    fields=ExtractedFields(
                        location=fields["location"],
                        location_confidence=fields["location_confidence"],
                        people_count=fields["people_count"],
                        vulnerable=list(fields["vulnerable"]),
                        medical=fields["medical"],
                        danger=list(fields["danger"]),
                        needs=[Need(need) for need in fields["needs"]],
                    ),
                    memory_context=[],
                    policy_flags=list(scenario["flags"]),
                    resources={},
                    received_at=base_time + timedelta(minutes=ordinal),
                )
                memory_models = [MemoryItem.model_validate(item) for item in memory]
                expected = derive_expected(
                    case,
                    memory_models,
                    colour=scenario["colour"],
                    labels=scenario["labels"],
                )
                assert_rescue(expected, fields["needs"])
                if "rescue" in fields["needs"] and expected["system"] != "system_2":
                    raise RuntimeError(case_id)
                tags = ["synthetic", expected["system"], lang, primary]
                if scenario["tag"]:
                    tags.append(scenario["tag"])
                if len(scenario["labels"]) > 1:
                    tags.append("multi_label")
                if scenario["hard_negatives"]:
                    tags.append("hard_negative")
                if scenario["gap"] == "people":
                    tags.append("missing_people")
                if scenario["gap"] == "location":
                    tags.append("missing_location")
                if source_group:
                    tags.append("duplicate")
                if case_id in DEMO_IDS:
                    tags.append("demo")
                payload = {
                    "id": case_id,
                    "group_id": group_id,
                    "lang": lang,
                    "primary_label": primary,
                    "colour": scenario["colour"],
                    "labels": scenario["labels"],
                    "hard_negatives": scenario["hard_negatives"],
                    "title": f"{primary} {lang} {variant + 1}",
                    "tags": tags,
                    "transcript_stream": turns,
                    "case_state": {
                        "case_id": case_id,
                        "caller_id_hash": case.caller_id_hash,
                        "transcript": turns,
                        "fields": fields,
                        "memory_context": [],
                        "policy_flags": list(scenario["flags"]),
                        "resources": {},
                        "received_at": case.received_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    },
                    "memory_context": memory,
                    "expected": {
                        "system": expected["system"],
                        "priority": expected["priority"],
                        "route": expected["route"],
                        "needs": expected["needs"],
                        "requires_human": expected["requires_human"],
                        "missing_evidence": expected["missing_evidence"],
                        "acceptable_next_questions": expected["acceptable_next_questions"],
                        "labels": scenario["labels"],
                        "action": expected["action"],
                    },
                    "notes": _notes(primary, scenario, expected),
                }
                calls.append(payload)
                ordinal += 1

    train, held = stratified_split(groups, SEED)
    if len(train) + len(held) != 80:
        raise RuntimeError("split does not cover 80 groups")
    if set(train) & set(held):
        raise RuntimeError("group landed on both sides")
    _check(calls, train, held)
    return {
        "seed": SEED,
        "calls": calls,
        "train_groups": train,
        "held_out_groups": held,
        "demo_ids": list(DEMO_IDS),
    }


def _notes(primary: str, scenario: dict, expected: dict) -> str:
    bits = [f"Synthetic {primary}. Colour {scenario['colour']}."]
    if scenario["tag"] == "calm_critical":
        bits.append("Calm delivery with a critical fact.")
    if scenario["tag"] == "sarcasm":
        bits.append("Sarcasm is not the label.")
    if scenario["tag"] == "duplicate":
        bits.append("Repeat caller. Memory similar_case drives duplicate_merge when System 1 runs.")
    if scenario["gap"] == "people":
        bits.append("Household size was not said.")
    if scenario["gap"] == "location":
        bits.append("District was not said.")
    if "rescue" in scenario["needs"]:
        bits.append("Rescue is system_2 rescue_coordination.")
    bits.append(f"Route {expected['route']} on {expected['system']}.")
    return " ".join(bits)


def _check(calls: list[dict], train: list[str], held: list[str]) -> None:
    if len(calls) != 240:
        raise RuntimeError(f"expected 240 calls, found {len(calls)}")
    counts = {label: 0 for label in (list(COLOUR_TO_LABEL.values()) + list(NOUL_LABELS))}
    thai_caller = []
    en_caller = []
    for call in calls:
        for label in call["labels"]:
            counts[label] = counts.get(label, 0) + 1
        if set(call["hard_negatives"]) & set(call["labels"]):
            raise RuntimeError(f"{call['id']} hard negative is also positive")
        text = " ".join(
            turn["text"] for turn in call["transcript_stream"] if turn["speaker"] == "caller"
        )
        if call["lang"] == "th":
            thai_caller.append(text)
        if call["lang"] == "en":
            en_caller.append(text)
        blob = json.dumps(call, ensure_ascii=False)
        if "TODO_HUMAN" in blob:
            raise RuntimeError(f"{call['id']} contains TODO_HUMAN")
        # ISO timestamps contain 2026-10-24, which the phone pattern also matches.
        spoken = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", "", blob)
        if re.search(r"(?:\+66|0)[\s-]?\d[\d\s-]{7,}", spoken):
            raise RuntimeError(f"{call['id']} looks like a phone number")
        if re.search(r"\b\d{13}\b", spoken):
            raise RuntimeError(f"{call['id']} looks like a 13-digit id")
        if not call["case_state"]["caller_id_hash"].startswith("synthetic:"):
            raise RuntimeError(f"{call['id']} caller hash is not synthetic")
    missing = [label for label, count in counts.items() if count < 12]
    if missing:
        raise RuntimeError(f"labels under 12 positives: {missing} {counts}")
    thai_blob = "\n".join(thai_caller)
    for word in KINSHIP_TH:
        if word not in thai_blob:
            raise RuntimeError(f"Thai kinship word missing: {word}")
    for word in NUMBER_TH:
        if word not in thai_blob:
            raise RuntimeError(f"Thai number word missing: {word}")
    en_blob = "\n".join(en_caller)
    if "three of us" not in en_blob or "my two kids" not in en_blob:
        raise RuntimeError("English number phrases missing")
    grandmother = next(call for call in calls if call["id"] == "syn-niems-red-critical-05-th")
    body = " ".join(turn["text"] for turn in grandmother["transcript_stream"])
    if "เด็ก" in body:
        raise RuntimeError("grandmother call used เด็ก; grandchildren must be หลาน only")
    for word in ("ยาย", "หลาน", "หายใจไม่ออก"):
        if word not in body:
            raise RuntimeError(f"grandmother call missing {word}")
    labels = set(grandmother["labels"])
    for label in (
        "niems_red_critical",
        "safeguarding_child",
        "safeguarding_older_person",
        "niems_not_conscious_or_breathing",
    ):
        if label not in labels:
            raise RuntimeError(f"grandmother call missing label {label}")
    if grandmother["expected"]["system"] != "system_2":
        raise RuntimeError("grandmother call is not system_2")
    if grandmother["expected"]["priority"] != "P1":
        raise RuntimeError("grandmother call is not P1")
    if grandmother["colour"] != "red":
        raise RuntimeError("grandmother call is not red")
    ratio = len(train) / (len(train) + len(held))
    if not 0.65 <= ratio <= 0.75:
        raise RuntimeError(f"split ratio {ratio}")


def write_catalog(root: Path | None = None) -> dict:
    catalog = build_catalog()
    folder = root or SYNTHETIC
    calls_dir = folder / "calls"
    calls_dir.mkdir(parents=True, exist_ok=True)
    for stale in calls_dir.glob("*.json"):
        stale.unlink()
    index_calls = []
    held = set(catalog["held_out_groups"])
    for call in catalog["calls"]:
        path = calls_dir / f"{call['id']}.json"
        path.write_text(
            json.dumps(call, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        index_calls.append(
            {
                "id": call["id"],
                "path": f"calls/{call['id']}.json",
                "group_id": call["group_id"],
                "lang": call["lang"],
                "primary_label": call["primary_label"],
                "labels": call["labels"],
                "split": "held_out" if call["group_id"] in held else "train",
                "demo": call["id"] in catalog["demo_ids"],
            }
        )
    index = {
        "seed": catalog["seed"],
        "call_count": len(catalog["calls"]),
        "group_count": len(catalog["train_groups"]) + len(catalog["held_out_groups"]),
        "calls": index_calls,
    }
    (folder / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    split = {
        "seed": catalog["seed"],
        "train_fraction": TRAIN_FRACTION,
        "train_groups": catalog["train_groups"],
        "held_out_groups": catalog["held_out_groups"],
        "train_calls": sum(1 for row in index_calls if row["split"] == "train"),
        "held_out_calls": sum(1 for row in index_calls if row["split"] == "held_out"),
    }
    (folder / "split.json").write_text(
        json.dumps(split, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    demo = {"ids": catalog["demo_ids"]}
    (folder / "demo.json").write_text(
        json.dumps(demo, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return catalog


def label_counts(calls: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for call in calls:
        for label in call["labels"]:
            counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))
