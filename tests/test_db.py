from snekomatic.db import PersistentStringSet


def test_persistent_string_set(heroku_style_pg):
    s1 = PersistentStringSet("s1")
    s2 = PersistentStringSet("s2")

    assert "foo" not in s1
    assert "foo" not in s2

    assert "bar" not in s1
    assert "bar" not in s2

    s1.add("foo")
    s2.add("bar")

    assert "foo" in s1
    assert "foo" not in s2

    assert "bar" in s2
    assert "bar" not in s1
