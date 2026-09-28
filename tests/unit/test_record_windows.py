"""Unit tests for the question/answer window rule (src/interview/record.py, research.md §5)."""
from src.interview.record import TranscriptFragment, close_answer
from src.interview.state import InterviewQuestion


def q(asked_at_ms: int = 1000) -> InterviewQuestion:
    return InterviewQuestion(index=1, text="What is a mutex?", asked_at_ms=asked_at_ms)


def user(text, start):
    return TranscriptFragment("user", text, start, start + 200)


def interviewer(text, start):
    return TranscriptFragment("interviewer", text, start, start + 200)


def test_only_user_fragments_in_the_window():
    fragments = [user("old answer", 500), user("A lock", 1500), user(" for threads.", 1800), user("next", 5000)]
    answer, _ = close_answer(q(), fragments, until_ms=4000)
    assert answer == "A lock for threads."


def test_sorted_by_start_even_out_of_order():
    fragments = [user(" for threads.", 1800), user("A lock", 1500)]
    assert close_answer(q(), fragments, 4000)[0] == "A lock for threads."


def test_interviewer_speech_is_spoken_text_not_answer():
    fragments = [interviewer("What is", 1000), interviewer(" a mutex?", 1200),
                 user("A lock.", 2000), interviewer("Thanks.", 3000)]
    answer, spoken = close_answer(q(), fragments, 4000)
    assert answer == "A lock."
    assert spoken == "What is a mutex?"


def test_empty_window():
    assert close_answer(q(), [], 4000) == ("", "")


def test_whitespace_is_collapsed():
    fragments = [user("  A   lock ", 1500), user("\nfor threads. ", 1600)]
    assert close_answer(q(), fragments, 4000)[0] == "A lock for threads."


def test_open_ended_window():
    fragments = [user("Still", 1500), user(" talking", 90000)]
    assert close_answer(q(), fragments, float("inf"))[0] == "Still talking"


def test_spoken_text_includes_words_just_before_the_mark():
    fragments = [interviewer("Thanks.", -2000 + 1000), interviewer("How would", 400),
                 interviewer(" you scale it?", 1100), user("With shards.", 2000)]
    answer, spoken = close_answer(q(1000), fragments, 4000)
    assert spoken == "How would you scale it?"
    assert answer == "With shards."
