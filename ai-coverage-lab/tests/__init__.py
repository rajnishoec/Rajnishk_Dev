from coverage_lab.reports import parse_report

LCOV = """TN:
SF:app.py
DA:1,1
DA:2,0
DA:3,2
BRDA:2,0,0,1
BRDA:2,0,1,-
end_of_record
"""


def sample_report():
    return parse_report(LCOV).to_dict()
