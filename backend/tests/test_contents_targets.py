"""A contents entry's target is found when its unit was merged into a longer published unit."""

from types import SimpleNamespace

from book_core.assembly.assemble import link_targets
from book_core.assembly.build import sid


def test_target_merged_into_a_heading_is_the_published_heading():
    title, number = "a" * 16, "b" * 16
    ctx = SimpleNamespace(published_of_source={number: sid(number)}, heading_rest={number: [title]})
    published = {sid(number)}
    assert link_targets({"unit_ids": [title]}, ctx, published) == [sid(number)]


def test_target_unchanged_when_published_as_itself_and_missing_ones_are_dropped():
    one, gone = "c" * 16, "d" * 16
    ctx = SimpleNamespace(published_of_source={}, heading_rest={})
    assert link_targets({"unit_ids": [one, gone]}, ctx, {sid(one)}) == [sid(one)]
    assert link_targets({}, ctx, {sid(one)}) == []
