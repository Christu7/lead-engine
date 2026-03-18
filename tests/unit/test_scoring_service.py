"""Unit tests for the pure calculate_score function.

These tests run entirely in-memory — no database, no HTTP.
"""
import pytest

from app.services.scoring import calculate_score
from tests.factories import LeadFactory, ScoringRuleFactory


@pytest.mark.unit
class TestCalculateScore:
    def test_single_matching_rule(self):
        lead = LeadFactory.build(title="VP of Sales")
        rule = ScoringRuleFactory.build(
            field="title", operator="contains", value="VP", points=20
        )
        score, details = calculate_score(lead, [rule])
        assert score == 20
        assert details["total"] == 20
        assert details["total_raw"] == 20
        assert details["rules"][0]["matched"] is True

    def test_no_match(self):
        lead = LeadFactory.build(title="Junior Developer")
        rule = ScoringRuleFactory.build(
            field="title", operator="contains", value="VP", points=20
        )
        score, details = calculate_score(lead, [rule])
        assert score == 0
        assert details["rules"][0]["matched"] is False

    def test_multiple_rules_sum(self):
        lead = LeadFactory.build(title="VP of Sales", company="Acme Corp")
        rules = [
            ScoringRuleFactory.build(
                field="title", operator="contains", value="VP", points=20
            ),
            ScoringRuleFactory.build(
                field="company", operator="not_empty", value="_", points=5
            ),
        ]
        score, _ = calculate_score(lead, rules)
        assert score == 25

    def test_negative_points_clamped_at_zero(self):
        lead = LeadFactory.build(title="Intern")
        rule = ScoringRuleFactory.build(
            field="title", operator="contains", value="Intern", points=-10
        )
        score, details = calculate_score(lead, [rule])
        assert score == 0
        assert details["total_raw"] == -10
        assert details["total"] == 0

    def test_clamped_at_100(self):
        lead = LeadFactory.build(title="VP CEO Director")
        rules = [
            ScoringRuleFactory.build(
                id=i,
                field="title",
                operator="contains",
                value=v,
                points=50,
            )
            for i, v in enumerate(["VP", "CEO", "Director"], start=1)
        ]
        score, _ = calculate_score(lead, rules)
        assert score == 100

    def test_equals_operator(self):
        lead = LeadFactory.build(source="website")
        rule = ScoringRuleFactory.build(
            field="source", operator="equals", value="website", points=10
        )
        score, _ = calculate_score(lead, [rule])
        assert score == 10

    def test_equals_case_insensitive(self):
        lead = LeadFactory.build(source="Website")
        rule = ScoringRuleFactory.build(
            field="source", operator="equals", value="website", points=10
        )
        score, _ = calculate_score(lead, [rule])
        assert score == 10

    def test_greater_than_operator(self):
        lead = LeadFactory.build(
            enrichment_data={"apollo": {"company_size": 200}}
        )
        rule = ScoringRuleFactory.build(
            field="enrichment_data.apollo.company_size",
            operator="greater_than",
            value="50",
            points=15,
        )
        score, _ = calculate_score(lead, [rule])
        assert score == 15

    def test_greater_than_no_match(self):
        lead = LeadFactory.build(
            enrichment_data={"apollo": {"company_size": 10}}
        )
        rule = ScoringRuleFactory.build(
            field="enrichment_data.apollo.company_size",
            operator="greater_than",
            value="50",
            points=15,
        )
        score, _ = calculate_score(lead, [rule])
        assert score == 0

    def test_in_list_operator(self):
        lead = LeadFactory.build(source="typeform")
        rule = ScoringRuleFactory.build(
            field="source",
            operator="in_list",
            value="typeform, apollo, website",
            points=10,
        )
        score, _ = calculate_score(lead, [rule])
        assert score == 10

    def test_in_list_no_match(self):
        lead = LeadFactory.build(source="manual")
        rule = ScoringRuleFactory.build(
            field="source",
            operator="in_list",
            value="typeform, apollo",
            points=10,
        )
        score, _ = calculate_score(lead, [rule])
        assert score == 0

    def test_missing_field_scores_zero_not_crash(self):
        lead = LeadFactory.build(company=None)
        rule = ScoringRuleFactory.build(
            field="company", operator="contains", value="Acme", points=10
        )
        score, details = calculate_score(lead, [rule])
        assert score == 0
        assert details["rules"][0]["matched"] is False

    def test_empty_rules_returns_zero(self):
        lead = LeadFactory.build()
        score, details = calculate_score(lead, [])
        assert score == 0
        assert details["rules"] == []
        assert details["total_raw"] == 0

    def test_score_details_has_required_keys(self):
        lead = LeadFactory.build(title="VP")
        rule = ScoringRuleFactory.build(
            field="title", operator="contains", value="VP", points=20
        )
        _, details = calculate_score(lead, [rule])
        assert "rules" in details
        assert "total_raw" in details
        assert "total" in details
        r = details["rules"][0]
        assert all(k in r for k in ("rule_id", "field", "operator", "value", "points", "matched"))

    def test_bad_rule_is_skipped_not_crash(self):
        """A rule whose operator evaluation raises should be skipped without aborting scoring.

        rule_value=None causes rule_value.lower() → AttributeError inside _apply_operator,
        which the try/except in calculate_score must catch and skip.
        The remaining good rule must still be evaluated.
        """
        lead = LeadFactory.build(title="VP of Sales")
        # This rule will raise AttributeError: None has no .lower()
        bad_rule = ScoringRuleFactory.build(
            id=1, field="title", operator="contains", value=None, points=10
        )
        # This rule is valid and should still fire
        good_rule = ScoringRuleFactory.build(
            id=2, field="title", operator="not_empty", value="_", points=5
        )
        score, details = calculate_score(lead, [bad_rule, good_rule])

        # bad_rule was skipped (not raised), good_rule matched
        assert score == 5
        assert len(details["rules"]) == 2
        bad = details["rules"][0]
        good = details["rules"][1]
        assert "error" in bad  # skipped with error key
        assert bad["matched"] is False
        assert good["matched"] is True
