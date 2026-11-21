import json

import pytest

from src.loaders import LoadError, load_chat, load_reference, load_transcript
from src.models import ChatEvent, ReferenceClip, Segment


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


def test_reference_json_with_seconds(tmp_path):
    path = write(tmp_path, "r.json", [{"start_s": 610, "end_s": 640.5}])
    assert load_reference(path) == [ReferenceClip(start_s=610, end_s=640.5)]


def test_reference_json_with_hhmmss_times(tmp_path):
    path = write(tmp_path, "r.json", [{"start_s": "00:33:30", "end_s": "00:34:10"}])
    assert load_reference(path) == [ReferenceClip(start_s=2010, end_s=2050)]


def test_reference_mixes_both_time_formats(tmp_path):
    path = write(
        tmp_path,
        "r.json",
        [
            {"start_s": 610, "end_s": "00:10:40"},
            {"start_s": "00:50:00", "end_s": 3030},
        ],
    )
    assert load_reference(path) == [
        ReferenceClip(start_s=610, end_s=640),
        ReferenceClip(start_s=3000, end_s=3030),
    ]


def test_reference_csv(tmp_path):
    path = write(tmp_path, "r.csv", "start_s,end_s\n610,640\n00:33:30,00:34:10\n")
    assert load_reference(path) == [
        ReferenceClip(start_s=610, end_s=640),
        ReferenceClip(start_s=2010, end_s=2050),
    ]


def test_reference_extra_keys_are_ignored(tmp_path):
    path = write(
        tmp_path,
        "r.json",
        [{"title": "Coche volando", "start_s": 610, "end_s": 640, "views": 1234}],
    )
    assert load_reference(path) == [ReferenceClip(start_s=610, end_s=640)]


def test_reference_empty_list_raises_a_load_error_naming_the_file(tmp_path):
    with pytest.raises(LoadError, match="^r.json: reference has no clips$"):
        load_reference(write(tmp_path, "r.json", []))


def test_reference_empty_csv_raises_a_load_error(tmp_path):
    path = tmp_path / "r.csv"
    path.write_text("start_s,end_s\n", encoding="utf-8")

    with pytest.raises(LoadError, match="reference has no clips"):
        load_reference(path)


def test_reference_missing_key_says_what_was_expected(tmp_path):
    path = write(tmp_path, "r.json", [{"start_s": 610, "title": "x"}])
    with pytest.raises(LoadError) as error:
        load_reference(path)
    message = str(error.value)
    assert "r.json" in message
    assert "record 1" in message
    assert "missing keys end_s" in message
    assert "expected start_s, end_s" in message
    assert "title" in message


def test_reference_wrong_keys_report_both_missing(tmp_path):
    path = write(tmp_path, "r.json", [{"inicio": 1, "fin": 2}])
    with pytest.raises(LoadError, match="missing keys start_s, end_s"):
        load_reference(path)


@pytest.mark.parametrize("end", [640, 600])
def test_reference_end_not_after_start_is_rejected(tmp_path, end):
    path = write(tmp_path, "r.json", [{"start_s": 640, "end_s": end}])
    with pytest.raises(LoadError, match="end_s must be greater than start_s"):
        load_reference(path)


def test_reference_invalid_time_names_file_record_and_key(tmp_path):
    path = write(tmp_path, "r.json", [{"start_s": 1, "end_s": "99:99:99"}])
    with pytest.raises(LoadError, match=r"r\.json, record 1, key end_s"):
        load_reference(path)


def test_reference_missing_file(tmp_path):
    with pytest.raises(LoadError, match="file does not exist"):
        load_reference(tmp_path / "nope.json")


def test_a_directory_as_input_is_a_load_error(tmp_path):
    directory = tmp_path / "data.json"
    directory.mkdir()

    with pytest.raises(LoadError, match="not a file"):
        load_chat(directory)


@pytest.mark.parametrize("name", ["bad.json", "bad.csv"])
def test_invalid_utf8_bytes_are_a_load_error_naming_the_file(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b"t_s,message\n1,\xff\xfe not utf-8\n")

    with pytest.raises(LoadError, match=rf"{name}: file is not valid UTF-8"):
        load_chat(path)


def test_a_csv_with_an_unclosed_quote_is_a_load_error(tmp_path):
    path = write(tmp_path, "c.csv", 't_s,message\n1,"' + "a" * 140_000 + "\n")

    with pytest.raises(LoadError, match=r"c\.csv: invalid CSV"):
        load_chat(path)


def test_a_huge_integer_time_in_json_is_a_load_error_naming_the_file(tmp_path):
    path = tmp_path / "t.json"
    path.write_text(
        '[{"start_s": 1' + "0" * 399 + ', "end_s": 5, "text": "x"}]', encoding="utf-8"
    )

    with pytest.raises(LoadError, match=r"t\.json"):
        load_transcript(path)
