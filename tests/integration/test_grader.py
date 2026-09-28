"""The grader against the real Jev on OpenRouter. Skipped without OPENROUTER_API_KEY; costs ~US$ 0.0001."""
import pytest

from src.evaluation.grader import grade_answer
from src.interview.record import InterviewRecord
from tests.integration import requires_openrouter

pytestmark = [pytest.mark.integration, requires_openrouter]

QUESTION = {"index": 1, "text": "Como você decide quais tarefas priorizar quando várias demandas importantes "
                                "chegam ao mesmo tempo?"}

# The shape of a model answer that reached level 5 in research.md §6.
STRONG = (
    "Eu priorizo pelo impacto no negócio e pelo risco de atraso, e alinho a decisão com as pessoas afetadas. "
    "Na Vobys, em [março], chegaram na mesma semana três demandas: um relatório regulatório com prazo legal, "
    "uma melhoria pedida pela diretoria e a correção de um pipeline que atrasava dados para [dois clientes]. "
    "Eu listei o impacto e o esforço de cada uma, e vi que o relatório tinha multa se atrasasse e que o "
    "pipeline afetava a receita. Levei essa análise ao meu gestor com uma proposta: primeiro o relatório, "
    "em paralelo a correção do pipeline com um colega, e a melhoria da diretoria para a semana seguinte. "
    "Eu mesmo conversei com a diretoria para explicar o motivo e combinar a nova data. Entregamos o relatório "
    "[dois dias] antes do prazo, o pipeline voltou a entregar os dados em [24 horas] e a melhoria saiu na "
    "semana combinada, sem reclamação. Aprendi que priorizar é uma decisão que eu preciso explicar com dados, "
    "e não só uma pergunta que eu levo para o gestor."
)


def record() -> InterviewRecord:
    return InterviewRecord(interview_id="20260926-124939-hr-1buota", interview_type="hr", language="pt-BR",
                           started_at="2026-09-26T12:49:39+00:00", seniority="mid")


async def test_a_weak_answer_scores_low():
    result = await grade_answer(record(), QUESTION, "Eu alinho com meu gestor qual é a prioridade.")
    assert result.score < 2.5
    assert "concrete_situation" in result.gaps
    assert result.model.startswith("typesafe/jev")


async def test_a_strong_answer_reaches_the_top_level():
    result = await grade_answer(record(), QUESTION, STRONG)
    assert result.level == 5, (result.score, result.probabilities, result.gaps)
