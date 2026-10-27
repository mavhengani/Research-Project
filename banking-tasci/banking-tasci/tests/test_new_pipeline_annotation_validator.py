from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT/"src"))
from banking_tasci.data.new_pipeline_annotation_validator import report_markdown, validate_records

def record(**overrides):
    value={"record_id":"r1","source_record_id":"s1","source":"south_africa_tweet","region":"south_africa","bank":"FNB","review_id":None,"thread_id":None,"conversation_id":None,"publish_year":2020,"text":"The app is bad.","previous_text":"[NO_CONTEXT]","context_available":False,"duplicate_group":None,"leakage_group":None,"privacy_status":"anonymised","primary_intent":None,"public_warning":None,"opinions":[],"annotation_status":"not_started","annotation_version":"new_pipeline_v1","annotation_notes":None}; value.update(overrides); return value

def test_label_hidden_is_valid_input_but_not_completed_gold():
    source=[record()]
    assert validate_records(source,source,{"calibration_001":{"r1"}})["result"]=="PASS"
    assert validate_records(source,source,completed_gold=True)["result"]=="FAIL"

def test_mutated_source_and_wrong_batch_are_reported_without_text():
    source=[record()]; submitted=[record(text="secret_customer_phrase")]
    report=validate_records(submitted,source,{"other":{"r1"}})
    assert "immutable_source_field_changed" in report["errors_by_code"]
    assert "secret_customer_phrase" not in report_markdown(report)

def test_duplicate_id_is_reported():
    source=[record()]
    assert "duplicate_record_id" in validate_records([record(),record()],source)["errors_by_code"]

def test_completed_gold_requires_every_approved_source_record():
    first=record()
    second=record(record_id="r2",source_record_id="s2")
    report=validate_records([first],[first,second],completed_gold=True)
    assert report["result"]=="FAIL"
    assert report["errors_by_code"]["completed_gold_record_missing"]==1
    assert report["affected_record_ids"]["completed_gold_record_missing"]==["r2"]

def test_source_review_links_must_share_one_leakage_group():
    first=record(review_id="review-1",leakage_group="group-1")
    second=record(record_id="r2",source_record_id="s2",review_id="review-1",leakage_group="group-2")
    report=validate_records([first,second],[first,second])
    assert report["result"]=="FAIL"
    assert report["errors_by_code"]["linked_records_leakage_group_mismatch"]==2

def test_duplicate_link_without_leakage_group_is_rejected():
    source=record(duplicate_group="duplicate-1",leakage_group=None)
    report=validate_records([source],[source])
    assert report["result"]=="FAIL"
    assert report["errors_by_code"]["group_link_missing_leakage_group"]==1

def test_consistent_review_linkage_with_shared_leakage_group_passes():
    first=record(review_id="review-1",leakage_group="group-1")
    second=record(record_id="r2",source_record_id="s2",review_id="review-1",leakage_group="group-1")
    assert validate_records([first,second],[first,second])["result"]=="PASS"

def test_general_category_warning_is_reported_without_failing_validation():
    text="The bank is bad."
    start=text.index("bank")
    opinion={"target":"bank","target_start":start,"target_end":start+4,"target_type":"explicit","entity":"BANK","attribute":"GENERAL","category":"BANK#GENERAL","opinion_phrase":None,"opinion_start":None,"opinion_end":None,"sentiment":"negative","annotation_notes":None}
    annotated=record(text=text,primary_intent="complaint",public_warning=False,opinions=[opinion],annotation_status="completed")
    report=validate_records([annotated],[annotated],completed_gold=True)
    assert report["result"]=="PASS"
    assert report["error_count"]==0
    assert report["warning_count"]==1
    assert report["warnings_by_code"]["general_attribute_used"]==1
    assert "Warnings: 1" in report_markdown(report)
