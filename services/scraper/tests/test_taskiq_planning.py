from app.tasks.planning import CadernoRange, build_caderno_ranges


def test_build_caderno_ranges_for_15298_questions():
    ranges = build_caderno_ranges(expected_total=15298, page_size=200)

    assert len(ranges) == 77
    assert ranges[0] == CadernoRange(
        inicio=0,
        page_size=200,
        position_start=1,
        position_end=200,
        is_last=False,
    )
    assert ranges[5] == CadernoRange(
        inicio=1000,
        page_size=200,
        position_start=1001,
        position_end=1200,
        is_last=False,
    )
    assert ranges[6] == CadernoRange(
        inicio=1200,
        page_size=200,
        position_start=1201,
        position_end=1400,
        is_last=False,
    )
    assert ranges[-1] == CadernoRange(
        inicio=15200,
        page_size=200,
        position_start=15201,
        position_end=15298,
        is_last=True,
    )


def test_build_caderno_ranges_for_29774_questions():
    ranges = build_caderno_ranges(expected_total=29774, page_size=200)

    assert len(ranges) == 149
    assert ranges[-1].inicio == 29600
    assert ranges[-1].position_start == 29601
    assert ranges[-1].position_end == 29774
    assert ranges[-1].is_last is True


def test_build_caderno_ranges_rejects_invalid_values():
    import pytest

    with pytest.raises(ValueError, match="expected_total"):
        build_caderno_ranges(expected_total=0, page_size=200)

    with pytest.raises(ValueError, match="page_size"):
        build_caderno_ranges(expected_total=100, page_size=0)
