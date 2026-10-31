"""Offline tests for the optional Jev judge (GIVEMEMD_JEV=1). The HTTP call is injected; nothing hits the network."""
import pytest

from givememd import extract, jev
from givememd.extract import convert

LINKS = ''.join(f'<li><a href="/wiki/T{i}">Related topic {i}</a></li>' for i in range(8))
PAGE = (f'<html><head><title>Markdown - Wiki</title></head><body><main><h1>Markdown</h1><p>{"Markdown is a markup language. " * 30}</p>'
        f'<section><h2>See also</h2><ul>{LINKS}</ul></section>'
        f'<div class="sidebar">' + ''.join(f'<a href="/m{i}">Menu item {i}</a>' for i in range(10)) + '</div></main></body></html>')


def fake(answer_for, log=None):
    def post(body):
        if log is not None: log.append(body)
        ans = {}
        for qid, q in body['questions'].items():
            c = answer_for(q['instructions'])
            ans[qid] = {'type': 'choice', 'choice': c, 'confidence': 0.9, 'probabilities': {k: (0.9 if k == c else 0.02) for k in jev.CATS}}
        return {'answers': ans, 'usage': {'input_tokens': 100, 'output_tokens': 10}}
    return post


def see_also_is_content(instr): return 'supporting_content' if 'See also' in instr else 'navigation'


def test_heuristic_drops_see_also():
    md = convert(PAGE, 'https://w.org/Markdown', judge=False)
    assert 'Related topic 3' not in md and 'Menu item 3' not in md


def test_rescue_keeps_see_also_but_not_menus():
    log = []
    md = convert(PAGE, 'https://w.org/Markdown', judge=jev.Judge(key='k', post=fake(see_also_is_content, log)))
    assert '## See also' in md and 'Related topic 3' in md
    assert 'Menu item 3' not in md                       # heading-less link block is never even asked about
    assert len(log) == 1 and len(log[0]['questions']) == 1
    assert 'Outline' in log[0]['state'] and 'Markdown - Wiki' in log[0]['state']


def test_rescue_respects_navigation_verdict():
    md = convert(PAGE, 'https://w.org/Markdown', judge=jev.Judge(key='k', post=fake(lambda i: 'recommendations')))
    assert 'Related topic 3' not in md


def test_judge_failure_falls_back_to_heuristic():
    def boom(body): raise TimeoutError
    j = jev.Judge(key='k', post=boom)
    assert convert(PAGE, 'https://w.org/Markdown', judge=j) == convert(PAGE, 'https://w.org/Markdown', judge=False)
    assert j.stats['errors'] == 1


def test_questions_are_batched_into_one_request_unless_per_request():
    log = []
    blocks = [f'block {i}' for i in range(5)]
    jev.Judge(key='k', post=fake(lambda i: 'main_content', log)).classify('state', blocks)
    assert len(log) == 1 and len(log[0]['questions']) == 5
    log.clear()
    jev.Judge(key='k', post=fake(lambda i: 'main_content', log), per_request=1).classify('state', blocks)
    assert len(log) == 5


def test_off_by_default_and_needs_key(monkeypatch):
    monkeypatch.delenv('GIVEMEMD_JEV', raising=False)
    monkeypatch.setenv('GIVEMEMD_JEV_KEY', 'k')
    assert not jev.enabled()
    monkeypatch.setenv('GIVEMEMD_JEV', '1')
    monkeypatch.delenv('GIVEMEMD_JEV_KEY')
    monkeypatch.delenv('GIVEMEMD_JEV_KEY_FILE', raising=False)
    assert not jev.enabled()


def test_env_flag_routes_convert_through_judge(monkeypatch):
    monkeypatch.setenv('GIVEMEMD_JEV', '1')
    monkeypatch.setenv('GIVEMEMD_JEV_KEY', 'k')
    monkeypatch.setattr(jev.Judge, '_send', lambda self, body: fake(see_also_is_content)(body))
    assert 'Related topic 3' in convert(PAGE, 'https://w.org/Markdown')
