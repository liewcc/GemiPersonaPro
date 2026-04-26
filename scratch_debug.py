import sys
sys.path.insert(0, '.')
from health_parser import parse_account_health
import json

s, d, a = parse_account_health('PECCNorthJohor')
res_pecc = [r for r in d if r.get('round') in [121, 122, 123, 124, 125, 126]]
print("PECCNorthJohor:")
for r in res_pecc:
    print(r)

s, d, a = parse_account_health('tv.komuniti')
res_tv = [r for r in d if r.get('round') in [81, 82, 83]]
print("\ntv.komuniti:")
for r in res_tv:
    print(r)
