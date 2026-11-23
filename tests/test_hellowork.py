"""Regression tests for HelloWork location parsing (issue #472).

HelloWork only lists jobs in France, so every location it reports should
carry France as its country, not just the ones with a department number.
"""

import pytest

from jobspy.hellowork import HelloWork
from jobspy.model import Country


@pytest.mark.parametrize(
    ("text", "city", "state"),
    [
        ("Lyon 3e - 69", "Lyon 3e", "69"),
        ("Paris - 75", "Paris", "75"),
        ("Ajaccio - 2A", "Ajaccio", "2A"),
        ("Pointe-à-Pitre - 971", "Pointe-à-Pitre", "971"),
    ],
)
def test_location_with_department(text, city, state):
    location = HelloWork._parse_location(text)
    assert location.city == city
    assert location.state == state
    assert location.country == Country.FRANCE


@pytest.mark.parametrize("text", ["Île-de-France", "Bretagne", "Nouvelle-Aquitaine"])
def test_location_without_department_keeps_france(text):
    location = HelloWork._parse_location(text)
    assert location.city == text
    assert location.state is None
    assert location.country == Country.FRANCE
