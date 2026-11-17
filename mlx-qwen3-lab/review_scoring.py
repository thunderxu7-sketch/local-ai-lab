"""Apply the existing review rubric to raw outputs and explicit semantic judgments."""
from validate_review_data import parse_json


def score_results(raw, notes):
    judgments = {r['id']:r for r in notes['results']}
    assert len(judgments) == len(notes['results']) == len(raw['results']) == 20
    assert set(judgments) == {r['id'] for r in raw['results']}
    results = []
    for row in raw['results']:
        review = judgments[row['id']]
        bug = bool(row['reference']['issues'])
        try:
            parse_json(row['raw_response'])
            json_valid = True
        except (ValueError, TypeError):
            json_valid = False
        if bug:
            assert all(type(review[k]) is bool for k in ['detects_gold','fix_usable','line_correct'])
            passed = row['schema_valid'] and all(review[k] for k in ['detects_gold','fix_usable','line_correct']) and review['extra_false_positives'] == 0
        else:
            passed = row['schema_valid'] and row['parsed_response'] == {'issues':[]} and review['extra_false_positives'] == 0
        results.append(dict(row, review=review, json_valid=json_valid, has_gold_issue=bug, overall_pass=bool(passed)))
    bugs = [r for r in results if r['has_gold_issue']]
    clean = [r for r in results if not r['has_gold_issue']]
    assert len(bugs) == len(clean) == 10
    def metric(n, d):
        return dict(numerator=n, denominator=d, rate=n/d)
    metrics = dict(
        parseable_json=metric(sum(r['json_valid'] for r in results),20),
        schema_compliant=metric(sum(r['schema_valid'] for r in results),20),
        bug_detection=metric(sum(r['review']['detects_gold'] for r in bugs),10),
        clean_false_positive=metric(sum(r['review']['extra_false_positives'] > 0 for r in clean),10),
        usable_fix=metric(sum(r['review']['fix_usable'] for r in bugs),10),
        correct_bug_location=metric(sum(r['review']['line_correct'] for r in bugs),10),
        end_to_end_usable=metric(sum(r['overall_pass'] for r in results),20))
    return results, metrics
