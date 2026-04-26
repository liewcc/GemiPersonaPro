import json
with open('engine.log', encoding='utf-8', errors='replace') as f, open('out.txt', 'w', encoding='utf-8') as out:
    for line in f:
        if '"round": 101' in line or '"round": 36' in line or '"round": 27' in line or '"round": 2' in line:
            out.write(line)
