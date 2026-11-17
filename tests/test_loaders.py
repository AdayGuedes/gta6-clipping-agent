import json

import pytest

from src.loaders import LoadError, load_chat, load_transcript
from src.models import ChatEvent, Segment


def write(tmp_path, name, content):
    path = tmp_path / name
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_text(json.dumps(content), encoding="utf-8")
    return path


def test_transcript_json_with_seconds(tmp_path):
    path = write(tmp_path, "t.json", [{"start_s": 0, "end_s": 4.5, "text": "hello"}])
    assert load_transcript(path) == [Segment(start_s=0, end_s=4.5, text="hello")]


def test_transcript_json_with_hhmmss_times(tmp_path):
    path = write(
        tmp_path,
        "t.json",
        [{"start_s": "00:01:05", "end_s": "00:01:10", "text": "hey"}],
    )
    assert load_transcript(path) == [Segment(start_s=65, end_s=70, text="hey")]


def test_transcript_json_mixes_both_time_formats_in_one_file(tmp_path):
    path = write(
        tmp_path,
        "t.json",
        [
            {"start_s": 5, "end_s": "00:00:09", "text": "one"},
            {"start_s": "00:00:09", "end_s": 12.5, "text": "two"},
        ],
    )
    segments = load_transcript(path)
    assert [(s.start_s, s.end_s) for s in segments] == [(5.0, 9.0), (9.0, 12.5)]


def test_transcript_csv(tmp_path):
    path = write(
        tmp_path,
        "t.csv",
        'start_s,end_s,text\n0,4.5,hello\n00:00:05,00:00:09,"qué, tal"\n',
    )
    assert load_transcript(path) == [
        Segment(start_s=0, end_s=4.5, text="hello"),
        Segment(start_s=5, end_s=9, text="qué, tal"),
    ]


def test_chat_json(tmp_path):
    path = write(tmp_path, "c.json", [{"t_s": 3725, "message": "lol"}])
    assert load_chat(path) == [ChatEvent(t_s=3725, message="lol")]


def test_chat_json_with_hhmmss_time(tmp_path):
    path = write(tmp_path, "c.json", [{"t_s": "01:02:05", "message": "lol"}])
    assert load_chat(path)[0].t_s == 3725.0


def test_chat_csv(tmp_path):
    path = write(tmp_path, "c.csv", "t_s,message\n3725,lol\n01:02:06,LUL\n")
    assert load_chat(path) == [
        ChatEvent(t_s=3725, message="lol"),
        ChatEvent(t_s=3726, message="LUL"),
    ]


def test_uppercase_extension(tmp_path):
    path = write(tmp_path, "C.JSON", [{"t_s": 1, "message": "x"}])
    assert len(load_chat(path)) == 1


def test_accepts_path_as_string(tmp_path):
    path = write(tmp_path, "c.json", [{"t_s": 1, "message": "x"}])
    assert len(load_chat(str(path))) == 1


def test_empty_list_returns_empty_list(tmp_path):
    assert load_chat(write(tmp_path, "c.json", [])) == []
    assert load_chat(write(tmp_path, "c.csv", "t_s,message\n")) == []


def test_csv_with_excel_bom(tmp_path):
    path = tmp_path / "c.csv"
    path.write_bytes("﻿t_s,message\n1,hello\n".encode())
    assert load_chat(path) == [ChatEvent(t_s=1, message="hello")]


def test_extra_keys_are_ignored_when_expected_keys_are_present(tmp_path):
    path = write(tmp_path, "c.json", [{"t_s": 1, "message": "x", "user": "ana"}])
    assert load_chat(path) == [ChatEvent(t_s=1, message="x")]


def test_wrong_keys_say_what_was_expected(tmp_path):
    path = write(tmp_path, "t.json", [{"inicio": 0, "fin": 4, "texto": "hello"}])
    with pytest.raises(LoadError) as error:
        load_transcript(path)
    message = str(error.value)
    assert "t.json" in message
    assert "record 1" in message
    for key in ("start_s", "end_s", "text"):
        assert key in message
    assert "inicio" in message


def test_wrong_keys_in_chat_csv(tmp_path):
    path = write(tmp_path, "c.csv", "time,msg\n1,hello\n")
    with pytest.raises(LoadError, match="t_s, message"):
        load_chat(path)


def test_single_missing_key(tmp_path):
    path = write(tmp_path, "c.json", [{"t_s": 1}])
    with pytest.raises(LoadError, match="missing keys message"):
        load_chat(path)


def test_error_reports_the_record_number(tmp_path):
    path = write(
        tmp_path,
        "c.json",
        [{"t_s": 1, "message": "a"}, {"t_s": 2, "message": "b"}, {"t_s": 3}],
    )
    with pytest.raises(LoadError, match="record 3"):
        load_chat(path)


@pytest.mark.parametrize("time", ["0:05:30", "abc", -5, True, None, "99:99:99"])
def test_invalid_time_names_file_record_and_key(tmp_path, time):
    path = write(tmp_path, "c.json", [{"t_s": time, "message": "x"}])
    with pytest.raises(LoadError, match=r"c\.json, record 1, key t_s"):
        load_chat(path)


def test_segment_ending_before_it_starts(tmp_path):
    path = write(tmp_path, "t.json", [{"start_s": 9, "end_s": 4, "text": "x"}])
    with pytest.raises(LoadError, match="record 1.*end_s"):
        load_transcript(path)


def test_segment_with_end_equal_to_start(tmp_path):
    path = write(tmp_path, "t.json", [{"start_s": 4, "end_s": 4, "text": "x"}])
    with pytest.raises(LoadError, match="record 1.*end_s must be greater than start_s"):
        load_transcript(path)


def test_text_that_is_not_a_string(tmp_path):
    path = write(tmp_path, "c.json", [{"t_s": 1, "message": 42}])
    with pytest.raises(LoadError, match="record 1.*message"):
        load_chat(path)


def test_json_that_is_not_a_list(tmp_path):
    path = write(tmp_path, "c.json", {"t_s": 1, "message": "x"})
    with pytest.raises(LoadError, match="list of objects"):
        load_chat(path)


def test_json_with_non_object_elements(tmp_path):
    path = write(tmp_path, "c.json", [{"t_s": 1, "message": "x"}, 5])
    with pytest.raises(LoadError, match="record 2.*object"):
        load_chat(path)


def test_malformed_json(tmp_path):
    path = write(tmp_path, "c.json", "[{")
    with pytest.raises(LoadError, match="invalid JSON"):
        load_chat(path)


def test_csv_without_header(tmp_path):
    path = write(tmp_path, "c.csv", "")
    with pytest.raises(LoadError, match="header"):
        load_chat(path)


def test_csv_with_more_columns_than_the_header(tmp_path):
    path = write(tmp_path, "c.csv", "t_s,message\n1,hello,extra\n")
    with pytest.raises(LoadError, match="record 1.*columns"):
        load_chat(path)


def test_csv_with_fewer_columns_than_the_header(tmp_path):
    path = write(tmp_path, "c.csv", "t_s,message\n1\n")
    with pytest.raises(LoadError, match="record 1"):
        load_chat(path)


def test_unsupported_extension(tmp_path):
    path = write(tmp_path, "c.txt", "t_s,message\n1,x\n")
    with pytest.raises(LoadError, match=r"\.json or \.csv"):
        load_chat(path)


def test_missing_file(tmp_path):
    with pytest.raises(LoadError, match="does not exist"):
        load_chat(tmp_path / "missing.json")


def test_load_error_is_a_value_error():
    assert issubclass(LoadError, ValueError)
