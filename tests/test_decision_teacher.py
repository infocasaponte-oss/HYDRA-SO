# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
import hashlib
import json
from pathlib import Path

import pytest

from hydra.router.decision_contract import CRITERIA
from hydra.training.decision_active_learning import read_rows
from hydra.training.decision_teacher import experimental_snapshot
from hydra.training.decision_balanced_examples import generate


@pytest.fixture
def snapshot(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    paths, proposals = {}, []
    for split in ('fit', 'dev', 'cal_prob', 'cal_policy', 'test'):
        rows = []
        for index, label in enumerate(CRITERIA):
            text = f'Fixture sintética {split} {index}'
            row = {'id': split + '-' + label, 'text': text, 'expected': label,
                   'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
                   'group_id': split + '-scenario-' + str(index), 'training_allowed': split == 'fit'}
            if split == 'fit' and label == 'privacy':
                row['label_review'] = {'human_label': 'privacy', 'reviewer': 'Synthetic reviewer'}
            rows.append(row)
            proposals.append({'id': row['id'], 'text_sha256': row['text_sha256'],
                              'proposed_label': list(CRITERIA)[(index + 1) % 10],
                              'label_source': 'local_ai_proposal', 'human_confirmed': False})
        path = root / (split + '.jsonl')
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
        paths[split] = str(path)
    # Keep all ten fit labels represented while disagreeing with one confirmed human.
    for row in proposals:
        if row['id'].startswith('fit-') and row['id'] != 'fit-privacy':
            row['proposed_label'] = row['id'][4:]
    (root / 'manifest.json').write_text(json.dumps({'paths': paths}), encoding='utf-8')
    target = tmp_path / 'proposals.jsonl'
    target.write_text(''.join(json.dumps(r) + '\n' for r in proposals), encoding='utf-8')
    return root, target, paths


def test_teacher_never_changes_evaluation_or_confirmed_human(snapshot, tmp_path):
    root, target, original = snapshot
    paths = experimental_snapshot(root, target, tmp_path / 'experiment')
    for split in ('dev', 'cal_prob', 'cal_policy', 'test'):
        assert Path(paths[split]).read_bytes() == Path(original[split]).read_bytes()
    rows = read_rows(Path(paths['fit']))
    assert next(r for r in rows if r['id'] == 'fit-privacy')['expected'] == 'privacy'
    assert not json.loads((tmp_path / 'experiment/manifest.json').read_text())['authority']


def test_teacher_rejects_changed_question_binding(snapshot, tmp_path):
    root, target, _ = snapshot
    rows = [json.loads(line) for line in target.read_text().splitlines()]
    rows[0]['text_sha256'] = 'changed'
    target.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
    with pytest.raises(ValueError, match='another question'):
        experimental_snapshot(root, target, tmp_path / 'experiment')
    assert not (tmp_path / 'experiment').exists()


def test_synthetic_balance_is_declared_and_never_overlaps_reserved_inputs(snapshot, tmp_path):
    root, target, original = snapshot
    generated = tmp_path / 'generated'
    generate(generated)
    synthetic = generated / 'balanced-examples.jsonl'
    rows = read_rows(synthetic)
    from collections import Counter
    assert Counter(r['expected'] for r in rows) == {label: 24 for label in CRITERIA}
    traps = read_rows(generated / 'contrast-traps.jsonl')
    assert all(r['expected'] is None and not r['human_confirmed'] for r in traps)
    # A synthetic proposal identical to a held-out question must never enter fit.
    held = read_rows(Path(original['test']))[0]
    collision = {**rows[0], 'text': held['text'], 'text_sha256': held['text_sha256']}
    synthetic.write_text(''.join(json.dumps(r) + '\n' for r in [collision, *rows]), encoding='utf-8')
    paths = experimental_snapshot(root, target, tmp_path / 'experiment', synthetic)
    fit = read_rows(Path(paths['fit']))
    assert all(r['text'] != held['text'] for r in fit)
    assert Path(paths['test']).read_bytes() == Path(original['test']).read_bytes()
    meta = json.loads((tmp_path / 'experiment/manifest.json').read_text())
    assert meta['synthetic_collisions_skipped'] == 1 and meta['synthetic_examples_added_to_fit'] == 240
