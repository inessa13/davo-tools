import datetime

import pytest

from davo.services.photo import replace_classes


@pytest.mark.parametrize("field", ["creationdate", "encoded_date"])
def test_datetime_for_video_parses_mediainfo_utc_suffix(field):
    context = {"mediainfo": {field: "2017-07-18 09:15:10 UTC"}}

    result = replace_classes._datetime_for_video_("video.mp4", context)

    assert result == datetime.datetime(2017, 7, 18, 9, 15, 10)


def test_datetime_for_video_parses_mediainfo_utc_prefix():
    context = {"mediainfo": {"encoded_date": "UTC 2017-07-18 09:15:10"}}

    result = replace_classes._datetime_for_video_("video.mp4", context)

    assert result == datetime.datetime(2017, 7, 18, 9, 15, 10)


@pytest.mark.parametrize(
    "creationdate",
    ["2017-07-18T09:15:10Z", "2017-07-18 09:15:10+03:00"],
)
def test_datetime_for_video_discards_iso_timezone(creationdate):
    context = {"mediainfo": {"creationdate": creationdate}}

    result = replace_classes._datetime_for_video_("video.mp4", context)

    assert result == datetime.datetime(2017, 7, 18, 9, 15, 10)
