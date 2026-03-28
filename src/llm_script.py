"""
LLM 요약 서브프로세스 — subprocess.Popen 으로 실행됩니다.
진행 상황과 결과를 JSON 라인으로 stdout 에 출력합니다.
"""
import argparse
import io
import json
import re
import sys
import traceback

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_CHUNK_MIN_CHARS = 2500
_SENTENCE_END = re.compile(r'[.!?。！？]\s|[다요죠까]\s')

_CHUNK_PROMPT = """\
다음은 음성 녹음 전사 텍스트의 일부입니다. 핵심 내용을 3~5문장으로 간결하게 요약해 주세요.

[텍스트]
{text}

[요약]"""

_FINAL_PROMPT = """\
다음은 음성 녹음의 구간별 요약입니다. 전체 내용을 종합하여 핵심 사항을 정리해 주세요.

{summaries}

[전체 요약]"""


def emit(data: dict):
    print(json.dumps(data, ensure_ascii=False), flush=True)


def _split_chunks(text: str) -> list[str]:
    chunks = []
    pos = 0
    while pos < len(text):
        if pos + _CHUNK_MIN_CHARS >= len(text):
            chunks.append(text[pos:])
            break
        m = _SENTENCE_END.search(text, pos + _CHUNK_MIN_CHARS)
        end = m.end() if m else len(text)
        chunks.append(text[pos:end])
        pos = end
    return [c.strip() for c in chunks if c.strip()]


def _generate(llm, prompt: str, max_tokens: int) -> str:
    result = llm(prompt, max_tokens=max_tokens, stop=["[텍스트]", "[요약]", "[전체 요약]"])
    return result["choices"][0]["text"].strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="GGUF 모델 파일 경로")
    parser.add_argument("--text-file", required=True, help="요약할 텍스트가 저장된 파일 경로")
    args = parser.parse_args()

    with open(args.text_file, encoding="utf-8") as f:
        text = f.read()

    emit({"status": "progress", "pct": 5, "msg": "LLM 모델 로딩 중..."})

    from llama_cpp import Llama
    llm = Llama(model_path=args.model, n_ctx=4096, n_threads=2, verbose=False)

    chunks = _split_chunks(text)
    total = len(chunks)
    chunk_summaries = []

    for i, chunk in enumerate(chunks):
        pct = 10 + int((i / total) * 75)
        emit({"status": "progress", "pct": pct,
              "msg": f"구간 요약 중... ({i + 1}/{total})"})
        summary = _generate(llm, _CHUNK_PROMPT.format(text=chunk), max_tokens=300)
        chunk_summaries.append(summary)

    emit({"status": "progress", "pct": 88, "msg": "최종 요약 생성 중..."})

    if len(chunk_summaries) == 1:
        final_summary = chunk_summaries[0]
    else:
        combined = "\n\n".join(
            f"[{i + 1}구간] {s}" for i, s in enumerate(chunk_summaries)
        )
        final_summary = _generate(llm, _FINAL_PROMPT.format(summaries=combined), max_tokens=500)

    emit({
        "status": "done",
        "summary": final_summary,
        "chunk_summaries": chunk_summaries,
    })


if __name__ == "__main__":
    try:
        main()
    except Exception:
        emit({"status": "error", "error": traceback.format_exc()})
        sys.exit(1)
