"""R2: every rejection names the file and the row or line."""

from __future__ import annotations

import pytest

from netscope.errors import InputError, NetscopeError


def test_csv_error_names_file_row_and_column() -> None:
    error = InputError(
        "sites.csv",
        "access_capacity must be a positive number, got '-5'",
        row=4,
        field="access_capacity",
    )
    assert str(error) == (
        "sites.csv, row 4, column 'access_capacity': "
        "access_capacity must be a positive number, got '-5'"
    )


def test_xml_error_names_file_and_line() -> None:
    error = InputError("nobel-eu.xml", "link 'L7' has an unknown target 'Atlantis'", line=512)
    assert str(error) == "nobel-eu.xml, line 512: link 'L7' has an unknown target 'Atlantis'"


def test_file_alone_is_enough_when_the_fault_is_the_whole_file() -> None:
    error = InputError("sites.csv", "file is empty")
    assert str(error) == "sites.csv: file is empty"


def test_row_and_line_are_mutually_exclusive() -> None:
    """Guards against a caller implying a CSV row has an XML line too."""
    with pytest.raises(ValueError, match="either row or line"):
        InputError("sites.csv", "confused", row=1, line=1)


def test_fields_stay_available_for_structured_handling() -> None:
    """The API layer formats its own response, so it needs the parts."""
    error = InputError("sites.csv", "bad", row=4, field="site_type")
    assert (error.file, error.row, error.line, error.field) == ("sites.csv", 4, None, "site_type")
    assert error.message == "bad"


def test_input_error_is_catchable_as_a_netscope_error() -> None:
    with pytest.raises(NetscopeError):
        raise InputError("sites.csv", "bad", row=2)
