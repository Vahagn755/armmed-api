"""Քեյսերի պատասխանների բանալիները՝ սերվերի կողմում (client-ին չեն վստահում)։"""
import json
from pathlib import Path


def load_answer_key(cases_dir: str) -> dict[str, int]:
    """cases/*.json → {case_id: correctOptionIndex}։ Ֆայլերը նույն JSON ձևաչափն ունեն, ինչ քեյսերը։"""
    key: dict[str, int] = {}
    for path in sorted(Path(cases_dir).glob("*.json")):
        for c in json.loads(path.read_text(encoding="utf-8")):
            cid, idx, n = c["id"], c["correctOptionIndex"], len(c["options"])
            if not 0 <= idx < n:
                raise ValueError(f"{path.name}:{cid} correctOptionIndex out of range")
            if cid in key:
                raise ValueError(f"duplicate case id {cid}")
            key[cid] = idx
    return key
