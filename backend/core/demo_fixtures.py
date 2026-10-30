"""Small synthetic fixtures, never used as detections for arbitrary recordings.

Masks are canonical SAM one_bit payloads for the silhouettes drawn by demo.py.
"""

GLASSES_MASK = "<|mask;x=0;y=0;data=80,140,!!!!#`1r4@5W8/Phq`rkZUNSW24q9C5R^@k:R)+0+-)5jR^I7j&wGeddfQyA2TAaQ1kfR^A/xRCJFWKV$BF/w0.z3xu3*?u{9rjXUj@ud7gm$8F(rIU&nogTZpp{^!Cf)!eBiy+[cFGc(Q(ur7D(h==rUdg(r'1axxXgiD4hY?iSKivDEDsFS!!!|>"
KEYS_MASK = "<|mask;x=0;y=0;data=40,50,!!!!!cBSC-``!AMru%s1L!UR]@c5P2mT)@JRWJ9b{q4DIDlI3l]+X^UWKL&yUw.&E0ou^Z]vIXtN]8hRJ|>"
MUG_MASK = "<|mask;x=0;y=0;data=80,70,!!!!!_8zO(csYds%cHf4aTSebM.#2=R(oxy_6g&zKJr48*RshS^8{i5(i32_TW/tTO^1%kX@D/ay|>"

DEMO_SEGMENTATIONS = {
    ("demo_keys_01", "keys"): {"boxes": [[120, 180, 170, 220]], "scores": [0.94], "masks": [KEYS_MASK]},
    ("demo_keys_02", "keys"): {"boxes": [[122, 181, 172, 221]], "scores": [0.93], "masks": [KEYS_MASK]},
    ("demo_glasses_01", "reading glasses"): {"boxes": [[120, 80, 260, 160]], "scores": [0.93], "masks": [GLASSES_MASK]},
    ("demo_glasses_02", "reading glasses"): {"boxes": [[400, 90, 540, 170]], "scores": [0.94], "masks": [GLASSES_MASK]},
    ("demo_mug_01", "mug"): {"boxes": [[180, 120, 250, 200]], "scores": [0.51], "masks": [MUG_MASK]},
}
