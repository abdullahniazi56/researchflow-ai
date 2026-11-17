"""Runs the whole LangGraph agent with fake tools and a fake pipeline."""

import asyncio
import importlib
import sys
import types


def load_graph(monkeypatch, *, doc_score=5.0, plan=None):
    calls = {"tools": [], "planner": 0, "answer": 0}

    class FakeMCP:
        async def call_tool(self, name, args):
            calls["tools"].append((name, args))
            if name == "document_search":
                return [{"content": "Nike was founded in 1964.", "source": "nike.pdf",
                         "page": 1, "rerank_score": doc_score, "type": "document"}]
            return [{"content": "Nike news today.", "source": "Web", "url": "https://x.com",
                     "type": "web"}]

    client = types.ModuleType("backend.mcp.client")
    client.mcp_client = FakeMCP()
    client.get_mcp_tools = lambda: []
    monkeypatch.setitem(sys.modules, "backend.mcp.client", client)

    pipeline = types.ModuleType("backend.rag.pipeline")

    def create_research_plan(question, history=None):
        calls["planner"] += 1
        return types.SimpleNamespace(
            standalone_question=plan or question, sub_questions=["part one", "part two"]
        )

    def generate_answer(question, evidence, history=None):
        calls["answer"] += 1
        calls["answer_question"] = question
        return "Nike was founded in 1964 [E1]."

    def select_evidence(results):
        items = [e for r in results for e in r["evidence"]]
        return [{**e, "evidence_id": f"E{i + 1}"} for i, e in enumerate(items)]

    pipeline.create_research_plan = create_research_plan
    pipeline.generate_answer = generate_answer
    pipeline.select_evidence = select_evidence
    pipeline.verify_citations = lambda answer, ev: (answer, {"cited_claims": 1, "supported_claims": 1})
    pipeline.resolve_citations = lambda answer, ev: answer.replace("[E1]", "[Source: nike.pdf, Page: 1]")
    monkeypatch.setitem(sys.modules, "backend.rag.pipeline", pipeline)

    monkeypatch.delitem(sys.modules, "backend.agent.graph", raising=False)
    graph = importlib.import_module("backend.agent.graph")
    monkeypatch.setattr(graph, "ROUTING_MODE", "rules")
    return graph, calls


def run(graph, question, history=None, document_ids=None):
    return asyncio.run(graph.app.ainvoke(graph.initial_state(question, history, document_ids)))


def test_simple_question_uses_one_llm_call(monkeypatch):
    graph, calls = load_graph(monkeypatch)
    state = run(graph, "What is Nike?")

    assert calls["planner"] == 0
    assert calls["answer"] == 1
    assert [name for name, _ in calls["tools"]] == ["document_search"]
    assert state["answer"] == "Nike was founded in 1964 [Source: nike.pdf, Page: 1]."
    assert state["verification"]["supported_claims"] == 1


def test_weak_pdf_results_add_web_search(monkeypatch):
    graph, calls = load_graph(monkeypatch, doc_score=-5.0)
    run(graph, "What is Nike?")

    assert [name for name, _ in calls["tools"]] == ["document_search", "web_search_tool"]


def test_follow_up_is_rewritten_by_planner(monkeypatch):
    graph, calls = load_graph(monkeypatch, plan="When was Nike founded?")
    history = [{"role": "user", "content": "What is Nike?"}]
    state = run(graph, "When was it founded?", history=history)

    assert calls["planner"] == 1
    assert state["standalone_question"] == "When was Nike founded?"
    assert calls["answer_question"] == "When was Nike founded?"
    # two sub-questions searched in parallel
    assert sum(1 for name, _ in calls["tools"] if name == "document_search") == 2


def test_document_filter_reaches_the_tool(monkeypatch):
    graph, calls = load_graph(monkeypatch)
    run(graph, "What is Nike?", document_ids=["doc-1"])

    name, args = calls["tools"][0]
    assert name == "document_search"
    assert args["document_ids"] == ["doc-1"]
