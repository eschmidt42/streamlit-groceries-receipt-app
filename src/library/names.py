NAME_MAP = {
    "BIOD BANANEN": "BIO BANANEN",
    "BIOD Paprika Mix": "BIO Paprika Mix",
}


def assign_normalized_name(raw_name: str) -> str:
    return NAME_MAP.get(raw_name, raw_name)
