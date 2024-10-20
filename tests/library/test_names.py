from library.names import NAME_MAP, assign_normalized_name


def test_assign_normalized_name_existing():
    contained = "BIOD BANANEN"
    pretty = "BIO BANANEN"
    assert contained in NAME_MAP
    assert assign_normalized_name(contained) == pretty

    not_contained = "This is definitively not in the map"
    assert not_contained not in NAME_MAP
    assert assign_normalized_name(not_contained) == not_contained
