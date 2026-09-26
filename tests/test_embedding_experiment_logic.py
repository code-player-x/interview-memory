"""Offline verdict checks; real embedding quality still needs a running model."""
import numpy as np
import pytest

from crawler.scripts import test_embed_discriminative as experiment


def test_distinct_vectors_pass_the_discrimination_smoke_test(monkeypatch, capsys):
    monkeypatch.setattr(experiment, "embed", lambda texts: np.eye(len(texts)).tolist())
    experiment.main()
    output = capsys.readouterr().out
    assert "非对角平均余弦: 0.0000" in output
    assert "0 / 272" in output
    assert "OK 通过本组短中文区分度冒烟检查" in output


def test_collapsed_vectors_fail_the_discrimination_smoke_test(monkeypatch, capsys):
    monkeypatch.setattr(experiment, "embed", lambda texts: [[1.0, 0.0] for _ in texts])
    with pytest.raises(SystemExit) as exc:
        experiment.main()
    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert "非对角平均余弦: 1.0000" in output
    assert "272 / 272" in output
    assert "不可用于去重" in output


@pytest.mark.parametrize("kind", ["zero", "nan", "inf", "short", "ragged", "empty_dimension", "text", "null"])
def test_invalid_embedding_response_fails(monkeypatch, capsys, kind):
    vectors = np.eye(len(experiment.TEXTS)).tolist()
    if kind == "zero": vectors[0] = [0.] * len(vectors)
    elif kind == "nan": vectors[0][0] = float("nan")
    elif kind == "inf": vectors[0][0] = float("inf")
    elif kind == "short": vectors.pop()
    elif kind == "ragged": vectors[0].pop()
    elif kind == "empty_dimension": vectors = [[] for _ in vectors]
    elif kind == "text": vectors[0][0] = "not a number"
    elif kind == "null": vectors = None
    monkeypatch.setattr(experiment, "embed", lambda _: vectors)
    with pytest.raises(SystemExit) as exc:
        experiment.main()
    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert "无效嵌入响应" in output
    assert "OK" not in output
