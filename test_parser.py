import health_parser
import json

_, detailed_results, _ = health_parser.parse_account_health()

print(f"Total detailed results: {len(detailed_results)}")
# print the top 20 (which are the most recent 20)
for r in detailed_results[:20]:
    print(r)
