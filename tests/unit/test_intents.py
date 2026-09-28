"""Unit tests for src/interview/intents.py."""
import pytest

from src.interview.intents import ends_with_done, is_stop_request



class TestIsStopRequest:
    @pytest.mark.parametrize("text", [
        "let's stop here",
        "Let's end here.",
        "stop the interview",
        "Can we end the interview now?",
        "let's end the interview",
        "that's enough for today",
        "I'm done with the interview",
    ])
    def test_explicit_stop_phrases(self, text):
        assert is_stop_request(text) is True

    @pytest.mark.parametrize("text", [
        "if the queue is full the producer will stop",
        "the process should stop and restart",
        "I would end the loop early",
        "",
    ])
    def test_stop_words_inside_answers_do_not_end_the_interview(self, text):
        assert is_stop_request(text) is False


class TestStopRequestByLanguage:
    @pytest.mark.parametrize("text", [
        "ok, vamos encerrar a entrevista",
        "Vamos encerrar a entrevísta",       # accent noise from transcription
        "pode encerrar a entrevista, por favor",
        "chega por hoje",
    ])
    def test_portuguese_phrases(self, text):
        assert is_stop_request(text, "pt-BR") is True

    def test_portuguese_mid_answer_parar_does_not_end(self):
        assert is_stop_request("o produtor vai parar quando a fila encher", "pt-BR") is False

    def test_phrases_only_match_their_language(self):
        assert is_stop_request("let's end the interview", "pt-BR") is False
        assert is_stop_request("vamos encerrar a entrevista", "en") is False

    def test_english_is_the_default(self):
        assert is_stop_request("let's end the interview") is True


class TestEndsWithDone:
    @pytest.mark.parametrize("text,language", [
        ("I would shard by tenant. That's it.", "en"),
        ("and we shipped it on time, I'm done", "en"),
        ("E aí eu analisei o Data Quality... E... é isso. Pronto", "pt-BR"),
        ("Eu alinhei com minha liderança. Pronto.", "pt-BR"),
        ("foi basicamente isso, terminei", "pt-BR"),
        ("E é isso aí", "pt-BR"),
    ])
    def test_done_phrase_at_the_end(self, text, language):
        assert ends_with_done(text, language) is True

    @pytest.mark.parametrize("text,language", [
        ("that's it for the first part, then the second service", "en"),
        ("the job is done by the scheduler and then", "en"),
        ("pronto, então o segundo ponto é o custo", "pt-BR"),
        ("o sistema ficou pronto em duas semanas e depois", "pt-BR"),
        ("", "pt-BR"),
    ])
    def test_done_phrase_mid_answer_does_not_count(self, text, language):
        assert ends_with_done(text, language) is False

    def test_phrases_only_match_their_language(self):
        assert ends_with_done("é isso, pronto", "en") is False
        assert ends_with_done("okay, that's it", "pt-BR") is False
