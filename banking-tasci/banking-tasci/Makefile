.PHONY: install test prepare-data

install:
	pip install -r requirements.txt

test:
	pytest -q

prepare-data:
	python scripts/prepare_data.py --tweets data/raw/sampledbanktweet.csv --reviews data/raw/bank_reviews3.csv --output data/interim/prepared.csv --report outputs/data_report.json
