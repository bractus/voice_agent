"""Unit tests for the interview stage machine in src/interview/state.py."""
import re

import pytest

from src.interview.state import Interview, InterviewStage, InvalidStageError

ID_PATTERN = re.compile(r"^[0-9]{8}-[0-9]{6}-(hr|technical)-[a-z0-9]{6}$")


def started(interview_type="technical", language="en") -> Interview:
    iv = Interview()
    iv.start(interview_type, language)
    return iv


class TestStart:
    @pytest.mark.parametrize("interview_type", ["hr", "technical"])
    def test_start_moves_to_introducing(self, interview_type):
        iv = started(interview_type)
        assert iv.stage == InterviewStage.INTRODUCING
        assert iv.interview_type == interview_type

    def test_unknown_type_is_rejected(self):
        with pytest.raises(ValueError):
            Interview().start("sales")

    def test_unknown_language_is_rejected(self):
        with pytest.raises(ValueError):
            Interview().start("hr", "fr")

    def test_language_defaults_to_english(self):
        iv = Interview()
        iv.start("hr")
        assert iv.language == "en"

    def test_portuguese(self):
        assert started("hr", "pt-BR").language == "pt-BR"

    def test_cannot_start_twice(self):
        iv = started()
        with pytest.raises(InvalidStageError):
            iv.start("hr")

    def test_interview_id_pattern(self):
        iv = started("hr")
        assert ID_PATTERN.match(iv.interview_id)
        assert "-hr-" in iv.interview_id


class TestTransitions:
    def test_happy_path_keeps_type_and_language(self):
        iv = started("technical", "pt-BR")
        iv.begin_interviewing()
        assert iv.stage == InterviewStage.INTERVIEWING
        iv.request_end("user_request")
        assert iv.stage == InterviewStage.CONCLUDING
        assert iv.end_reason == "user_request"
        iv.finish()
        assert iv.stage == InterviewStage.CONCLUDED
        assert (iv.interview_type, iv.language) == ("technical", "pt-BR")

    def test_begin_interviewing_only_from_introducing(self):
        with pytest.raises(InvalidStageError):
            Interview().begin_interviewing()
        iv = started()
        iv.begin_interviewing()
        with pytest.raises(InvalidStageError):
            iv.begin_interviewing()

    def test_request_end_from_introducing(self):
        iv = started()
        iv.request_end("end_button")
        assert iv.stage == InterviewStage.CONCLUDING

    def test_request_end_not_from_setup_or_concluded(self):
        with pytest.raises(InvalidStageError):
            Interview().request_end("end_button")
        iv = started()
        iv.request_end("end_button")
        iv.finish()
        with pytest.raises(InvalidStageError):
            iv.request_end("end_button")

    def test_finish_only_from_concluding(self):
        iv = started()
        with pytest.raises(InvalidStageError):
            iv.finish()

    def test_uploads_only_in_setup(self):
        iv = Interview()
        assert iv.uploads_allowed
        iv.start("hr")
        assert not iv.uploads_allowed


class TestRoleAndSeniority:
    def test_role_is_normalised(self):
        iv = Interview()
        iv.start("hr", "en", role="  Backend \n Engineer\t", seniority="senior")
        assert iv.role == "Backend Engineer"
        assert iv.seniority == "senior"

    def test_empty_role_is_none(self):
        iv = Interview()
        iv.start("hr", role="   ")
        assert iv.role is None

    def test_role_longer_than_80_is_rejected(self):
        with pytest.raises(ValueError):
            Interview().start("hr", role="x" * 81)

    def test_80_characters_is_fine(self):
        iv = Interview()
        iv.start("hr", role="x" * 80)
        assert len(iv.role) == 80

    def test_unknown_seniority_is_rejected(self):
        with pytest.raises(ValueError):
            Interview().start("hr", seniority="lead")

    def test_default_seniority_is_mid(self):
        iv = Interview()
        iv.start("technical")
        assert iv.seniority == "mid"
