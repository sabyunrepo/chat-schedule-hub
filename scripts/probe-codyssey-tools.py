"""Explicit live capability probe. Synthetic data only; never executes real tools."""
import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--key-file', type=Path, required=True)
parser.add_argument('--model', default='gpt-5.4-mini')
args = parser.parse_args()
secret = args.key_file.read_text().strip()
endpoint = 'https://copa.codyssey.kr/v1/chat/completions'
tools = [{'type': 'function', 'function': {
    'name': 'schedule_lookup', 'description': '합성 일정 조회. 일정 질문에는 이 도구를 호출해야 한다.',
    'strict': True,
    'parameters': {'type': 'object', 'properties': {'date': {'type': 'string', 'description': 'YYYY-MM-DD'}},
                   'required': ['date'], 'additionalProperties': False}}}]
messages = [{'role': 'system', 'content': '도구 시험이다. 일정은 기억으로 답하지 말고 도구로 조회한다. 도구 결과만 근거로 한국어로 간결하게 답한다.'},
            {'role': 'user', 'content': '2030년 1월 2일 내 약속의 이름, 장소, 시간을 알려줘.'}]
results = {'model': args.model, 'syntheticOnly': True, 'requests': []}

def request(payload):
    start = time.monotonic()
    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers={
        'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            data = json.load(response)
        results['requests'].append({'status': 200, 'seconds': round(time.monotonic()-start, 2), 'usage': data.get('usage')})
        return data
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors='replace').replace(secret, '[REDACTED]')
        raise RuntimeError(f'HTTP {error.code}: {detail[:1000]}') from None

try:
    first = request({'model': args.model, 'messages': messages, 'tools': tools, 'tool_choice': 'auto'})
    message = first['choices'][0]['message']
    calls = message.get('tool_calls') or []
    assert len(calls) == 1, 'Expected one tool call'
    call = calls[0]
    assert call['type'] == 'function' and call['function']['name'] == 'schedule_lookup', 'Unexpected tool'
    assert json.loads(call['function']['arguments']) == {'date': '2030-01-02'}, 'Arguments mismatch'
    results['automaticToolCall'] = True
    results['argumentsValidated'] = True
    messages.extend([message, {'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps({
        'events': [{'id': 'synthetic-742', 'title': '합성 추리 모임', 'start': '2030-01-02T15:00:00+09:00', 'location': '테스트룸-742'}],
        'synthetic': True}, ensure_ascii=False)}])
    second = request({'model': args.model, 'messages': messages, 'tools': tools, 'tool_choice': 'none'})
    answer = second['choices'][0]['message'].get('content') or ''
    assert '테스트룸-742' in answer and '추리' in answer, 'Tool result was not reflected'
    results['toolResultRoundTrip'] = True
    results['answer'] = answer
    results['passed'] = True
except Exception as error:
    results['passed'] = False
    results['error'] = str(error).replace(secret, '[REDACTED]')
print(json.dumps(results, ensure_ascii=False, indent=2))
raise SystemExit(0 if results['passed'] else 1)
